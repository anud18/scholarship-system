export type QuotaMatrix = Record<string, Record<string, number>>;

export interface KnownCollege {
  code: string;
  name: string;
  nameEn?: string;
}

export interface KnownSubType {
  code: string;
  label?: string;
}

export interface QuotaParseIssue {
  kind: "college" | "subType" | "cell" | "duplicate" | "zeroed";
  severity: "error" | "warning";
  row?: number; // 1-based sheet row
  col?: number; // 1-based sheet column
  message: string;
}

export interface QuotaParseResult {
  quotas: QuotaMatrix;
  errors: QuotaParseIssue[];
  warnings: QuotaParseIssue[];
}

const MAX_CELL_QUOTA = 1000;

const norm = (v: unknown): string => String(v ?? "").trim().toLowerCase();

function resolveCollege(header: unknown, colleges: KnownCollege[]): string | null {
  const key = norm(header);
  if (!key) return null;
  for (const c of colleges) {
    if (norm(c.code) === key || norm(c.name) === key || (c.nameEn && norm(c.nameEn) === key)) {
      return c.code;
    }
  }
  return null;
}

function resolveSubType(label: unknown, subTypes: KnownSubType[]): string | null {
  const key = norm(label);
  if (!key) return null;
  for (const s of subTypes) {
    if (norm(s.code) === key || (s.label && norm(s.label) === key)) return s.code;
  }
  return null;
}

export function parseQuotaSheet(
  rows: unknown[][],
  knownColleges: KnownCollege[],
  knownSubTypes: KnownSubType[],
  currentQuotas: QuotaMatrix,
): QuotaParseResult {
  const errors: QuotaParseIssue[] = [];
  const warnings: QuotaParseIssue[] = [];

  // Start from a full zero matrix so absent rows/columns become 0 (full-replace).
  const quotas: QuotaMatrix = {};
  for (const s of knownSubTypes) {
    quotas[s.code] = {};
    for (const c of knownColleges) quotas[s.code][c.code] = 0;
  }

  // Map sheet column index -> canonical college code.
  const header = rows[0] ?? [];
  const colCode: (string | null)[] = [];
  const seenCols = new Set<string>();
  for (let j = 1; j < header.length; j++) {
    const raw = header[j];
    if (norm(raw) === "") {
      colCode[j] = null;
      continue;
    }
    const code = resolveCollege(raw, knownColleges);
    if (!code) {
      errors.push({ kind: "college", severity: "error", col: j + 1, message: `未知的學院欄位：「${String(raw)}」（第 ${j + 1} 欄）` });
      colCode[j] = null;
      continue;
    }
    if (seenCols.has(code)) {
      errors.push({ kind: "duplicate", severity: "error", col: j + 1, message: `學院欄位重複：${code}` });
      colCode[j] = null;
      continue;
    }
    seenCols.add(code);
    colCode[j] = code;
  }

  const seenRows = new Set<string>();
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i] ?? [];
    if (norm(row[0]) === "") continue; // skip blank rows
    const sub = resolveSubType(row[0], knownSubTypes);
    if (!sub) {
      errors.push({ kind: "subType", severity: "error", row: i + 1, message: `未知的子類型列：「${String(row[0])}」（第 ${i + 1} 列）` });
      continue;
    }
    if (seenRows.has(sub)) {
      errors.push({ kind: "duplicate", severity: "error", row: i + 1, message: `子類型列重複：${sub}` });
      continue;
    }
    seenRows.add(sub);

    for (let j = 1; j < row.length; j++) {
      const code = colCode[j];
      if (!code) continue; // unknown/blank/duplicate column already reported
      const raw = row[j];
      if (norm(raw) === "") {
        quotas[sub][code] = 0;
        continue;
      }
      const n = Number(String(raw).trim());
      if (!Number.isInteger(n) || n < 0 || n > MAX_CELL_QUOTA) {
        errors.push({ kind: "cell", severity: "error", row: i + 1, col: j + 1, message: `第 ${i + 1} 列第 ${j + 1} 欄配額無效：「${String(raw)}」（需為 0–${MAX_CELL_QUOTA} 的整數）` });
        continue;
      }
      quotas[sub][code] = n;
    }
  }

  // An empty / header-less sheet must not silently zero everything in a full replace.
  if (seenCols.size === 0) {
    errors.push({ kind: "college", severity: "error", message: "找不到有效的學院欄位（請確認標題列含學院代碼或名稱）" });
  }
  if (seenRows.size === 0) {
    errors.push({ kind: "subType", severity: "error", message: "找不到有效的子類型列" });
  }

  // Zeroed-cell warnings: a cell currently > 0 that the import sets to 0.
  for (const s of knownSubTypes) {
    for (const c of knownColleges) {
      const before = currentQuotas?.[s.code]?.[c.code] ?? 0;
      if (before > 0 && quotas[s.code][c.code] === 0) {
        warnings.push({ kind: "zeroed", severity: "warning", message: `此匯入會將 ${s.label || s.code}/${c.name || c.code} 由 ${before} 歸零` });
      }
    }
  }

  return { quotas, errors, warnings };
}
