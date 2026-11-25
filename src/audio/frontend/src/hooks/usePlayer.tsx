// Player hook: one `<audio>` element per open recording (chat-and-player.md).
// Holds the playhead, playing, speed (localStorage), drag-timeline and Range seeking.

import { useEffect, useRef, useState, type RefObject } from 'react';
import { PLAYBACK_SPEEDS } from './playback';
import { readSpeed, writeSpeed } from '../core/utils';

export interface PlayerApi {
  audioRef: RefObject<HTMLAudioElement>;
  playing: boolean;
  playheadMs: number; // current position (ms)
  durationMs: number;
  speed: number;
  toggle: () => void;
  seek: (ms: number) => void;
  setSpeed: (s: number) => void;
}

export function usePlayer(
  recordingId: string | null,
  canPlay: boolean,
  /** `recording.duration_ms` — the fallback when the browser reports no duration. */
  fallbackDurationMs = 0,
): PlayerApi {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [durationMs, setDurationMs] = useState(fallbackDurationMs);
  const [speed, setSpeedState] = useState<number>(() => readSpeed(1));

  const playingRef = useRef(false);
  playingRef.current = playing;

  // Reset when the recording changes: stop the current sound and zero the position.
  useEffect(() => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.currentTime = 0;
    }
    setPlaying(false);
    setPlayheadMs(0);
    setDurationMs(fallbackDurationMs);
  }, [recordingId, fallbackDurationMs]);

  // Apply the speed to the element on every change.
  useEffect(() => {
    const a = audioRef.current;
    if (a) a.playbackRate = speed;
    writeSpeed(speed);
  }, [speed, recordingId]);

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      void a.play().catch(() => setPlaying(false));
    } else {
      a.pause();
    }
  };

  const seek = (ms: number) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = ms / 1000; // the browser will issue a Range request if needed
    setPlayheadMs(ms);
  };

  const setSpeed = (s: number) => {
    if (!PLAYBACK_SPEEDS.includes(s as (typeof PLAYBACK_SPEEDS)[number])) return;
    setSpeedState(s);
  };

  // Audio event listeners.
  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;

    const onTime = () => setPlayheadMs(Math.round(a.currentTime * 1000));
    // A WebM from MediaRecorder (a voice note) has no duration in its header: the browser
    // reports `Infinity` and the timeline would read `Infinity:NaN`. Fall back to the
    // duration the server computed from the samples.
    const onDur = () => {
      if (Number.isFinite(a.duration) && a.duration > 0) {
        setDurationMs(Math.round(a.duration * 1000));
      } else if (fallbackDurationMs > 0) {
        setDurationMs(fallbackDurationMs);
      }
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => {
      setPlaying(false);
      if (a.duration) setPlayheadMs(Math.round(a.duration * 1000));
    };

    a.addEventListener('timeupdate', onTime);
    a.addEventListener('durationchange', onDur);
    a.addEventListener('loadedmetadata', onDur);
    a.addEventListener('play', onPlay);
    a.addEventListener('pause', onPause);
    a.addEventListener('ended', onEnded);
    return () => {
      a.removeEventListener('timeupdate', onTime);
      a.removeEventListener('durationchange', onDur);
      a.removeEventListener('loadedmetadata', onDur);
      a.removeEventListener('play', onPlay);
      a.removeEventListener('pause', onPause);
      a.removeEventListener('ended', onEnded);
    };
  }, [recordingId, canPlay, fallbackDurationMs]);

  return {
    audioRef,
    playing,
    playheadMs,
    durationMs,
    speed,
    toggle,
    seek,
    setSpeed,
  };
}
