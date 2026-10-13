"use client";

import { RefreshCw } from "lucide-react";

interface RankingDriftBannerProps {
  locale: "zh" | "en";
  /** Eligible applications not in the ranking yet. */
  pendingCount: number;
  /** Ranked applications withdrawn, deleted or no longer eligible. */
  staleCount: number;
  isFinalized: boolean;
  distributionExecuted: boolean;
  /** The college-review deadline passed (non-admin): only an admin can act. */
  isLockedByDeadline: boolean;
}

// What the college can do about a drifted ranking. A distributed ranking only
// gains rows on sync (allocated positions must stay stable).
function driftActionText({
  locale,
  isFinalized,
  distributionExecuted,
  isLockedByDeadline,
}: Pick<
  RankingDriftBannerProps,
  "locale" | "isFinalized" | "distributionExecuted" | "isLockedByDeadline"
>): string {
  if (isLockedByDeadline) {
    return locale === "zh" ? "如需調整請聯絡管理員。" : "Contact an administrator to adjust it.";
  }
  if (isFinalized) {
    return locale === "zh"
      ? "此排名已鎖定，如需更新請先解除鎖定再同步申請名單。"
      : "This ranking is locked; unlock it first, then sync the application list.";
  }
  if (distributionExecuted) {
    return locale === "zh"
      ? "請按「同步申請名單」將新申請加入名單末端（已分發的排名不會移除或重排既有學生），再確認排名。"
      : 'Press "同步申請名單" to append the new applications (a distributed ranking keeps its existing rows), then confirm the ranking.';
  }
  return locale === "zh"
    ? "請按「同步申請名單」更新名單"
    : 'Press "同步申請名單" to update the list.';
}

/**
 * The ranking drifted from the application list: applications became eligible
 * after it was built (pending) and/or ranked ones were withdrawn, deleted or no
 * longer match (stale). Without a prompt either would go unnoticed. The backend
 * reports 0/0 for a locked, distributed ranking, so historic rankings stay
 * quiet. Mirrors the deadline banner's shape.
 */
export function RankingDriftBanner(props: RankingDriftBannerProps) {
  const { locale, pendingCount, staleCount } = props;
  if (pendingCount <= 0 && staleCount <= 0) return null;

  return (
    <div className="rounded-md border p-3 text-sm flex items-start gap-2 border-sky-300 bg-sky-50 text-sky-900">
      <RefreshCw className="h-4 w-4 mt-0.5 shrink-0" />
      <div className="flex-1 leading-relaxed space-y-1">
        {pendingCount > 0 && (
          <p>
            <strong>
              {locale === "zh"
                ? `有 ${pendingCount} 筆新申請尚未加入此排名`
                : `${pendingCount} new application(s) are not in this ranking yet`}
            </strong>
          </p>
        )}
        {staleCount > 0 && (
          <p>
            <strong>
              {locale === "zh"
                ? `此排名中有 ${staleCount} 筆申請已撤回、刪除或不再符合排名條件`
                : `${staleCount} application(s) in this ranking were withdrawn, deleted or are no longer eligible`}
            </strong>
          </p>
        )}
        <p>{driftActionText(props)}</p>
      </div>
    </div>
  );
}
