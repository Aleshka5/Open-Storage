// Auto-scroll-to-active-phrase hook: the five-second rule (follow.ts).
// The active tile is held on the center of the chat above the player while
// playback is following, then the next tile is brought to that same center.

import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react';
import {
  FOLLOW_IDLE_MS,
  FOLLOW_SCROLL_MS,
  FOLLOW_TICK_MS,
  activePhraseIndex,
  centerPads,
  initialFollowState,
  onActiveChanged,
  scrollTopForVisualCenter,
  shouldRecenter,
  visualCenterDrift,
  onUserScroll,
} from '../core/follow';
import { prefersReducedMotion } from '../core/utils';

export interface AutoFollowBind {
  scrollRef: RefObject<HTMLDivElement>;
  /** The current active seq (for aria-current on the tile). */
  activeSeq: number | null;
  /** Call from the container's onScroll (non-programmatic scrolling). */
  handleUserScroll: () => void;
}

interface TrackedPhrase {
  seq: number;
  start_ms: number;
  end_ms: number;
}

/** How much of the scrollport's bottom the player covers, in px. */
export function occludedByPlayer(container: HTMLElement): number {
  const player = container.closest('.stage')?.querySelector('.player');
  if (!(player instanceof HTMLElement)) return 0;
  const c = container.getBoundingClientRect();
  const p = player.getBoundingClientRect();
  if (p.top >= c.bottom || p.bottom <= c.top) return 0;
  const covered = c.bottom - p.top;
  return Math.max(0, Math.min(covered, c.height));
}

/**
 * Tracks the active phrase (start_ms ≤ playhead < end_ms) and keeps it on the
 * center of the chat above the player. Manual scrolling turns following off;
 * after 5s of idle, and only while playing, the list catches up. On pause it stays put.
 */
