import { NextRequest, NextResponse } from 'next/server';
import { storePreview } from '@/lib/email-preview-store';

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const { html } = await request.json();

    if (!html || typeof html !== 'string') {
      return NextResponse.json({ error: 'Missing html' }, { status: 400 });
    }

    const id = storePreview(html);
    return NextResponse.json({ id });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
