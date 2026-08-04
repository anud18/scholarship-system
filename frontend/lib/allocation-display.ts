/**
 * Short zh labels for allocated sub-types on roster screens.
 *
 * Keep in sync with SUB_TYPE_SHORT_LABELS in
 * backend/app/services/excel_export_service.py — the Excel export must
 * show the same label finance sees on the roster screens.
 */
const ALLOCATED_SUB_TYPE_SHORT_LABELS: Record<string, string> = {
  nstc: "國科會",
  moe_1w: "教育部(5000)",
  moe_2w: "教育部(2萬)",
};

/** Unknown sub-types (config-driven additions) pass through as the raw code. */
export function formatAllocatedSubType(subType: string): string {
  return ALLOCATED_SUB_TYPE_SHORT_LABELS[subType] ?? subType;
}
