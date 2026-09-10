"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  ChevronRight,
  Compass,
  Feather,
  Leaf,
  LockKeyhole,
  LogOut,
  MessageSquare,
  Plus,
  Settings2,
  Square,
  X,
} from "lucide-react";
import { Brand, Mark } from "./brand";
import { KeyForm, Welcome } from "./provider-setup";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  apiRequest,
  boundedHistory,
  type Message,
  type Reply,
} from "@/lib/api";

const starters = [
  {
    icon: Feather,
    title: "Find the right words",
    description: "Turn a rough thought into a first draft",
    prompt:
      "Help me turn a rough thought into a clear first draft. Ask me what I’m writing and who it’s for.",
  },
  {
    icon: Compass,
    title: "Make a little progress",
    description: "Break something big into smaller steps",
    prompt:
      "Help me break a goal into small, practical next steps. First, ask me what I want to work on.",
  },
  {
    icon: BookOpen,
    title: "Follow your curiosity",
    description: "Understand something in a new way",
    prompt:
      "I’d like to understand something new. Ask me what I’m curious about, then help me explore it.",
  },
  {
    icon: MessageSquare,
    title: "Think it through",
    description: "Give an idea some room to grow",
    prompt:
      "Be a sounding board for an idea. Ask me what’s on my mind and help me think it through.",
  },
];

