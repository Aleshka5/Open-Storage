// audio-api contract (docs/backend/audio-api/api.md). Response fields are as in the spec;
// the frontend invents nothing beyond what is described there.

export type RecordingStatus =
  | 'uploaded'
  | 'diarizing'
  | 'transcribing'
  | 'ready'
  | 'failed'
  | 'recording'
  | 'finalizing';

export type AudioKind = 'voice_note';

/** Short recording entry in the list (GET /api/recordings). */
export interface RecordingListItem {
  id: string;
  title: string;
  kind: 'upload' | AudioKind;
  status: RecordingStatus;
  duration_ms: number;
  is_default_voice: boolean;
  created_at: string;
  progress: { phrases_done: number; phrases_total: number } | null;
}

export interface RecordingListResponse {
  items: RecordingListItem[];
  next_cursor: string | null;
}

/** Full recording (GET/POST/PATCH /api/recordings/{id}). */
export interface RecordingDetail {
  id: string;
  title: string;
  kind: 'upload' | AudioKind;
  status: RecordingStatus;
  duration_ms: number;
  language: string | null;
  is_default_voice: boolean;
  audio: { content_type: string; bytes: number } | null;
  processing: {
    error_code: string | null;
    phrases_done: number;
    phrases_total: number;
    /** Voice-vector state (US-07). May be absent in older responses. */
    embedding?: 'none' | 'pending' | 'ready' | 'failed' | 'incompatible';
  } | null;
  created_at: string;
  ready_at: string | null;
}

export interface Speaker {
  id: string;
  order_index: number;
  label: string;
  nick_id: string | null;
  is_me: boolean;
}

export interface RecordingDetailResponse {
  recording: RecordingDetail;
  speakers: Speaker[];
}

export type PhraseState = 'final' | 'partial';
export type PhraseSide = 'left' | 'right';

/** Chat phrase (GET /api/recordings/{id}/phrases). */
export interface Phrase {
  id: string;
  seq: number;
  speaker_id: string;
  label: string;
  side: PhraseSide;
  start_ms: number;
  end_ms: number;
  text: string;
  state: PhraseState;
  revision: number;
  overlap: boolean;
}

export interface PhrasesResponse {
  recording: {
    status: RecordingStatus;
    processing: { phrases_done: number; phrases_total: number };
  } | null;
  items: Phrase[];
  next_after_seq: number;
}

/** Unified error envelope (constitution §11). */
export interface ApiErrorDetail {
  error_code: string;
  message: string;
  recording_id?: string;
}

/** POST /api/voice-notes response (api.md). */
export interface VoiceNoteCreated {
  recording_id: string;
  title: string;
  phrase_id: string;
  ws_url: string;
  audio_format: string;
  sample_rate: number;
  channels: number;
}

/** Server frames on WS /api/voice-notes/{id}/stream. */
export type VoiceNoteServerFrame =
  | { type: 'ready'; recording_id: string; phrase_id: string; sample_rate: number }
  | { type: 'partial'; phrase_id: string; text: string; end_ms: number; revision: number }
  | { type: 'final'; phrase_id: string; text: string; end_ms: number; revision: number }
  | { type: 'stopped'; audio_bytes: number; duration_ms: number; audio_ready: boolean }
  | { type: 'done' }
  | { type: 'error'; error_code: string; message: string };

export class ApiError extends Error {
  readonly status: number;
  readonly errorCode: string;

  constructor(status: number, errorCode: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errorCode = errorCode;
  }
}
