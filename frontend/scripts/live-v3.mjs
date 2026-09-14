// Opt-in live provider/public web/Companion/voice acceptance. No credential or response logs.
import { parseEnv } from "node:util";
import { readFileSync } from "node:fs";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { randomBytes, randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { chromium, expect } from "@playwright/test";

let key = process.env.DEEPSEEK_API_KEY;
for (const file of ["../backend/.env", "../.env"]) {
  if (key) break;
  try {
    key = parseEnv(readFileSync(file, "utf8")).DEEPSEEK_API_KEY;
  } catch {
    /* optional */
  }
}
delete process.env.DEEPSEEK_API_KEY;
if (!key) {
  console.log("BLOCKED: configure the live key locally.");
  process.exit(2);
}
const directory = await mkdtemp(join(tmpdir(), "thryv-live-v3-"));
const env = Object.fromEntries(
  [
    "PATH",
    "HOME",
    "DISPLAY",
    "XAUTHORITY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
  ]
    .filter((k) => process.env[k])
    .map((k) => [k, process.env[k]]),
);
const base = "http://localhost:8000";
const headers = { Origin: "http://localhost:3000", "X-THRYV-Request": "1" };
let browser,
  page,
  companion,
  device,
  stage = "synthetic research microphone fixture";
const check = (value) => {
  if (!value) throw new Error("check_failed");
};
const pass = () => console.log(`PASS ${stage}`);
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
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page
    .getByRole("button", { name: "Send message", exact: true })
    .waitFor({ timeout: 70000 });
}
async function researchResult() {
  let action;
  await expect
    .poll(
      async () => {
        const items = await (
          await page.request.get(`${base}/api/actions`)
        ).json();
        action = items.find(
          (a) =>
            a.conversation_id === new URL(page.url()).hash.slice(1) &&
            a.device_id === null,
        );
        return action && !["queued", "running"].includes(action.status);
      },
      { timeout: 100000 },
    )
    .toBeTruthy();
  check(action.status === "succeeded");
  check(
    action.details.sources.length > 0 &&
      action.details.sources.every(
        (s) => s.content && s.url.startsWith("https://"),
      ),
  );
  return action;
}
try {
  const fixture = join(directory, "research.wav");
  const made = spawnSync(
    "uv",
    [
      "run",
      "--extra",
      "voice",
      "python",
      "-m",
      "scripts.voice_fixture",
      fixture,
      "--research",
    ],
    { cwd: resolve("../backend"), env, stdio: "ignore", timeout: 60000 },
  );
  check(made.status === 0);
  pass();
  browser = await chromium.launch({
    channel: "chromium",
    args: [
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${fixture}`,
    ],
  });
  const context = await browser.newContext({ permissions: ["microphone"] });
  page = await context.newPage();
  stage = "account and live provider connection";
  await page.goto("http://localhost:3000");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page
    .getByLabel("Email", { exact: true })
    .fill(`live-v3-${randomUUID()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill(randomBytes(24).toString("base64url"));
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByLabel("DeepSeek API key", { exact: true }).fill(key);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await page
    .getByLabel("Message THRYV", { exact: true })
    .waitFor({ timeout: 70000 });
  pass();
  let result;
  if (!process.argv.includes("--voice-only")) {
    if (!process.argv.includes("--remaining")) {
      stage =
        "live LangGraph persistence research with official retrieved sources";
      await send(
        "Research the latest official LangGraph documentation about persistence and explain the important points.",
      );
      result = await researchResult();
      check(
        result.details.sources.some((s) =>
          /docs.langchain.com|langchain-ai.github.io/.test(s.url),
        ),
      );
      check(
        result.details.sources.some((s) =>
          /checkpoint|persistence/i.test(s.content),
        ),
      );
      pass();
    }
    stage = "memory-aware live speech-recognition research";
    await fresh();
    await send("Remember that I prefer free and open-source tools.");
    await fresh();
    await send("Research good speech-recognition options for a personal AI.");
    await researchResult();
    await expect(page.getByRole("log")).toContainText(/free|open.source/i, {
      timeout: 10000,
    });
    pass();
    stage = "real Companion pairing";
    const pairingToken = (
      await (
        await page.request.post(`${base}/api/devices/pairing`, { headers })
      ).json()
    ).token;
    const pairing = await (
      await page.request.post(`${base}/api/companion/pair`, {
        data: {
          token: pairingToken,
          name: "V3 live laptop",
          platform: "Linux",
        },
      })
    ).json();
    device = pairing.device_id;
    check(device);
    await writeFile(
      join(directory, "device.json"),
      JSON.stringify({ server: base, ...pairing }),
      { mode: 0o600 },
    );
    companion = spawn(
      "uv",
      [
        "run",
        "--project",
        "companion",
        "thryv-companion",
        "run",
        "--state-dir",
        directory,
      ],
      { cwd: resolve(".."), env, stdio: "ignore" },
    );
    await expect(page.getByLabel("Device", { exact: true })).toHaveValue(
      device,
      {
        timeout: 15000,
      },
    );
    pass();
    stage = "confirmed official FastAPI URL and observed browser window";
    await fresh();
    await send("Open the official FastAPI website on my computer.");
    await page
      .getByRole("button", { name: "Allow action" })
      .waitFor({ timeout: 70000 });
    const pending = (
      await (await page.request.get(`${base}/api/actions`)).json()
    ).find((a) => a.status === "pending_confirmation");
    check(
      pending.tool === "open_url" &&
        pending.device_id === device &&
        pending.permission === "CONFIRM",
    );
    await page.getByRole("button", { name: "Allow action" }).click();
    await expect(page.getByRole("log")).toContainText(
      "A browser window opened for the requested URL",
      { timeout: 30000 },
    );
    pass();
  }
  stage = "Talk, VAD, local STT, live FastAPI research and final TTS playback";
  await fresh();
  let spoken = false;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/voice/speak")) spoken = true;
  });
  await page.getByRole("button", { name: "Talk to THRYV" }).click();
  result = await researchResult();
  check(
    result.details.sources.some((s) => s.url.includes("fastapi.tiangolo.com")),
  );
  await expect.poll(() => spoken, { timeout: 20000 }).toBeTruthy();
  await page
    .getByRole("button", { name: "Stop voice", exact: true })
    .waitFor({ timeout: 30000 });
  await expect(
    page
      .getByRole("region", { name: "Voice", exact: true })
      .getByRole("status"),
  ).toHaveText("Speaking…", { timeout: 55000 });
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
  pass();
} catch {
  console.log(`FAIL ${stage}; raw errors, responses and credentials withheld.`);
  process.exitCode = 1;
} finally {
  try {
    if (page) {
      const actions = await (
        await page.request.get(`${base}/api/actions`)
      ).json();
      for (const a of actions.filter(
        (a) => a.device_id === null && ["queued", "running"].includes(a.status),
      ))
        await page.request.post(`${base}/api/actions/${a.id}/cancel`, {
          headers,
        });
      if (device)
        await page.request.delete(`${base}/api/devices/${device}`, { headers });
      await page.request.delete(`${base}/api/memories`, { headers });
      await page.request.delete(`${base}/api/account/provider`, { headers });
      await page.request.post(`${base}/api/auth/logout`, { headers });
    }
  } catch {
    /* no raw errors */
  }
  companion?.kill("SIGTERM");
  await browser?.close();
  await rm(directory, { recursive: true, force: true });
}
