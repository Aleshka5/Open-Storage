// Fixed mic button in the bottom-right corner (US-05).
// States: microphone → pulse (recording) → spinner (finalizing) → microphone.

import type { MicState } from '../voice-note/flow';

interface MicButtonProps {
  state: MicState;
  onToggle: () => void;
}

export function MicButton({ state, onToggle }: MicButtonProps) {
  return (
    <button
      type="button"
      className={`mic-button mic-button--${state}`}
      aria-label={state === 'recording' ? 'Stop recording' : 'Record a note'}
      title={state === 'recording' ? 'Stop' : 'Record a note'}
      onClick={onToggle}
      disabled={state === 'finalizing'}
    >
      {state === 'finalizing' && <span className="mic-button__spinner" aria-hidden="true" />}
      {state !== 'finalizing' && (
        <svg viewBox="0 0 24 24" aria-hidden="true" className="mic-button__icon">
          <rect x="9" y="2.5" width="6" height="10.5" rx="3" />
          <path d="M8.25 6.25h7.5M8.25 8.75h7.5" />
          <path d="M6.75 11.25a5.25 5.25 0 0 0 10.5 0" />
          <path d="M12 16.5V20.25M8.5 20.25h7" />
        </svg>
      )}
    </button>
  );
}
