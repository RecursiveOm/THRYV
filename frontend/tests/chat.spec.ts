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
  await page.getByRole("dialog").getByRole("checkbox").check();
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

test("V2 explicit memory persists and can be disabled, deleted and cleared", async ({
  page,
}) => {
  await connect(page);
  await send(page, "Remember that I prefer Python projects to use uv.");
  await expect(page.getByRole("log")).toContainText(
    "Saved to your personal memory",
  );
  await page
    .getByRole("button", { name: "New conversation", exact: false })
    .first()
    .click();
  await page.getByRole("button", { name: "Start a new conversation" }).click();
  await send(page, "What Python package workflow do I prefer?");
  await expect(page.getByRole("log")).toContainText("You prefer uv");
  await page.reload();
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  const panel = page.getByRole("region", { name: "Personal memory" });
  await expect(panel).toContainText("Python projects to use uv");
  await panel.getByRole("checkbox").uncheck();
  await expect(panel.getByLabel("Remember something")).toBeDisabled();
  await panel.getByRole("checkbox").check();
  await expect(panel.getByLabel("Remember something")).toBeEnabled();
  await panel
    .getByRole("button", { name: "Delete memory", exact: true })
    .click();
  await expect(panel).toContainText("0/200");
  await panel
    .getByLabel("Remember something")
    .fill("My favorite tea is jasmine.");
  await panel.getByRole("button", { name: "Save memory", exact: true }).click();
  await expect(panel).toContainText("1/200");
  page.once("dialog", (dialog) => dialog.accept());
  await panel
    .getByRole("button", { name: "Clear all memories", exact: true })
    .click();
  await expect(panel).toContainText("0/200");
});

test("V2 memory rejects secrets without echoing them", async ({ page }) => {
  await connect(page);
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  const panel = page.getByRole("region", { name: "Personal memory" });
  await panel
    .getByLabel("Remember something")
    .fill("My password is test-secret-sentinel");
  await panel.getByRole("button", { name: "Save memory", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("cannot be saved");
  await expect(panel.getByRole("alert")).not.toContainText(
    "test-secret-sentinel",
  );
  await expect(panel).toContainText("0/200");
});

test("V2 microphone denial falls back to text", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: async () => {
        throw new DOMException("Permission denied", "NotAllowedError");
      },
    });
  });
  await connect(page);
  await page.getByRole("button", { name: "Talk to THRYV" }).click();
  await expect(
    page.getByRole("region", { name: "Voice", exact: true }).getByRole("alert"),
  ).toContainText("permission denied");
  await send(page, "Text still works");
  await expect(page.getByRole("log")).toContainText("your personal AI");
});

test("V2 captured voice uses SAFE tool and real audio playback can stop", async ({
  page,
  context,
}) => {
  const spoken: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/voice/speak"))
      spoken.push(request.postDataJSON().text);
  });
  await context.grantPermissions(["microphone"]);
  await connect(page);
  const headers = { Origin: "http://127.0.0.1:3001", "X-THRYV-Request": "1" };
  const token = (
    await (
      await page.request.post("http://127.0.0.1:8001/api/devices/pairing", {
        headers,
      })
    ).json()
  ).token;
  const paired = await (
    await page.request.post("http://127.0.0.1:8001/api/companion/pair", {
      data: { token, name: "Voice laptop", platform: "Linux" },
    })
  ).json();
  await expect(page.getByLabel("Device", { exact: true })).toHaveValue(
    paired.device_id,
  );
  await page.getByRole("button", { name: "Talk to THRYV" }).click();
  await expect(
    page.getByRole("button", { name: "Finish voice message" }),
  ).toBeVisible();
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: "Finish voice message" }).click();
  await expect(page.getByRole("log")).toContainText(
    "Get system information from my paired device",
  );
  await expect(page.getByRole("log")).toContainText(
    "Waiting for your Companion",
  );
  const auth = { Authorization: `Bearer ${paired.credential}` };
  const action = (
    await (
      await page.request.post("http://127.0.0.1:8001/api/companion/poll", {
        headers: auth,
      })
    ).json()
  ).action;
  expect(action.tool).toBe("get_system_info");
  await page.request.post(
    `http://127.0.0.1:8001/api/companion/actions/${action.id}/result`,
    {
      headers: auth,
      data: { code: "system_info", platform: "Linux", architecture: "x86_64" },
    },
  );
  await expect(page.getByRole("log")).toContainText("Device reports Linux");
  const voice = page.getByRole("region", { name: "Voice", exact: true });
  await expect
    .poll(() => spoken.some((text) => text.includes("Device reports Linux")))
    .toBe(true);
  expect(
    spoken.some((text) => text.includes("Waiting for your Companion")),
  ).toBe(false);
  await voice.getByRole("checkbox", { name: "Speak voice replies" }).uncheck();
  await page.getByRole("button", { name: "Read reply", exact: true }).click();
  await expect(voice.getByRole("status")).toHaveText("Speaking…");
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
  await expect(voice.getByRole("status")).toHaveText("Ready");
});

