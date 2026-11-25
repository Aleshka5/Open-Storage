import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePlayer } from '../hooks/usePlayer';
import { PLAYBACK_SPEEDS } from '../hooks/playback';

describe('usePlayer: seeking (Range)', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('seek() sets currentTime and updates the playhead — the browser sends Range itself', () => {
    const { result } = renderHook(() => usePlayer('rec-1', true));

    // Replace the DOM element with a mock that tracks currentTime.
    let currentTime = 0;
    const fake = {
      paused: true,
      currentTime: 0,
      playbackRate: 1,
      duration: 100,
      play: () => Promise.resolve(),
      pause: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
    } as unknown as HTMLAudioElement;

    Object.defineProperty(fake, 'currentTime', {
      configurable: true,
      get: () => currentTime,
      set: (v: number) => {
        currentTime = v;
      },
    });

    act(() => {
      // The readonly current cannot be assigned — use seek() directly,
      // which writes to the element's currentTime. For the check we mock it globally.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (result.current.audioRef as any).current = fake;
    });

    act(() => {
      result.current.seek(90_000); // 90s — not yet downloaded part
    });

    expect(currentTime).toBeCloseTo(90, 5);
    expect(result.current.playheadMs).toBe(90_000);
  });

  it('speed is validated and persisted', () => {
    const { result } = renderHook(() => usePlayer('rec-1', true));
    act(() => {
      result.current.setSpeed(2);
    });
    expect(result.current.speed).toBe(2);
    expect(localStorage.getItem('player.speed')).toBe('2');

    // An invalid value is ignored.
    act(() => {
      result.current.setSpeed(7);
    });
    expect(result.current.speed).toBe(2);
  });

  it('the speed set matches the spec', () => {
    expect([...PLAYBACK_SPEEDS]).toEqual([0.25, 0.5, 1, 1.5, 2, 3]);
  });
});
