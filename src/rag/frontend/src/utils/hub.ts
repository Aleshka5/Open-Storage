const HUB_ORIGIN = "https://filenkov.store";

export function signInHref(returnTo?: string): string {
  const target = returnTo ?? window.location.href;
  return `${HUB_ORIGIN}/auth?return_to=${encodeURIComponent(target)}`;
}

export function hubHref(): string {
  return HUB_ORIGIN;
}
