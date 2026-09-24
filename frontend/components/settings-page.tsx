"use client";
import { useEffect, useRef, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
export const sections = [
  "General",
  "Voice",
  "Appearance",
  "Provider",
  "Devices",
  "Workspaces",
  "Connected Apps",
  "Memory",
  "Privacy",
  "Account",
] as const;
export type SettingsSection = (typeof sections)[number];
export function SettingsPage({
  section,
  onSection,
  onClose,
  children,
}: {
  section: SettingsSection;
  onSection: (section: SettingsSection) => void;
  onClose: () => void;
  children: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [section]);
  return (
    <main className="settings-page" aria-label="Settings">
      <header className="settings-header">
        <button className="text-button" onClick={onClose}>
          <ArrowLeft size={18} /> Back to chat
        </button>
        <h1>Settings</h1>
      </header>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          {sections.map((name) => (
            <button
              key={name}
              aria-current={section === name ? "page" : undefined}
              onClick={() => onSection(name)}
            >
              {name}
            </button>
          ))}
        </nav>
        <div
          className="settings-content"
          aria-labelledby="settings-section-title"
          key={section}
        >
          <h2 ref={heading} tabIndex={-1} id="settings-section-title">
            {section}
          </h2>
          {children}
        </div>
      </div>
    </main>
  );
}
