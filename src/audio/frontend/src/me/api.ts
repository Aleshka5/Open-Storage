// HTTP to audio-api for the "Me" voice (US-07, docs/backend/audio-api/api.md
// §PUT /api/me/voice). Identity is set by the gateway via the `X-Auth-Subject` header (a canonical
// lower-case UUID); the client does NOT hold owner_id (constitution §2). Self-contained module — does not touch api/client.ts.

export interface MeVoiceResponse {
  label: 'Me';
  has_default_voice: boolean;
  default_voice: {
    recording_id: string;
    kind: 'voice_note' | 'upload';
    title: string;
  } | null;
}

export interface MeVoiceRequest {
  recording_id: string;
  speaker_id: string | null;
}

async function handleError(res: Response): Promise<never> {
  let code = 'INTERNAL';
  let message = `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as {
      detail?: { error_code?: string; message?: string };
    };
    if (body?.detail) {
      code = body.detail.error_code ?? 'INTERNAL';
      message = body.detail.message ?? message;
    }
  } catch {
    // body is not JSON
  }
  const err = new Error(message) as Error & { status: number; error_code: string };
  err.status = res.status;
  err.error_code = code;
  throw err;
}

/** Replace the "Me" voice: from a note (`speaker_id: null`) or from a recording's speaker. */
export async function setMeVoice(body: MeVoiceRequest): Promise<MeVoiceResponse> {
  const res = await fetch('/api/me/voice', {
    method: 'PUT',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) await handleError(res);
  return (await res.json()) as MeVoiceResponse;
}
