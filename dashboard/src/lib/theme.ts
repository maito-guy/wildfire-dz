// Light / dark theme: the `.dark` class on <html>. The choice is kept in this browser; with no choice
// yet, the system setting decides. index.html applies it before React starts, so there is no flash.
import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "hareeq.theme";

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function initial(): Theme {
  return stored() ?? (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
  const toggle = () =>
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        // private window: the choice lasts for this page only
      }
      return next;
    });
  return [theme, toggle];
}
