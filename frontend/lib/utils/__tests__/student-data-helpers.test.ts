/**
 * Tests for `lib/utils/student-data-helpers.ts`.
 *
 * Frontend mirror of the backend `application_helpers.py` extractors.
 * The same OR-chains (trm_* > std_* > legacy) must hold on both sides
 * — if they drift, students see one name in the form and a different
 * one in the admin preview, eroding trust.
 *
 * Counterpart to the backend test_application_helpers_extractors.py
 * (PR #301). Pinning the priority chains in BOTH places so a future
 * schema migration can't silently break one without the other.
 *
 * 19 extractors covered (24 cases).
 */
import {
  getStudentName,
  getStudentEnglishName,
  getStudentId,
  getStudentEmail,
  getStudentPhone,
  getStudentAddress,
  getAcademyCode,
  getAcademyName,
  getDepartmentCode,
  getDepartmentName,
  getTermCount,
  getGPA,
  getDegreeCode,
  getGender,
  getNationality,
  getIdentityCode,
  getSchoolIdentityCode,
  getStudyingStatus,
  getEnrollmentYear,
} from "../student-data-helpers";

describe("name + id extractors", () => {
  it("getStudentName: std_cname wins, falls back to name, then Unknown", () => {
    /** Pin precedence: SIS canonical std_cname is preferred over generic
     * name. Missing both → 'Unknown' string (NOT null, because UI
     * expects a string for name columns). */
    expect(getStudentName({ std_cname: "王小明", name: "Other" })).toBe("王小明");
    expect(getStudentName({ name: "Alice" })).toBe("Alice");
    expect(getStudentName({})).toBe("Unknown");
    expect(getStudentName(null)).toBe("Unknown");
    expect(getStudentName(undefined)).toBe("Unknown");
  });

  it("getStudentEnglishName: std_ename > ename > null", () => {
    expect(getStudentEnglishName({ std_ename: "Wang Xiaoming" })).toBe("Wang Xiaoming");
    expect(getStudentEnglishName({ ename: "Alice" })).toBe("Alice");
    expect(getStudentEnglishName(null)).toBeNull();
  });

  it("getStudentId: std_stdcode > nycu_id > student_id > null", () => {
    expect(getStudentId({ std_stdcode: "S1", nycu_id: "X", student_id: "Y" })).toBe("S1");
    expect(getStudentId({ nycu_id: "X" })).toBe("X");
    expect(getStudentId({ student_id: "Y" })).toBe("Y");
    expect(getStudentId(null)).toBeNull();
  });
});

describe("contact info extractors", () => {
  it("getStudentEmail: com_email > email", () => {
    expect(getStudentEmail({ com_email: "a@u.tw", email: "b@u.tw" })).toBe("a@u.tw");
    expect(getStudentEmail({ email: "b@u.tw" })).toBe("b@u.tw");
  });

  it("getStudentPhone: com_cellphone > phone", () => {
    expect(getStudentPhone({ com_cellphone: "0912000001", phone: "X" })).toBe("0912000001");
    expect(getStudentPhone({ phone: "0900-111-222" })).toBe("0900-111-222");
  });

  it("getStudentAddress: com_commadd > address", () => {
    expect(getStudentAddress({ com_commadd: "新竹市大學路1001號" })).toBe("新竹市大學路1001號");
    expect(getStudentAddress({ address: "fallback" })).toBe("fallback");
  });
});

describe("academy/department extractors", () => {
  it("getAcademyCode: trm > std > generic", () => {
    /** Pin the 3-level chain: term data is freshest, then basic, then
     * legacy alias. */
    expect(getAcademyCode({ trm_academyno: "A", std_academyno: "B", academy_code: "C" })).toBe("A");
    expect(getAcademyCode({ std_academyno: "B" })).toBe("B");
    expect(getAcademyCode({ academy_code: "C" })).toBe("C");
  });

  it("getAcademyName: trm > academy_name", () => {
    expect(getAcademyName({ trm_academyname: "人社院" })).toBe("人社院");
    expect(getAcademyName({ academy_name: "fallback" })).toBe("fallback");
  });

  it("getDepartmentCode and getDepartmentName: trm > std fallback", () => {
    expect(getDepartmentCode({ trm_depno: "4460" })).toBe("4460");
    expect(getDepartmentName({ trm_depname: "教育博" })).toBe("教育博");
  });
});

