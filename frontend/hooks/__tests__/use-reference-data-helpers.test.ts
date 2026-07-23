/**
 * Tests for the pure lookup helpers exported alongside
 * `useReferenceData` in `frontend/hooks/use-reference-data.ts`.
 *
 * These helpers convert numeric / string IDs from the SIS API into
 * Traditional-Chinese display names rendered all over the UI (student
 * cards, ranking tables, admin dashboards). They are NOT the SWR hook
 * itself — just the deterministic lookup functions, fully testable
 * without React.
 *
 * A regression here surfaces in the UI as:
 *  - blank cells (returns "" or null instead of fallback)
 *  - leaked database IDs ("4551" instead of "資訊工程學系")
 *  - silent fallback on real data (the lookup misses a valid match
 *    and shows "未知 (id)" forever)
 *
 * Functions covered:
 *   getStudyingStatusName, getDegreeName, getIdentityName,
 *   getSchoolIdentityName, getAcademyName, getDepartmentName,
 *   getGenderName, getEnrollTypeName, getSubTypeName
 *
 * 24 cases. Pure jest, no jsdom interaction beyond the default env.
 */

import {
  getAcademyName,
  getDegreeName,
  getDepartmentName,
  getEnrollTypeName,
  getGenderName,
  getIdentityName,
  getSchoolIdentityName,
  getStudyingStatusName,
  getSubTypeName,
} from "../use-reference-data";

// ─── ID-keyed name lookups ───────────────────────────────────────────

describe("getStudyingStatusName", () => {
  const statuses = [
    { id: 1, name: "在學" },
    { id: 2, name: "畢業" },
    { id: 3, name: "休學" },
  ];

  it("returns the matching name", () => {
    expect(getStudyingStatusName(1, statuses)).toBe("在學");
    expect(getStudyingStatusName(2, statuses)).toBe("畢業");
  });

  it("returns dash for undefined id (no SIS value yet)", () => {
    /* Pin: '-' sentinel for the empty-row case. UI relies on this so
     * rendered tables stay aligned. */
    expect(getStudyingStatusName(undefined, statuses)).toBe("-");
  });

  it("returns dash for null id (defensive against legacy data)", () => {
    expect(
      getStudyingStatusName(null as unknown as undefined, statuses)
    ).toBe("-");
  });

  it("falls back to '未知狀態 (id)' for unmapped ids", () => {
    /* Pin: id-in-parens fallback. Surfaces missing reference data
     * loudly during integration without erasing the id. */
    expect(getStudyingStatusName(99, statuses)).toBe("未知狀態 (99)");
  });
});

describe("getDegreeName", () => {
  const degrees = [
    { id: 1, name: "博士" },
    { id: 2, name: "碩士" },
    { id: 3, name: "學士" },
  ];

  it("returns the matching name", () => {
    expect(getDegreeName(2, degrees)).toBe("碩士");
  });

  it("returns dash for undefined id", () => {
    expect(getDegreeName(undefined, degrees)).toBe("-");
  });

  it("falls back to '未知學位 (id)' for unmapped ids", () => {
    expect(getDegreeName(42, degrees)).toBe("未知學位 (42)");
  });
});

describe("getIdentityName", () => {
  const identities = [
    { id: 1, name: "本國學生" },
    { id: 2, name: "僑生" },
  ];

  it("returns the matching name", () => {
    expect(getIdentityName(1, identities)).toBe("本國學生");
  });

  it("falls back to '未知身份 (id)' for unmapped ids", () => {
    expect(getIdentityName(7, identities)).toBe("未知身份 (7)");
  });

  it("returns dash for undefined", () => {
    expect(getIdentityName(undefined, identities)).toBe("-");
  });
});

describe("getSchoolIdentityName", () => {
  const schoolIdentities = [{ id: 1, name: "在校生" }];

  it("falls back to '未知學校身份 (id)'", () => {
    expect(getSchoolIdentityName(99, schoolIdentities)).toBe(
      "未知學校身份 (99)"
    );
  });

  it("returns dash for undefined", () => {
    expect(getSchoolIdentityName(undefined, schoolIdentities)).toBe("-");
  });
});

describe("getGenderName", () => {
  const genders = [
    { id: 1, name: "男性" },
    { id: 2, name: "女性" },
  ];

  it("returns the matching name", () => {
    expect(getGenderName(1, genders)).toBe("男性");
    expect(getGenderName(2, genders)).toBe("女性");
  });

  it("falls back to '未知性別 (id)' for unmapped ids", () => {
    expect(getGenderName(3, genders)).toBe("未知性別 (3)");
  });
});

// ─── Code-keyed name lookups ─────────────────────────────────────────

