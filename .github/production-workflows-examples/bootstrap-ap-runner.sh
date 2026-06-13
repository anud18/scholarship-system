#!/usr/bin/env bash
#
# bootstrap-ap-runner.sh — turn a COMPLETELY EMPTY production AP VM into a
# machine that can run the GitHub Actions workflows (setting-env.yml,
# deploy.yml, ...).
#
# WHY THIS EXISTS (the chicken-and-egg):
#   Every production workflow has `runs-on: [self-hosted, linux]`. A bare VM
#   has no runner, so NO action can run there yet. This script is the one
#   manual, run-once-per-VM step that installs Docker + the GitHub Actions
#   runner as a systemd service. After it succeeds, everything else is driven
#   by `setting-env.yml` (which sets up the DB VM over SSH).
#
# WHERE TO RUN:
#   On the production AP VM only, as a sudo-capable user, via console or SSH.
#   The DB VM does NOT need this — it never runs a runner (setting-env.yml
#   reaches it over SSH).
#
# HOW TO RUN:
#   1. Get a registration token (expires in ~1h):
#        gh api -X POST repos/<OWNER>/<PROD_REPO>/actions/runners/registration-token --jq .token
#      (or: prod repo → Settings → Actions → Runners → New self-hosted runner)
#   2. Copy this script to the AP VM, then:
#        chmod +x bootstrap-ap-runner.sh
#        ./bootstrap-ap-runner.sh \
#            --repo-url https://github.com/<OWNER>/<PROD_REPO> \
#            --token    <REGISTRATION_TOKEN>
#      Optional: --labels "self-hosted,linux"  (default)
#                --runner-version 2.319.1       (default: latest at write time)
#                --name <runner-name>           (default: <hostname>-ap)
#
# GUARANTEES:
#   - set -euo pipefail + an ERR trap that prints the failing line — a failure
#     is loud and points at the exact command, so you fix it in ONE pass.
#   - Idempotent: re-running is safe (skips Docker if present, reconfigures the
#     runner if it already exists).
#   - Every command's output is shown AND tee'd to a timestamped logfile.
#
set -euo pipefail

# ── logging ──────────────────────────────────────────────────────────────
LOG_FILE="/tmp/bootstrap-ap-runner-$(date +%Y%m%d-%H%M%S).log"
# Mirror all stdout/stderr to the logfile from here on.
exec > >(tee -a "$LOG_FILE") 2>&1

log()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[1;32m✅ %s\033[0m\n' "$*"; }
warn() { printf '   \033[1;33m⚠️  %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m❌ %s\033[0m\n' "$*" >&2; exit 1; }

on_err() {
  local rc=$? line=$1
  printf '\n\033[1;31m❌ FAILED at line %s (exit %s): %s\033[0m\nFull log: %s\n' \
    "$line" "$rc" "$BASH_COMMAND" "$LOG_FILE" >&2
}
trap 'on_err "$LINENO"' ERR

# ── args ─────────────────────────────────────────────────────────────────
REPO_URL=""
REG_TOKEN=""
LABELS="self-hosted,linux"
RUNNER_VERSION="2.319.1"
RUNNER_NAME="$(hostname)-ap"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-url)        REPO_URL="$2"; shift 2 ;;
    --token)           REG_TOKEN="$2"; shift 2 ;;
    --labels)          LABELS="$2"; shift 2 ;;
    --runner-version)  RUNNER_VERSION="$2"; shift 2 ;;
    --name)            RUNNER_NAME="$2"; shift 2 ;;
    -h|--help)         grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                 die "Unknown argument: $1 (use --help)" ;;
  esac
done

[ -n "$REPO_URL" ]  || die "--repo-url is required (https://github.com/<OWNER>/<PROD_REPO>)"
[ -n "$REG_TOKEN" ] || die "--token is required (runner registration token, expires ~1h)"

RUN_USER="$(id -un)"
[ "$RUN_USER" != "root" ] || die "Run as a normal sudo-capable user, NOT root — the GitHub runner refuses to run as root."

log "Bootstrap plan"
echo "   AP VM user      : $RUN_USER"
echo "   Repo URL        : $REPO_URL"
echo "   Runner name     : $RUNNER_NAME"
echo "   Runner labels   : $LABELS"
echo "   Runner version  : $RUNNER_VERSION"
echo "   Logfile         : $LOG_FILE"

