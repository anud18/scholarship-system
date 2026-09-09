/**
 * Chinese classification tags for the e2e suite.
 *
 * Tags render as filterable chips in the Playwright HTML report (the GitHub
 * Pages site) and can be selected on the CLI: `playwright test --grep @學生`.
 *
 * Every test carries
 *   1. one MODE tag  — 瀏覽器 (drives a real page via Playwright) or API (HTTP only)
 *   2. ≥1 ROLE tag   — who performs the flow
 *   3. ≥1 FEATURE tag — what the flow exercises
 */
export const MODE = {
  browser: "@瀏覽器",
  api: "@API",
} as const;

export const ROLE = {
  student: "@學生",
  professor: "@教授",
  college: "@學院",
  admin: "@管理員",
} as const;

export const FEATURE = {
  apply: "@申請",
  draft: "@草稿",
  upload: "@上傳文件",
  preview: "@預覽",
  review: "@審核",
  ranking: "@排名",
  distribution: "@分發",
  roster: "@造冊",
  revokeSuspend: "@撤銷停發",
  whitelist: "@白名單",
  batchImport: "@批次匯入",
  renewalImport: "@續領匯入",
  export: "@匯出",
  config: "@設定",
  history: "@領獎紀錄",
  permissions: "@權限",
  regulations: "@要點",
  label: "@文案",
  withdraw: "@撤回",
  notification: "@通知",
} as const;
