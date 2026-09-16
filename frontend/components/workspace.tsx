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
  accountRequest,
  ApiError,
  type Account,
  type Conversation,
  type Device,
  type Action,
  type Message,
  type Reply,
} from "@/lib/api";

import { Authentication } from "./authentication";
import { Devices, RecentActions } from "./devices";
import { MemoryPanel } from "./memory-panel";
import { VoiceControls } from "./voice-controls";
import { ProjectPanel } from "./project-panel";
import { ConnectedApps } from "./connected-apps";

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
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const signal = new AbortController();
    accountRequest<Account>("/api/account", "GET", undefined, signal.signal)
      .then(setAccount)
      .catch((e) => {
        if (
          !signal.signal.aborted &&
          (!(e instanceof ApiError) || e.code !== "unauthenticated")
        )
          setError(e.message);
      })
      .finally(() => {
        if (!signal.signal.aborted) setLoading(false);
      });
    return () => signal.abort();
  }, []);
  if (loading)
    return (
      <main className="auth-page">
        <p role="status">Opening your space…</p>
      </main>
    );
  if (!account)
    return (
      <>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <Authentication
          onSignIn={(a) => {
            setError("");
            setAccount(a);
          }}
        />
      </>
    );
  return (
    <SignedWorkspace
      key={account.id}
      account={account}
      onSignOut={() => setAccount(null)}
    />
  );
}

