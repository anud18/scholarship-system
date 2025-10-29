/**
 * Email Rendering API Endpoint
 *
 * Backend calls this endpoint to render React Email templates with actual data.
 *
 * Architecture:
 * - Backend: Creates context with actual data (snake_case)
 * - Frontend: Renders React Email templates with @react-email/render
 * - Returns: Complete HTML string ready to send
 *
 * POST /api/email/render
 * Body: { template_name: string, context: Record<string, any> }
 * Response: { success: true, html: string } | { success: false, error: string }
 */

import { NextRequest, NextResponse } from 'next/server';
import { renderEmailTemplate, EmailTemplate } from '@/lib/email-renderer';

// Whitelist of valid template names (security: prevent template injection)
const VALID_TEMPLATES: EmailTemplate[] = [
  'application-submitted',
  'professor-review-request',
  'college-review-request',
  'deadline-reminder',
  'document-request',
  'result-notification',
  'roster-notification',
  'whitelist-notification',
];

interface RenderEmailRequest {
  template_name: string;
  context: Record<string, any>;
}

interface RenderEmailResponse {
  success: boolean;
  html?: string;
  error?: string;
}

export async function POST(request: NextRequest): Promise<NextResponse<RenderEmailResponse>> {
  try {
    // Parse request body
    const body: RenderEmailRequest = await request.json();
    const { template_name, context } = body;

    // Validate template name
    if (!template_name || typeof template_name !== 'string') {
      return NextResponse.json(
        { success: false, error: 'Missing or invalid template_name' },
        { status: 400 }
      );
    }

    // Security: Check template name against whitelist
    if (!VALID_TEMPLATES.includes(template_name as EmailTemplate)) {
      return NextResponse.json(
        { success: false, error: `Invalid template name: ${template_name}` },
        { status: 400 }
      );
    }

    // Validate context
    if (!context || typeof context !== 'object') {
      return NextResponse.json(
        { success: false, error: 'Missing or invalid context' },
        { status: 400 }
      );
    }

    // Render email template
    const html = await renderEmailTemplate(template_name as EmailTemplate, context);

    // Return rendered HTML
    return NextResponse.json({
      success: true,
      html,
    });

  } catch (error: any) {
    console.error('[Email Render API] Error rendering email:', error);

    return NextResponse.json(
      {
        success: false,
        error: error.message || 'Failed to render email template'
      },
      { status: 500 }
    );
  }
}

// Health check endpoint (optional)
export async function GET(): Promise<NextResponse> {
  return NextResponse.json({
    status: 'ok',
    templates: VALID_TEMPLATES,
    message: 'Email rendering API is running. Use POST with {template_name, context}',
  });
}
