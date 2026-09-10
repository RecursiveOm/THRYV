"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUp,
  Check,
  Compass,
  KeyRound,
  Leaf,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { Brand } from "./brand";

export function KeyForm({
  onConnect,
  isSettings = false,
}: {
  onConnect: (key: string) => void;
  isSettings?: boolean;
}) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function connect(event: FormEvent) {
    event.preventDefault();
    if (controller.current || !input.trim()) return;
    const key = input.trim();
    if (!/^[A-Za-z0-9_-]{8,256}$/.test(key)) {
      setError("Enter a valid DeepSeek API key, without spaces.");
      return;
    }
    const current = new AbortController();
    controller.current = current;
    setBusy(true);
    setError("");
    try {
      const result = await apiRequest<{ connected: boolean; provider: string }>(
        "/api/provider/connect",
        key,
        current.signal,
      );
      if (!result.connected || result.provider !== "deepseek")
        throw new Error("THRYV couldn’t verify the provider connection.");
      if (!current.signal.aborted) {
        setInput("");
        onConnect(key);
      }
    } catch (failure) {
      if (!current.signal.aborted)
        setError(
          failure instanceof Error
            ? failure.message
            : "Connection failed. Please try again.",
        );
    } finally {
      if (!current.signal.aborted) setBusy(false);
      controller.current = null;
    }
  }

  return (
    <form onSubmit={connect} className="key-form">
      <div className="provider-option">
        <div className="provider-icon">
          <Compass size={23} />
        </div>
        <div>
          <strong>DeepSeek</strong>
          <span>Use your own API key</span>
        </div>
        <span className="provider-check">
          <Check size={16} />
        </span>
      </div>
      <div className="field-label">
        <label htmlFor="provider-key">DeepSeek API key</label>
        <a
          href="https://platform.deepseek.com/api_keys"
          target="_blank"
          rel="noopener noreferrer"
        >
          Get a key <ArrowUp size={12} className="diagonal-arrow" />
        </a>
      </div>
      <div className="key-input-wrap">
        <KeyRound size={17} aria-hidden="true" />
        <input
          id="provider-key"
          type="password"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Paste your API key"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={256}
          required
          disabled={busy}
          aria-describedby="key-privacy key-error"
        />
      </div>
      <p className="field-hint">
        Your API usage is billed directly by DeepSeek.
      </p>
      {error && (
        <p id="key-error" className="error" role="alert">
          {error}
        </p>
      )}
      <button
        type="submit"
        className="primary-button"
        disabled={busy || !input.trim()}
      >
        {busy ? (
          <>
            <LoaderCircle className="spin" size={17} /> Verifying connection…
          </>
        ) : (
          <>
            {isSettings ? "Connect new key" : "Connect & get started"}
            <ArrowRight size={18} />
          </>
        )}
      </button>
      <div className="privacy-note" id="key-privacy">
        <ShieldCheck size={18} />
        <p>
          Your key stays in this tab’s memory and is sent securely through THRYV
          to DeepSeek. It isn’t saved by THRYV. Refreshing clears it.
        </p>
      </div>
    </form>
  );
}

export function Welcome({ onConnect }: { onConnect: (key: string) => void }) {
  return (
    <main className="welcome">
      <section className="welcome-story">
        <Brand />
        <div className="story-content">
          <span className="eyebrow">
            <span className="status-dot" /> A LITTLE SPACE FOR POSSIBILITY
          </span>
          <h1>
            More clarity.
            <br />
            More possibility.
            <br />
            <em>More you.</em>
          </h1>
          <p>
            A thought partner for your everyday.
            <br />
            Make sense of an idea, find the right words,
            <br className="desktop-break" /> or take your next step.
          </p>
          <div className="story-signature">
            <span className="signature-line" /> YOUR MIND, WITH ROOM TO GROW
          </div>
        </div>
        <div className="story-bottom">
          <span>Created by Omkar Zunje</span>
          <span>THRYV / V0</span>
        </div>
        <div className="orbit-art" aria-hidden="true">
          <div />
          <div />
          <div />
          <span />
        </div>
      </section>
      <section className="welcome-connect">
        <div className="setup-top">
          <span>YOUR SPACE. YOUR KEY.</span>
          <span className="setup-badge">
            <LockKeyhole size={13} /> Session only
          </span>
        </div>
        <div className="setup-card">
          <div className="intro-icon">
            <Leaf size={24} />
          </div>
          <span className="eyebrow">LET’S BEGIN</span>
          <h2>
            Make yourself
            <br />
            at home.
          </h2>
          <p className="setup-description">
            Connect DeepSeek to start a conversation.
            <br />
            No account. Just you and what’s next.
          </p>
          <KeyForm onConnect={onConnect} />
        </div>
        <div className="setup-bottom">
          <span>Created by Omkar Zunje</span>
          <span className="mini-mark">✳</span>
        </div>
      </section>
    </main>
  );
}