test("V2 memory setting reverts when the server rejects the change", async ({
  page,
}) => {
  await connect(page);
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  const panel = page.getByRole("region", { name: "Personal memory" });
  await expect(panel).toContainText("0/200");
  await page.route("**/api/memories/settings", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: '{"error":{"code":"server_busy"}}',
    }),
  );
  await panel.getByRole("checkbox").click();
  await expect(panel.getByRole("alert")).toContainText("Could not change");
  await expect(panel.getByRole("checkbox")).toBeChecked();
  await expect(panel.getByLabel("Remember something")).toBeEnabled();
});

test("V2 cancelling capture releases the microphone without sending audio", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["microphone"]);
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices,
    );
    const tracks: MediaStreamTrack[] = [];
    Object.defineProperty(window, "voiceTracks", { value: tracks });
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      const stream = await original(constraints);
      tracks.push(...stream.getTracks());
      return stream;
    };
  });
  let transcriptions = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/voice/transcribe")) transcriptions++;
  });
  await connect(page);
  await page.getByRole("button", { name: "Talk to THRYV" }).click();
  await expect(
    page.getByRole("button", { name: "Finish voice message" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "Voice", exact: true })
      .getByRole("status"),
  ).toHaveText("Ready");
  expect(
    await page.evaluate(() => {
      const tracks = (window as unknown as { voiceTracks: MediaStreamTrack[] })
        .voiceTracks;
      return tracks.length > 0 && tracks.every((t) => t.readyState === "ended");
    }),
  ).toBe(true);
  expect(transcriptions).toBe(0);
});

async function syntheticUtterances(page: Page, count: number) {
  await page.addInitScript(
    ({ count }) => {
      let remaining = count;
      const original = navigator.mediaDevices.getUserMedia.bind(
        navigator.mediaDevices,
      );
      const tracks: MediaStreamTrack[] = [];
      Object.defineProperty(window, "wakeTracks", { value: tracks });
      navigator.mediaDevices.getUserMedia = async (constraints) => {
        const microphone = await original(constraints);
        const context = new AudioContext();
        const destination = context.createMediaStreamDestination();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        gain.gain.value = 0;
        oscillator.connect(gain);
        gain.connect(destination);
        oscillator.start();
        if (remaining-- > 0) {
          const now = context.currentTime;
          gain.gain.setValueAtTime(0.1, now + 0.15);
          gain.gain.setValueAtTime(0, now + 0.7);
          // A short internal pause must not cause an early submission.
          gain.gain.setValueAtTime(0.1, now + 1.15);
          gain.gain.setValueAtTime(0, now + 1.7);
        }
        for (const track of destination.stream.getTracks()) {
          tracks.push(track);
          const stop = track.stop.bind(track);
          track.stop = () => {
            stop();
            microphone.getTracks().forEach((t) => t.stop());
            oscillator.stop();
            void context.close();
          };
        }
        await context.resume();
        return destination.stream;
      };
    },
    { count },
  );
}

async function wakeToggle(page: Page) {
  const voice = page.getByRole("region", { name: "Voice", exact: true });
  await voice.getByText("Settings", { exact: true }).click();
  return voice.getByRole("checkbox", { name: /Wake word \(Beta\)/ });
}

