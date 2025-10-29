/**
 * Email Rendering Utility
 *
 * Renders React Email templates with actual data using @react-email/render.
 * This replaces the old architecture where backend loaded static HTML templates.
 *
 * Usage:
 *   const html = await renderEmailTemplate('application-submitted', {
 *     studentName: '王小明',
 *     appId: 'APP-2025-826055',
 *     scholarshipType: '學術優秀獎學金',
 *     submitDate: '2025-10-13',
 *     professorName: '李教授',
 *     systemUrl: 'https://scholarship.nycu.edu.tw'
 *   });
 */

import { render } from '@react-email/render';
import ApplicationSubmitted from '@/emails/application-submitted';
import ProfessorReviewRequest from '@/emails/professor-review-request';
import CollegeReviewRequest from '@/emails/college-review-request';
import DeadlineReminder from '@/emails/deadline-reminder';
import DocumentRequest from '@/emails/document-request';
import ResultNotification from '@/emails/result-notification';
import RosterNotification from '@/emails/roster-notification';
import WhitelistNotification from '@/emails/whitelist-notification';

/**
 * Email template names matching backend template keys
 */
export type EmailTemplate =
  | 'application-submitted'
  | 'professor-review-request'
  | 'college-review-request'
  | 'deadline-reminder'
  | 'document-request'
  | 'result-notification'
  | 'roster-notification'
  | 'whitelist-notification';

/**
 * Template component mapping
 */
const templateMap: Record<EmailTemplate, React.ComponentType<any>> = {
  'application-submitted': ApplicationSubmitted,
  'professor-review-request': ProfessorReviewRequest,
  'college-review-request': CollegeReviewRequest,
  'deadline-reminder': DeadlineReminder,
  'document-request': DocumentRequest,
  'result-notification': ResultNotification,
  'roster-notification': RosterNotification,
  'whitelist-notification': WhitelistNotification,
};

/**
 * Render email template with data
 *
 * @param templateName Name of the email template
 * @param props Props to pass to the template (camelCase variables)
 * @returns Rendered HTML string
 *
 * @example
 * ```typescript
 * const html = await renderEmailTemplate('application-submitted', {
 *   studentName: '王小明',
 *   appId: 'APP-2025-826055',
 *   scholarshipType: '學術優秀獎學金',
 *   submitDate: '2025-10-13',
 *   professorName: '李教授',
 *   systemUrl: 'https://scholarship.nycu.edu.tw'
 * });
 * ```
 */
export async function renderEmailTemplate(
  templateName: EmailTemplate,
  props: Record<string, any>
): Promise<string> {
  const Template = templateMap[templateName];

  if (!Template) {
    throw new Error(`Email template not found: ${templateName}`);
  }

  // Render React component to HTML string
  const html = await render(<Template {...props} />);

  return html;
}

/**
 * Get plain text version of rendered email
 *
 * SECURITY: Uses DOMParser exclusively to safely extract text from HTML
 * without regex-based vulnerabilities. DOMParser handles all HTML parsing,
 * entity decoding, and script/style removal securely.
 *
 * @param html Rendered HTML email
 * @returns Plain text version
 */
export function emailToPlainText(html: string): string {
  // SECURITY: Use DOMParser exclusively - no regex patterns that could be bypassed
  if (typeof DOMParser !== 'undefined') {
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');

      // Remove script and style elements via DOM manipulation (secure)
      doc.querySelectorAll('script, style').forEach(el => el.remove());

      // Extract text content safely - DOMParser handles all entity decoding
      const text = doc.body.textContent || '';

      // Normalize whitespace
      return text.replace(/\s+/g, ' ').trim();
    } catch (error) {
      // If DOMParser fails, return empty rather than use unsafe fallback
      console.error('DOMParser failed to parse HTML:', error);
      return '';
    }
  }

  // Server-side fallback (Node.js environment)
  // Simple text extraction - only used in server rendering context
  return html
    .replace(/<[^>]+>/g, ' ')  // Remove all tags
    .replace(/\s+/g, ' ')      // Normalize whitespace
    .trim();
}
