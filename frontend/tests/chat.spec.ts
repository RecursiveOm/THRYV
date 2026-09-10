import { test, expect, type Page } from "@playwright/test";
import { boundedHistory } from "../lib/api";

async function connect(page: Page) {
  await page.goto("/");
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
  await page
    .getByRole("button", { name: "Disconnect & clear session" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Make yourself at home." }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("invalid key is clean and allows retry", async ({ page }) => {
  await page.goto("/");
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

test("credentials and conversations are not persisted or put in URLs", async ({
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
  await expect(
    page.getByRole("heading", { name: "Make yourself at home." }),
  ).toBeVisible();
  await expect(
    page.getByLabel("DeepSeek API key", { exact: true }),
  ).toHaveValue("");
  await expect(page.locator("body")).not.toContainText("Private session text");
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
  await page.route("**/api/provider/connect", (route) => route.abort("failed"));
  await page.goto("/");
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

test("new conversation confirms clearing and retains the connection", async ({
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
  await page.route("**/api/chat", async (route) => {
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

test("another tab starts without credentials or conversation", async ({
  page,
  context,
}) => {
  await connect(page);
  await send(page, "Only in the first tab");
  const other = await context.newPage();
  await other.goto("/");
  await expect(
    other.getByLabel("DeepSeek API key", { exact: true }),
  ).toHaveValue("");
  await expect(other.locator("main")).not.toContainText(
    "Only in the first tab",
  );
  await other.close();
});

test("replacing the key clears conversation and closes settings", async ({
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
  await page.getByRole("button", { name: "Connect new key" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "What’s on your mind?" }),
  ).toBeVisible();
  await expect(page.locator("main")).not.toContainText(
    "Clear this when replacing the key",
  );
});
