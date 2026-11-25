/** Theme preference. The blocking script in `index.html` reads the same cookie before first paint. */

export const THEME_KEY = "theme.preference";

export type Preference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const THEME_APEX = "filenkov.store";
const THEME_DOMAIN = ".filenkov.store";

function sharedDomainAttribute(): string {
  const host = location.hostname;
  if (host === THEME_APEX || host.endsWith(THEME_DOMAIN)) return `; Domain=${THEME_DOMAIN}`;
  return "";
}

/** Session cookie: no Max-Age, no Expires. Secure only on https. */
function preferenceCookie(preference: Preference): string {
  const secure = location.protocol === "https:" ? "; Secure" : "";
  return `${THEME_KEY}=${preference}; Path=/; SameSite=Lax${secure}${sharedDomainAttribute()}`;
}

function storedPreference(): string | null {
  const prefix = `${THEME_KEY}=`;
  for (const part of document.cookie.split(";")) {
    const entry = part.trim();
    if (entry.startsWith(prefix)) return entry.slice(prefix.length);
  }
  return null;
}

export function readPreference(): Preference {
  try {
    const stored = storedPreference();
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // A blocked cookie stays silent and paints dark.
  }
  return "dark";
}

export function resolve(preference: string): ResolvedTheme {
  if (preference === "light" || preference === "dark") return preference;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function apply(preference: string): ResolvedTheme {
  const theme = resolve(preference);
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme === "light" ? "light" : "dark";
  const meta = document.querySelector("meta[name='color-scheme']");
  if (meta) meta.setAttribute("content", root.style.colorScheme);
  return theme;
}

/** Persist the choice, never the resolved theme. A write failure still paints. */
export function persist(preference: Preference): void {
  try {
    document.cookie = preferenceCookie(preference);
  } catch {
    // Silent, same as a blocked read.
  }
  apply(preference);
}

/** `system` keeps listening. A fixed light or dark choice ignores the query. */
export function watchSystem(onChange: () => void): () => void {
  const media = window.matchMedia("(prefers-color-scheme: light)");
  const onScheme = () => {
    if (readPreference() === "system") onChange();
  };
  media.addEventListener("change", onScheme);
  return () => media.removeEventListener("change", onScheme);
}
