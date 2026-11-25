// Player: Play/Pause, draggable timeline, speed. Range seeking goes through `<audio>`
// (the browser sends `Range` to `/audio` itself). Fixed at the bottom of the chat. The
// `<audio>` element itself is rendered in App (AudioElement) via player.audioRef — only controls here.

import { PLAYBACK_SPEEDS } from '../hooks/playback';
import { formatTime } from '../strings';

export interface PlayerProps {
  playing: boolean;
  playheadMs: number;
  durationMs: number;
  speed: number;
  disabled: boolean;
  onToggle: () => void;
  onSeek: (ms: number) => void;
  onSpeedChange: (s: number) => void;
}

export function Player({
  playing,
  playheadMs,
  durationMs,
  speed,
  disabled,
  onToggle,
  onSeek,
  onSpeedChange,
}: PlayerProps) {
  const onRange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = Number(e.target.value);
    if (Number.isFinite(t)) onSeek(t);
  };

  return (
    <div className="player">
      <button
        type="button"
        className="player-btn"
        onClick={onToggle}
        disabled={disabled}
        aria-label={playing ? 'Pause' : 'Play'}
      >
        {playing ? '❚❚' : '▶'}
      </button>

      <div className="player-body">
        <input
          type="range"
          className="player-timeline"
          min={0}
          max={durationMs > 0 ? durationMs : 1}
          step={1}
          value={Math.round(playheadMs)}
          onChange={onRange}
          disabled={disabled}
          aria-label="Timeline"
        />
        <div className="player-times">
          <span>{formatTime(playheadMs)}</span>
          <span>{formatTime(durationMs)}</span>
        </div>
      </div>

      <label className="player-speed">
        <span className="sr-only">Speed</span>
        <select
          value={speed}
          disabled={disabled}
          onChange={(e) => onSpeedChange(Number(e.target.value))}
        >
          {PLAYBACK_SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
