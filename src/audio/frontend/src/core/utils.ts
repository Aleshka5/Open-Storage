// Utilities: isolating `prefers-reduced-motion` and localStorage-backed settings.

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** `scrollIntoView` that respects reduced-motion (instant, not smooth). */
export interface ScrollOptions {
  block?: ScrollLogicalPosition;
  inline?: ScrollLogicalPosition;
}

export function scrollTo(element: HTMLElement, opts: ScrollOptions = {}): void {
  const behavior: ScrollBehavior = prefersReducedMotion() ? 'auto' : 'smooth';
  element.scrollIntoView({
    behavior,
    block: opts.block ?? 'center',
    inline: opts.inline ?? 'nearest',
  });
}

// ---- localStorage (remembers sidebar collapse and player speed) ----

export function readBool(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === null) return fallback;
    return v === '1';
  } catch {
    return fallback;
  }
}

export function writeBool(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, value ? '1' : '0');
  } catch {
    /* private mode — skip silently */
  }
}

export function readSpeed(fallback: number): number {
  try {
    const v = localStorage.getItem('player.speed');
    const n = v === null ? NaN : Number(v);
    return Number.isFinite(n) ? n : fallback;
  } catch {
    return fallback;
  }
}

export function writeSpeed(value: number): void {
  try {
    localStorage.setItem('player.speed', String(value));
  } catch {
    /* private mode — skip silently */
  }
}
