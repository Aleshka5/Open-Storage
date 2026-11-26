export const THEME_KEY = "theme.preference";

export type Preference = "light" | "dark" | "system";

function sharedDomain(): string {
  const host = location.hostname;
  if (host === "filenkov.store" || host.endsWith(".filenkov.store")) return "; Domain=.filenkov.store";
  return "";
}

function stored(): string | null {
  const prefix = `${THEME_KEY}=`;
  for (const part of document.cookie.split(";")) {
    const entry = part.trim();
    if (entry.startsWith(prefix)) return entry.slice(prefix.length);
  }
  return null;
}

export function readPreference(): Preference {
  try {
    const value = stored();
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    // A blocked cookie paints dark.
  }
  return "dark";
}

export function resolve(preference: string): "light" | "dark" {
  if (preference === "light" || preference === "dark") return preference;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function apply(preference: string): void {
  const theme = resolve(preference);
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document.querySelector("meta[name='color-scheme']")?.setAttribute("content", theme);
}

export function persist(preference: Preference): void {
  try {
    const secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${THEME_KEY}=${preference}; Path=/; SameSite=Lax${secure}${sharedDomain()}`;
  } catch {
    // The page still paints.
  }
  apply(preference);
}
