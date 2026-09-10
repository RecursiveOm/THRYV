// Opt-in manual verification only. Never imported by the app or ordinary tests.
import { loadEnvFile } from "node:process";
import { chromium } from "playwright";

try {
  loadEnvFile("../backend/.env");
} catch {
  /* Environment key may already be set. */
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
let stage = "frontend launch";
function check(condition) {
  if (!condition) throw new Error("check_failed");
}
try {
  await page.goto("http://localhost:3000");
  await page.getByLabel("DeepSeek API key", { exact: true }).waitFor();
  process.stdout.write("PASS frontend launch\n");
  stage = "invalid live DeepSeek key";
  await page
    .getByLabel("DeepSeek API key", { exact: true })
    .fill("test-only-invalid-key");
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await page.locator("#key-error").waitFor({ timeout: 70000 });
  check(
    (await page.locator("#key-error").textContent()).includes("didn’t accept"),
  );
  process.stdout.write("PASS invalid live DeepSeek key\n");
  stage = "valid live DeepSeek connection";
  await page.getByLabel("DeepSeek API key", { exact: true }).fill(key);
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await page
    .getByLabel("Message THRYV", { exact: true })
    .waitFor({ timeout: 70000 });
  process.stdout.write("PASS valid live DeepSeek connection\n");
  stage = "live THRYV identity";
  await page
    .getByLabel("Message THRYV", { exact: true })
    .fill("Hello, who are you?");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page
    .locator(".message.assistant .message-content")
    .waitFor({ timeout: 70000 });
  check(
    /THRYV/i.test(
      await page.locator(".message.assistant .message-content").textContent(),
    ),
  );
  process.stdout.write("PASS live THRYV identity\n");
  stage = "live conversational follow-up";
  await page
    .getByLabel("Message THRYV", { exact: true })
    .fill("What was the exact question I asked in my previous message?");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page
    .locator(".message.assistant .message-content")
    .nth(1)
    .waitFor({ timeout: 70000 });
  check(
    /who are you/i.test(
      await page
        .locator(".message.assistant .message-content")
        .nth(1)
        .textContent(),
    ),
  );
  process.stdout.write("PASS live conversational follow-up\n");
  stage = "browser key safety";
  check(!observed.join("\n").includes(key));
  check(
    await page.evaluate(
      () => localStorage.length === 0 && sessionStorage.length === 0,
    ),
  );
  process.stdout.write("PASS no key in browser logs, URLs or web storage\n");
  await page
    .getByRole("button", { name: "DeepSeek connected — provider settings" })
    .click();
  await page
    .getByRole("button", { name: "Disconnect & clear session" })
    .click();
  process.stdout.write("PASS disconnect and session clear\n");
} catch {
  // Never emit Playwright errors: locators, inputs or request details can contain the key.
  process.stdout.write(
    `FAIL ${stage}; credential and provider content withheld.\n`,
  );
  process.exitCode = 1;
} finally {
  await browser.close();
}
