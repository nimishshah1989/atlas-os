// POST /api/maal/image — attach a chart screenshot to a call or an
// evidence section. A route handler, NOT a server action: server actions cap the
// body at 1 MB. NOTE: nginx in front of pm2 caps at 1m by default — the box needs
// `client_max_body_size 5m;` or these 413 before Next ever sees them.
import { NextResponse } from 'next/server'

import {
  clearCallImage,
  clearEvidenceImage,
  saveCallImage,
  saveEvidenceImage,
} from '@/lib/queries/maal'

export const dynamic = 'force-dynamic'

const MAX_BYTES = 2 * 1024 * 1024
const ALLOWED = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif'])

export async function POST(req: Request) {
  let form: FormData
  try {
    form = await req.formData()
  } catch {
    return NextResponse.json({ error_code: 'bad_request', message: 'expected multipart form data' }, { status: 400 })
  }

  const file = form.get('file')
  const confirmationId = Number(form.get('confirmationId'))
  const target = String(form.get('target') ?? '') // "call" | "evidence"
  const ref = String(form.get('ref') ?? '') // instrument key, or evidence position

  if (!(file instanceof File)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'file is required' }, { status: 400 })
  }
  if (!Number.isInteger(confirmationId) || confirmationId <= 0) {
    return NextResponse.json({ error_code: 'bad_request', message: 'confirmationId is required' }, { status: 400 })
  }
  if (!ALLOWED.has(file.type)) {
    return NextResponse.json(
      { error_code: 'bad_image', message: `${file.type || 'that file'} is not a PNG, JPEG, WebP or GIF` },
      { status: 415 },
    )
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json(
      { error_code: 'too_large', message: `charts must be under ${MAX_BYTES / 1024 / 1024} MB` },
      { status: 413 },
    )
  }

  const bytes = Buffer.from(await file.arrayBuffer())
  const attached =
    target === 'evidence'
      ? await saveEvidenceImage(confirmationId, Number(ref), bytes, file.type)
      : await saveCallImage(confirmationId, ref, bytes, file.type)

  if (!attached) {
    return NextResponse.json(
      { error_code: 'not_found', message: 'save the row before attaching its chart' },
      { status: 404 },
    )
  }
  return NextResponse.json({ attached: true, bytes: bytes.length })
}

/**
 * DELETE /api/maal/image — detach a chart.
 *
 * Clears the bytes; the call row itself stands. Attaching the wrong screenshot was
 * previously permanent for the week, which made the FM hesitant to attach at all.
 */
export async function DELETE(req: Request) {
  const body = await req.json().catch(() => null)
  const confirmationId = Number(body?.confirmationId)
  const target = body?.target
  const ref = body?.ref
  if (
    !Number.isInteger(confirmationId) ||
    confirmationId <= 0 ||
    (target !== 'call' && target !== 'evidence') ||
    typeof ref !== 'string' ||
    ref === ''
  ) {
    return NextResponse.json(
      { error_code: 'bad_request', message: 'bad image reference' },
      { status: 400 },
    )
  }

  const cleared =
    target === 'evidence'
      ? await clearEvidenceImage(confirmationId, Number(ref))
      : await clearCallImage(confirmationId, ref)

  if (!cleared) {
    return NextResponse.json(
      { error_code: 'not_found', message: 'no chart to remove' },
      { status: 404 },
    )
  }
  return NextResponse.json({ attached: false })
}
