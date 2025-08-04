/**
 * Date utility functions for Taiwan/ROC calendar system
 */

/**
 * Convert Western year to 民國年 (Republic of China year)
 * @param westernYear - Western calendar year (e.g., 2025)
 * @returns ROC year (e.g., 114)
 */
export function toROCYear(westernYear: number): number {
  return westernYear - 1911;
}

/**
 * Convert 民國年 to Western year  
 * @param rocYear - ROC calendar year (e.g., 114)
 * @returns Western year (e.g., 2025)
 */
export function fromROCYear(rocYear: number): number {
  return rocYear + 1911;
}

/**
 * Format semester with 民國年
 * @param semester - Semester in format "YYYY-S" (e.g., "2025-1")
 * @returns Formatted semester with ROC year (e.g., "114-1")
 */
export function formatSemesterROC(semester: string): string {
  const [year, term] = semester.split('-');
  if (!year || !term) return semester;
  
  const westernYear = parseInt(year);
  const rocYear = toROCYear(westernYear);
  
  return `${rocYear}-${term}`;
}

/**
 * Format semester with 民國年 and Chinese text
 * @param semester - Semester in format "YYYY-S" (e.g., "2025-1") 
 * @returns Formatted semester (e.g., "民國114年第1學期")
 */
export function formatSemesterROCText(semester: string): string {
  const [year, term] = semester.split('-');
  if (!year || !term) return semester;
  
  const westernYear = parseInt(year);
  const rocYear = toROCYear(westernYear);
  
  const termText = term === '1' ? '第1學期' : term === '2' ? '第2學期' : `第${term}學期`;
  
  return `民國${rocYear}年${termText}`;
}

/**
 * Generate available semesters in ROC format
 * @param currentYear - Current western year
 * @param yearsBack - Number of years to go back (default: 3)
 * @returns Array of semesters in format "ROC_YEAR-TERM"
 */
export function generateAvailableSemesters(currentYear: number = new Date().getFullYear(), yearsBack: number = 3): string[] {
  const semesters: string[] = [];
  
  for (let i = 0; i < yearsBack; i++) {
    const year = currentYear - i;
    const rocYear = toROCYear(year);
    semesters.push(`${rocYear}-1`);
    semesters.push(`${rocYear}-2`);
  }
  
  return semesters.sort((a, b) => {
    const [yearA, termA] = a.split('-').map(Number);
    const [yearB, termB] = b.split('-').map(Number);
    
    // Sort by year descending, then by term descending
    if (yearA !== yearB) return yearB - yearA;
    return termB - termA;
  });
}

/**
 * Get current semester in ROC format
 * @returns Current semester (e.g., "114-1")
 */
export function getCurrentSemesterROC(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1; // getMonth() returns 0-11
  
  const rocYear = toROCYear(year);
  
  // Determine semester based on month
  // Typically: Sep-Jan = 1st semester, Feb-Aug = 2nd semester
  // Adjust this logic based on your school's calendar
  const term = (month >= 9 || month <= 1) ? '1' : '2';
  
  return `${rocYear}-${term}`;
}

/**
 * Parse ROC semester back to Western format for API calls
 * @param rocSemester - ROC semester (e.g., "114-1")
 * @returns Western semester format (e.g., "2025-1")
 */
export function parseROCSemesterToWestern(rocSemester: string): string {
  const [rocYear, term] = rocSemester.split('-');
  if (!rocYear || !term) return rocSemester;
  
  const westernYear = fromROCYear(parseInt(rocYear));
  return `${westernYear}-${term}`;
}

/**
 * Check if a semester string is in ROC format
 * @param semester - Semester string
 * @returns true if ROC format (year < 200), false otherwise
 */
export function isROCFormat(semester: string): boolean {
  const [year] = semester.split('-');
  if (!year) return false;
  
  const yearNum = parseInt(year);
  return yearNum < 200; // ROC years are typically < 200
}