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
 * @param html Rendered HTML email
 * @returns Plain text version
 */
export function emailToPlainText(html: string): string {
  // Remove script/style blocks
  let text = html.replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, '');

  // Strip HTML tags
  text = text.replace(/<[^>]+>/g, ' ');

  // Decode HTML entities
  text = text.replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");

  // Normalize whitespace
  text = text.replace(/\s+/g, ' ').trim();

  return text;
}
