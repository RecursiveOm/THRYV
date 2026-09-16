"use client";
import { useEffect, useRef, useState } from "react";
import { accountRequest, type Action, type Device } from "@/lib/api";

export function Devices({
  devices,
  refresh,
}: {
  devices: Device[];
  refresh: () => Promise<void>;
}) {
  const [token, setToken] = useState("");
  const [expires, setExpires] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  async function pair() {
    setBusy(true);
    setError("");
    try {
      const result = await accountRequest<{
        token: string;
        expires_in: number;
      }>("/api/devices/pairing", "POST");
      setToken(result.token);
      setExpires(Date.now() + result.expires_in * 1000);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setToken(""), result.expires_in * 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pairing unavailable.");
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    setBusy(true);
    setError("");
    try {
      await accountRequest(`/api/devices/${id}`, "DELETE");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Revocation failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="device-panel" aria-label="Devices">
      <h2>Your devices</h2>
      <p>
        Companion connects from your computer. Application launches always need
        your approval.
      </p>
      <button className="new-chat" disabled={busy} onClick={pair}>
        Add device
      </button>
      {token && (
        <div className="pairing-card">
          <p>
            Run{" "}
            <code>
              uv run --project companion thryv-companion pair --server
              YOUR_SERVER_ORIGIN
            </code>{" "}
            from the THRYV checkout on your computer. Paste this token into its
            hidden prompt, then run{" "}
            <code>uv run --project companion thryv-companion run</code>.
          </p>
          <label htmlFor="pairing-token">Single-use pairing token</label>
          <input
            id="pairing-token"
            type="password"
            value={token}
            readOnly
            autoComplete="off"
            onFocus={(e) => e.target.select()}
          />
          <small>
            Select and copy. Keep this private. Expires at{" "}
            {new Date(expires).toLocaleTimeString()}.
          </small>
          <button className="text-button" onClick={() => setToken("")}>
            Hide token
          </button>
        </div>
      )}
      {!devices.length && <p>No paired devices yet.</p>}
      {devices.map((d) => (
        <div className="device-row" key={d.id}>
          <div>
            <strong>{d.name}</strong>
            <span>
              {d.platform} · {d.status}
            </span>
            <small>
              {d.last_seen
                ? `Last seen ${new Date(d.last_seen * 1000).toLocaleString()}`
                : "Not seen yet"}
            </small>
          </div>
          {d.status !== "revoked" && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => revoke(d.id)}
            >
              Revoke {d.name}
            </button>
          )}
        </div>
      ))}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

export function RecentActions({
  actions,
  devices,
  refresh,
}: {
  actions: Action[];
  devices: Device[];
  refresh: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  async function decide(id: string, allow: boolean) {
    if (busy) return;
    setBusy(id);
    setError("");
    try {
      await accountRequest(`/api/actions/${id}/decision`, "POST", { allow });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision failed.");
    } finally {
      setBusy("");
    }
  }
  async function cancel(id: string) {
    if (busy) return;
    setBusy(id);
    setError("");
    try {
      await accountRequest(`/api/actions/${id}/cancel`, "POST");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancellation failed.");
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="recent-actions" aria-label="Recent Actions">
      <h2>Recent Actions</h2>
      {!actions.length && <p>Your computer actions will appear here.</p>}
      {actions.map((a) => (
        <article key={a.id} className="action-card">
          <strong>
            {a.tool === "v4_workflow"
              ? "Requested workflow"
              : /^(workspace_|development_|github_|gmail_|calendar_|drive_)/.test(
                    a.tool,
                  )
                ? a.tool.replaceAll("_", " ")
                : a.tool === "open_application"
                  ? `Open ${a.arguments.application === "chrome" ? "Chrome" : "VS Code"}`
                  : a.tool === "open_url"
                    ? "Open website on your computer"
                    : a.device_id === null
                      ? "Public web research"
                      : "Read basic system information"}
          </strong>
          <p>
            {a.device_id === null
              ? a.tool === "v4_workflow" ||
                /^(github_|gmail_|calendar_|drive_)/.test(a.tool)
                ? "Your connected services"
                : "Isolated public research context"
              : `On ${devices.find((d) => d.id === a.device_id)?.name || "paired device"}`}
          </p>
          {a.arguments.url && <p>{a.arguments.url}</p>}
          {a.arguments.query && <p>{a.arguments.query}</p>}
          {a.tool !== "v4_workflow" &&
            /^(workspace_git|development_|github_|gmail_|calendar_|drive_)/.test(
              a.tool,
            ) && (
              <details open={a.status === "pending_confirmation"}>
                <summary>Review exact action</summary>
                <pre>{JSON.stringify(a.arguments, null, 2)}</pre>
              </details>
            )}
          {a.details?.progress && <p>{a.details.progress}</p>}
          {a.details?.data !== undefined && (
            <details>
              <summary>Captured service result</summary>
              <pre>{JSON.stringify(a.details.data, null, 2)}</pre>
            </details>
          )}
          {a.arguments.workspace_id && (
            <p>Workspace: {a.arguments.workspace_id}</p>
          )}
          {a.arguments.path && <p>File: {a.arguments.path}</p>}
          {a.arguments.content !== undefined && (
            <details>
              <summary>Review proposed file content</summary>
              <pre>{a.arguments.content}</pre>
            </details>
          )}
          {/^(workspace_|development_)/.test(a.tool) && a.details && (
            <details>
              <summary>Captured project result</summary>
              <pre>{JSON.stringify(a.details, null, 2)}</pre>
            </details>
          )}
          <small>
            {a.permission} · {a.status.replaceAll("_", " ")} ·{" "}
            {new Date(a.created_at * 1000).toLocaleString()}
          </small>
          {a.result && <p>{a.result}</p>}
          {((a.device_id === null &&
            !/^(github_|gmail_|calendar_|drive_)/.test(a.tool)) ||
            a.tool === "v4_workflow") &&
            ["queued", "running"].includes(a.status) && (
              <button
                className="text-button"
                disabled={Boolean(busy)}
                onClick={() => cancel(a.id)}
              >
                {a.tool === "v4_workflow"
                  ? "Cancel workflow"
                  : "Cancel research"}
              </button>
            )}
          {a.details?.sources?.map((source) => (
            <details key={source.url}>
              <summary>{source.title}</summary>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                referrerPolicy="no-referrer"
              >
                {source.url}
              </a>
              <small>
                Retrieved{" "}
                {new Date(source.retrieved_at * 1000).toLocaleString()}
              </small>
              <p>{source.content}</p>
            </details>
          ))}
          {a.status === "pending_confirmation" && (
            <div>
              <p>
                {/^(workspace_|development_|github_|gmail_|calendar_)/.test(
                  a.tool,
                )
                  ? "Review the exact project or connected-service action above."
                  : "Launches a new application window."}{" "}
                Approval expires at{" "}
                {new Date(a.expires_at * 1000).toLocaleTimeString()}.
              </p>
              <button
                className="primary-button"
                disabled={Boolean(busy)}
                onClick={() => decide(a.id, true)}
              >
                Allow action
              </button>
              <button
                className="text-button"
                disabled={Boolean(busy)}
                onClick={() => decide(a.id, false)}
              >
                Deny action
              </button>
            </div>
          )}
        </article>
      ))}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