export function useAutoFollow(
  phrases: ReadonlyArray<TrackedPhrase>,
  playheadMs: number,
  playing: boolean,
): AutoFollowBind {
  const scrollRef = useRef<HTMLDivElement>(null);

  const stateRef = useRef(initialFollowState());
  const lastActiveSeqRef = useRef<number | null>(null);
  // Programmatic-scroll flag: our own calls do not count as "manual".
  const programmaticRef = useRef(false);
  const scrollGen = useRef(0);
  const rafRef = useRef(0);
  const alignedRef = useRef(false);

  // Hint for the fast index lookup.
  const hint = Math.max(
    0,
    phrases.findIndex((p) => p.seq === lastActiveSeqRef.current),
  );
  const activeIdx = activePhraseIndex(phrases, playheadMs, hint);
  const activeSeq = activeIdx === null ? null : phrases[activeIdx].seq;

  const cancelScroll = () => {
    scrollGen.current += 1;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = 0;
    programmaticRef.current = false;
  };

  const desiredScrollTop = (container: HTMLElement, el: HTMLElement): number => {
    const cRect = container.getBoundingClientRect();
    const eRect = el.getBoundingClientRect();
    const elementCenter =
      eRect.top - cRect.top + container.scrollTop + eRect.height / 2;
    return scrollTopForVisualCenter(
      elementCenter,
      container.clientHeight,
      occludedByPlayer(container),
      container.scrollHeight,
    );
  };

  const scrollToActiveRef = useRef<() => void>(() => {});
  scrollToActiveRef.current = () => {
    const container = scrollRef.current;
    const seq = lastActiveSeqRef.current;
    if (!container || seq == null) return;
    const el = container.querySelector<HTMLElement>(`[data-seq="${seq}"]`);
    if (!el) return;

    const top = desiredScrollTop(container, el);
    const token = ++scrollGen.current;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    programmaticRef.current = true;

    const finish = () => {
      if (scrollGen.current !== token) return;
      programmaticRef.current = false;
      rafRef.current = 0;
    };

    if (prefersReducedMotion() || Math.abs(top - container.scrollTop) < 1) {
      container.scrollTop = top;
      finish();
      return;
    }

    const from = container.scrollTop;
    const start = performance.now();
    const step = (now: number) => {
      if (scrollGen.current !== token) return;
      const current = container.querySelector<HTMLElement>(`[data-seq="${seq}"]`);
      if (!current) {
        finish();
        return;
      }
      // Remeasure so a resize mid-scroll still lands on the visible center.
      const desired = desiredScrollTop(container, current);
      const t = Math.min(1, (now - start) / FOLLOW_SCROLL_MS);
      const eased = 1 - (1 - t) ** 3;
      container.scrollTop = from + (desired - from) * eased;
      if (t < 1) rafRef.current = requestAnimationFrame(step);
      else finish();
    };
    rafRef.current = requestAnimationFrame(step);
  };

  const readDriftRef = useRef<() => number | null>(() => null);
  readDriftRef.current = () => {
    const container = scrollRef.current;
    const seq = lastActiveSeqRef.current;
    if (!container || seq == null) return null;
    const el = container.querySelector<HTMLElement>(`[data-seq="${seq}"]`);
    if (!el) return null;
    const cRect = container.getBoundingClientRect();
    const eRect = el.getBoundingClientRect();
    return visualCenterDrift(
      eRect.top,
      eRect.height,
      cRect.top,
      container.clientHeight,
      occludedByPlayer(container),
    );
  };

  // Spacers so the first and last phrase can reach the center above the player.
  // The first layout scrolls the top spacer away, leaving the first phrase at the top.
  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    let prevTop = Number.NaN;
    let prevBottom = Number.NaN;

    const apply = () => {
      const pads = centerPads(container.clientHeight, occludedByPlayer(container));
      container.style.setProperty('--follow-pad-top', `${pads.top}px`);
      container.style.setProperty('--follow-pad-bottom', `${pads.bottom}px`);
      if (pads.top === prevTop && pads.bottom === prevBottom) return;
      const delta = Number.isNaN(prevTop) ? pads.top : pads.top - prevTop;
      prevTop = pads.top;
      prevBottom = pads.bottom;
      if (container.clientHeight <= 0 || delta === 0) return;
      // A running follow remeasures each frame and lands on the new center.
      if (rafRef.current) return;

      const token = ++scrollGen.current;
      programmaticRef.current = true;
      if (!alignedRef.current) {
        const paddingTop =
          Number.parseFloat(getComputedStyle(container).paddingTop) || 0;
        container.scrollTop = paddingTop + pads.top;
        alignedRef.current = true;
      } else {
        container.scrollTop += delta;
      }
      // Keep the flag through the scroll event this assignment fires.
      requestAnimationFrame(() => {
        if (scrollGen.current === token) programmaticRef.current = false;
      });
    };

    apply();
    if (typeof ResizeObserver !== 'function') return;
    const ro = new ResizeObserver(() => apply());
    ro.observe(container);
    const player = container.closest('.stage')?.querySelector('.player');
    if (player instanceof HTMLElement) ro.observe(player);
    return () => ro.disconnect();
  }, []);

  // Wheel and touch are user intent even while our animation is moving the list.
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const onIntent = () => {
      cancelScroll();
      stateRef.current = onUserScroll(stateRef.current, Date.now());
    };
    container.addEventListener('wheel', onIntent, { passive: true });
    container.addEventListener('touchmove', onIntent, { passive: true });
    return () => {
      container.removeEventListener('wheel', onIntent);
      container.removeEventListener('touchmove', onIntent);
    };
  }, []);

  // When the active phrase changes (playback crossing a boundary, or a seek).
  useEffect(() => {
    if (activeSeq === lastActiveSeqRef.current) return;
    lastActiveSeqRef.current = activeSeq;
    if (activeSeq === null) return;

    const decision = onActiveChanged(stateRef.current, Date.now());
    if (decision.scroll) scrollToActiveRef.current();
    stateRef.current.pendingFollow = decision.pendingFollow;
  }, [activeSeq]);

  // Playback started: the phrase may already be active, so hold it at the center.
  useEffect(() => {
    if (!playing || lastActiveSeqRef.current == null) return;
    const now = Date.now();
    if (now - stateRef.current.lastUserScroll >= FOLLOW_IDLE_MS) {
      scrollToActiveRef.current();
      stateRef.current.pendingFollow = false;
    } else {
      stateRef.current.pendingFollow = true;
    }
  }, [playing]);

  // Hold the active phrase on center while playing.
  useEffect(() => {
    if (!playing) return;
    const id = globalThis.setInterval(() => {
      if (programmaticRef.current) return;
      const drift = readDriftRef.current();
      if (drift == null) return;
      if (!shouldRecenter(stateRef.current, Date.now(), drift)) return;
      scrollToActiveRef.current();
      stateRef.current.pendingFollow = false;
    }, FOLLOW_TICK_MS);
    return () => globalThis.clearInterval(id);
  }, [playing]);

  const handleUserScroll = () => {
    if (programmaticRef.current) return;
    stateRef.current = onUserScroll(stateRef.current, Date.now());
  };

  return { scrollRef, activeSeq, handleUserScroll };
}

// Re-export for tests.
export { activePhraseIndex };