export function Workspace() {
  const [key, setKey] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [settings, setSettings] = useState(false);
  const [clearConfirmation, setClearConfirmation] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const clearDialog = useRef<HTMLDialogElement>(null);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);
  useEffect(() => {
    if (settings) dialog.current?.showModal();
    else dialog.current?.close();
  }, [settings]);
  useEffect(() => {
    if (clearConfirmation) clearDialog.current?.showModal();
    else clearDialog.current?.close();
  }, [clearConfirmation]);
  useEffect(() => {
    if (!key) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [key]);

  function reset() {
    controller.current?.abort();
    controller.current = null;
    setMessages([]);
    setDraft("");
    setPending("");
    setError("");
    setNotice("");
    setClearConfirmation(false);
  }

  function connect(newKey: string) {
    reset();
    setKey(newKey);
    setSettings(false);
  }
  function disconnect() {
    reset();
    setKey("");
    setSettings(false);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || controller.current || !key) return;
    const current = new AbortController();
    controller.current = current;
    setPending(text);
    setDraft("");
    setError("");
    setNotice("");
    try {
      const reply = await apiRequest<Reply>("/api/chat", key, current.signal, {
        message: text,
        history: boundedHistory(messages, text),
      });
      if (
        reply?.message?.role !== "assistant" ||
        typeof reply.message.content !== "string" ||
        !reply.message.content.trim() ||
        Array.from(reply.message.content).length > 32_000 ||
        typeof reply.truncated !== "boolean"
      ) {
        throw new Error(
          "THRYV received an incomplete reply. Please try again.",
        );
      }
      if (!current.signal.aborted) {
        setMessages((previous) =>
          [
            ...previous,
            { role: "user", content: text } as Message,
            reply.message,
          ].slice(-100),
        );
        if (reply.truncated)
          setNotice(
            "This reply reached its length limit. Ask THRYV to continue if you’d like more.",
          );
      }
    } catch (failure) {
      if (!current.signal.aborted) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Something went wrong. Please try again.",
        );
        setDraft(text);
      }
    } finally {
      if (controller.current === current) {
        controller.current = null;
        setPending("");
        composer.current?.focus();
      }
    }
  }

  function cancel() {
    controller.current?.abort();
    controller.current = null;
    setDraft(pending);
    setPending("");
    setNotice(
      "Stopped waiting. DeepSeek may still finish and bill the request.",
    );
  }

  if (!key) return <Welcome onConnect={connect} />;

  return (
    <div className="workspace">
      <aside className="sidebar">
        <Brand />
        <button
          className="new-chat"
          onClick={() =>
            messages.length || pending || draft
              ? setClearConfirmation(true)
              : reset()
          }
        >
          <Plus size={18} /> New conversation <span>↗</span>
        </button>
        <div className="sidebar-section">
          <span className="eyebrow">YOUR SPACE</span>
          <div className="active-conversation">
            <MessageSquare size={16} />
            <span>{messages[0]?.content || "A fresh perspective"}</span>
            <span className="status-dot" />
          </div>
          <p>
            One conversation.
            <br />A little room to think.
          </p>
        </div>
        <div className="sidebar-note">
          <Leaf size={22} />
          <p>
            Good things start
            <br />
            with a little curiosity.
          </p>
        </div>
        <div className="sidebar-bottom">
          <button onClick={() => setSettings(true)}>
            <Settings2 size={17} /> Provider settings
          </button>
          <span>Created by Omkar Zunje</span>
        </div>
      </aside>
      <main className="chat-main">
        <header className="chat-header">
          <div>
            <span className="mobile-wordmark">THRYV</span>
            <span className="desktop-heading">Your Personal AI</span>
            <span className="header-divider" />
            <span className="session-label">A fresh space, every session</span>
          </div>
          <button
            className="connection-pill"
            onClick={() => setSettings(true)}
            aria-label="DeepSeek connected — provider settings"
          >
            <span className="status-dot" /> DeepSeek <Settings2 size={13} />
          </button>
          <button
            className="mobile-new icon-button"
            aria-label="New conversation"
            onClick={() =>
              messages.length || pending || draft
                ? setClearConfirmation(true)
                : reset()
            }
          >
            <Plus size={19} />
          </button>
        </header>
        <div
          className={`chat-scroll ${messages.length || pending ? "has-messages" : ""}`}
        >
          {!messages.length && !pending ? (
            <section className="empty-state">
              <div className="greeting-mark">
                <Mark />
              </div>
              <span className="eyebrow">A CLEARER MIND. A FRESH START.</span>
              <h1>What’s on your mind?</h1>
              <p>
                Big ideas, small questions, and everything in between.
                <br />
                Let’s make a little progress together.
              </p>
              <div className="starter-grid">
                {starters.map(({ icon: Icon, title, description, prompt }) => (
                  <button
                    className="starter"
                    key={title}
                    onClick={() => {
                      setDraft(prompt);
                      composer.current?.focus();
                    }}
                  >
                    <span className="starter-top">
                      <Icon size={20} />
                      <ArrowUp size={15} className="diagonal-arrow" />
                    </span>
                    <strong>{title}</strong>
                    <span>{description}</span>
                  </button>
                ))}
              </div>
              <div className="empty-footnote">
                <LockKeyhole size={13} /> Just this session. Nothing saved by
                THRYV.
              </div>
            </section>
          ) : (
            <section
              className="messages"
              aria-label="Conversation"
              role="log"
              aria-live="polite"
              aria-relevant="additions text"
            >
              {messages.map((message, index) => (
                <article className={`message ${message.role}`} key={index}>
                  <div className="message-meta">
                    {message.role === "assistant" ? (
                      <>
                        <Mark small />
                        <span>THRYV</span>
                      </>
                    ) : (
                      <>
                        <span className="user-avatar">Y</span>
                        <span>You</span>
                      </>
                    )}
                  </div>
                  <div className="message-content">
                    {message.role === "assistant" ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        skipHtml
                        components={{
                          img: () => null,
                          a: ({ href, children }) => (
                            <a
                              href={
                                href?.startsWith("https://") ||
                                href?.startsWith("http://")
                                  ? href
                                  : undefined
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    ) : (
                      <p>{message.content}</p>
                    )}
                  </div>
                </article>
              ))}
              {pending && (
                <>
                  <article className="message user">
                    <div className="message-meta">
                      <span className="user-avatar">Y</span>
                      <span>You</span>
                    </div>
                    <div className="message-content">
                      <p>{pending}</p>
                    </div>
                  </article>
                  <article className="message assistant">
                    <div className="message-meta">
                      <Mark small />
                      <span>THRYV</span>
                    </div>
                    <div className="generating" role="status">
                      <span className="thinking-dots">
                        <i />
                        <i />
                        <i />
                      </span>{" "}
                      Making room for a thought…
                    </div>
                  </article>
                </>
              )}
              <div ref={end} />
            </section>
          )}
        </div>
        <div className="composer-area">
          {error && (
            <div className="composer-feedback error" role="alert">
              <p>{error}</p>
              <button onClick={() => setSettings(true)}>
                Provider settings <ChevronRight size={14} />
              </button>
            </div>
          )}
          {notice && (
            <p className="composer-feedback notice" role="status">
              {notice}
            </p>
          )}
          <form onSubmit={send} className="composer">
            <label className="sr-only" htmlFor="message">
              Message THRYV
            </label>
            <textarea
              ref={composer}
              id="message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask, imagine, or think out loud…"
              maxLength={8000}
              rows={2}
              disabled={Boolean(pending)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing &&
                  window.matchMedia("(pointer: fine)").matches
                ) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="composer-bottom">
              <span>
                <span className="status-dot" /> THRYV{" "}
                <span className="composer-provider">with DeepSeek</span>
              </span>
              <div>
                {draft.length > 7000 && (
                  <span className="char-count">{draft.length}/8,000</span>
                )}
                {pending ? (
                  <button
                    key="stop"
                    type="button"
                    className="send-button"
                    onClick={(event) => {
                      event.preventDefault();
                      cancel();
                    }}
                    aria-label="Stop waiting"
                  >
                    <Square size={16} />
                  </button>
                ) : (
                  <button
                    key="send"
                    type="submit"
                    className="send-button"
                    disabled={!draft.trim()}
                    aria-label="Send message"
                  >
                    <ArrowUp size={20} />
                  </button>
                )}
              </div>
            </div>
          </form>
          <div className="composer-caption">
            <span>
              THRYV can make mistakes. Give important details a second look.
            </span>
            <span title="Up to 10 recent turns fit within the context limit.">
              <ArrowDown size={11} /> Recent context only
            </span>
          </div>
        </div>
      </main>
      <dialog
        ref={dialog}
        onCancel={() => setSettings(false)}
        onClose={() => setSettings(false)}
        className="settings-dialog"
        aria-labelledby="settings-title"
      >
        <button
          className="dialog-close icon-button"
          onClick={() => setSettings(false)}
          aria-label="Close provider settings"
        >
          <X size={20} />
        </button>
        <span className="eyebrow">YOUR CONNECTION</span>
        <h2 id="settings-title">Provider settings</h2>
        <p className="dialog-description">
          DeepSeek is connected for this tab. Connecting a new key or
          disconnecting clears this conversation.
        </p>
        {settings && <KeyForm onConnect={connect} isSettings />}
        <button className="disconnect-button" onClick={disconnect}>
          <LogOut size={16} /> Disconnect & clear session
        </button>
      </dialog>
      <dialog
        ref={clearDialog}
        onCancel={() => setClearConfirmation(false)}
        onClose={() => setClearConfirmation(false)}
        className="settings-dialog clear-dialog"
        aria-labelledby="clear-title"
      >
        <h2 id="clear-title">A fresh start?</h2>
        <p className="dialog-description">
          This clears the current conversation and draft. Your DeepSeek
          connection stays active.
        </p>
        <button className="primary-button" onClick={reset}>
          Start a new conversation <Plus size={18} />
        </button>
        <button
          className="text-button"
          onClick={() => setClearConfirmation(false)}
        >
          Keep this conversation
        </button>
      </dialog>
    </div>
  );
}
