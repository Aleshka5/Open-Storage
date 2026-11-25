// Sidebar list items built from a freshly created recording.
//
// `POST /api/recordings` answers `201` with the recording object itself (api.md), while the
// list holds `RecordingListItem`s: the progress pair is flattened out of `processing`.
// Reading that response as a `{recording, speakers}` envelope (`created.recording`) threw
// inside the `setRecordings` updater — a render-phase error — so React unmounted the whole
// tree and the page went blank until a manual reload.

import type { RecordingDetail, RecordingListItem, VoiceNoteCreated } from '../api/types';

export function toListItem(rec: RecordingDetail): RecordingListItem {
  return {
    id: rec.id,
    title: rec.title,
    kind: rec.kind,
    status: rec.status,
    duration_ms: rec.duration_ms,
    is_default_voice: rec.is_default_voice,
    created_at: rec.created_at,
    progress: rec.processing
      ? {
          phrases_done: rec.processing.phrases_done,
          phrases_total: rec.processing.phrases_total,
        }
      : null,
  };
}

/** The sidebar entry for a note that has just been announced (replaced by `refresh()`). */
export function noteListItem(created: VoiceNoteCreated): RecordingListItem {
  return {
    id: created.recording_id,
    title: created.title,
    kind: 'voice_note',
    status: 'recording',
    duration_ms: 0,
    is_default_voice: false,
    created_at: new Date().toISOString(),
    progress: null,
  };
}
