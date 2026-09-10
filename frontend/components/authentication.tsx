"use client";
import { useState, type FormEvent } from "react";
import { accountRequest, type Account } from "@/lib/api";
import { Brand } from "./brand";

export function Authentication({
  onSignIn,
}: {
  onSignIn: (account: Account) => void;
}) {
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (register)
        await accountRequest("/api/auth/register", "POST", { email, password });
      await accountRequest(
        "/api/auth/login",
        "POST",
        new URLSearchParams({ username: email, password }),
      );
      setPassword("");
      onSignIn(await accountRequest<Account>("/api/account"));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <div className="auth-card">
        <Brand />
        <span className="eyebrow">YOUR PERSONAL AI</span>
        <h1>{register ? "Make room for you." : "Welcome back."}</h1>
        <p>Your conversations and devices, in your own space.</p>
        <form onSubmit={submit} className="account-form">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            maxLength={320}
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete={register ? "new-password" : "current-password"}
            minLength={12}
            maxLength={128}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
          {register && <small>Use 12–128 characters.</small>}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="primary-button" disabled={busy}>
            {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
          </button>
        </form>
        <button
          className="text-button"
          disabled={busy}
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
        >
          {register
            ? "Already have an account? Sign in"
            : "New here? Create an account"}
        </button>
        <small>Created by Omkar Zunje · THRYV V1</small>
      </div>
    </main>
  );
}
