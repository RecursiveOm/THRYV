"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { accountRequest } from "@/lib/api";
type Memory = { id: string; category: string; content: string };
export function MemoryPanel() {
  const [items, setItems] = useState<Memory[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("preference");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    const data = await accountRequest<{ enabled: boolean; memories: Memory[] }>(
      "/api/memories",
    );
    setItems(data.memories);
    setEnabled(data.enabled);
  }, []);
  useEffect(() => {
    let active = true;
    accountRequest<{ enabled: boolean; memories: Memory[] }>("/api/memories")
      .then((data) => {
        if (active) {
          setItems(data.memories);
          setEnabled(data.enabled);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function mutate(path: string, method: string, body?: unknown) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await accountRequest(path, method, body);
      await refresh();
      setContent("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Memory update failed.");
    } finally {
      setBusy(false);
    }
  }
  async function toggle(next: boolean) {
    if (busy) return;
    const previous = enabled;
    setEnabled(next);
    setBusy(true);
    setError("");
    try {
      const saved = await accountRequest<{ enabled: boolean }>(
        "/api/memories/settings",
        "POST",
        { enabled: next },
      );
      setEnabled(saved.enabled);
    } catch {
      setEnabled(previous);
      setError("Could not change memory settings. Please try again.");
    } finally {
      setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void mutate("/api/memories", "POST", { content, category });
  }
  return (
    <section className="memory-panel" aria-label="Personal memory">
      <h2>Personal memory</h2>
      <p>
        Save durable preferences, facts, project context, and decisions. You can
        also say “Remember that…” in chat. Ordinary chats are not automatically
        saved as memories.
      </p>
      <label>
        <input
          type="checkbox"
          checked={enabled}
          disabled={busy}
          onChange={(e) => void toggle(e.target.checked)}
        />{" "}
        Enable saving and using memory
      </label>
      <form className="account-form" onSubmit={submit}>
        <label htmlFor="memory-content">Remember something</label>
        <textarea
          id="memory-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          minLength={3}
          maxLength={500}
          required
          disabled={!enabled || busy}
        />
        <label htmlFor="memory-category">Category</label>
        <select
          id="memory-category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="preference">Preference</option>
          <option value="fact">Fact</option>
          <option value="project">Project context</option>
          <option value="decision">Decision</option>
        </select>
        <button
          className="primary-button"
          disabled={!enabled || busy || content.trim().length < 3}
        >
          Save memory
        </button>
      </form>
      <p>
        Never enter credentials or secrets. {items.length}/200 memories saved.
      </p>
      {items.map((item) => (
        <article className="memory-item" key={item.id}>
          <small>{item.category}</small>
          <p>{item.content}</p>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => void mutate(`/api/memories/${item.id}`, "DELETE")}
          >
            Delete memory
          </button>
        </article>
      ))}
      <button
        className="text-button"
        disabled={busy || !items.length}
        onClick={() => {
          if (
            window.confirm(
              "Delete all your personal memories? This cannot be undone.",
            )
          )
            void mutate("/api/memories", "DELETE");
        }}
      >
        Clear all memories
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
