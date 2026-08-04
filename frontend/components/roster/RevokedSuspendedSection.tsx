import type { RevokedSuspendedEntry } from "@/lib/api/modules/payment-rosters";
import { maskIdNumber } from "@/lib/utils/mask";

interface RevokedSuspendedSectionProps {
  kind: "revoked" | "suspended";
  entries: RevokedSuspendedEntry[];
  removingItemId: number | null;
  onRemove: (itemId: number, studentName: string) => void;
}

export function RevokedSuspendedSection({
  kind,
  entries,
  removingItemId,
  onRemove,
}: RevokedSuspendedSectionProps) {
  if (entries.length === 0) return null;
  const isRevoked = kind === "revoked";
  const verb = isRevoked ? "撤銷" : "停發";

  return (
    <details
      open
      className={
        isRevoked
          ? "border border-red-300 bg-red-50 rounded p-3"
          : "border border-slate-300 bg-slate-50 rounded p-3"
      }
    >
      <summary
        className={
          isRevoked
            ? "text-red-800 font-semibold cursor-pointer text-sm"
            : "text-slate-700 font-semibold cursor-pointer text-sm"
        }
      >
        {isRevoked ? "⚠️ " : "ℹ️ "}此造冊有 {entries.length} 位學生被{verb}，請手動處理
      </summary>
      <ul className="mt-2 space-y-2">
        {entries.map(s => (
          <li
            key={s.application_id}
            className="text-sm flex items-start justify-between gap-3"
          >
            <div>
              <div>
                <span className="font-medium">{s.student_name}</span>
                {s.student_id_number && (
                  <span className="text-slate-500">
                    {` (${maskIdNumber(s.student_id_number)})`}
                  </span>
                )}
                <span className="text-xs text-slate-500 ml-2">
                  {verb}於 {new Date(s.event_at).toLocaleDateString()}
                </span>
              </div>
              {s.reason && (
                <div className="text-xs text-slate-600">原因：{s.reason}</div>
              )}
            </div>
            {s.item_id !== null && (
              <button
                onClick={() => onRemove(s.item_id!, s.student_name)}
                disabled={removingItemId === s.item_id}
                className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 whitespace-nowrap"
              >
                {removingItemId === s.item_id ? "處理中…" : "從本造冊移除"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
