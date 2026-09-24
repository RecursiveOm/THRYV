"use client";
import { useEffect, useSyncExternalStore } from "react";

const key = "thryv-theme";
let temporary: string | null = null;
function preference() {
  if (temporary) return temporary;
  try {
    const value = localStorage.getItem(key);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}
function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener("thryv-theme", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("thryv-theme", listener);
  };
}
export function ThemeRoot() {
  const mode = useSyncExternalStore(subscribe, preference, () => "system");
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        mode === "system" ? (media.matches ? "dark" : "light") : mode;
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode]);
  return null;
}
export function Appearance() {
  const mode = useSyncExternalStore(subscribe, preference, () => "system");
  return (
    <fieldset className="theme-options">
      <legend>Theme</legend>
      {(["light", "dark", "system"] as const).map((value) => (
        <label key={value}>
          <input
            type="radio"
            name="theme"
            value={value}
            checked={mode === value}
            onChange={() => {
              try {
                localStorage.setItem(key, value);
                temporary = null;
              } catch {
                temporary = value;
              }
              window.dispatchEvent(new Event("thryv-theme"));
            }}
          />
          <span className={`theme-preview ${value}`} aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          {value[0].toUpperCase() + value.slice(1)}
        </label>
      ))}
    </fieldset>
  );
}