describe("getAcademyName", () => {
  const academies = [
    { code: "C", name: "資訊學院" },
    { code: "A", name: "人社院" },
  ];

  it("returns the matching name by code", () => {
    expect(getAcademyName("C", academies)).toBe("資訊學院");
  });

  it("returns dash for null / undefined / empty string", () => {
    /* Pin: SIS sometimes sends null/empty for academy_code on staff
     * records — must not render 'null' as text. */
    expect(getAcademyName(null, academies)).toBe("-");
    expect(getAcademyName(undefined, academies)).toBe("-");
    expect(getAcademyName("", academies)).toBe("-");
  });

  it("returns the raw code when not found (NOT '未知')", () => {
    /* Pin: unlike ID lookups, code lookups echo the code on miss so
     * staff can spot the missing reference entry without losing the
     * underlying identifier. Match real production behaviour. */
    expect(getAcademyName("Z", academies)).toBe("Z");
  });
});

describe("getDepartmentName", () => {
  const departments = [
    { code: "4551", name: "資訊工程學系" },
    { code: "4460", name: "教育博" },
  ];

  it("returns the matching name by code", () => {
    expect(getDepartmentName("4551", departments)).toBe("資訊工程學系");
  });

  it("returns dash for null / empty", () => {
    expect(getDepartmentName(null, departments)).toBe("-");
    expect(getDepartmentName("", departments)).toBe("-");
  });

  it("returns the raw code when not found", () => {
    expect(getDepartmentName("9999", departments)).toBe("9999");
  });
});

// ─── Compound-key lookup ─────────────────────────────────────────────

describe("getEnrollTypeName", () => {
  const enrollTypes = [
    { degree_id: 3, code: "1", name: "一般入學" },
    { degree_id: 3, code: "2", name: "考試分發" },
    { degree_id: 1, code: "1", name: "博士甄試" },
  ];

  it("matches by (code, degree_id) tuple", () => {
    /* Pin: (degree_id=3, code='1') must NOT collide with
     * (degree_id=1, code='1'). Both have code='1' but completely
     * different display names. A bug that only matched code would
     * show "博士甄試" for an undergrad — wrong. */
    expect(getEnrollTypeName(1, 3, enrollTypes)).toBe("一般入學");
    expect(getEnrollTypeName(1, 1, enrollTypes)).toBe("博士甄試");
  });

  it("falls back to code-only lookup if degree_id provided but no match", () => {
    /* Pin: documented fallback at lines 319-327 — degree mismatch
     * still resolves to a name (defensive against bad seed data). */
    expect(getEnrollTypeName(2, 999, enrollTypes)).toBe("考試分發");
  });

  it("returns dash for undefined enrollTypeCode", () => {
    expect(getEnrollTypeName(undefined, 3, enrollTypes)).toBe("-");
  });

  it("returns '未知入學方式 (code)' for unmatched code", () => {
    expect(getEnrollTypeName(99, 3, enrollTypes)).toBe(
      "未知入學方式 (99)"
    );
  });
});

// ─── Translation-table lookup ────────────────────────────────────────

describe("getSubTypeName", () => {
  /* Fixture labels are deliberately synthetic (not production wording):
   * getSubTypeName is a pure lookup of the injected map, and fake values
   * prove it reads the map rather than any hardcoded copy. */
  const translations = {
    zh: { nstc: "國科會", moe_1w: "測試子項標籤" },
    en: { nstc: "NSTC", moe_1w: "TEST_SUBTYPE_LABEL" },
  };

  it("returns the zh translation by default", () => {
    expect(getSubTypeName("nstc", translations)).toBe("國科會");
  });

  it("returns the en translation when locale='en'", () => {
    expect(getSubTypeName("moe_1w", translations, "en")).toBe("TEST_SUBTYPE_LABEL");
  });

  it("falls back to the raw code when translation missing", () => {
    /* Pin: code-as-fallback. Per CLAUDE.md §4, sub-type codes are
     * configuration-driven and new ones may not have translations yet
     * — show the code rather than blanking the cell. */
    expect(getSubTypeName("custom_new_type", translations)).toBe(
      "custom_new_type"
    );
  });

  it("returns dash for undefined sub-type", () => {
    expect(getSubTypeName(undefined, translations)).toBe("-");
  });

  it("returns dash for empty string sub-type", () => {
    expect(getSubTypeName("", translations)).toBe("-");
  });

  it("falls back to code when the chosen locale is empty", () => {
    /* Pin: zh-only translations should still degrade gracefully for
     * en lookups, returning the code (not undefined). */
    expect(getSubTypeName("nstc", { zh: { nstc: "國科會" }, en: {} }, "en")).toBe(
      "nstc"
    );
  });
});
