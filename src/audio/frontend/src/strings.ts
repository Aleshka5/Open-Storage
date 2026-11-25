// Interface strings (design_document.md §«Interface strings»). English interface.
// Speaker `label`s ("Speaker N", "Me", nicknames) come from the server and are not translated.

export const strings = {
  'app.title': 'Audio',
  'sidebar.upload': 'Upload file',
  'sidebar.empty': 'No recordings yet',
  'note.default_title': 'Note {N}',
  'speaker.numbered': 'Speaker {N}',
  'status.diarizing': 'Detecting voices…',
  'status.transcribing': 'Transcribing speech…',
  'status.failed': 'Processing failed',
  'error.asr_busy': 'Recognition is busy, please try again',
  'player.speed': 'Speed',
  'empty.title': 'Upload a file or record a note',
  'empty.recording_not_found': 'Recording not found',
  'rename.placeholder': 'Recording title',
  'rename.save': 'Save',
  'sidebar.collapse': 'Collapse sidebar',
  'sidebar.expand': 'Expand sidebar',
  'player.play': 'Play',
  'player.pause': 'Pause',
  'error.crash_title': 'Something went wrong',
  'error.crash_hint':
    'The interface could not render. Reload the page: your recordings are safe on the server.',
  'error.crash_reload': 'Reload',
} as const;

export type StringKey = keyof typeof strings;

/** Substitutes `{N}`. */
export function t(key: StringKey, params?: Record<string, string | number>): string {
  let out: string = strings[key];
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      out = out.replaceAll(`{${k}}`, String(v));
    }
  }
  return out;
}

/** `mm:ss` from the start (milliseconds), not wall-clock. */
export function formatTime(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Translates `processing.error_code` into human-readable text (chat-and-player.md).
 * An unknown code does not crash: the code itself is shown as the reason.
 */
export function humanizeErrorCode(code: string | null | undefined): string {
  switch (code) {
    case 'UNSUPPORTED_MEDIA':
      return 'Could not read the file';
    case 'PROCESSING_STALLED':
      return 'Processing stalled';
    case 'QUEUE_UNAVAILABLE':
      return 'Processing queue is unavailable';
    case 'STORAGE_UNAVAILABLE':
      return 'Storage is unavailable';
    default:
      return code ?? 'Unknown error';
  }
}