# ── pre-flight ───────────────────────────────────────────────────────────
log "Pre-flight checks"
command -v sudo >/dev/null || die "sudo not found."
sudo -n true 2>/dev/null || warn "sudo may prompt for a password (no passwordless sudo) — that's fine for an interactive run."
command -v curl >/dev/null || { sudo apt-get update && sudo apt-get install -y curl; }
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
  amd64) RUNNER_ARCH="x64" ;;
  arm64) RUNNER_ARCH="arm64" ;;
  *)     die "Unsupported architecture '$ARCH' — GitHub runner ships x64/arm64 only." ;;
esac
ok "Architecture: $ARCH (runner pkg: $RUNNER_ARCH)"
# Reachability to GitHub (the runner needs an outbound HTTPS path).
curl -fsS -o /dev/null --max-time 15 https://api.github.com || die "Cannot reach api.github.com — the AP VM needs outbound HTTPS to register/run the runner."
ok "GitHub reachable"

# ── Docker ───────────────────────────────────────────────────────────────
log "Installing Docker on the AP VM"
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  ok "Docker already present: $(docker --version)"
else
  echo "Installing prerequisites + Docker from the official repository..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg lsb-release
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo systemctl enable --now docker
  ok "Docker installed: $(sudo docker --version)"
fi
# Let the runner user drive Docker without sudo.
if ! groups "$RUN_USER" | grep -qw docker; then
  sudo usermod -aG docker "$RUN_USER"
  warn "Added $RUN_USER to the docker group — takes effect on next login. The runner service picks it up after the (re)start below."
fi
sudo docker ps >/dev/null && ok "Docker daemon responding"

# ── GitHub Actions runner ────────────────────────────────────────────────
log "Installing the GitHub Actions runner"
RUNNER_DIR="$HOME/actions-runner"
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [ -f "$RUNNER_DIR/.runner" ]; then
  warn "A runner is already configured in $RUNNER_DIR — reconfiguring."
  if [ -x "$RUNNER_DIR/svc.sh" ]; then sudo ./svc.sh stop || true; sudo ./svc.sh uninstall || true; fi
  ./config.sh remove --token "$REG_TOKEN" || warn "Could not cleanly remove the old registration (token may be for a different scope) — continuing."
fi

TARBALL="actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$TARBALL" ]; then
  echo "Downloading $TARBALL ..."
  curl -fsSL -o "$TARBALL" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}" \
    || die "Runner download failed — check --runner-version against https://github.com/actions/runner/releases"
fi
echo "Extracting runner..."
tar xzf "$TARBALL"
# The runner bundles its own .NET deps installer.
sudo ./bin/installdependencies.sh

echo "Configuring runner (unattended)..."
./config.sh \
  --unattended \
  --url "$REPO_URL" \
  --token "$REG_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$LABELS" \
  --replace
ok "Runner configured: $RUNNER_NAME [$LABELS]"

echo "Installing + starting the runner as a systemd service..."
sudo ./svc.sh install "$RUN_USER"
sudo ./svc.sh start
sleep 3
SVC_STATUS="$(sudo ./svc.sh status 2>&1 || true)"
echo "$SVC_STATUS"
# svc.sh wraps a systemd unit named actions.runner.<owner>-<repo>.<name>;
# is-active is the language/format-stable check.
if echo "$SVC_STATUS" | grep -qiE "active \(running\)|active: active|is running"; then
  ok "Runner service is running"
else
  die "Runner service did not reach running state. Status above; full log: $LOG_FILE. Try: sudo systemctl status 'actions.runner.*'"
fi

# ── summary ──────────────────────────────────────────────────────────────
log "✅ Bootstrap complete"
cat <<EOF

The AP VM is now a working self-hosted runner.

  Runner dir : $RUNNER_DIR
  Service    : actions.runner.* (systemd) — survives reboot
  Logfile    : $LOG_FILE

Verify in the prod repo: Settings → Actions → Runners → "$RUNNER_NAME" should be Idle.

Next steps:
  1. Set all production secrets (see SECRETS-SETUP-GUIDE.md in the dev repo's
     .github/production-workflows-examples/).
  2. Run the "Setup Production Environment" action (setting-env.yml) with
     action=full-check — it installs Docker on the DB VM over SSH and
     transfers the postgres/minio images.
  3. Then deploy via deploy.yml.

If the runner ever needs re-registering, re-run this script with a fresh
--token; it reconfigures in place.
EOF
