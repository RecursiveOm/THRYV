// Opt-in actual DeepSeek, local speech and Companion acceptance. Synthetic microphone input.
// No traces, screenshots, response text or credentials are logged.
import { parseEnv } from "node:util";
import { readFileSync } from "node:fs";
import { randomBytes, randomUUID } from "node:crypto";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
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
    /* optional local file */
  }
}
delete process.env.DEEPSEEK_API_KEY;
if (!key) {
  console.log("BLOCKED: configure the live key locally.");
  process.exit(2);
}
const directory = await mkdtemp(join(tmpdir(), "thryv-live-v2-"));
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
const chromeCheck =
  process.argv.includes("--wake-chrome") ||
  process.argv.includes("--talk-chrome");
const wakeCheck =
  process.argv.includes("--wake-chrome") || process.argv.includes("--wake");
const voiceOnly = process.argv.includes("--voice-only");
const resultText = chromeCheck
  ? "The application window opened on your device."
  : "Device reports Linux";
const headers = { Origin: "http://localhost:3000", "X-THRYV-Request": "1" };
let browser,
  page,
  companion,
  device,
  stage = "local speech fixture";
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
try {
  const fixture = join(directory, "input.wav");
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
      ...(wakeCheck
        ? [chromeCheck ? "--wake-chrome" : "--wake"]
        : chromeCheck
          ? ["--chrome"]
          : []),
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
  let leaked = false;
  page.on("console", (m) => {
    if (m.text().includes(key)) leaked = true;
  });
  page.on("request", (r) => {
    if (r.url().includes(key)) leaked = true;
  });
  const email = `live-v2-${randomUUID()}@example.com`,
    password = randomBytes(24).toString("base64url");
  stage = "account and live provider connection";
  await page.goto("http://localhost:3000");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
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
  if (!voiceOnly) {
    stage = "explicit memory, logout/login and relevant recall in a new chat";
    await send("Remember that I prefer Python projects to use uv.");
    await expect(page.getByRole("log")).toContainText(
      "Saved to your personal memory",
    );
    await fresh();
    await send("What Python package workflow do I prefer?");
    await expect(page.getByRole("log")).toContainText(/\buv\b/i);
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByRole("log").waitFor();
    await fresh();
    await send("What Python package workflow do I prefer?");
    await expect(page.getByRole("log")).toContainText(/\buv\b/i);
    pass();
  }
  stage = "real Companion pairing";
  const pairedToken = await page.request.post(`${base}/api/devices/pairing`, {
    headers,
  });
  check(pairedToken.ok());
  const paired = await page.request.post(`${base}/api/companion/pair`, {
    data: {
      token: (await pairedToken.json()).token,
      name: "V2 live laptop",
      platform: "Linux",
    },
  });
  check(paired.ok());
  const pairing = await paired.json();
  device = pairing.device_id;
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
  await expect(page.getByLabel("Device", { exact: true })).toHaveValue(device, {
    timeout: 15000,
  });
  pass();
  stage =
    "browser capture, real STT, DeepSeek SAFE tool and observed device result";
  await fresh();
  const voice = page.getByRole("region", { name: "Voice", exact: true });
  let spokenResult = false;
  page.on("request", (r) => {
    if (
      r.url().endsWith("/api/voice/speak") &&
      r.postData()?.includes(resultText)
    )
      spokenResult = true;
  });
  if (wakeCheck) {
    await voice.getByText("Settings", { exact: true }).click();
    await voice.getByRole("checkbox", { name: /Wake word \(Beta\)/ }).check();
    await expect(voice.getByRole("status")).toHaveText(
      "Wake listening for THRYV…",
    );
  } else {
    await page.getByRole("button", { name: "Talk to THRYV" }).click();
    await expect(voice.getByRole("status")).toHaveText("Listening…");
  }
  if (chromeCheck) {
    stage = "voice requests Chrome and requires approval";
    await page
      .getByRole("button", { name: "Allow action", exact: true })
      .waitFor({ timeout: 90000 });
    await expect(page.getByRole("log")).toContainText(
      "Nothing has executed yet",
    );
    await page
      .getByRole("button", { name: "Allow action", exact: true })
      .click();
  }
  await expect(page.getByRole("log")).toContainText(resultText, {
    timeout: 90000,
  });
  const actions = await (await page.request.get(`${base}/api/actions`)).json();
  check(
    actions.some(
      (a) =>
        a.device_id === device &&
        a.tool === (chromeCheck ? "open_application" : "get_system_info") &&
        a.permission === (chromeCheck ? "CONFIRM" : "SAFE") &&
        a.status === "succeeded",
    ),
  );
  pass();
  stage = "actual result synthesized, browser playback and stop";
  await expect.poll(() => spokenResult, { timeout: 55000 }).toBe(true);
  await expect(voice.getByRole("status")).toHaveText("Speaking…", {
    timeout: 55000,
  });
  check(spokenResult);
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
  await expect(voice.getByRole("status")).toHaveText("Ready");
  pass();
  if (wakeCheck) {
    await voice.getByRole("checkbox", { name: /Wake word \(Beta\)/ }).uncheck();
    await expect(
      voice.getByRole("checkbox", { name: /Wake word \(Beta\)/ }),
    ).toBeEnabled();
  }
  if (!voiceOnly) {
    stage = "technical, casual and playful live personality samples";
    for (const prompt of [
      "Briefly explain why Python virtual environments are useful.",
      "Long day. Can we keep things easy for a minute?",
      "You missed me? Keep it playful.",
    ]) {
      await fresh();
      await send(prompt);
      const chat = await (
        await page.request.get(
          `${base}/api/conversations/${new URL(page.url()).hash.slice(1)}`,
        )
      ).json();
      const reply =
        chat.messages.filter((m) => m.role === "assistant").at(-1)?.content ||
        "";
      check(reply.length > 15 && reply.length < 3500);
      check(
        !/sexual|sexy|darling|sweetheart|babe|I have feelings|I love you/i.test(
          reply,
        ),
      );
      if (prompt.includes("virtual environments"))
        check(/dependenc|package|isolat/i.test(reply));
    }
    pass();
    stage = "memory management and browser credential safety";
    await page.getByRole("button", { name: "Memory", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "Personal memory" }),
    ).toContainText("Python projects to use uv");
    check(
      (await page.request.delete(`${base}/api/memories`, { headers })).ok(),
    );
    check(
      (await (await page.request.get(`${base}/api/memories`)).json()).memories
        .length === 0,
    );
    await page.getByRole("button", { name: "Memory", exact: true }).click();
    await fresh();
    await send(
      "Do you have any saved memory of my preferred Python workflow? Answer yes only if there is saved memory.",
    );
    const afterDelete = await (
      await page.request.get(
        `${base}/api/conversations/${new URL(page.url()).hash.slice(1)}`,
      )
    ).json();
    const deletedReply =
      afterDelete.messages.filter((m) => m.role === "assistant").at(-1)
        ?.content || "";
    check(
      /\bno\b|don't|do not|haven't|not stored/i.test(deletedReply) &&
        !/^yes\b/i.test(deletedReply),
    );
    check(
      !leaked &&
        (await page.evaluate(
          () =>
            localStorage.length === 0 &&
            sessionStorage.length === 0 &&
            !document.cookie.includes("thryv_session"),
        )),
    );
    pass();
  }
} catch {
  console.log(`FAIL ${stage}; raw errors, speech and credentials withheld.`);
  process.exitCode = 1;
} finally {
  try {
    if (device)
      await page.request.delete(`${base}/api/devices/${device}`, { headers });
    if (page) {
      await page.request.post(`${base}/api/voice/settings`, {
        headers,
        data: { wake_enabled: false },
      });
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
