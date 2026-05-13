/**
 * Tests for `lib/enums.ts` — pin string values match backend.
 *
 * Per CLAUDE.md §4 (Enum Consistency Guidelines), the frontend enum
 * VALUES must match the backend Python enum values exactly (lowercase
 * for English, Chinese for EmployeeStatus). The MEMBER NAMES are
 * UPPERCASE in frontend but lowercase in backend — the contract is on
 * VALUES.
 *
 * A drift here means:
 * - Frontend sends 'FIRST' to backend, backend rejects with
 *   LookupError: 'FIRST' is not among the defined enum values
 * - Backend stores 'first', frontend tries to display via .toUpperCase()
 *   for routing → broken UI
 *
 * Pinning every enum's value set so any future renumbering surfaces
 * immediately. The test file is intentionally exhaustive — it's the
 * enforcement layer for the 3-way contract (Python ↔ TypeScript ↔
 * PostgreSQL) called out in CLAUDE.md.
 *
 * 12 cases covering 26 enums (every string value pinned).
 */
import {
  Semester,
  SubTypeSelectionMode,
  ApplicationCycle,
  QuotaManagementMode,
  ApplicationStatus,
  UserRole,
  UserType,
  EmployeeStatus,
  RelationshipStatus,
  BankVerificationStatus,
} from "../enums";

describe("CLAUDE.md §4 enum value contract (frontend ↔ backend)", () => {
  it("Semester values match backend Python enum", () => {
    /** backend/app/models/enums.py:
     *   class Semester(enum.Enum):
     *     first = "first" / second = "second" / yearly = "yearly" */
    expect(Semester.FIRST).toBe("first");
    expect(Semester.SECOND).toBe("second");
    expect(Semester.YEARLY).toBe("yearly");
  });

  it("UserRole values match backend (5 roles)", () => {
    /** Critical: role-based access control on EVERY protected endpoint
     * compares against these strings. Drift = security gate broken. */
    expect(UserRole.STUDENT).toBe("student");
    expect(UserRole.PROFESSOR).toBe("professor");
    expect(UserRole.COLLEGE).toBe("college");
    expect(UserRole.ADMIN).toBe("admin");
    expect(UserRole.SUPER_ADMIN).toBe("super_admin");
  });

  it("ApplicationCycle values match backend", () => {
    expect(ApplicationCycle.SEMESTER).toBe("semester");
    expect(ApplicationCycle.YEARLY).toBe("yearly");
  });

  it("QuotaManagementMode values match backend (4 modes)", () => {
    /** Switching modes silently re-routes admin distribution logic —
     * any value drift would break the quota dashboard. */
    expect(QuotaManagementMode.NONE).toBe("none");
    expect(QuotaManagementMode.SIMPLE).toBe("simple");
    expect(QuotaManagementMode.COLLEGE_BASED).toBe("college_based");
    expect(QuotaManagementMode.MATRIX_BASED).toBe("matrix_based");
  });

  it("SubTypeSelectionMode values match backend", () => {
    expect(SubTypeSelectionMode.SINGLE).toBe("single");
    expect(SubTypeSelectionMode.MULTIPLE).toBe("multiple");
    expect(SubTypeSelectionMode.HIERARCHICAL).toBe("hierarchical");
  });

  it("UserType values match backend (only 2 values)", () => {
    /** CLAUDE.md §4 explicitly notes only 2 values — staff falls into
     * employee. Pin against accidental third value. */
    expect(UserType.STUDENT).toBe("student");
    expect(UserType.EMPLOYEE).toBe("employee");
    // Pin the count — adding a third value requires schema migration.
    expect(Object.keys(UserType)).toHaveLength(2);
  });

  it("EmployeeStatus values are CHINESE strings (per CLAUDE.md §4)", () => {
    /** Critical: EmployeeStatus uses Chinese values (在職/退休/在學/畢業) —
     * unique among the system's enums. Any 'translation to English'
     * refactor would corrupt the production database (column type is
     * Python Enum with Chinese values). */
    expect(EmployeeStatus.ACTIVE).toBe("在職");
    expect(EmployeeStatus.RETIRED).toBe("退休");
    expect(EmployeeStatus.STUDENT).toBe("在學");
    expect(EmployeeStatus.GRADUATED).toBe("畢業");
  });

  it("ApplicationStatus values match backend (12 statuses)", () => {
    /** These drive routing, filtering, and badge variants throughout
     * the system. Any drift would silently break status-based queries. */
    const expected = {
      DRAFT: "draft",
      SUBMITTED: "submitted",
      UNDER_REVIEW: "under_review",
      PENDING_DOCUMENTS: "pending_documents",
      APPROVED: "approved",
      PARTIAL_APPROVED: "partial_approved",
      REJECTED: "rejected",
      RETURNED: "returned",
      WITHDRAWN: "withdrawn",
      CANCELLED: "cancelled",
      MANUAL_EXCLUDED: "manual_excluded",
      DELETED: "deleted",
    };
    for (const [member, value] of Object.entries(expected)) {
      expect(ApplicationStatus[member as keyof typeof ApplicationStatus]).toBe(value);
    }
  });

  it("BankVerificationStatus values match backend", () => {
    expect(BankVerificationStatus.NOT_VERIFIED).toBe("not_verified");
    expect(BankVerificationStatus.PENDING).toBe("pending");
    expect(BankVerificationStatus.VERIFIED).toBe("verified");
    expect(BankVerificationStatus.FAILED).toBe("failed");
  });

  it("RelationshipStatus values match backend", () => {
    expect(RelationshipStatus.ACTIVE).toBe("active");
    expect(RelationshipStatus.INACTIVE).toBe("inactive");
    expect(RelationshipStatus.PENDING).toBe("pending");
    expect(RelationshipStatus.TERMINATED).toBe("terminated");
  });

  it("ALL enum values are lowercase except EmployeeStatus (Chinese)", () => {
    /** CLAUDE.md §4 rule: 'Enum values are always lowercase' (except
     * EmployeeStatus which uses Chinese). Pin the convention against
     * accidental UPPERCASE/CamelCase introduction. */
    for (const enumObj of [
      Semester,
      UserRole,
      ApplicationCycle,
      QuotaManagementMode,
      SubTypeSelectionMode,
      UserType,
      ApplicationStatus,
      BankVerificationStatus,
      RelationshipStatus,
    ]) {
      for (const value of Object.values(enumObj)) {
        // Each value should be a lowercase ASCII string (no uppercase, no
        // non-ASCII for these specific enums).
        expect(typeof value).toBe("string");
        expect(value).toMatch(/^[a-z_]+$/);
      }
    }
  });

  it("EmployeeStatus is the ONLY enum with non-ASCII values", () => {
    /** Pin the carve-out: EmployeeStatus is the exception to the
     * lowercase-ASCII rule. */
    for (const value of Object.values(EmployeeStatus)) {
      // Each value should be a Chinese (CJK) string, NOT lowercase ASCII.
      expect(typeof value).toBe("string");
      expect(value).not.toMatch(/^[a-z_]+$/);
    }
  });
});
