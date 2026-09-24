"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowUp,
  BookOpen,
  ChevronRight,
  Compass,
  Feather,
  LogOut,
  MessageSquare,
  Plus,
  Settings2,
  Square,
  Menu,
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
import { Appearance } from "./appearance";
import { SettingsPage, sections, type SettingsSection } from "./settings-page";

const starters = [
  {
    icon: Feather,
    title: "Write something",
    description: "Turn a rough thought into a first draft",
    prompt:
      "Help me turn a rough thought into a clear first draft. Ask me what I’m writing and who it’s for.",
  },
  {
    icon: Compass,
    title: "Plan a project",
    description: "Break something big into smaller steps",
    prompt:
      "Help me break a goal into small, practical next steps. First, ask me what I want to work on.",
  },
  {
    icon: BookOpen,
    title: "Learn something",
    description: "Understand something in a new way",
    prompt:
      "I’d like to understand something new. Ask me what I’m curious about, then help me explore it.",
  },
  {
    icon: MessageSquare,
    title: "Explore an idea",
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
  const [conversation, setConversation] = useState(() =>
    window.location.hash.startsWith("#settings/")
      ? new URLSearchParams(window.location.hash.split("?")[1]).get("chat") ||
        ""
      : "",
  );
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const [search, setSearch] = useState("");
  const sidebar = useRef<HTMLElement>(null);
  const [voiceHost, setVoiceHost] = useState<HTMLDivElement | null>(null);
  const [section, setSection] = useState<SettingsSection>(() => {
    return (
      sections.find(
        (s) =>
          "#settings/" + encodeURIComponent(s) ===
          window.location.hash.split("?")[0],
      ) || "General"
    );
  });
  const [voiceReset, setVoiceReset] = useState(0);
  const [voiceStatus, setVoiceStatus] = useState("Ready");
  const conversationRef = useRef(conversation);
  const selection = useRef(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [settings, setSettings] = useState(() =>
    window.location.hash.startsWith("#settings/"),
  );
  const [clearConfirmation, setClearConfirmation] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const clearDialog = useRef<HTMLDialogElement>(null);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);
  function openSettings(next: SettingsSection = "General") {
    setError("");
    setSection(next);
    setSettings(true);
    setNavOpen(false);
    window.history.pushState(
      null,
      "",
      "#settings/" +
        encodeURIComponent(next) +
        (conversationRef.current
          ? "?chat=" + encodeURIComponent(conversationRef.current)
          : ""),
    );
  }
  function closeSettings() {
    setSettings(false);
    window.history.pushState(
      { thryvConversation: conversationRef.current },
      "",
      "#" + (conversationRef.current || "new"),
    );
  }
  useEffect(() => {
    const navigate = () => {
      const hash = window.location.hash;
      const selected = sections.find(
        (s) => "#settings/" + encodeURIComponent(s) === hash.split("?")[0],
      );
      setSettings(Boolean(selected));
      if (selected) setSection(selected);
    };
    window.addEventListener("hashchange", navigate);
    window.addEventListener("popstate", navigate);
    return () => {
      window.removeEventListener("hashchange", navigate);
      window.removeEventListener("popstate", navigate);
    };
  }, []);
  useEffect(() => {
    if (!navOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const nodes = () =>
      Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input, a[href]",
        ) || [],
      ).filter((n) => n.getClientRects().length);
    nodes()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNavOpen(false);
      if (event.key === "Tab") {
        const items = nodes(),
          first = items[0],
          last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    const size = matchMedia("(max-width: 640px)");
    const resize = () => {
      if (!size.matches) setNavOpen(false);
    };
    size.addEventListener("change", resize);
    return () => {
      document.removeEventListener("keydown", keydown);
      size.removeEventListener("change", resize);
      previous?.focus();
    };
  }, [navOpen]);
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
    setNavOpen(false);
    closeSettings();
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
        const hash = window.location.hash.startsWith("#settings/")
          ? new URLSearchParams(window.location.hash.split("?")[1]).get(
              "chat",
            ) || "new"
          : window.location.hash.slice(1);
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
    closeSettings();
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
    setNavOpen(false);
    setSettings(false);
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
      {navOpen && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      )}
      <aside
        ref={sidebar}
        className={`sidebar ${navOpen ? "is-open" : ""}`}
        aria-label="Navigation"
        role={navOpen ? "dialog" : undefined}
        aria-modal={navOpen || undefined}
      >
        <button
          className="mobile-close icon-button"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        >
          <X size={20} />
        </button>
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
          <label className="sr-only" htmlFor="conversation-search">
            Search conversations
          </label>
          <input
            id="conversation-search"
            className="conversation-search"
            placeholder="Search conversations"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <span className="nav-label">Conversations</span>
          <nav className="chat-list" aria-label="Recent conversations">
            {conversations
              .filter((c) =>
                c.title.toLowerCase().includes(search.toLowerCase()),
              )
              .map((c) => (
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
        <nav className="sidebar-bottom" aria-label="Utilities">
          <button onClick={() => openSettings("Memory")}>
            <BookOpen size={17} /> Memory
          </button>
          <button onClick={() => openSettings("Devices")}>
            <Compass size={17} /> Devices & Actions
            {actions.some((a) => a.status === "pending_confirmation") && (
              <span className="approval-count">Approval needed</span>
            )}
          </button>
          <button onClick={() => openSettings("General")}>
            <Settings2 size={17} /> Settings
          </button>
          <button
            className="account-link"
            onClick={() => openSettings("Account")}
          >
            {account.email}
          </button>
          <span>Created by Omkar Zunje</span>
        </nav>
      </aside>
      <main className="chat-main" hidden={settings} inert={navOpen}>
        <header className="chat-header">
          <div className="chat-heading">
            <button
              className="mobile-menu icon-button"
              aria-label="Open navigation"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <Menu size={20} />
            </button>
            <span className="conversation-title">
              {conversations.find((c) => c.id === conversation)?.title ||
                "New conversation"}
            </span>
            {conversation && (
              <details className="conversation-menu">
                <summary aria-label="Conversation options">•••</summary>
                <button onClick={deleteChat}>Delete chat</button>
              </details>
            )}
          </div>
          <button
            className="connection-pill"
            onClick={() => openSettings("Provider")}
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
        {devices.some((d) => d.status !== "revoked") && (
          <div className="workspace-toolbar">
            <label htmlFor="device-picker">Device</label>
            <select
              id="device-picker"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
            >
              <option value="">No device selected</option>
              {devices
                .filter((d) => d.status !== "revoked")
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} · {d.status}
                  </option>
                ))}
            </select>
          </div>
        )}
        <div
          className={`chat-scroll ${messages.length || pending ? "has-messages" : ""}`}
        >
          {actions.some(
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
              <h1>What can I help with?</h1>
              <div className="starter-grid">
                {starters.map(({ icon: Icon, title, prompt }) => (
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
                  </button>
                ))}
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
                      Working…
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
            settingsTarget={settings && section === "Voice" ? voiceHost : null}
            preferenceKey={account.id}
            onStatus={setVoiceStatus}
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
              <button onClick={() => openSettings("Provider")}>
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
              placeholder="Message THRYV…"
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
            THRYV can make mistakes. Review important results.
          </div>
        </div>
      </main>
      {settings &&
        section !== "Devices" &&
        actions.some((a) => a.status === "pending_confirmation") && (
          <button
            className="approval-notice"
            aria-label="Review pending actions"
            onClick={() => openSettings("Devices")}
          >
            Approval needed · Review action
          </button>
        )}
      {settings && section !== "Voice" && voiceStatus !== "Ready" && (
        <button
          className="global-voice-status"
          onClick={() => openSettings("Voice")}
        >
          {voiceStatus} · Voice controls
        </button>
      )}
      {settings && (
        <SettingsPage
          section={section}
          onSection={openSettings}
          onClose={closeSettings}
        >
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {section === "General" && (
            <div className="settings-summary">
              <p>Your assistant, set up your way.</p>
              <button onClick={() => openSettings("Appearance")}>
                Appearance <ChevronRight size={16} />
              </button>
              <button onClick={() => openSettings("Voice")}>
                Voice preferences <ChevronRight size={16} />
              </button>
              <button onClick={() => openSettings("Provider")}>
                DeepSeek · {key ? "Connected" : "Not connected"}{" "}
                <ChevronRight size={16} />
              </button>
            </div>
          )}
          {section === "Appearance" && <Appearance />}
          {section === "Voice" && <div ref={setVoiceHost} />}
          {section === "Provider" && (
            <>
              <p>
                Your key is encrypted on this server. Changing it keeps your
                conversations.
              </p>
              <KeyForm onConnect={connect} isSettings />
              <button className="disconnect-button" onClick={disconnect}>
                Remove saved key
              </button>
            </>
          )}
          {section === "Devices" && (
            <>
              <Devices devices={devices} refresh={refresh} />
              <RecentActions
                actions={actions}
                devices={devices}
                refresh={refresh}
              />
            </>
          )}
          {section === "Workspaces" && <ProjectPanel onSelect={setDeviceId} />}
          {section === "Connected Apps" && <ConnectedApps />}
          {section === "Memory" && <MemoryPanel />}
          {section === "Privacy" && (
            <div className="settings-summary">
              <h3>You stay in control</h3>
              <p>
                Tool permissions and confirmations apply to both text and voice.
                Actions remain in your history.
              </p>
              <h3>Voice</h3>
              <p>
                Audio is processed on your THRYV server. Background wake
                listening is optional and off by default. Microphone audio is
                never continuously streamed to DeepSeek.
              </p>
              <h3>Saved data</h3>
              <p>
                Conversations and memory belong to your account. Provider and
                connected-app credentials are encrypted on the server. Only
                explicitly saved memories carry across chats.
              </p>
            </div>
          )}
          {section === "Account" && (
            <div className="settings-summary">
              <p>{account.email}</p>
              <p>Your THRYV account is separate from connected services.</p>
              <button onClick={signOut}>
                <LogOut size={17} /> Sign out
              </button>
            </div>
          )}
        </SettingsPage>
      )}
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
