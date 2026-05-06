import { NextRequest, NextResponse } from 'next/server';
import { getPreview } from '@/lib/email-preview-store';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  try {
    const { id } = await params;
    const html = getPreview(id);

    if (!html) {
      return new NextResponse('Preview not found or expired', { status: 404 });
    }

    // Serve with a permissive CSP scoped only to this preview route.
    // Inline styles are required because React Email outputs style="..." attributes.
    // Scripts are blocked so the email HTML cannot execute code.
    return new NextResponse(html, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Content-Security-Policy':
          "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data: https:;",
        'X-Frame-Options': 'SAMEORIGIN',
        'Cache-Control': 'no-store',
      },
    });
  } catch (err) {
    const message = err instanceof Error ? `${err.name}: ${err.message}\n${err.stack}` : String(err);
    return new NextResponse(
      `<pre style="font-family:monospace;padding:1rem;white-space:pre-wrap">${message}</pre>`,
      { status: 500, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
  }
}