test("V2 VAD ignores clicks and short pauses, then finishes after natural silence", async () => {
  const { VoiceActivity } = await import("../lib/voice-activity");
  const vad = new VoiceActivity();
  const sound = new Float32Array(160).fill(0.1),
    silence = new Float32Array(160);
  expect(vad.push(sound, 16000)).toBe(false);
  for (let i = 0; i < 200; i++) expect(vad.push(silence, 16000)).toBe(false);
  for (let i = 0; i < 50; i++) expect(vad.push(sound, 16000)).toBe(false);
  for (let i = 0; i < 80; i++) expect(vad.push(silence, 16000)).toBe(false);
  for (let i = 0; i < 50; i++) expect(vad.push(sound, 16000)).toBe(false);
  for (let i = 0; i < 129; i++) expect(vad.push(silence, 16000)).toBe(false);
  expect(vad.push(silence, 16000)).toBe(true);
});

test("V2 Talk automatically finishes once, preserving short pauses", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["microphone"]);
  await syntheticUtterances(page, 1);
  let sent = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/voice/transcribe")) sent++;
  });
  await connect(page);
  await page.getByRole("button", { name: "Talk to THRYV" }).click();
  await expect(
    page.getByRole("button", { name: "Finish voice message" }),
  ).toBeVisible();
  await page.waitForTimeout(1800);
  expect(sent).toBe(0);
  await expect(page.getByRole("log")).toContainText(
    "Get system information from my paired device",
    { timeout: 10000 },
  );
  expect(sent).toBe(1);
});

test("V2 wake preference persists, unrelated speech is ignored, and Off releases capture", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["microphone"]);
  await syntheticUtterances(page, 1);
  let checked = 0,
    chats = 0;
  await page.route("**/api/voice/wake", (route) => {
    checked++;
    return route.fulfill({ json: { detected: false, command: "" } });
  });
  page.on("request", (request) => {
    if (/\/messages$/.test(request.url()) && request.method() === "POST")
      chats++;
  });
  await connect(page);
  const toggle = await wakeToggle(page);
  await expect(toggle).not.toBeChecked();
  await expect(page.getByText(/Beta may miss invocations/)).toBeVisible();
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  const status = page
    .getByRole("region", { name: "Voice", exact: true })
    .getByRole("status");
  await expect(status).toHaveText("Wake listening for THRYV…");
  await expect.poll(() => checked).toBe(1);
  await expect(status).toHaveText("Wake listening for THRYV…");
  expect(chats).toBe(0);
  await page.reload();
  const restored = await wakeToggle(page);
  await expect(restored).toBeChecked();
  await expect(status).toHaveText("Wake listening for THRYV…");
  await restored.uncheck();
  await expect(status).toHaveText("Ready");
  expect(
    await page.evaluate(() =>
      (
        window as unknown as { wakeTracks: MediaStreamTrack[] }
      ).wakeTracks.every((t) => t.readyState === "ended"),
    ),
  ).toBe(true);
  await page.reload();
  await expect(await wakeToggle(page)).not.toBeChecked();
  expect(chats).toBe(0);
});

test("V2 wake keyword alone opens command capture and Cancel stops it", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["microphone"]);
  await syntheticUtterances(page, 1);
  await page.route("**/api/voice/wake", (route) =>
    route.fulfill({ json: { detected: true, command: "" } }),
  );
  await connect(page);
  await (await wakeToggle(page)).check();
  await expect(
    page.getByRole("button", { name: "Finish voice message" }),
  ).toBeVisible({ timeout: 10000 });
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
  const voice = page.getByRole("region", { name: "Voice", exact: true });
  await expect(voice.getByRole("status")).toHaveText("Ready");
  await expect(voice).toContainText("Wake listening is paused");
  expect(
    await page.evaluate(() =>
      (
        window as unknown as { wakeTracks: MediaStreamTrack[] }
      ).wakeTracks.every((t) => t.readyState === "ended"),
    ),
  ).toBe(true);
  await expect(page.getByRole("log")).toHaveCount(0);
});

