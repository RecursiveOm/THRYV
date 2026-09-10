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
import { accountRequest } from "@/lib/api";
import { Brand } from "./brand";

export function KeyForm({
  onConnect,
  isSettings = false,
}: {
  onConnect: () => void;
  isSettings?: boolean;
}) {
  const [input, setInput] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function connect(event: FormEvent) {
    event.preventDefault();
    if (controller.current || !input.trim() || !consent) return;
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
      const result = await accountRequest<{
        connected: boolean;
        provider: string;
      }>(
        "/api/account/provider",
        "POST",
        { api_key: key, consent_to_store: consent },
        current.signal,
      );
      if (!result.connected || result.provider !== "deepseek")
        throw new Error("THRYV couldn’t verify the provider connection.");
      if (!current.signal.aborted) {
        setInput("");
        onConnect();
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
      <label className="consent-label">
        <input
          type="checkbox"
          checked={consent}
          onChange={(event) => setConsent(event.target.checked)}
          disabled={busy}
          required
        />{" "}
        Save my key encrypted on this THRYV server for future sessions.
      </label>
      {error && (
        <p id="key-error" className="error" role="alert">
          {error}
        </p>
      )}
      <button
        type="submit"
        className="primary-button"
        disabled={busy || !input.trim() || !consent}
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
          Your key is encrypted at rest and sent to DeepSeek through THRYV. The
          server decrypts it only to make provider requests. Remove it in
          settings.
        </p>
      </div>
    </form>
  );
}

export function Welcome({ onConnect }: { onConnect: () => void }) {
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
          <span>THRYV / V1</span>
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
            <LockKeyhole size={13} /> Encrypted storage
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
            Your connection stays available after reload.
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
