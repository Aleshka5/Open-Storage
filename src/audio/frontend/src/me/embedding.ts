// The recording's voice-vector state (`recordings.processing.embedding`, data-model.md).
// The "Make it my voice" item is available only when `ready` (queue-audio-embedding §«While
// the vector is missing»): without a ready vector the server would answer 409 VOICE_NOT_READY.

export type EmbeddingState = 'none' | 'pending' | 'ready' | 'failed' | 'incompatible';

/** Whether the voice vector is ready: only `ready` enables the menu item. */
export function isVoiceReady(embedding: EmbeddingState | undefined): boolean {
  return embedding === 'ready';
}
