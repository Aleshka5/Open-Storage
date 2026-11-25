import { describe, it, expect } from 'vitest';
import {
  FOLLOW_CENTER_DRIFT_PX,
  FOLLOW_IDLE_MS,
  activePhraseIndex,
  centerPads,
  initialFollowState,
  onActiveChanged,
  onFollowTick,
  onUserScroll,
  scrollTopForVisualCenter,
  shouldRecenter,
  visualCenterDrift,
} from './follow';

describe('activePhraseIndex', () => {
  const phrases = [
    { start_ms: 0, end_ms: 5000 },
    { start_ms: 5000, end_ms: 12000 },
    { start_ms: 12000, end_ms: 20000 },
  ];

  it('finds the phrase by playhead (start_ms ≤ playhead < end_ms)', () => {
    expect(activePhraseIndex(phrases, 0)).toBe(0);
    expect(activePhraseIndex(phrases, 4999)).toBe(0);
    expect(activePhraseIndex(phrases, 5000)).toBe(1);
    expect(activePhraseIndex(phrases, 11999)).toBe(1);
    expect(activePhraseIndex(phrases, 12000)).toBe(2);
    expect(activePhraseIndex(phrases, 19999)).toBe(2);
  });

  it('returns null in pauses between phrases (end_ms boundary)', () => {
    // with full continuity there are no pauses, but the last end_ms is the end
    expect(activePhraseIndex(phrases, 20000)).toBe(null);
  });

  it('returns null for an empty list', () => {
    expect(activePhraseIndex([], 100)).toBe(null);
  });

  it('a pause between phrases → null (gap in the timeline)', () => {
    const gapped = [
      { start_ms: 0, end_ms: 5000 },
      { start_ms: 8000, end_ms: 10000 },
    ];
    expect(activePhraseIndex(gapped, 6500)).toBe(null); // pause
    expect(activePhraseIndex(gapped, 8500)).toBe(1);
  });
});

describe('five-second rule', () => {
  it.each([
    // [now - lastUserScroll, expected scroll]
    [4999, false], // <5s — do not scroll, remember that we "should"
    [5000, true], // ≥5s — scroll right away
    [20000, true],
  ])(
    'phrase change with elapsed=%dms → scroll=%s',
    (elapsed, expectedScroll) => {
      const state = initialFollowState();
      const now = 10_000;
      state.lastUserScroll = now - elapsed;
      const d = onActiveChanged(state, now);
      expect(d.scroll).toBe(expectedScroll);
      expect(d.pendingFollow).toBe(!expectedScroll);
    },
  );

  it('the tick catches up after 5s, only if we "should"', () => {
    const state = initialFollowState();
    const base = 10_000;
    state.lastUserScroll = base;
    state.pendingFollow = true;

    // 5s have not passed yet.
    let d = onFollowTick(state, base + FOLLOW_IDLE_MS - 1);
    expect(d.scroll).toBe(false);
    expect(d.pendingFollow).toBe(true);

    // ≥5s have passed.
    d = onFollowTick(state, base + FOLLOW_IDLE_MS);
    expect(d.scroll).toBe(true);
    expect(d.pendingFollow).toBe(false);
  });

  it('the tick does not fire when nothing is pending', () => {
    const state = initialFollowState();
    state.pendingFollow = false;
    const d = onFollowTick(state, 1_000_000);
    expect(d.scroll).toBe(false);
  });
});

describe('visual center above the player', () => {
  const clientHeight = 500;
  const occluded = 88;
  const visible = clientHeight - occluded;

  it('pads let a phrase at either end reach the center of the visible band', () => {
    const pads = centerPads(clientHeight, occluded);
    expect(pads).toEqual({ top: visible / 2, bottom: (clientHeight + occluded) / 2 });

    const firstTop = scrollTopForVisualCenter(pads.top, clientHeight, occluded, 10_000);
    expect(pads.top - firstTop).toBeCloseTo(visible / 2, 5);

    const lastCenter = 2000;
    const scrollHeight = lastCenter + pads.bottom;
    const lastTop = scrollTopForVisualCenter(
      lastCenter,
      clientHeight,
      occluded,
      scrollHeight,
    );
    expect(lastCenter - lastTop).toBeCloseTo(visible / 2, 5);
  });

  it('returns no pads before the scrollport has a height', () => {
    expect(centerPads(0, 88)).toEqual({ top: 0, bottom: 0 });
  });

  it('clamps when there is no room to scroll', () => {
    expect(scrollTopForVisualCenter(100, 400, 80, 400)).toBe(0);
  });

  it('measures drift against the visible center, not the full scrollport', () => {
    // Container top 0, height 500, player covers 88. Visible center is at 206.
    // Element top 180, height 52 → center 206. Drift 0.
    expect(visualCenterDrift(180, 52, 0, 500, 88)).toBe(0);
    // Same element centered in the full scrollport (250) sits 44px too low.
    expect(visualCenterDrift(224, 52, 0, 500, 88)).toBeCloseTo(44, 5);
  });
});

describe('shouldRecenter', () => {
  const now = 10_000;

  it('holds the phrase on center once the user has been idle for 5s', () => {
    const state = initialFollowState();
    state.lastUserScroll = now - FOLLOW_IDLE_MS;
    expect(shouldRecenter(state, now, FOLLOW_CENTER_DRIFT_PX + 1)).toBe(true);
  });

  it('ignores a few pixels of drift (the rise, sub-pixel layout)', () => {
    const state = initialFollowState();
    state.lastUserScroll = 0;
    expect(shouldRecenter(state, now, FOLLOW_CENTER_DRIFT_PX)).toBe(false);
  });

  it('does not pull the list back during the 5s after a manual scroll', () => {
    const state = initialFollowState();
    state.lastUserScroll = now - (FOLLOW_IDLE_MS - 1);
    state.pendingFollow = true;
    expect(shouldRecenter(state, now, 400)).toBe(false);
  });

  it('catches up an owed follow once the 5s have passed, even on center', () => {
    const state = initialFollowState();
    state.lastUserScroll = now - FOLLOW_IDLE_MS;
    state.pendingFollow = true;
    expect(shouldRecenter(state, now, 0)).toBe(true);
  });
});

describe('onUserScroll', () => {
  it('resets lastUserScroll and keeps pendingFollow', () => {
    const state = { lastUserScroll: 100, pendingFollow: true };
    const next = onUserScroll(state, 5000);
    expect(next.lastUserScroll).toBe(5000);
    expect(next.pendingFollow).toBe(true);
  });
});
