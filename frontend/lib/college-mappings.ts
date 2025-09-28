/**
 * Centralized college mappings for the frontend
 */

export interface CollegeMapping {
  code: string;
  name: string;
  name_en: string;
}

export const COLLEGE_MAPPINGS: Record<string, CollegeMapping> = {
  E: {
    code: "E",
    name: "電機學院",
    name_en: "College of Electrical and Computer Engineering",
  },
  C: { code: "C", name: "資訊學院", name_en: "College of Computer Science" },
  I: { code: "I", name: "工學院", name_en: "College of Engineering" },
  S: { code: "S", name: "理學院", name_en: "College of Science" },
  B: {
    code: "B",
    name: "工程生物學院",
    name_en: "College of Biological Science and Technology",
  },
  O: { code: "O", name: "光電學院", name_en: "College of Photonics" },
  D: {
    code: "D",
    name: "半導體學院",
    name_en: "College of Semiconductor Research",
  },
  "1": { code: "1", name: "醫學院", name_en: "College of Medicine" },
  "6": {
    code: "6",
    name: "生醫工學院",
    name_en: "College of Biomedical Engineering",
  },
  "7": { code: "7", name: "生命科學院", name_en: "College of Life Science" },
  M: { code: "M", name: "管理學院", name_en: "College of Management" },
  A: {
    code: "A",
    name: "人社院",
    name_en: "College of Humanities and Social Sciences",
  },
  K: { code: "K", name: "客家學院", name_en: "College of Hakka Studies" },
};

export function getCollegeName(code: string, lang: "zh" | "en" = "zh"): string {
  const college = COLLEGE_MAPPINGS[code];
  if (!college) return code;
  return lang === "en" ? college.name_en : college.name;
}

export function getAllColleges(): CollegeMapping[] {
  return Object.values(COLLEGE_MAPPINGS).sort((a, b) =>
    a.code.localeCompare(b.code)
  );
}

export function isValidCollegeCode(code: string): boolean {
  return code in COLLEGE_MAPPINGS;
}

export function getCollegeCodes(): string[] {
  return Object.keys(COLLEGE_MAPPINGS).sort();
}

// Sub-type mappings for scholarship categories
export const SUBTYPE_MAPPINGS: Record<string, string> = {
  nstc: "國科會",
  moe_1w: "教育部一萬",
  moe_2w: "教育部兩萬",
  general: "一般",
};

export function getSubTypeName(code: string): string {
  return SUBTYPE_MAPPINGS[code] || code;
}

export function getSubTypeCodes(): string[] {
  return Object.keys(SUBTYPE_MAPPINGS);
}
