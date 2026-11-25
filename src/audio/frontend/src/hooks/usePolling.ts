// Chat data hook: the phrase history is fetched once when the recording is opened and then
// kept in sync from the same endpoint (ADR-005, chat-and-player.md §«The growing chat»).
// `GET /phrases?after_seq` is the only source of the chat text — a `ready` recording opened
// from the sidebar has to be back-filled, otherwise the chat would stay empty forever.

import { useEffect, useRef, useState } from 'react';
import { getPhrases } from '../api/client';
import type { Phrase, PhrasesResponse, RecordingStatus } from '../api/types';
import {
  PollController,
  PollRateLimitedError,
} from '../core/poll';

/** The API ceiling for one page of `GET /phrases` (docs/backend/audio-api/api.md). */
export const PHRASE_PAGE_LIMIT = 500;
/** Safety valve for the history back-fill: 20 pages = 10 000 phrases. */
const MAX_BACKFILL_PAGES = 20;

export interface PollingState {
  phrases: Phrase[];
  status: RecordingStatus | null;
  phrasesDone: number;
  phrasesTotal: number;
  /** Whether the recording looks like it is still being processed (for the badge). */
  isProcessing: boolean;
  /** The recording's voice-vector state (US-07): pending → the menu item waits for `ready`. */
  embedding: string | null;
}

function isProcessingStatus(s: string | null): s is 'diarizing' | 'transcribing' {
  return s === 'diarizing' || s === 'transcribing';
}

/** `ready`/`failed` — the status after which nothing new can arrive for this recording. */
function isTerminalStatus(s: string | null): boolean {
  return s === 'ready' || s === 'failed';
}

/** Polling of a ready recording continues until the voice vector is computed (US-07). */
export function shouldContinueAfterReady(embedding: string | null): boolean {
  return embedding === 'pending';
}

/**
 * Loads the chat of `recordingId`: one back-fill from `after_seq=0` (works for any status,
 * so an already `ready` recording shows its text), then `GET /phrases?after_seq` every
 * 1.5 s while the recording is not `ready`/`failed`. Pauses while the tab is hidden,
 * backs off on 429 and on a run of empty responses.
 *
 * `initialPhrases` seeds the state before the first request lands (usually empty: the
 * detail response carries no phrases).
 */