test("V2 one-shot wake command enforces confirmation and dispatches only once", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["microphone"]);
  await syntheticUtterances(page, 1);
  await page.route("**/api/voice/wake", (route) =>
    route.fulfill({
      json: { detected: true, command: "Open Chrome on my laptop." },
    }),
  );
  await connect(page);
  const headers = { Origin: "http://127.0.0.1:3001", "X-THRYV-Request": "1" };
  const token = (
    await (
      await page.request.post("http://127.0.0.1:8001/api/devices/pairing", {
        headers,
      })
    ).json()
  ).token;
  const paired = await (
    await page.request.post("http://127.0.0.1:8001/api/companion/pair", {
      data: { token, name: "Wake laptop", platform: "Linux" },
    })
  ).json();
  await expect(page.getByLabel("Device", { exact: true })).toHaveValue(
    paired.device_id,
  );
  const auth = { Authorization: `Bearer ${paired.credential}` };
  await (await wakeToggle(page)).check();
  await expect(
    page.getByRole("button", { name: "Allow action", exact: true }),
  ).toBeVisible({ timeout: 15000 });
  expect(
    (
      await (
        await page.request.post("http://127.0.0.1:8001/api/companion/poll", {
          headers: auth,
        })
      ).json()
    ).action,
  ).toBeNull();
  await expect(page.getByRole("log")).toContainText("Nothing has executed yet");
  await page.getByRole("button", { name: "Allow action", exact: true }).click();
  await expect(page.getByRole("log")).toContainText(
    "Waiting for your Companion",
  );
  const action = (
    await (
      await page.request.post("http://127.0.0.1:8001/api/companion/poll", {
        headers: auth,
      })
    ).json()
  ).action;
  expect(action.tool).toBe("open_application");
  expect(
    (
      await (
        await page.request.post("http://127.0.0.1:8001/api/companion/poll", {
          headers: auth,
        })
      ).json()
    ).action,
  ).toBeNull();
  await page.request.post(
    `http://127.0.0.1:8001/api/companion/actions/${action.id}/result`,
    { headers: auth, data: { code: "application_opened" } },
  );
  await expect(page.getByRole("log")).toContainText(
    "The application window opened on your device",
  );
  expect(
    (await (await page.request.get("http://127.0.0.1:8001/api/actions")).json())
      .length,
  ).toBe(1);
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
});

test("V2 repeated wake commands resume listening without duplicate submissions", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["microphone"]);
  await syntheticUtterances(page, 2);
  await page.route("**/api/voice/wake", (route) =>
    route.fulfill({ json: { detected: true, command: "Hello THRYV" } }),
  );
  let sent = 0;
  page.on("request", (request) => {
    if (/\/messages$/.test(request.url()) && request.method() === "POST")
      sent++;
  });
  await connect(page);
  await (await wakeToggle(page)).check();
  await expect.poll(() => sent, { timeout: 20000 }).toBe(2);
  await expect(
    page
      .getByRole("region", { name: "Voice", exact: true })
      .getByRole("status"),
  ).toHaveText("Wake listening for THRYV…", { timeout: 10000 });
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
  expect(sent).toBe(2);
});

test("V2 only one tab can own wake capture", async ({ page, context }) => {
  await context.grantPermissions(["microphone"]);
  await syntheticUtterances(page, 0);
  await connect(page);
  await (await wakeToggle(page)).check();
  const voice = page.getByRole("region", { name: "Voice", exact: true });
  await expect(voice.getByRole("status")).toHaveText(
    "Wake listening for THRYV…",
  );
  const second = await context.newPage();
  await syntheticUtterances(second, 0);
  await second.goto("/");
  await expect(
    second.getByRole("button", { name: "Talk to THRYV" }),
  ).toBeVisible();
  const activeTracks = (tab: Page) =>
    tab.evaluate(
      () =>
        (
          window as unknown as { wakeTracks: MediaStreamTrack[] }
        ).wakeTracks.filter((t) => t.readyState === "live").length,
    );
  await expect
    .poll(async () => (await activeTracks(page)) + (await activeTracks(second)))
    .toBe(1);
  const locks = await second.evaluate(
    async () =>
      (await navigator.locks.query()).held?.filter(
        (lock) => lock.name === "thryv-voice",
      ).length,
  );
  expect(locks).toBe(1);
  await second.close();
  await page.getByRole("button", { name: "Stop voice", exact: true }).click();
  expect(await activeTracks(page)).toBe(0);
});
