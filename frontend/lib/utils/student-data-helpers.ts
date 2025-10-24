/**
 * Student Data Extraction Helpers
 *
 * Provides consistent extraction of student information from application data.
 * Follows backend pattern from application_helpers.py with field priority:
 * - trm_* (term-specific data) > std_* (basic student data) > legacy fields
 *
 * Based on schema from backend/app/schemas/student_snapshot.py
 */

type StudentData = Record<string, any>;

/**
 * Extract student Chinese name from student data
 * Priority: std_cname > name > "Unknown"
 */
export function getStudentName(studentData?: StudentData | null): string {
  if (!studentData) return "Unknown";
  return studentData.std_cname || studentData.name || "Unknown";
}

/**
 * Extract student English name from student data
 */
export function getStudentEnglishName(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_ename || studentData.ename || null;
}

/**
 * Extract student ID (NYCU ID) from student data
 * Priority: std_stdcode > nycu_id > student_id
 */
export function getStudentId(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_stdcode || studentData.nycu_id || studentData.student_id || null;
}

/**
 * Extract student email from student data
 * Priority: com_email > email
 */
export function getStudentEmail(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.com_email || studentData.email || null;
}

/**
 * Extract student phone number from student data
 * Priority: com_cellphone > phone
 */
export function getStudentPhone(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.com_cellphone || studentData.phone || null;
}

/**
 * Extract student address from student data
 */
export function getStudentAddress(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.com_commadd || studentData.address || null;
}

/**
 * Extract academy code from student data
 * Priority: trm_academyno (term data) > std_academyno (basic data) > academy_code
 */
export function getAcademyCode(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.trm_academyno || studentData.std_academyno || studentData.academy_code || null;
}

/**
 * Extract academy name from student data
 * Priority: trm_academyname (term data) > academy_name
 */
export function getAcademyName(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.trm_academyname || studentData.academy_name || null;
}

/**
 * Extract department code from student data
 * Priority: trm_depno (term data) > std_depno (basic data) > department_code
 */
export function getDepartmentCode(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.trm_depno || studentData.std_depno || studentData.department_code || null;
}

/**
 * Extract department name from student data
 * Priority: trm_depname (term data) > department_name
 */
export function getDepartmentName(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.trm_depname || studentData.department_name || null;
}

/**
 * Extract term count (semester count) from student data
 * Priority: trm_termcount (term data) > std_termcount (basic data) > term_count
 */
export function getTermCount(studentData?: StudentData | null): number | null {
  if (!studentData) return null;
  const termCount = studentData.trm_termcount ?? studentData.std_termcount ?? studentData.term_count;
  return termCount !== null && termCount !== undefined ? Number(termCount) : null;
}

/**
 * Extract GPA from student data
 * Priority: trm_ascore_gpa (term data) > gpa
 */
export function getGPA(studentData?: StudentData | null): number | null {
  if (!studentData) return null;
  const gpa = studentData.trm_ascore_gpa ?? studentData.gpa;
  return gpa !== null && gpa !== undefined ? Number(gpa) : null;
}

/**
 * Extract degree code from student data
 */
export function getDegreeCode(studentData?: StudentData | null): number | null {
  if (!studentData) return null;
  const degree = studentData.std_degree ?? studentData.degree;
  return degree !== null && degree !== undefined ? Number(degree) : null;
}

/**
 * Extract gender from student data
 */
export function getGender(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_sex || studentData.gender || null;
}

/**
 * Extract nationality from student data
 */
export function getNationality(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_nation || studentData.nationality || null;
}

/**
 * Extract identity code from student data
 */
export function getIdentityCode(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_identity || studentData.identity || null;
}

/**
 * Extract school identity code from student data
 */
export function getSchoolIdentityCode(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_schoolid || studentData.school_identity || null;
}

/**
 * Extract studying status from student data
 */
export function getStudyingStatus(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_studingstatus || studentData.studying_status || null;
}

/**
 * Extract enrollment year from student data
 */
export function getEnrollmentYear(studentData?: StudentData | null): number | null {
  if (!studentData) return null;
  const year = studentData.std_enrollyear ?? studentData.enroll_year;
  return year !== null && year !== undefined ? Number(year) : null;
}

/**
 * Extract enrollment term from student data
 */
export function getEnrollmentTerm(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_enrollterm || studentData.enroll_term || null;
}

/**
 * Extract academic year from student data
 * This is the year of the term data snapshot
 */
export function getAcademicYear(studentData?: StudentData | null): number | null {
  if (!studentData) return null;
  const year = studentData.trm_year ?? studentData.academic_year;
  return year !== null && year !== undefined ? Number(year) : null;
}

/**
 * Extract academic term from student data
 * This is the term of the term data snapshot (1 or 2)
 */
export function getAcademicTerm(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.trm_term || studentData.term || null;
}

/**
 * Extract highest education school name from student data
 */
export function getHighestEducation(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_highestschname || studentData.highest_education || null;
}

/**
 * Extract overseas place from student data
 */
export function getOverseasPlace(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.std_overseaplace || studentData.overseas_place || null;
}

/**
 * Extract student status title (學籍狀態) from student data
 */
export function getStatusTitle(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData.mgd_title || studentData.status_title || null;
}

/**
 * Format academic year and term as display string
 * Example: "114-1" or "113-2"
 */
export function formatAcademicYearTerm(
  studentData?: StudentData | null,
  locale: "zh" | "en" = "zh"
): string | null {
  if (!studentData) return null;
  const year = getAcademicYear(studentData);
  const term = getAcademicTerm(studentData);

  if (year === null || term === null) return null;

  if (locale === "zh") {
    const termDisplay = term === "1" ? "上" : term === "2" ? "下" : term;
    return `${year}-${termDisplay}`;
  }

  return `${year}-${term}`;
}

/**
 * Check if student data has term-specific information
 */
export function hasTermData(studentData?: StudentData | null): boolean {
  if (!studentData) return false;
  return !!(studentData.trm_year && studentData.trm_term);
}

/**
 * Get API fetch timestamp
 */
export function getApiFetchedAt(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData._api_fetched_at || null;
}

/**
 * Get term data fetch status
 */
export function getTermDataStatus(studentData?: StudentData | null): string | null {
  if (!studentData) return null;
  return studentData._term_data_status || null;
}
