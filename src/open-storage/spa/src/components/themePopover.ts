import type { Preference } from "../theme";

export const OPTIONS = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const satisfies ReadonlyArray<{ value: Preference; label: string }>;

/**
 * How long the surface widens before the panel arrives. `INTENT_DELAY` is the
 * whole lead-in from the first pointer frame; this is the part after it.
 */
export const MORPH_LEAD = 140;
/** Pointer over the trigger opens the popover only after this intent delay. */
export const INTENT_DELAY = 120;
/** Leaving the trigger and the popover closes it only after this grace. */
export const GRACE_DELAY = 400;

const VALUES = OPTIONS.map((option) => option.value);

export type OpenReason = "pointer" | "keyboard" | "focus";
export type RowEvent = { type: "next" } | { type: "previous" } | { type: "home" } | { type: "end" };

/** One move over the `radiogroup`. A closed list has no row to move. */
export function rowIndex(current: number, event: RowEvent, count = VALUES.length): number {
  if (count <= 0) return -1;
  const last = count - 1;
  if (current < 0) return event.type === "end" ? last : 0;
  const from = current;
  switch (event.type) {
    case "next":
      return from === last ? last : from + 1;
    case "previous":
      return from <= 0 ? 0 : from - 1;
    case "home":
      return 0;
    case "end":
      return last;
    default:
      return from;
  }
}

/**
 * Every state change goes through here, so the timers and the open flag are
 * written in one place and the component only renders what it is handed.
 */
export class PopoverController {
  private listeners = new Set<() => void>();
  private openState = false;
  private intent: ReturnType<typeof setTimeout> | null = null;
  private grace: ReturnType<typeof setTimeout> | null = null;

  readonly intentDelay: number;
  readonly graceDelay: number;

  constructor(options: { intentDelay?: number; graceDelay?: number } = {}) {
    this.intentDelay = options.intentDelay ?? INTENT_DELAY;
    this.graceDelay = options.graceDelay ?? GRACE_DELAY;
  }

  get open(): boolean {
    return this.openState;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /** Pointer enters the trigger: cancel a pending close, arm the intent delay. */
  pointerEnter(): void {
    this.clearGrace();
    if (this.openState || this.intent) return;
    this.intent = setTimeout(() => {
      this.intent = null;
      this.setOpen(true);
    }, this.intentDelay);
  }

  /** Pointer enters the popover: keep it open while it is there. */
  pointerStay(): void {
    if (this.intent) {
      clearTimeout(this.intent);
      this.intent = null;
    }
    this.clearGrace();
  }

  /** Pointer left the trigger or the popover: close after the grace. */
  pointerLeave(): void {
    if (this.intent) {
      clearTimeout(this.intent);
      this.intent = null;
    }
    if (!this.openState || this.grace) return;
    this.grace = setTimeout(() => {
      this.grace = null;
      this.setOpen(false);
    }, this.graceDelay);
  }

  /** `Escape`, an outside pointer press, `Tab` out and focus leaving the control. */
  closeNow(): void {
    this.clearIntent();
    this.clearGrace();
    this.setOpen(false);
  }

  requestOpen(): void {
    this.clearIntent();
    this.clearGrace();
    this.setOpen(true);
  }

  dispose(): void {
    this.clearIntent();
    this.clearGrace();
    this.listeners.clear();
  }

  private setOpen(next: boolean): void {
    if (this.openState === next) return;
    this.openState = next;
    for (const listener of [...this.listeners]) listener();
  }

  private clearIntent(): void {
    if (!this.intent) return;
    clearTimeout(this.intent);
    this.intent = null;
  }

  private clearGrace(): void {
    if (!this.grace) return;
    clearTimeout(this.grace);
    this.grace = null;
  }
}

/** The element and everything it wraps; a detached trigger matches itself. */
export function within(target: EventTarget | null, root: Element | null): boolean {
  return root !== null && target instanceof Node && root.contains(target);
}

/**
 * A pointer press outside every root closes at once. A change of window focus is
 * not a press. Browsers report the press target on `target` or, for some
 * synthetic events, only on `currentTarget`.
 */
export function isOutsidePress(
  event: PointerEvent | FocusEvent | MouseEvent,
  roots: ReadonlyArray<Element | null>,
  currentTarget?: EventTarget | null,
): boolean {
  if (event.type === "blur") return false;
  const target = event.target ?? currentTarget ?? null;
  return !roots.some((root) => within(target, root));
}
