// Thin HTTP client over audio-api. Identity is set by the gateway via the
// `X-Auth-Subject` header (a canonical lower-case UUID); the client does NOT store and does NOT send owner_id (constitution §2,
// ADR-001). In dev mode the path is proxied by Vite to audio-api.

import { apiUrl } from './base';
import {
  ApiError,
  type ApiErrorDetail,
  type PhrasesResponse,
  type RecordingDetail,
  type RecordingDetailResponse,
  type RecordingListResponse,
  type VoiceNoteCreated,
} from './types';

const BASE = apiUrl('/api');

async function parseError(res: Response): Promise<ApiError> {
  let errorCode = 'INTERNAL';
  let message = `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as { detail?: ApiErrorDetail };
    if (body?.detail) {
      errorCode = body.detail.error_code ?? 'INTERNAL';
      message = body.detail.message ?? message;
    }
  } catch {
    // body is not JSON — keep the default
  }
  return new ApiError(res.status, errorCode, message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: 'include',
    headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export function listRecordings(
  limit = 100,
  cursor?: string,
): Promise<RecordingListResponse> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (cursor) qs.set('cursor', cursor);
  return request<RecordingListResponse>(`${BASE}/recordings?${qs}`);
}

export function getRecording(id: string): Promise<RecordingDetailResponse> {
  return request<RecordingDetailResponse>(`${BASE}/recordings/${id}`);
}

export function renameRecording(
  id: string,
  title: string,
): Promise<RecordingDetailResponse> {
  return request<RecordingDetailResponse>(`${BASE}/recordings/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export function getPhrases(
  id: string,
  afterSeq: number,
  limit = 200,
): Promise<PhrasesResponse> {
  const qs = new URLSearchParams({
    after_seq: String(afterSeq),
    limit: String(limit),
  });
  return request<PhrasesResponse>(
    `${BASE}/recordings/${id}/phrases?${qs}`,
  );
}

/**
 * File upload (multipart/form-data). The `201` body is the recording object itself —
 * NOT the `{recording, speakers}` envelope of `GET /api/recordings/{id}` (api.md).
 */
export async function uploadRecording(file: File): Promise<RecordingDetail> {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${BASE}/recordings`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    body: form,
  });

  if (!res.ok) throw await parseError(res);
  return (await res.json()) as RecordingDetail;
}

/**
 * Upload with progress via XHR (fetch cannot report upload progress).
 * Returns the same recording object (not the `{recording}` envelope) after `201`.
 */
export function uploadRecordingWithProgress(
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<RecordingDetail> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/recordings`);
    xhr.withCredentials = true;
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.responseType = 'json';

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded / e.total);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as RecordingDetail);
      } else {
        const detail = xhr.response as { detail?: ApiErrorDetail } | null;
        const d = detail?.detail;
        reject(
          new ApiError(
            xhr.status,
            d?.error_code ?? 'INTERNAL',
            d?.message ?? `HTTP ${xhr.status}`,
          ),
        );
      }
    };

    xhr.onerror = () =>
      reject(new ApiError(0, 'NETWORK', 'Network unavailable'));
    xhr.onabort = () =>
      reject(new ApiError(0, 'ABORTED', 'Upload aborted'));

    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}

/** Audio URL for `<audio>` — always through audio-api (ADR-010). */
export function audioUrl(id: string): string {
  return `${BASE}/recordings/${id}/audio`;
}

/** Creating a voice note (POST /api/voice-notes). */
export function createVoiceNote(): Promise<VoiceNoteCreated> {
  return request<VoiceNoteCreated>(`${BASE}/voice-notes`, { method: 'POST' });
}

/** WS stream URL of the note, from the relative path in the POST response. */
export function voiceNoteStreamUrl(wsUrl: string): string {
  // ws_url from the response: `/api/voice-notes/{id}/stream`. Browser — same host,
  // ws/wss scheme according to the page's current protocol.
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}${wsUrl}`;
}
