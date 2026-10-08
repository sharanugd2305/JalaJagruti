import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { PALETTES } from "./theme.js";

// Centralised light/dark theme. Dark is the default; the choice is saved in
// localStorage under "jalajagruti-theme" and applied as <html data-theme="...">.
export const THEME_KEY = "jalajagruti-theme";
const ThemeContext = createContext(null);

function readStored() {
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "dark";
  } catch {
    return "dark";
  }
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readStored);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try { window.localStorage.setItem(THEME_KEY, theme); } catch { /* storage unavailable */ }
  }, [theme]);
  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  const value = useMemo(() => ({ theme, setTheme, toggle, palette: PALETTES[theme] }), [theme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}

export const usePalette = () => useTheme().palette;
