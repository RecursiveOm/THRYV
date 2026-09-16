"use client";

import { useEffect, useState } from "react";
import { accountRequest } from "@/lib/api";

type Project = {
  id: string;
  device_id: string;
  name: string;
  path: string;
  active: boolean;
};

export function ProjectPanel({
  onSelect,
}: {
  onSelect: (device: string) => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    try {
      setProjects(await accountRequest<Project[]>("/api/workspaces"));
    } catch {
      setError("Could not load authorized workspaces.");
    }
  }
  useEffect(() => {
    let active = true;
    accountRequest<Project[]>("/api/workspaces")
      .then((rows) => {
        if (active) setProjects(rows);
      })
      .catch(() => {
        if (active) setError("Could not load authorized workspaces.");
      });
    return () => {
      active = false;
    };
  }, []);
  async function change(project: Project, remove: boolean) {
    setBusy(true);
    setError("");
    try {
      await accountRequest(
        `/api/workspaces/${project.id}${remove ? "" : "/select"}`,
        remove ? "DELETE" : "POST",
      );
      if (!remove) onSelect(project.device_id);
      await refresh();
    } catch {
      setError("Workspace change failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Authorized Workspaces">
      <h3>Authorized Workspaces</h3>
      <p>
        Authorize a project on your paired computer with{" "}
        <code>thryv-companion workspace-add /path/to/project</code>, then keep
        Companion running.
      </p>
      <button className="text-button" onClick={refresh}>
        Refresh workspaces
      </button>
      {error && <p role="alert">{error}</p>}
      {projects.map((project) => (
        <article key={project.id}>
          <strong>
            {project.name}
            {project.active ? " · Active" : ""}
          </strong>
          <p>{project.path}</p>
          <button
            className="text-button"
            disabled={busy || project.active}
            onClick={() => change(project, false)}
          >
            Select {project.name}
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => change(project, true)}
          >
            Revoke {project.name}
          </button>
        </article>
      ))}
    </section>
  );
}