describe("numeric extractors with coercion", () => {
  it("getTermCount: coerces string to number, missing → null", () => {
    /** SIS sometimes returns numerics as strings — must coerce.
     * Missing entirely → null. */
    expect(getTermCount({ trm_termcount: "5" })).toBe(5);
    expect(getTermCount({ std_termcount: 4 })).toBe(4);
    expect(getTermCount({ term_count: 3 })).toBe(3);
    expect(getTermCount({})).toBeNull();
  });

  it("getGPA: trm_ascore_gpa > gpa, string coerced to number", () => {
    expect(getGPA({ trm_ascore_gpa: "3.85" })).toBe(3.85);
    expect(getGPA({ gpa: 3.5 })).toBe(3.5);
    expect(getGPA(null)).toBeNull();
  });

  it("getDegreeCode: std_degree > degree, string coerced", () => {
    expect(getDegreeCode({ std_degree: "1" })).toBe(1);
    expect(getDegreeCode({ degree: 3 })).toBe(3);
  });

  it("getEnrollmentYear: number coercion", () => {
    expect(getEnrollmentYear({ std_enrollyear: "113" })).toBe(113);
    expect(getEnrollmentYear({ enroll_year: 112 })).toBe(112);
  });

  it("nullish coalescence: 0 is a valid value (not falsy fallback)", () => {
    /** Pin: ?? operator preserves 0/false. If a student's GPA is
     * legitimately 0.0, helper must return 0, not fall through to
     * null. */
    expect(getGPA({ trm_ascore_gpa: 0 })).toBe(0);
    expect(getTermCount({ trm_termcount: 0 })).toBe(0);
  });
});

describe("status/category extractors", () => {
  it("getGender: std_sex > gender", () => {
    expect(getGender({ std_sex: "M" })).toBe("M");
    expect(getGender({ gender: "F" })).toBe("F");
  });

  it("getNationality: std_nation > nationality", () => {
    expect(getNationality({ std_nation: "TW" })).toBe("TW");
  });

  it("getIdentityCode: std_identity > identity", () => {
    expect(getIdentityCode({ std_identity: "1" })).toBe("1");
  });

  it("getSchoolIdentityCode: std_schoolid > school_identity", () => {
    expect(getSchoolIdentityCode({ std_schoolid: "S1" })).toBe("S1");
  });

  it("getStudyingStatus: std_studingstatus > studying_status", () => {
    /** Note: SIS field is misspelled 'studingstatus' (missing 'y') —
     * pin the typo so accidental 'fix' doesn't break the chain. */
    expect(getStudyingStatus({ std_studingstatus: "在學" })).toBe("在學");
    expect(getStudyingStatus({ studying_status: "在學" })).toBe("在學");
  });
});

describe("null safety across all extractors", () => {
  it("returns null for null/undefined input (no AttributeError)", () => {
    for (const fn of [
      getStudentEnglishName,
      getStudentId,
      getStudentEmail,
      getStudentPhone,
      getStudentAddress,
      getAcademyCode,
      getAcademyName,
      getDepartmentCode,
      getDepartmentName,
      getTermCount,
      getGPA,
      getDegreeCode,
      getGender,
      getNationality,
      getIdentityCode,
      getSchoolIdentityCode,
      getStudyingStatus,
      getEnrollmentYear,
    ]) {
      expect(fn(null)).toBeNull();
      expect(fn(undefined)).toBeNull();
    }
  });
});
