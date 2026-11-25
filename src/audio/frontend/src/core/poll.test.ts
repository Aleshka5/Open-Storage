import { describe, it, expect } from 'vitest';
import {
  EMPTY_BACKOFF_THRESHOLD,
  POLL_BACKOFF_MS,
  POLL_INTERVAL_MS,
  PollController,
  planNextTick,
} from './poll';

function makeController() {
  return new PollController({
    getStatus: () => 'transcribing',
    isTabVisible: () => true,
    setTimeout: () => 0,
    clearTimeout: () => {},
    fetch: async () => ({ status: 'transcribing', empty: false }),
    now: () => Date.now(),
  });
}

describe('PollController: base interval', () => {
  it('starts at 1.5s while diarizing|transcribing', () => {
    const c = makeController();
    expect(c.nextDelayMs()).toBe(POLL_INTERVAL_MS);
  });

  it('keeps polling while the status is a processing one', () => {
    const c = makeController();
    expect(c.shouldContinue('transcribing')).toBe(true);
    expect(c.shouldContinue('diarizing')).toBe(true);
  });
});

describe('PollController: backoff on 429', () => {
  it('doubles the interval up to 6s after a 429', () => {
    const c = makeController();
    c.onRateLimited();
    expect(c.nextDelayMs()).toBe(POLL_BACKOFF_MS);
  });

  it('backoff resets after a non-empty response', () => {
    const c = makeController();
    c.onRateLimited();
    expect(c.nextDelayMs()).toBe(POLL_BACKOFF_MS);
    c.onResponse(false);
    expect(c.nextDelayMs()).toBe(POLL_INTERVAL_MS);
  });
});

describe('PollController: backoff on a run of empty responses', () => {
  it('switches to 6s after >N empty responses in a row', () => {
    const c = makeController();
    for (let i = 0; i <= EMPTY_BACKOFF_THRESHOLD; i++) {
      c.onResponse(true);
    }
    expect(c.nextDelayMs()).toBe(POLL_BACKOFF_MS);
  });

  it('does not go into backoff on a short run of empty responses', () => {
    const c = makeController();
    for (let i = 0; i < EMPTY_BACKOFF_THRESHOLD - 1; i++) {
      c.onResponse(true);
    }
    expect(c.nextDelayMs()).toBe(POLL_INTERVAL_MS);
  });
});

describe('planNextTick: stop on ready/failed', () => {
  it('stops polling on ready', () => {
    const c = makeController();
    expect(planNextTick(c, 'ready', true)).toBe(null);
    expect(c.isStopped).toBe(true);
  });

  it('stops polling on failed', () => {
    const c = makeController();
    expect(planNextTick(c, 'failed', true)).toBe(null);
    expect(c.isStopped).toBe(true);
  });

  it('pauses while the tab is hidden (schedules no tick)', () => {
    const c = makeController();
    expect(planNextTick(c, 'transcribing', false)).toBe(null);
    expect(c.isStopped).toBe(false);
  });

  it('schedules the next tick while processing with the tab visible', () => {
    const c = makeController();
    expect(planNextTick(c, 'transcribing', true)).toBe(POLL_INTERVAL_MS);
  });
});
