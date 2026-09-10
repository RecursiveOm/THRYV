import { test, expect, type Page } from "@playwright/test";
import { boundedHistory } from "../lib/api";

async function register(page: Page) {
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page
    .getByLabel("Email", { exact: true })
    .fill(`browser-${crypto.randomUUID()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-password-for-browser");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByLabel("DeepSeek API key", { exact: true }),
  ).toBeVisible();
  await page.getByRole("checkbox").check();
}

async function connect(page: Page) {
  await register(page);
  await page
    .getByLabel("DeepSeek API key", { exact: true })
    .fill("test-only-valid-key");
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await expect(
    page.getByRole("heading", { name: "What’s on your mind?" }),
  ).toBeVisible();
}

async function send(page: Page, message: string) {
  await page.getByLabel("Message THRYV", { exact: true }).fill(message);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeVisible();
}

test("setup, conversation, follow-up, settings and disconnect", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await connect(page);
  await send(page, "My favorite color is green.");
  await expect(page.getByRole("log")).toContainText("your personal AI");
  await send(page, "What is my favorite color?");
  await expect(page.getByRole("log")).toContainText(
    "You told me: My favorite color is green.",
  );
  await page
    .getByRole("button", { name: "DeepSeek connected — provider settings" })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByLabel("DeepSeek API key", { exact: true }),
  ).toHaveValue("");
  await page.getByRole("button", { name: "Remove saved key" }).click();
  await expect(
    page.getByRole("heading", { name: "Make yourself at home." }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("invalid key is clean and allows retry", async ({ page }) => {
  await register(page);
  await page
    .getByLabel("DeepSeek API key", { exact: true })
    .fill("test-only-invalid-key");
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "didn’t accept this key",
  );
  await expect(page.locator("main").getByRole("alert")).not.toContainText(
    "test-only-invalid-key",
  );
  await page
    .getByLabel("DeepSeek API key", { exact: true })
    .fill("test-only-valid-key");
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await expect(page.getByLabel("Message THRYV", { exact: true })).toBeVisible();
});

test("sessions and conversations persist without browser-stored keys or secrets in URLs", async ({
  page,
  context,
}) => {
  const urls: string[] = [];
  const logs: string[] = [];
  page.on("request", (request) => urls.push(request.url()));
  page.on("console", (message) => logs.push(message.text()));
  await connect(page);
  await send(page, "Private session text");
  expect(
    await page.evaluate(() => ({
      local: { ...localStorage },
      session: { ...sessionStorage },
    })),
  ).toEqual({ local: {}, session: {} });
  expect(
    (await context.cookies()).filter((cookie) =>
      cookie.value.includes("test-only"),
    ),
  ).toEqual([]);
  expect([...urls, ...logs].join("\n")).not.toContain("test-only-valid-key");
  await page.reload();
  await expect(page.getByRole("log")).toContainText("Private session text");
  const session = (await context.cookies()).find(
    (c) => c.name === "thryv_session",
  );
  expect(session?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "thryv_session",
  );
});

test("provider timeout preserves the draft for retry", async ({ page }) => {
  await connect(page);
  await send(page, "Simulate timeout");
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "took too long",
  );
  await expect(page.getByLabel("Message THRYV", { exact: true })).toHaveValue(
    "Simulate timeout",
  );
  await expect(page.locator("main").getByRole("alert")).not.toContainText(
    "test-only-valid-key",
  );
  await send(page, "Hello again");
  await expect(page.getByRole("log")).toContainText("your personal AI");
});

test("unavailable backend has a useful connection error", async ({ page }) => {
  await page.route("**/api/account/provider", (route) => route.abort("failed"));
  await register(page);
  await page
    .getByLabel("DeepSeek API key", { exact: true })
    .fill("test-only-valid-key");
  await page.getByRole("button", { name: "Connect & get started" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "couldn’t reach its server",
  );
});

test("Markdown is formatted without active HTML or tracking images", async ({
  page,
}) => {
  await connect(page);
  await send(page, "Show unsafe markup");
  await expect(page.getByRole("log").locator("strong")).toHaveText(
    "Safe formatting",
  );
  await expect(page.getByRole("log").locator("script, img")).toHaveCount(0);
  await expect(page.getByRole("log").getByText("bad link")).not.toHaveAttribute(
    "href",
  );
});

test("new conversation retains the saved chat and provider connection", async ({
  page,
}) => {
  await connect(page);
  await send(page, "An old conversation");
  await page
    .getByRole("button", { name: "New conversation", exact: false })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Start a new conversation" }).click();
  await expect(
    page.getByRole("heading", { name: "What’s on your mind?" }),
  ).toBeVisible();
  await expect(page.getByLabel("Message THRYV", { exact: true })).toHaveValue(
    "",
  );
});

test("responsive setup and chat have no horizontal overflow", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-setup.png`,
    fullPage: true,
    caret: "initial",
  });
  await connect(page);
  await expect(
    page.getByLabel("Message THRYV", { exact: true }),
  ).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-chat.png`,
    fullPage: true,
    caret: "initial",
  });
  await send(page, "a".repeat(3000));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("history retains complete recent turns within the context budget", () => {
  const history = Array.from({ length: 30 }, (_, index) => ({
    role: index % 2 ? ("assistant" as const) : ("user" as const),
    content: String(index).padEnd(3000, "x"),
  }));
  const bounded = boundedHistory(history, "x".repeat(8000));
  expect(bounded.length % 2).toBe(0);
  expect(bounded.length).toBeLessThanOrEqual(20);
  expect(
    bounded.reduce((sum, message) => sum + message.content.length, 8000),
  ).toBeLessThanOrEqual(32000);
  expect(bounded[0].role).toBe("user");
  expect(history).toHaveLength(30);
});

test("stop waiting restores the draft and discards late replies", async ({
  page,
}) => {
  await connect(page);
  let release!: () => void;
  const released = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/conversations/*/messages", async (route) => {
    await released;
    await route.fulfill({
      json: {
        message: { role: "assistant", content: "A stale response" },
        truncated: false,
      },
    });
  });
  await page.getByLabel("Message THRYV", { exact: true }).fill("Keep my draft");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.getByRole("button", { name: "Stop waiting" }).click();
  release();
  await expect(page.getByLabel("Message THRYV", { exact: true })).toHaveValue(
    "Keep my draft",
  );
  await expect(
    page.getByText("Stopped waiting.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("log")).toHaveCount(0);
  await page.unrouteAll({ behavior: "wait" });
  await expect(page.locator("main")).not.toContainText("A stale response");
});

test("another tab restores the account and conversation", async ({
  page,
  context,
}) => {
  await connect(page);
  await send(page, "Only in the first tab");
  const other = await context.newPage();
  await other.goto("/");
  await expect(other.getByRole("log")).toContainText("Only in the first tab");
  await other.close();
});

test("replacing the key preserves conversation and closes settings", async ({
  page,
}) => {
  await connect(page);
  await send(page, "Clear this when replacing the key");
  await page
    .getByRole("button", { name: "DeepSeek connected — provider settings" })
    .click();
  await page
    .getByLabel("DeepSeek API key", { exact: true })
    .fill("test-only-valid-key");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Connect new key" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("log")).toContainText(
    "Clear this when replacing the key",
  );
});

test("pairing, confirmation, truthful result, audit and revocation", async ({
  page,
}) => {
  await connect(page);
  await page
    .getByRole("button", { name: "Devices & Actions", exact: true })
    .click();
  await page.getByRole("button", { name: "Add device", exact: true }).click();
  const token = await page.getByLabel("Single-use pairing token").inputValue();
  const paired = await page.request.post(
    "http://127.0.0.1:8001/api/companion/pair",
    {
      data: { token, name: "Browser test laptop", platform: "Linux" },
    },
  );
  expect(paired.ok()).toBe(true);
  const device = await paired.json();
  const headers = { Authorization: `Bearer ${device.credential}` };
  await expect(
    page.getByRole("region", { name: "Devices", exact: true }),
  ).toContainText("online");
  await page.getByRole("button", { name: "Hide token" }).click();
  await page
    .getByRole("button", { name: "Devices & Actions", exact: true })
    .click();
  await send(page, "Open Chrome on my laptop.");
  await expect(page.getByRole("log")).toContainText("Nothing has executed yet");
  await expect(page.getByRole("log")).not.toContainText("I already opened it");
  const preApproval = await page.request.post(
    "http://127.0.0.1:8001/api/companion/poll",
    { headers },
  );
  expect((await preApproval.json()).action).toBeNull();
  const decision = page.waitForResponse(
    (r) => r.url().endsWith("/decision") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Allow action", exact: true }).click();
  expect((await decision).ok()).toBe(true);
  const poll = await page.request.post(
    "http://127.0.0.1:8001/api/companion/poll",
    { headers },
  );
  const action = (await poll.json()).action;
  expect(action.tool).toBe("open_application");
  // Desktop side effects are mocked in CI; manual verification uses real Chrome.
  expect(
    (
      await page.request.post(
        `http://127.0.0.1:8001/api/companion/actions/${action.id}/authorize`,
        { headers },
      )
    ).ok(),
  ).toBe(true);
  expect(
    (
      await page.request.post(
        `http://127.0.0.1:8001/api/companion/actions/${action.id}/result`,
        { headers, data: { code: "application_opened" } },
      )
    ).ok(),
  ).toBe(true);
  await expect(page.getByRole("log")).toContainText(
    "The application window opened on your device.",
  );
  await page
    .getByRole("button", { name: "Devices & Actions", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Recent Actions" }),
  ).toContainText("succeeded");
  await page
    .getByRole("button", { name: "Revoke Browser test laptop" })
    .click();
  await expect(
    page.getByRole("region", { name: "Devices", exact: true }),
  ).toContainText("revoked");
  expect(
    (
      await page.request.post("http://127.0.0.1:8001/api/companion/poll", {
        headers,
      })
    ).status(),
  ).toBe(401);
  await send(page, "Open Chrome on my laptop.");
  await expect(page.getByRole("log")).toContainText(
    "This device has been revoked",
  );
  await expect(
    page.getByRole("button", { name: "Allow action", exact: true }),
  ).toHaveCount(0);
});

test("sign out invalidates the session and signing in restores the chat", async ({
  page,
  context,
}) => {
  await connect(page);
  const email = await page.request
    .get("http://127.0.0.1:8001/api/account")
    .then((r) => r.json())
    .then((a) => a.email);
  await send(page, "Restore my saved chat");
  const oldSession = (await context.cookies()).find(
    (c) => c.name === "thryv_session",
  )!;
  await page
    .getByRole("button", { name: "Sign out", exact: true })
    .filter({ visible: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
  const rejected = await page.request.get("http://127.0.0.1:8001/api/account", {
    headers: { Cookie: `thryv_session=${oldSession.value}` },
  });
  expect(rejected.status()).toBe(401);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-password-for-browser");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("Restore my saved chat");
});