function SignedWorkspace({
  account,
  onSignOut,
}: {
  account: Account;
  onSignOut: () => void;
}) {
  const [key, setKey] = useState(account.provider_connected);
  const [conversation, setConversation] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [panel, setPanel] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [voiceReset, setVoiceReset] = useState(0);
  const conversationRef = useRef("");
  const selection = useRef(0);
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
  async function refresh() {
    const [chats, paired, recent] = await Promise.all([
      accountRequest<Conversation[]>("/api/conversations"),
      accountRequest<Device[]>("/api/devices"),
      accountRequest<Action[]>("/api/actions"),
    ]);
    setConversations(chats);
    setDevices(paired);
    setActions(recent);
    const available = paired.filter((d) => d.status !== "revoked");
    setDeviceId((previous) =>
      paired.some((d) => d.id === previous)
        ? previous
        : available.length === 1
          ? available[0].id
          : "",
    );
  }
  async function openConversation(id: string) {
    const version = ++selection.current;
    reset();
    conversationRef.current = id;
    setConversation(id);
    window.history.replaceState(null, "", `#${id}`);
    try {
      const chat = await accountRequest<Conversation>(
        `/api/conversations/${id}`,
      );
      if (version === selection.current) setMessages(chat.messages || []);
    } catch (e) {
      if (version === selection.current)
        setError(e instanceof Error ? e.message : "Could not load chat.");
    }
  }
  useEffect(() => {
    let active = true;
    accountRequest<Conversation[]>("/api/conversations")
      .then(async (chats) => {
        if (!active) return;
        setConversations(chats);
        const hash = window.location.hash.slice(1);
        const selected =
          hash === "new"
            ? undefined
            : chats.find((c) => c.id === hash) || chats[0];
        if (selected) {
          conversationRef.current = selected.id;
          setConversation(selected.id);
          const chat = await accountRequest<Conversation>(
            `/api/conversations/${selected.id}`,
          );
          if (active && conversationRef.current === chat.id)
            setMessages(chat.messages || []);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    let inFlight = false;
    async function poll() {
      if (inFlight) return;
      inFlight = true;
      try {
        const [paired, recent, chats] = await Promise.all([
          accountRequest<Device[]>("/api/devices"),
          accountRequest<Action[]>("/api/actions"),
          accountRequest<Conversation[]>("/api/conversations"),
        ]);
        if (!active) return;
        setDevices(paired);
        setConversations(chats);
        const available = paired.filter((d) => d.status !== "revoked");
        setDeviceId((previous) =>
          paired.some((d) => d.id === previous)
            ? previous
            : available.length === 1
              ? available[0].id
              : "",
        );
        const id = conversationRef.current;
        if (
          id &&
          !controller.current &&
          recent.some((a) => a.conversation_id === id)
        ) {
          const chat = await accountRequest<Conversation>(
            `/api/conversations/${id}`,
          );
          if (active && !controller.current && conversationRef.current === id)
            setMessages(chat.messages || []);
        }
        if (active) setActions(recent);
      } catch (e) {
        if (active && e instanceof ApiError && e.code === "unauthenticated")
          onSignOut();
      } finally {
        inFlight = false;
      }
    }
    void poll();
    const timer = setInterval(poll, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [onSignOut]);

  function reset() {
    setVoiceReset((value) => value + 1);
    controller.current?.abort();
    controller.current = null;
    setMessages([]);
    setDraft("");
    setPending("");
    setError("");
    setNotice("");
    setClearConfirmation(false);
  }

  function connect() {
    setKey(true);
    setSettings(false);
  }
  async function disconnect() {
    try {
      await accountRequest("/api/account/provider", "DELETE");
      setKey(false);
      setSettings(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Disconnect failed.");
    }
  }
  async function signOut() {
    try {
      await accountRequest("/api/auth/logout", "POST");
      controller.current?.abort();
      window.history.replaceState(null, "", window.location.pathname);
      onSignOut();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign out failed.");
    }
  }
  function newChat() {
    ++selection.current;
    reset();
    conversationRef.current = "";
    setConversation("");
    window.history.replaceState(null, "", "#new");
  }

  async function deleteChat() {
    if (
      !conversation ||
      controller.current ||
      !window.confirm(
        "Permanently delete this conversation? Its action audit records will remain.",
      )
    )
      return;
    try {
      await accountRequest(`/api/conversations/${conversation}`, "DELETE");
      newChat();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete chat.");
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    await sendText(draft.trim());
  }
  async function sendText(text: string, fromVoice = false) {
    if (!fromVoice) setVoiceReset((value) => value + 1);
    if (!text || controller.current || !key) return;
    const current = new AbortController();
    controller.current = current;
    setPending(text);
    setDraft("");
    setError("");
    setNotice("");
    try {
      let id = conversationRef.current;
      if (!id) {
        const chat = await accountRequest<Conversation>(
          "/api/conversations",
          "POST",
          {},
          current.signal,
        );
        if (current.signal.aborted) return;
        id = chat.id;
        conversationRef.current = id;
        setConversation(id);
        window.history.replaceState(null, "", `#${id}`);
      }
      const reply = await accountRequest<Reply>(
        `/api/conversations/${id}/messages`,
        "POST",
        {
          message: text,
          request_id: crypto.randomUUID(),
          device_id: deviceId || null,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        current.signal,
      );
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
        if (reply.action) {
          const action = reply.action;
          setActions((previous) => [
            action,
            ...previous.filter((item) => item.id !== action.id),
          ]);
        }
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
      "Stopped waiting. The server may finish and save the reply or request an action. Check Recent Actions before retrying.",
    );
  }

  if (!key)
    return (
      <>
        <div className="account-strip">
          <span>{account.email}</span>
          <button onClick={signOut}>Sign out</button>
        </div>
        <Welcome onConnect={connect} />
      </>
    );

  return (
    <div className="workspace">
      <aside className="sidebar">
        <Brand />
        <button
          className="new-chat"
          onClick={() =>
            messages.length || pending || draft
              ? setClearConfirmation(true)
              : newChat()
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
          <nav className="chat-list" aria-label="Recent conversations">
            {conversations.map((c) => (
              <button
                key={c.id}
                aria-current={c.id === conversation ? "page" : undefined}
                onClick={() => void openConversation(c.id)}
              >
                {c.title}
              </button>
            ))}
          </nav>
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
          {conversation && (
            <button onClick={deleteChat}>Delete this conversation</button>
          )}
          <button onClick={() => setPanel(!panel)}>
            Devices & Recent Actions
          </button>
          <button onClick={signOut}>
            <LogOut size={17} /> Sign out
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
            <span className="session-label">Your space, saved securely</span>
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
                : newChat()
            }
          >
            <Plus size={19} />
          </button>
        </header>
        <div className="workspace-toolbar">
          <button
            onClick={() => setMemoryOpen(!memoryOpen)}
            aria-expanded={memoryOpen}
          >
            Memory
          </button>
          <label htmlFor="device-picker">Device</label>
          <select
            id="device-picker"
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
          >
            <option value="">Select a device</option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} · {d.status}
              </option>
            ))}
          </select>
          <button onClick={() => setPanel(!panel)} aria-expanded={panel}>
            Devices & Actions
            {actions.some((a) => a.status === "pending_confirmation")
              ? " · Approval needed"
              : ""}
          </button>
          <button className="mobile-account" onClick={signOut}>
            Sign out
          </button>
          {conversation && (
            <button className="mobile-account" onClick={deleteChat}>
              Delete chat
            </button>
          )}
          <select
            className="mobile-account"
            aria-label="Recent conversations"
            value={conversation}
            onChange={(e) =>
              e.target.value ? void openConversation(e.target.value) : newChat()
            }
          >
            <option value="">New conversation</option>
            {conversations.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </div>
        <div
          className={`chat-scroll ${messages.length || pending ? "has-messages" : ""}`}
        >
          {memoryOpen && (
            <div className="tools-panel">
              <MemoryPanel />
            </div>
          )}
          {panel && (
            <div className="tools-panel">
              <Devices devices={devices} refresh={refresh} />
              <RecentActions
                actions={actions}
                devices={devices}
                refresh={refresh}
              />
            </div>
          )}
          {!panel &&
            actions.some(
              (a) =>
                (a.status === "pending_confirmation" ||
                  a.device_id === null ||
                  a.tool === "v4_workflow") &&
                a.conversation_id === conversation,
            ) && (
              <div className="inline-actions">
                <RecentActions
                  actions={actions.filter(
                    (a) =>
                      (a.status === "pending_confirmation" ||
                        a.device_id === null ||
                        a.tool === "v4_workflow") &&
                      a.conversation_id === conversation,
                  )}
                  devices={devices}
                  refresh={refresh}
                />
              </div>
            )}
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
                <LockKeyhole size={13} /> Conversations are saved to your THRYV
                account.
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
          <VoiceControls
            onTranscript={(text) => sendText(text, true)}
            reply={
              [...messages].reverse().find((m) => m.role === "assistant")
                ?.content || ""
            }
            busy={Boolean(pending)}
            waitingForDevice={actions.some(
              (action) =>
                action.conversation_id === conversation &&
                ["queued", "running"].includes(action.status),
            )}
            key={voiceReset}
          />
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
          Your key is encrypted on this server. Replacing or removing it keeps
          your conversations.
        </p>
        {settings && <KeyForm onConnect={connect} isSettings />}
        {settings && <ProjectPanel onSelect={setDeviceId} />}
        {settings && <ConnectedApps />}
        <button className="disconnect-button" onClick={disconnect}>
          <LogOut size={16} /> Remove saved key
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
          Your current conversation remains in Recent conversations. This starts
          a fresh chat and clears the draft.
        </p>
        <button className="primary-button" onClick={newChat}>
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