export function usePolling(
  recordingId: string | null,
  initialStatus: RecordingStatus | null,
  initialPhrases: Phrase[] = [],
): PollingState {
  const [phrases, setPhrases] = useState<Phrase[]>(initialPhrases);
  const [status, setStatus] = useState<RecordingStatus | null>(initialStatus);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [embedding, setEmbedding] = useState<string | null>(null);

  const idRef = useRef<string | null>(recordingId);
  idRef.current = recordingId;
  // The controller asks for the last known status through this ref (no stale closure).
  const statusRef = useRef<RecordingStatus | null>(initialStatus);
  statusRef.current = status;

  // Reset when the recording changes.
  useEffect(() => {
    setPhrases(initialPhrases);
    setStatus(initialStatus);
    setProgress({ done: 0, total: 0 });
    setEmbedding(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingId]);

  useEffect(() => {
    if (!recordingId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const controller = new PollController({
      getStatus: () => (cancelled ? null : statusRef.current),
      isTabVisible: () => document.visibilityState === 'visible',
      setTimeout: (cb, ms) => {
        timer = globalThis.setTimeout(cb, ms);
        return timer;
      },
      clearTimeout: (h) => {
        if (timer === h) timer = null;
        globalThis.clearTimeout(h as ReturnType<typeof setTimeout>);
      },
      fetch: async (afterSeq) => {
        const res = await getPhrases(recordingId, afterSeq, PHRASE_PAGE_LIMIT);
        return { status: res.recording?.status ?? null, empty: res.items.length === 0 };
      },
      now: () => Date.now(),
    });

    let afterSeq = 0;

    const run = async () => {
      if (cancelled) return;
      try {
        // Back-fill: the first tick starts at 0 and walks the whole history page by page,
        // all later ticks return only what is new. Both go through the same call.
        let received = 0;
        let last: PhrasesResponse | null = null;
        // A note keeps one phrase (`seq=1`, `state: partial`) and bumps its `revision` in place,
        // so `after_seq` must never step past it — otherwise the chat freezes on the first
        // partial text and the final result is never shown.
        let partialFloor = Number.POSITIVE_INFINITY;
        for (let page = 0; page < MAX_BACKFILL_PAGES; page += 1) {
          const res: PhrasesResponse = await getPhrases(
            recordingId,
            afterSeq,
            PHRASE_PAGE_LIMIT,
          );
          if (cancelled) return;
          last = res;
          const items = res.items ?? [];
          received += items.length;
          for (const p of items) {
            if (p.state === 'partial' && p.seq < partialFloor) partialFloor = p.seq;
          }
          // Already rendered phrases are not rewritten; a note's partial phrase is replaced
          // on a revision change (mergePhrases).
          if (items.length > 0) setPhrases((prev) => mergePhrases(prev, items));
          afterSeq = res.next_after_seq;
          if (items.length < PHRASE_PAGE_LIMIT) break;
        }
        if (!last) return;
        afterSeq =
          partialFloor === Number.POSITIVE_INFINITY
            ? last.next_after_seq
            : Math.min(last.next_after_seq, partialFloor - 1);

        const newStatus = last.recording?.status ?? null;
        setStatus(newStatus as RecordingStatus | null);
        let embeddingPending = false;
        if (last.recording?.processing) {
          setProgress({
            done: last.recording.processing.phrases_done,
            total: last.recording.processing.phrases_total,
          });
          // The voice vector (US-07) is computed AFTER the note is `ready`: while it is `pending`
          // polling continues, otherwise `processing.embedding` stays stale and the
          // "Make it my voice" item never unlocks.
          const emb = (last.recording.processing as { embedding?: string | null }).embedding;
          setEmbedding(emb ?? null);
          embeddingPending = shouldContinueAfterReady(emb ?? null);
        }

        controller.onResponse(received === 0);

        // Terminal status and nothing left to wait for — the chat is complete.
        if (isTerminalStatus(newStatus) && !embeddingPending) {
          controller.stop();
          return;
        }
        const delay = planNext(controller, newStatus, embeddingPending);
        if (delay !== null) timer = globalThis.setTimeout(run, delay);
      } catch (err) {
        if (cancelled) return;
        // The recording is gone (or belongs to somebody else): retrying will not help.
        if ((err as { status?: number })?.status === 404) {
          controller.stop();
          return;
        }
        if (err instanceof PollRateLimitedError || isRateLimited(err)) {
          controller.onRateLimited();
          const delay = planNext(controller, statusRef.current);
          if (delay !== null) timer = globalThis.setTimeout(run, delay);
          return;
        }
        // Network or other error: do not crash, retry after the base interval.
        if (idRef.current === recordingId) {
          timer = globalThis.setTimeout(run, controller.nextDelayMs());
        }
      }
    };

    const planNext = (
      c: PollController,
      s: string | null,
      embeddingPending = false,
    ): number | null => {
      if (document.visibilityState !== 'visible') return null;
      if (!c.shouldContinue(s) && !embeddingPending) {
        c.stop();
        return null;
      }
      return c.nextDelayMs();
    };

    const onVisibility = () => {
      if (document.visibilityState !== 'visible') {
        if (timer !== null) {
          globalThis.clearTimeout(timer);
          timer = null;
        }
        return;
      }
      // Back again — request immediately (ADR-005: reconcile instantly on return).
      if (timer !== null) {
        globalThis.clearTimeout(timer);
        timer = null;
      }
      if (idRef.current === recordingId) void run();
    };

    document.addEventListener('visibilitychange', onVisibility);

    // First run right away: the chat fills in on open, not 1.5 s later.
    timer = globalThis.setTimeout(run, 0);

    return () => {
      cancelled = true;
      controller.stop();
      if (timer !== null) globalThis.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [recordingId]);

  return {
    phrases,
    status,
    phrasesDone: progress.done,
    phrasesTotal: progress.total,
    isProcessing: isProcessingStatus(status),
    embedding,
  };
}

function mergePhrases(prev: Phrase[], incoming: Phrase[]): Phrase[] {
  if (incoming.length === 0) return prev;
  const bySeq = new Map<number, Phrase>();
  for (const p of prev) bySeq.set(p.seq, p);
  let changed = false;
  for (const p of incoming) {
    const existing = bySeq.get(p.seq);
    if (!existing) {
      bySeq.set(p.seq, p);
      changed = true;
    } else if (existing.state === 'partial' && p.revision !== existing.revision) {
      // A newer revision replaces the text in full — a growing note phrase, including its
      // last `partial` → `final` hand-over. A rendered `final` text is never rewritten.
      bySeq.set(p.seq, p);
      changed = true;
    }
  }
  if (!changed) return prev;
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
}

// Exported for tests.
export { mergePhrases };

function isRateLimited(err: unknown): boolean {
  return (
    (err as { status?: number })?.status === 429 ||
    (err as { errorCode?: string })?.errorCode === 'RATE_LIMITED'
  );
}
