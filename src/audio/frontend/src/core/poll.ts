// Growing-chat polling controller (ADR-005, chat-and-player.md §«Growing chat»).
// Pure timing logic; the network call is injected for testability.

export const POLL_INTERVAL_MS = 1500;
export const POLL_BACKOFF_MS = 6000;
export const EMPTY_BACKOFF_THRESHOLD = 10; // consecutive empty responses > 10 → backoff

export interface PollResult {
  status: string | null;
  // An empty response (0 items) is returned too — for backoff accounting.
  empty: boolean;
}

export type PollFetcher = (afterSeq: number) => Promise<PollResult>;

export interface PollControllerOptions {
  /** The recording status known to the client before the call. */
  getStatus(): string | null;
  isTabVisible(): boolean;
  setTimeout(cb: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  /** Throws a special error with `status === 429` (see RateLimited). */
  fetch: PollFetcher;
  now(): number;
}

export class PollRateLimitedError extends Error {
  constructor() {
    super('429');
    this.name = 'PollRateLimitedError';
  }
}

export type PollLoopState =
  | { kind: 'paused-hidden' }
  | { kind: 'active' }
  | { kind: 'stopped'; reason: 'ready' | 'failed' };

/**
 * Polling interval machine. Returns the next state after one "tick".
 *  - 1.5s while diarizing|transcribing;
 *  - 429 → doubles the interval up to 6s;
 *  - >10 consecutive empty responses → 6s;
 *  - tab hidden → pause (no new tick is scheduled);
 *  - status ready/failed → stop.
 *
 * The public API uses `nextDelayMs()` and `onResponse()`.
 */
export class PollController {
  readonly opts: PollControllerOptions;
  private delayMs = POLL_INTERVAL_MS;
  private consecutiveEmpty = 0;
  private stopped = false;

  constructor(opts: PollControllerOptions) {
    this.opts = opts;
  }

  /** Interval until the next poll, accounting for backoff. */
  nextDelayMs(): number {
    return this.delayMs;
  }

  /** Whether polling should continue after the latest response. */
  shouldContinue(status: string | null): boolean {
    if (status === 'ready' || status === 'failed') return false;
    return true;
  }

  /** Record the response result: updates the backoff and the empty-response counter. */
  onResponse(wasEmpty: boolean): void {
    if (wasEmpty) {
      this.consecutiveEmpty += 1;
      if (this.consecutiveEmpty > EMPTY_BACKOFF_THRESHOLD) {
        this.delayMs = POLL_BACKOFF_MS;
      }
    } else {
      this.consecutiveEmpty = 0;
      this.delayMs = POLL_INTERVAL_MS;
    }
  }

  /** Record a 429: the interval grows to the 6s maximum. */
  onRateLimited(): void {
    this.delayMs = POLL_BACKOFF_MS;
  }

  stop(): void {
    this.stopped = true;
  }

  get isStopped(): boolean {
    return this.stopped;
  }
}

/**
 * One polling "turn": which interval to schedule next and whether to continue.
 * Returns `delayMs | null` (null = do not schedule; polling is stopped or paused).
 */
export function planNextTick(
  controller: PollController,
  status: string | null,
  visible: boolean,
): number | null {
  if (!visible) return null; // hidden tab — pause
  if (!controller.shouldContinue(status)) {
    controller.stop();
    return null; // ready/failed — stop
  }
  return controller.nextDelayMs();
}
