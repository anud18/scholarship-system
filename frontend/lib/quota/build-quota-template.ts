import type { KnownCollege, KnownSubType, QuotaMatrix } from "@/lib/quota/parse-quota-sheet";

const CORNER_LABEL = "子類型＼學院";

// Pure: the array-of-arrays the .xlsx sheet will contain (header + body rows).
export function buildQuotaMatrixRows(
  quotas: QuotaMatrix,
  knownColleges: KnownCollege[],
  knownSubTypes: KnownSubType[],
): (string | number)[][] {
  const header: (string | number)[] = [CORNER_LABEL, ...knownColleges.map(c => c.code)];
  const body = knownSubTypes.map(s => [
    s.code,
    ...knownColleges.map(c => quotas?.[s.code]?.[c.code] ?? 0),
  ]);
  return [header, ...body];
}

export async function downloadQuotaTemplate(
  quotas: QuotaMatrix,
  knownColleges: KnownCollege[],
  knownSubTypes: KnownSubType[],
  configCode?: string,
): Promise<void> {
  const XLSX = await import("xlsx");
  const rows = buildQuotaMatrixRows(quotas, knownColleges, knownSubTypes);
  const ws = XLSX.utils.aoa_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "配額");
  XLSX.writeFile(wb, `quota-template-${configCode || "new"}.xlsx`);
}
