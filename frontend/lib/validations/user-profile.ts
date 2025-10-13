/**
 * User Profile validation utilities that align with backend Pydantic schemas
 */

export interface ValidationResult {
  isValid: boolean;
  errors: string[];
}

export interface AdvisorInfo {
  advisor_name?: string;
  advisor_email?: string;
  advisor_nycu_id?: string;
}

export interface BankInfo {
  account_number?: string;
}

/**
 * Email validation regex - matches backend validation
 */
const EMAIL_PATTERN = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

/**
 * Validate advisor email field
 * Aligns with backend AdvisorInfoBase validation
 */
export function validateAdvisorEmail(
  email: string | undefined | null
): ValidationResult {
  const errors: string[] = [];

  // Empty string or null/undefined is valid (optional field)
  if (!email || email.trim() === "") {
    return { isValid: true, errors: [] };
  }

  // If provided, must be valid email format
  if (!EMAIL_PATTERN.test(email.trim())) {
    errors.push("請輸入有效的Email格式 (例：professor@nycu.edu.tw)");
  }

  return { isValid: errors.length === 0, errors };
}

/**
 * Validate advisor information
 * Aligns with backend AdvisorInfoUpdate schema
 */
export function validateAdvisorInfo(data: AdvisorInfo): ValidationResult {
  const errors: string[] = [];

  // Validate advisor name (optional, max 100 chars)
  if (data.advisor_name && data.advisor_name.length > 100) {
    errors.push("指導教授姓名不能超過100個字符");
  }

  // Validate advisor email
  const emailValidation = validateAdvisorEmail(data.advisor_email);
  if (!emailValidation.isValid) {
    errors.push(...emailValidation.errors);
  }

  // Validate advisor NYCU ID (optional, max 20 chars)
  if (data.advisor_nycu_id && data.advisor_nycu_id.length > 20) {
    errors.push("指導教授本校人事編號不能超過20個字符");
  }

  return { isValid: errors.length === 0, errors };
}

/**
 * Validate post office account information
 * Aligns with backend BankInfoUpdate schema
 */
export function validateBankInfo(data: BankInfo): ValidationResult {
  const errors: string[] = [];

  // Validate account number (optional, max 50 chars)
  if (data.account_number && data.account_number.length > 50) {
    errors.push("郵局帳號不能超過50個字符");
  }

  return { isValid: errors.length === 0, errors };
}

/**
 * Sanitize advisor email for API submission
 * Converts empty strings to undefined to align with backend validation
 */
export function sanitizeAdvisorEmail(
  email: string | undefined | null
): string | undefined {
  if (!email || email.trim() === "") {
    return undefined;
  }
  return email.trim();
}

/**
 * Sanitize advisor data for API submission
 * Ensures data format matches backend expectations
 */
export function sanitizeAdvisorInfo(data: AdvisorInfo): AdvisorInfo {
  return {
    advisor_name: data.advisor_name?.trim() || undefined,
    advisor_email: sanitizeAdvisorEmail(data.advisor_email),
    advisor_nycu_id: data.advisor_nycu_id?.trim() || undefined,
  };
}

/**
 * Sanitize post office account data for API submission
 */
export function sanitizeBankInfo(data: BankInfo): BankInfo {
  return {
    account_number: data.account_number?.trim() || undefined,
  };
}
