// Opt-in REAL DeepSeek + Chrome acceptance test. Never run by CI; no traces/screenshots.
import { loadEnvFile } from "node:process";
import { randomBytes, randomUUID } from "node:crypto";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

try {
  loadEnvFile("../backend/.env");
} catch {
  /* Key may be in the environment. */
}
const key = process.env.DEEPSEEK_API_KEY;
delete process.env.DEEPSEEK_API_KEY;
if (!key) {
  process.stdout.write(
    "Live verification pending: add DEEPSEEK_API_KEY to ignored backend/.env.\n",
  );
  process.exit(2);
}
const browser = await chromium.launch();
const page = await browser.newPage();
const observed = [];
page.on("console", (message) => observed.push(message.text()));
page.on("request", (request) => observed.push(request.url()));
const base = "http://localhost:8000";
const headers = { Origin: "http://localhost:3000", "X-THRYV-Request": "1" };
const directory = await mkdtemp(join(tmpdir(), "thryv-live-"));
let companion;
let device;
let stage = "account registration and sign in";
function check(condition) {
  if (!condition) throw new Error("check_failed");
}
async function send(text) {
  await page.getByLabel("Message THRYV", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page
    .getByRole("button", { name: "Send message", exact: true })
    .waitFor({ timeout: 70000 });
}
try {
  await page.goto("http://localhost:3000");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page
    .getByLabel("Email", { exact: true })
    .fill(`live-check-${randomUUID()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill(randomBytes(24).toString("base64url"));
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByLabel("DeepSeek API key", { exact: true }).waitFor();
  process.stdout.write(`PASS ${stage}\n`);
  stage = "live DeepSeek connection";
  await page.getByLabel("DeepSeek API key", { exact: true }).fill(key);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await page
    .getByLabel("Message THRYV", { exact: true })
    .waitFor({ timeout: 70000 });
  process.stdout.write(`PASS ${stage}\n`);
  stage = "live chat and reload persistence";
  await send("Hello, who are you?");
  check(/THRYV/i.test(await page.getByRole("log").textContent()));
  await page.reload();
  await page.getByRole("log").waitFor();
  check(
    (await page.getByRole("log").textContent()).includes("Hello, who are you?"),
  );
  process.stdout.write(`PASS ${stage}\n`);
  stage = "pairing and Companion online";
  await page
    .getByRole("button", { name: "Devices & Actions", exact: true })
    .click();
  await page.getByRole("button", { name: "Add device", exact: true }).click();
  const token = await page.getByLabel("Single-use pairing token").inputValue();
  const paired = await page.request.post(`${base}/api/companion/pair`, {
    data: { token, name: "Live acceptance laptop", platform: "Linux" },
  });
  check(paired.ok());
  const data = await paired.json();
  device = data.device_id;
  await writeFile(
    join(directory, "device.json"),
    JSON.stringify({ server: base, ...data }),
    { mode: 0o600 },
  );
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
  await page
    .getByText("Linux · online", { exact: true })
    .waitFor({ timeout: 15000 });
  await page.getByRole("button", { name: "Hide token" }).click();
  await page
    .getByRole("button", { name: "Devices & Actions", exact: true })
    .click();
  process.stdout.write(`PASS ${stage}\n`);
  stage = "live model requests Chrome; confirmation before execution";
  await send("Open Chrome on my laptop.");
  await page
    .getByRole("button", { name: "Allow action", exact: true })
    .waitFor({ timeout: 15000 });
  check(
    (await page.getByRole("log").textContent()).includes(
      "Nothing has executed yet",
    ),
  );
  await page.getByRole("button", { name: "Allow action", exact: true }).click();
  process.stdout.write(`PASS ${stage}\n`);
  stage = "real Chrome window and truthful chat result";
  await page
    .getByRole("log")
    .getByText("The application window opened on your device.", { exact: true })
    .waitFor({ timeout: 30000 });
  await page
    .getByRole("button", { name: "Devices & Actions", exact: true })
    .click();
  await page
    .getByRole("region", { name: "Recent Actions" })
    .getByText(/CONFIRM · succeeded/)
    .waitFor();
  process.stdout.write(`PASS ${stage}\n`);
  stage = "revocation blocks repeated command";
  await page
    .getByRole("button", { name: "Revoke Live acceptance laptop" })
    .click();
  await page.getByText("Linux · revoked", { exact: true }).waitFor();
  await send("Open Chrome on my laptop.");
  await page
    .getByRole("log")
    .getByText("This device has been revoked. No action was executed.", {
      exact: true,
    })
    .waitFor();
  check(
    (await page
      .getByRole("button", { name: "Allow action", exact: true })
      .count()) === 0,
  );
  process.stdout.write(`PASS ${stage}\n`);
  stage = "browser credential safety";
  check(!observed.join("\n").includes(key));
  check(
    await page.evaluate(
      () =>
        localStorage.length === 0 &&
        sessionStorage.length === 0 &&
        !document.cookie.includes("thryv_session"),
    ),
  );
  process.stdout.write(`PASS ${stage}\n`);
} catch {
  // Playwright errors can contain locators and input values; never emit raw errors here.
  process.stdout.write(
    `FAIL ${stage}; credentials and raw content withheld.\n`,
  );
  process.exitCode = 1;
} finally {
  try {
    if (device)
      await page.request.delete(`${base}/api/devices/${device}`, { headers });
    await page.request.delete(`${base}/api/account/provider`, { headers });
    await page.request.post(`${base}/api/auth/logout`, { headers });
  } catch {
    /* No raw errors. */
  }
  companion?.kill("SIGTERM");
  await browser.close();
  await rm(directory, { recursive: true, force: true });
}
