import { describe, it, expect } from 'vitest';
import { mergePhrases } from '../hooks/usePolling';
import type { Phrase } from '../api/types';

function phrase(over: Partial<Phrase> & { seq: number }): Phrase {
  return {
    speaker_id: 'spk',
    label: 'Speaker 1',
    side: 'left',
    start_ms: 0,
    end_ms: 1000,
    text: '…',
    state: 'final',
    revision: 0,
    overlap: false,
    ...over,
    id: over.id ?? `id-${over.seq}`,
  };
}

describe('mergePhrases (rendering phrases by seq)', () => {
  it('adds new phrases and sorts by seq', () => {
    const prev: Phrase[] = [phrase({ seq: 1 }), phrase({ seq: 3 })];
    const incoming: Phrase[] = [phrase({ seq: 2 }), phrase({ seq: 4 })];
    const merged = mergePhrases(prev, incoming);
    expect(merged.map((p) => p.seq)).toEqual([1, 2, 3, 4]);
  });

  it('does not overwrite already rendered final phrases', () => {
    const prev: Phrase[] = [
      phrase({ seq: 1, text: 'original', state: 'final', revision: 0 }),
    ];
    // A repeated response with the same seq but different text (must not overwrite).
    const incoming: Phrase[] = [phrase({ seq: 1, text: 'X', state: 'final', revision: 1 })];
    const merged = mergePhrases(prev, incoming);
    expect(merged[0].text).toBe('original');
  });

  it('replaces the partial text when the revision changes', () => {
    const prev: Phrase[] = [
      phrase({ seq: 1, text: 'growin', state: 'partial', revision: 1 }),
    ];
    const incoming: Phrase[] = [
      phrase({ seq: 1, text: 'growing text', state: 'partial', revision: 2 }),
    ];
    const merged = mergePhrases(prev, incoming);
    expect(merged[0].text).toBe('growing text');
    expect(merged[0].revision).toBe(2);
  });

  it('returns the same array (unchanged) for empty incoming', () => {
    const prev: Phrase[] = [phrase({ seq: 1 })];
    expect(mergePhrases(prev, [])).toBe(prev);
  });

  it('hands a partial note phrase over to its final text', () => {
    const prev: Phrase[] = [
      phrase({ seq: 1, text: 'Раз, два', state: 'partial', revision: 3 }),
    ];
    const incoming: Phrase[] = [
      phrase({ seq: 1, text: 'Раз, два, три.', state: 'final', revision: 4 }),
    ];
    const merged = mergePhrases(prev, incoming);
    expect(merged[0].text).toBe('Раз, два, три.');
    expect(merged[0].state).toBe('final');
  });
});

describe('polling after ready while the voice vector is unfinished (US-07)', () => {
  // A ready note whose embedding is still `pending`: polling must continue,
  // otherwise `processing.embedding` stays `pending` in the UI forever and the
  // "Make it my voice" item never unlocks.
  it('continueAfterReady: pending → polling continues, otherwise — stop', async () => {
    const { shouldContinueAfterReady } = await import('../hooks/usePolling');
    expect(shouldContinueAfterReady('pending')).toBe(true);
    expect(shouldContinueAfterReady('ready')).toBe(false);
    expect(shouldContinueAfterReady('failed')).toBe(false);
    expect(shouldContinueAfterReady(null)).toBe(false);
  });
});
