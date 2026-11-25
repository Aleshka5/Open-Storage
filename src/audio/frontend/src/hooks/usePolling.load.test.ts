// The chat is fed only by GET /phrases (the detail response carries no phrases), so the hook
// must load the history of an already `ready` recording — not only poll a growing one.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { Phrase, PhrasesResponse, RecordingStatus } from '../api/types';

const getPhrases = vi.fn();

vi.mock('../api/client', () => ({
  getPhrases: (id: string, afterSeq: number, limit?: number) =>
    getPhrases(id, afterSeq, limit),
}));

import { usePolling, PHRASE_PAGE_LIMIT } from './usePolling';

function phrase(seq: number, over: Partial<Phrase> = {}): Phrase {
  return {
    id: `id-${seq}`,
    seq,
    speaker_id: 'spk',
    label: 'Speaker 1',
    side: 'left',
    start_ms: seq * 1000,
    end_ms: seq * 1000 + 900,
    text: `phrase ${seq}`,
    state: 'final',
    revision: 0,
    overlap: false,
    ...over,
  };
}

function page(
  items: Phrase[],
  status: RecordingStatus,
  nextAfterSeq = items.length ? items[items.length - 1].seq : 0,
  processing: { phrases_done?: number; phrases_total?: number; embedding?: string } = {},
): PhrasesResponse {
  return {
    recording: {
      status,
      processing: {
        phrases_done: processing.phrases_done ?? items.length,
        phrases_total: processing.phrases_total ?? items.length,
        embedding: processing.embedding ?? 'none',
      },
    },
    items,
    next_after_seq: nextAfterSeq,
  } as unknown as PhrasesResponse;
}

beforeEach(() => {
  getPhrases.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('usePolling — the chat of an opened recording', () => {
  it('loads the whole history of an already ready recording (one back-fill, then stop)', async () => {
    getPhrases.mockResolvedValueOnce(page([phrase(1), phrase(2), phrase(3)], 'ready'));

    const { result } = renderHook(() => usePolling('rec-1', null));

    await waitFor(() => expect(result.current.phrases).toHaveLength(3));
    expect(result.current.status).toBe('ready');
    expect(getPhrases).toHaveBeenCalledTimes(1);
    expect(getPhrases).toHaveBeenCalledWith('rec-1', 0, PHRASE_PAGE_LIMIT);

    // Terminal status: no further request is scheduled.
    await new Promise((r) => setTimeout(r, 50));
    expect(getPhrases).toHaveBeenCalledTimes(1);
  });

  it('walks the history page by page when it is longer than one page', async () => {
    const first = Array.from({ length: PHRASE_PAGE_LIMIT }, (_, i) => phrase(i + 1));
    getPhrases
      .mockResolvedValueOnce(page(first, 'ready', PHRASE_PAGE_LIMIT))
      .mockResolvedValueOnce(page([phrase(PHRASE_PAGE_LIMIT + 1)], 'ready'));

    const { result } = renderHook(() => usePolling('rec-long', null));

    await waitFor(() => expect(result.current.phrases).toHaveLength(PHRASE_PAGE_LIMIT + 1));
    expect(getPhrases).toHaveBeenNthCalledWith(2, 'rec-long', PHRASE_PAGE_LIMIT, PHRASE_PAGE_LIMIT);
  });

  it('keeps polling through uploaded → transcribing and stops once ready', async () => {
    vi.useFakeTimers();
    getPhrases
      .mockResolvedValueOnce(page([], 'uploaded', 0))
      .mockResolvedValueOnce(page([phrase(1)], 'transcribing', 1, { phrases_done: 1, phrases_total: 2 }))
      .mockResolvedValueOnce(page([phrase(2)], 'ready', 2, { phrases_done: 2, phrases_total: 2 }));

    const { result } = renderHook(() => usePolling('rec-2', null));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getPhrases).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe('uploaded');

    // `uploaded` is not terminal: the client waits for the workers instead of freezing.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(getPhrases).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe('transcribing');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(getPhrases).toHaveBeenCalledTimes(3);
    expect(result.current.phrases.map((p) => p.text)).toEqual(['phrase 1', 'phrase 2']);
    expect(result.current.status).toBe('ready');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(getPhrases).toHaveBeenCalledTimes(3);
  });

  it('keeps asking for a note phrase that grows in place (`seq` never advances)', async () => {
    vi.useFakeTimers();
    getPhrases
      .mockResolvedValueOnce(
        page([phrase(1, { text: 'Раз,', state: 'partial', revision: 1 })], 'recording', 1),
      )
      .mockResolvedValueOnce(
        page([phrase(1, { text: 'Раз, два,', state: 'partial', revision: 2 })], 'recording', 1),
      )
      .mockResolvedValueOnce(
        page([phrase(1, { text: 'Раз, два, три.', state: 'final', revision: 3 })], 'ready', 1),
      );

    const { result } = renderHook(() => usePolling('note-1', null));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.phrases[0].text).toBe('Раз,');

    // The second request must not use after_seq=1: that would skip the growing phrase.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(getPhrases).toHaveBeenNthCalledWith(2, 'note-1', 0, PHRASE_PAGE_LIMIT);
    expect(result.current.phrases[0].text).toBe('Раз, два,');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(result.current.phrases[0].text).toBe('Раз, два, три.');
    expect(result.current.phrases[0].state).toBe('final');
  });

  it('stops on 404 instead of retrying a recording that is not there', async () => {
    vi.useFakeTimers();
    getPhrases.mockRejectedValue(Object.assign(new Error('not found'), { status: 404 }));

    renderHook(() => usePolling('rec-gone', null));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getPhrases).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(getPhrases).toHaveBeenCalledTimes(1);
  });
});
