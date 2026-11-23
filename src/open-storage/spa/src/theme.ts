/** Theme preference. The blocking script in `index.html` is the same contract, run before first paint. */

export const THEME_KEY = "theme.preference";

export type Preference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export function readPreference(): Preference {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // A private-mode or blocked store stays silent and paints dark.
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
    localStorage.setItem(THEME_KEY, preference);
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
