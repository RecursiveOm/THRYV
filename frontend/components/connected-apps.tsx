"use client";
import { useEffect, useState } from "react";
import { accountRequest } from "@/lib/api";

type Connection = {
  service: string;
  configured: boolean;
  status: string;
  identity: string | null;
  scopes: string[];
};
const names: Record<string, string> = {
  github: "GitHub",
  gmail: "Gmail",
  calendar: "Google Calendar",
  drive: "Google Drive",
};

export function ConnectedApps() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [writes, setWrites] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  async function refresh() {
    try {
      setConnections(await accountRequest<Connection[]>("/api/integrations"));
    } catch {
      setNotice("Could not load connected apps.");
    }
  }
  useEffect(() => {
    let active = true;
    accountRequest<Connection[]>("/api/integrations")
      .then((rows) => {
        if (active) setConnections(rows);
      })
      .catch(() => {
        if (active) setNotice("Could not load connected apps.");
      });
    return () => {
      active = false;
    };
  }, []);
  async function change(connection: Connection, remove: boolean) {
    setBusy(connection.service);
    setNotice("");
    try {
      if (remove) {
        const result = await accountRequest<{ provider_revoked: boolean }>(
          `/api/integrations/${connection.service}`,
          "DELETE",
        );
        setNotice(
          result.provider_revoked
            ? "Disconnected. Google may also revoke this app’s other Google grants."
            : "Local connection removed. Revoke THRYV in the provider’s account settings to finish revocation.",
        );
        await refresh();
      } else {
        const result = await accountRequest<{ url: string }>(
          `/api/integrations/${connection.service}/connect`,
          "POST",
          { allow_writes: Boolean(writes[connection.service]) },
        );
        const url = new URL(result.url);
        if (
          url.protocol !== "https:" ||
          !["accounts.google.com", "github.com"].includes(url.hostname)
        )
          throw new Error("Invalid OAuth destination");
        window.location.assign(url.toString());
      }
    } catch {
      setNotice(
        "Connection unavailable. Check host OAuth configuration or reconnect.",
      );
    } finally {
      setBusy("");
    }
  }
  return (
    <section aria-label="Connected Apps">
      <h3>Connected Apps</h3>
      <p>
        These accounts are separate from your THRYV sign-in. Selected content
        may be sent to your runtime model when you request it; it is not
        automatically saved as memory.
      </p>
      {notice && <p role="status">{notice}</p>}
      {connections.map((connection) => (
        <article key={connection.service}>
          <strong>{names[connection.service]}</strong>
          <p>
            {connection.configured
              ? connection.status
              : "Host OAuth setup required"}
            {connection.identity ? ` · ${connection.identity}` : ""}
          </p>
          {["gmail", "calendar"].includes(connection.service) && (
            <label>
              <input
                type="checkbox"
                checked={Boolean(writes[connection.service])}
                onChange={(event) =>
                  setWrites({
                    ...writes,
                    [connection.service]: event.target.checked,
                  })
                }
              />{" "}
              Also request{" "}
              {connection.service === "gmail"
                ? "send permission"
                : "event editing permission"}
              ; each action still needs confirmation
            </label>
          )}
          {connection.service === "github" && (
            <p>
              GitHub OAuth’s repo scope covers private repositories and permits
              writes. THRYV still requires confirmation for writes.
            </p>
          )}
          {connection.scopes.length > 0 && (
            <details>
              <summary>Granted scopes</summary>
              <p>{connection.scopes.join(", ")}</p>
            </details>
          )}
          <button
            className="text-button"
            disabled={Boolean(busy) || !connection.configured}
            onClick={() => change(connection, false)}
          >
            {connection.status === "disconnected" ? "Connect" : "Reconnect"}{" "}
            {names[connection.service]}
          </button>
          {connection.status !== "disconnected" && (
            <button
              className="text-button"
              disabled={Boolean(busy)}
              onClick={() => change(connection, true)}
            >
              Disconnect {names[connection.service]}
            </button>
          )}
        </article>
      ))}
    </section>
  );
}
