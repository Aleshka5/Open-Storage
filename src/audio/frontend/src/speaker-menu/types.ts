// Speaker menu types (docs/backend/audio-api/api.md, UC-9/UC-10).
// Self-contained module: does not depend on api/types.ts so it does not conflict with
// the US-04 frontend branch (chat tiles). Wired to the phrase label on merge.

/** Current speaker assignment (no preselection for an unassigned speaker). */
export type SpeakerCurrent = { kind: 'none' } | { kind: 'me' } | { kind: 'nick'; nick_id: string };

export type SuggestionItem =
  | { kind: 'me'; name: 'Me'; score: number | null }
  | { kind: 'nick'; nick_id: string; name: string; score: number };

export interface SuggestionsResponse {
  speaker: { id: string; label: string; current: SpeakerCurrent };
  items: SuggestionItem[];
}

/** Three body shapes for POST …/speakers/{sid}/nick (exactly one is filled in). */
export type NickAssignment =
  | { nick_id: string }
  | { name: string }
  | { me: true };

export interface AssignResponse {
  speaker: { id: string; label: string; nick_id: string | null; is_me: boolean };
  nick: { id: string | null; name: string; reused: boolean };
  phrases_updated: number;
}

/** The speaker context the menu is built from. */
export interface SpeakerRef {
  recording_id: string;
  speaker_id: string;
  label: string;
  is_me: boolean;
  nick_id: string | null;
}
