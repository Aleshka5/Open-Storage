/** Dev-only harness for the theme control: mounts `ThemeControl` alone so a real browser can drive it. */
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { ThemeControl } from "./components/ThemeControl";
import { apply, readPreference, type Preference } from "./theme";

function Harness() {
  const [preference, setPreference] = useState<Preference>(() => readPreference());
  apply(preference);
  return (
    <ThemeControl
      preference={preference}
      onChange={(next) => {
        localStorage.setItem("theme.preference", next);
        apply(next);
        setPreference(next);
      }}
    />
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
