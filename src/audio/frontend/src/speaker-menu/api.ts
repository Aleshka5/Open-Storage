// HTTP to audio-api for the speaker menu. Identity is set by the gateway via the
// `X-Auth-Subject` header (a canonical lower-case UUID); the client does NOT hold owner_id (constitution §2). Self-contained
// module — does not touch api/client.ts from the US-04 branch.

import type {
  AssignResponse,
  NickAssignment,
  SuggestionsResponse,
} from './types';

const BASE = '/api';

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

/** Suggestions — called only when the menu opens (ADR-007). */
export async function fetchSuggestions(
  recordingId: string,
  speakerId: string,
): Promise<SuggestionsResponse> {
  const res = await fetch(
    `${BASE}/recordings/${recordingId}/speakers/${speakerId}/suggestions`,
    { headers: { Accept: 'application/json' } },
  );
  if (!res.ok) await handleError(res);
  return (await res.json()) as SuggestionsResponse;
}

/** Assign a nickname / create / "Me" (one of the three body shapes). */
export async function assignNick(
  recordingId: string,
  speakerId: string,
  body: NickAssignment,
): Promise<AssignResponse> {
  const res = await fetch(
    `${BASE}/recordings/${recordingId}/speakers/${speakerId}/nick`,
    {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) await handleError(res);
  return (await res.json()) as AssignResponse;
}
