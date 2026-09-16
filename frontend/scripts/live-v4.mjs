// Opt-in live DeepSeek, fixture workspace/Companion and synthetic Talk acceptance.
// Never prints credentials, provider responses, user messages or raw errors.
import { parseEnv } from "node:util";
import { readFileSync } from "node:fs";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { chromium, expect } from "@playwright/test";

const selected = new Set(process.argv.slice(2));
const wants = (name) => selected.size === 0 || selected.has(`--${name}`);
let key;
for (const path of ["../backend/.env", "../.env"]) {
  try {
    key ||= parseEnv(readFileSync(path, "utf8")).DEEPSEEK_API_KEY;
  } catch {
    /* optional */
  }
}
if (!key) {
  console.log("BLOCKED local DeepSeek key unavailable");
  process.exit(2);
}
const directory = await mkdtemp(join(tmpdir(), "thryv-live-v4-"));
const project = join(directory, "THRYV-demo"),
  state = join(directory, "companion");
const backend = resolve("../backend"),
  companionProject = resolve("../companion");
const base = "http://localhost:8000";
const headers = { Origin: "http://localhost:3000", "X-THRYV-Request": "1" };
let browser,
  context,
  page,
  companion,
  device,
  workspace,
  stage = "setup";
const check = (value) => {
  if (!value) throw new Error("acceptance_failed");
};
const environment = Object.fromEntries(
  [
    "PATH",
    "HOME",
    "DISPLAY",
    "XAUTHORITY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
  ]
    .filter((name) => process.env[name])
    .map((name) => [name, process.env[name]]),
);
function command(executable, args, cwd = directory) {
  const result = spawnSync(executable, args, {
    cwd,
    env: environment,
    encoding: "utf8",
    timeout: 60000,
  });
  check(result.status === 0);
  return result.stdout;
}
async function api(path, method = "GET", data) {
  const response = await context.request.fetch(base + path, {
    method,
    headers,
    data,
  });
  check(response.ok());
  return response.status() === 204 ? null : response.json();
}
async function fresh() {
  await page
    .getByRole("button", { name: "New conversation", exact: false })
    .first()
    .click();
  if (
    await page.getByRole("button", { name: "Start a new conversation" }).count()
  )
    await page
      .getByRole("button", { name: "Start a new conversation" })
      .click();
}
async function send(text) {
  await page.getByLabel("Message THRYV", { exact: true }).fill(text);
  const submitted = page.waitForResponse(
    (response) => /\/api\/conversations\/[^/]+\/messages$/.test(response.url()),
    { timeout: 90000 },
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const response = await submitted;
  console.log("Chat HTTP status", response.status());
  if (response.status() === 422) {
    const payload = await response.json();
    for (const item of Array.isArray(payload.detail) ? payload.detail : [])
      console.log("Validation", item.loc, item.type);
    if (payload.error?.code) console.log("Validation code", payload.error.code);
  }
  check(response.ok());
  await page
    .getByRole("button", { name: "Send message", exact: true })
    .waitFor({ timeout: 90000 });
}
async function workflow(after) {
  let root;
  const approved = new Set();
  for (let i = 0; i < 310; i++) {
    const actions = await api("/api/actions");
    root = actions.find((a) => a.tool === "v4_workflow" && !after.has(a.id));
    if (root) {
      for (const childId of root.details.children || []) {
        const child = actions.find((a) => a.id === childId);
        if (
          child?.status === "pending_confirmation" &&
          !approved.has(child.id)
        ) {
          check(child.arguments.workspace_id === workspace);
          check(
            ["development_run", "workspace_write", "workspace_open"].includes(
              child.tool,
            ),
          );
          if (child.tool === "workspace_write")
            check(child.arguments.path === "calculator.py");
          if (child.tool === "development_run")
            check(child.arguments.command === "tests");
          await api(`/api/actions/${child.id}/decision`, "POST", {
            allow: true,
          });
          approved.add(child.id);
        }
      }
      if (!["queued", "running"].includes(root.status)) {
        console.log(
          "Observed workflow",
          root.status,
          "steps",
          root.details.children?.length || 0,
          "approvals",
          approved.size,
        );
        for (const id of root.details.children || []) {
          const child = actions.find((a) => a.id === id);
          console.log(
            "Observed tool",
            child.tool,
            child.status,
            "verified",
            child.details?.verified ?? "n/a",
          );
        }
        check(root.status === "succeeded");
        return (root.details.children || []).map((id) =>
          actions.find((a) => a.id === id),
        );
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("workflow_timeout");
}
try {
  await mkdir(project, { mode: 0o700 });
  await mkdir(state, { mode: 0o700 });
  await writeFile(
    join(project, "calculator.py"),
    wants("repair")
      ? "def add(a, b):\n    return a - b\n"
      : "def add(a, b):\n    return a + b\n",
    { mode: 0o600 },
  );
  const tests =
    "import unittest\nfrom calculator import add\nclass Addition(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 2), 4)\n";
  await writeFile(join(project, "test_calculator.py"), tests, { mode: 0o600 });
  command("/usr/bin/git", ["init", "-q", project]);
  command("/usr/bin/git", [
    "-C",
    project,
    "add",
    "calculator.py",
    "test_calculator.py",
  ]);
  command("/usr/bin/git", [
    "-C",
    project,
    "-c",
    "user.name=THRYV Fixture",
    "-c",
    "user.email=fixture@example.com",
    "commit",
    "-qm",
    "Initial fixture",
  ]);
  const wav = join(directory, "development.wav");
  command(
    "uv",
    [
      "run",
      "--inexact",
      "--extra",
      "voice",
      "python",
      "-m",
      "scripts.voice_fixture",
      wav,
      "--development",
    ],
    backend,
  );
  browser = await chromium.launch({
    channel: "chromium",
    args: [
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${wav}`,
    ],
  });
  context = await browser.newContext({ permissions: ["microphone"] });
  context.setDefaultTimeout(30000);
  page = await context.newPage();
  const email = `v4-fixture-${randomUUID()}@example.com`,
    password = randomUUID();
  await api("/api/auth/register", "POST", { email, password });
  const login = await context.request.post(base + "/api/auth/login", {
    headers,
    form: { username: email, password },
  });
  check(login.ok());
  await api("/api/account/provider", "POST", {
    api_key: key,
    consent_to_store: true,
  });
  key = undefined;
  const pairing = await api("/api/devices/pairing", "POST");
  const paired = await api("/api/companion/pair", "POST", {
    token: pairing.token,
    name: "V4 fixture Companion",
    platform: "Linux",
  });
  device = paired.device_id;
  await writeFile(
    join(state, "device.json"),
    JSON.stringify({ server: base, ...paired }),
    { mode: 0o600 },
  );
  const output = command("uv", [
    "run",
    "--project",
    companionProject,
    "thryv-companion",
    "workspace-add",
    project,
    "--state-dir",
    state,
  ]);
  workspace = output.trim().split(": ").at(-1);
  command("uv", [
    "run",
    "--project",
    companionProject,
    "thryv-companion",
    "command-add",
    workspace,
    "--runner",
    "unittest",
    "--state-dir",
    state,
  ]);
  companion = spawn(
    "uv",
    [
      "run",
      "--project",
      companionProject,
      "thryv-companion",
      "run",
      "--state-dir",
      state,
    ],
    { cwd: directory, env: environment, stdio: "ignore", detached: true },
  );
  await expect
    .poll(
      async () =>
        (await api("/api/workspaces")).some((w) => w.id === workspace),
      { timeout: 15000 },
    )
    .toBeTruthy();
  await api(`/api/workspaces/${workspace}/select`, "POST");
  await page.goto("http://localhost:3000");
  await page
    .getByLabel("Message THRYV", { exact: true })
    .waitFor({ timeout: 30000 });
  await expect
    .poll(async () => page.getByLabel("Device", { exact: true }).inputValue(), {
      timeout: 15000,
    })
    .toBe(device);
  let before, children;
  if (wants("repair")) {
    stage = "development failure, scoped repair, verified rerun and diff";
    console.log("START", stage);
    before = new Set((await api("/api/actions")).map((a) => a.id));
    await send(
      "Use my selected THRYV-demo workspace. Run the approved tests, fix calculator.py if they fail without changing tests, rerun tests, and show git diff. Do not open an application.",
    );
    children = await workflow(before);
    check(
      children.some(
        (a) => a.tool === "development_run" && a.status === "failed",
      ),
    );
    check(
      children.some(
        (a) => a.tool === "workspace_write" && a.status === "succeeded",
      ),
    );
    check(
      children.some(
        (a) => a.tool === "development_run" && a.details.verified === true,
      ),
    );
    check(
      children.some(
        (a) => a.tool === "workspace_git" && a.arguments.operation === "diff",
      ),
    );
    check(
      (await readFile(join(project, "test_calculator.py"), "utf8")) === tests,
    );
    console.log("PASS", stage);
  }
  if (wants("git")) {
    stage = "actual Git status and latest commits";
    await fresh();
    before = new Set((await api("/api/actions")).map((a) => a.id));
    await send(
      "Show git status and the latest five commits in my selected workspace.",
    );
    children = await workflow(before);
    check(
      children.some(
        (a) => a.tool === "workspace_git" && a.arguments.operation === "status",
      ),
    );
    check(
      children.some(
        (a) => a.tool === "workspace_git" && a.arguments.operation === "log",
      ),
    );
    console.log("PASS", stage);
  }
  if (wants("vscode")) {
    stage = "confirmed VS Code project opening";
    await fresh();
    before = new Set((await api("/api/actions")).map((a) => a.id));
    await send("Open my selected THRYV-demo project in VS Code.");
    children = await workflow(before);
    check(
      children.some(
        (a) =>
          a.tool === "workspace_open" &&
          a.details.launch_result === "application_opened",
      ),
    );
    console.log("PASS", stage);
  }
  if (wants("voice")) {
    stage = "Talk VAD, local STT, confirmed development tool and local TTS";
    await fresh();
    before = new Set((await api("/api/actions")).map((a) => a.id));
    let spoken = false;
    page.on("response", (response) => {
      if (response.url().endsWith("/api/voice/speak") && response.ok())
        spoken = true;
    });
    await page.getByRole("button", { name: "Talk to THRYV", exact: true }).click();
    children = await workflow(before);
    check(
      children.some(
        (a) => a.tool === "development_run" && a.details.verified === true,
      ),
    );
    await expect.poll(() => spoken, { timeout: 30000 }).toBeTruthy();
    console.log("PASS", stage);
  }
} catch {
  console.log("FAIL", stage);
  process.exitCode = 1;
} finally {
  try {
    if (device) await api(`/api/devices/${device}`, "DELETE");
    await api("/api/account/provider", "DELETE");
    await api("/api/auth/logout", "POST");
  } catch {
    /* no raw errors */
  }
  if (companion?.pid) {
    try {
      process.kill(-companion.pid, "SIGTERM");
    } catch {
      /* already exited */
    }
  }
  await browser?.close();
  await rm(directory, { recursive: true, force: true });
}
