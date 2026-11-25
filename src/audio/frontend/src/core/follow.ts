// Five-second auto-scroll rule (chat-and-player.md §«Auto-scroll»).
// Pure decision function: whether to scroll to the active phrase when it changes, and when
// to "catch up" after manual scrolling. A 5s delay, only while playing.

export const FOLLOW_IDLE_MS = 5000;
export const FOLLOW_TICK_MS = 200;
/** Smooth scroll onto the active phrase (chat-and-player.md). */
export const FOLLOW_SCROLL_MS = 300;
/**
 * While following, ignore sub-pixel noise and the 4px rise. Anything further
 * from the center of the chat above the player is scrolled back.
 */
export const FOLLOW_CENTER_DRIFT_PX = 16;

export interface FollowState {
  lastUserScroll: number; // monotonic time of the last manual scroll
  pendingFollow: boolean; // we "should" scroll, but the user scrolled recently
}

export const initialFollowState = (): FollowState => ({
  lastUserScroll: 0,
  pendingFollow: false,
});

export interface FollowDecision {
  /** Whether to scroll to the active phrase right now (smoothly). */
  scroll: boolean;
  /** Update `pendingFollow` to this flag. */
  pendingFollow: boolean;
}

/**
 * Decision when the active phrase changes at time `now`.
 *  - if ≥5s have passed since the manual scroll → scroll right away;
 *  - otherwise — remember that we "should" scroll (pendingFollow).
 */
export function onActiveChanged(
  state: FollowState,
  now: number,
): FollowDecision {
  if (now - state.lastUserScroll >= FOLLOW_IDLE_MS) {
    return { scroll: true, pendingFollow: false };
  }
  return { scroll: false, pendingFollow: true };
}

/**
 * Periodic tick (every 200ms, only while playing):
 * if we were waiting and ≥5s have passed — smoothly catch up with the active phrase and clear the flag.
 * While paused the tick is not called at all (see useAutoFollow).
 */
export function onFollowTick(state: FollowState, now: number): FollowDecision {
  if (!state.pendingFollow) return { scroll: false, pendingFollow: false };
  if (now - state.lastUserScroll >= FOLLOW_IDLE_MS) {
    return { scroll: true, pendingFollow: false };
  }
  return { scroll: false, pendingFollow: true };
}

/** Manual scroll: reset the timer and (optionally) clear the pending flag. */
export function onUserScroll(state: FollowState, now: number): FollowState {
  return { lastUserScroll: now, pendingFollow: state.pendingFollow };
}

/**
 * Room above and below the phrase list so the first and last tile can sit on the
 * center of the visible band (the scrollport minus the player covering its bottom).
 * Returns zeros when the scrollport has not been laid out yet.
 */
export function centerPads(
  clientHeight: number,
  occludedBottom: number,
): { top: number; bottom: number } {
  if (clientHeight <= 0) return { top: 0, bottom: 0 };
  const occluded = Math.min(Math.max(0, occludedBottom), clientHeight);
  const visible = clientHeight - occluded;
  return {
    top: Math.round(visible / 2),
    bottom: Math.round((clientHeight + occluded) / 2),
  };
}

/**
 * Scroll offset that places `elementCenter` (px from the top of the scroll content)
 * on the center of the visible band. Clamped to the scroll range.
 */
export function scrollTopForVisualCenter(
  elementCenter: number,
  clientHeight: number,
  occludedBottom: number,
  scrollHeight: number,
): number {
  const occluded = Math.min(Math.max(0, occludedBottom), Math.max(0, clientHeight));
  const visible = Math.max(0, clientHeight - occluded);
  const raw = elementCenter - visible / 2;
  const maxScroll = Math.max(0, scrollHeight - clientHeight);
  return Math.min(maxScroll, Math.max(0, raw));
}

/**
 * Signed distance (px) from the element's center to the center of the visible band.
 * Positive means the element sits below that center.
 */
export function visualCenterDrift(
  elementTop: number,
  elementHeight: number,
  containerTop: number,
  clientHeight: number,
  occludedBottom: number,
): number {
  const occluded = Math.min(Math.max(0, occludedBottom), Math.max(0, clientHeight));
  const visible = Math.max(0, clientHeight - occluded);
  const visualCenter = containerTop + visible / 2;
  const elementCenter = elementTop + elementHeight / 2;
  return elementCenter - visualCenter;
}

/**
 * While playing and the user has left the list alone for 5s: catch up an owed
 * follow, or pull the active phrase back when it has left the center.
 */
export function shouldRecenter(
  state: FollowState,
  now: number,
  driftPx: number,
): boolean {
  if (now - state.lastUserScroll < FOLLOW_IDLE_MS) return false;
  if (state.pendingFollow) return true;
  return Math.abs(driftPx) > FOLLOW_CENTER_DRIFT_PX;
}

/**
 * Active phrase by playhead: `start_ms ≤ playhead < end_ms`.
 * Index-based lookup, not a scan per frame; returns null in pauses between phrases.
 */
export function activePhraseIndex<T extends { start_ms: number; end_ms: number }>(
  phrases: readonly T[],
  playheadMs: number,
  hint = 0,
): number | null {
  if (phrases.length === 0) return null;

  // Fast path: the hint (previous index) often matches.
  if (hint >= 0 && hint < phrases.length) {
    const p = phrases[hint];
    if (p.start_ms <= playheadMs && playheadMs < p.end_ms) return hint;
  }

  // Binary search by start_ms for the first candidate.
  let lo = 0;
  let hi = phrases.length - 1;
  let cand = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (phrases[mid].start_ms <= playheadMs) {
      cand = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  if (cand < 0) return null;
  const p = phrases[cand];
  if (p.start_ms <= playheadMs && playheadMs < p.end_ms) return cand;

  // We may have landed on the end of a phrase after merging — check the neighbour just above, rarely.
  return null;
}
