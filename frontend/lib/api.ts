export type Message = { role: "user" | "assistant"; content: string };
export type Reply = { message: Message; truncated: boolean };
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

const errorMessages: Record<string, string> = {
  missing_key: "Connect your DeepSeek API key to continue.",
  invalid_key:
    "DeepSeek didn’t accept this key. Check or replace it in provider settings.",
  insufficient_balance:
    "Your DeepSeek account needs API credit. Add credit at DeepSeek, then try again.",
  rate_limited:
    "DeepSeek is receiving too many requests. Wait a moment, then try again.",
  provider_timeout: "DeepSeek took too long to respond. Please try again.",
  provider_unavailable:
    "DeepSeek is temporarily unavailable. Please try again shortly.",
  model_unavailable:
    "The configured DeepSeek model is unavailable. Contact the THRYV host.",
  provider_response:
    "DeepSeek returned an incomplete response. Please try again.",
  provider_rejected:
    "DeepSeek couldn’t process this request. Please try again.",
  content_filtered: "DeepSeek couldn’t answer this request. Try rephrasing it.",
  invalid_request:
    "Check your message and try again. Messages can contain up to 8,000 characters.",
  request_too_large:
    "This conversation request is too large. Try a shorter message or a new chat.",
  server_busy: "THRYV is busy. Please try again shortly.",
  internal_error: "THRYV couldn’t complete this request. Please try again.",
};

export async function apiRequest<T>(
  path: string,
  key: string,
  signal: AbortSignal,
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.any([signal, AbortSignal.timeout(70_000)]),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
    });
  } catch (error) {
    if (signal.aborted) throw error;
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError("provider_timeout", errorMessages.provider_timeout);
    }
    throw new ApiError(
      "connection_failed",
      "THRYV couldn’t reach its server. Check your connection and try again.",
    );
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      "invalid_response",
      "THRYV received an unreadable server response. Please try again.",
    );
  }
  if (!response.ok) {
    const code =
      typeof payload?.error?.code === "string"
        ? payload.error.code
        : "internal_error";
    // Render only our own copy; a proxy or upstream error could echo a credential.
    throw new ApiError(
      code,
      errorMessages[code] || errorMessages.internal_error,
    );
  }
  return payload as T;
}

export function boundedHistory(
  messages: Message[],
  nextMessage: string,
): Message[] {
  const history = messages.slice(-20);
  let length =
    nextMessage.length +
    history.reduce((sum, item) => sum + Array.from(item.content).length, 0);
  while (history.length && length > 32_000) {
    const turn = history.splice(0, 2);
    length -= turn.reduce(
      (sum, item) => sum + Array.from(item.content).length,
      0,
    );
  }
  return history;
}

export async function accountRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    const form = body instanceof URLSearchParams;
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        "X-THRYV-Request": "1",
        ...(body === undefined
          ? {}
          : {
              "Content-Type": form
                ? "application/x-www-form-urlencoded"
                : "application/json",
            }),
      },
      body:
        body === undefined
          ? undefined
          : form
            ? body.toString()
            : JSON.stringify(body),
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(70_000)])
        : AbortSignal.timeout(70_000),
      credentials: "include",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(
      "connection_failed",
      "THRYV couldn’t reach its server. Check your connection and try again.",
    );
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const code = payload?.error?.code || "internal_error";
    const accountErrors: Record<string, string> = {
      unauthenticated: "Sign in to continue.",
      auth_failed:
        "Check your email and password. New accounts need a unique email and a password of 12–128 characters.",
      vault_unavailable:
        "The host must configure secure provider storage before connecting a key.",
      consent_required: "Confirm encrypted storage to connect your key.",
      device_offline:
        "The device is offline or revoked. Start Companion and try again.",
      confirmation_session:
        "Approve this action in the browser session that requested it.",
      confirmation_expired: "This confirmation expired or was already used.",
      conversation_busy:
        "This conversation has a request or action in progress. Please wait.",
      not_found: "This item is unavailable.",
      csrf_rejected:
        "The host’s browser origin configuration does not match this page.",
    };
    throw new ApiError(
      code,
      accountErrors[code] ||
        errorMessages[code] ||
        errorMessages.internal_error,
    );
  }
  if (payload === null)
    throw new ApiError(
      "invalid_response",
      "THRYV received an unreadable response.",
    );
  return payload as T;
}

export type Account = {
  id: string;
  email: string;
  provider_connected: boolean;
};
export type Conversation = { id: string; title: string; messages?: Message[] };
export type Device = {
  id: string;
  name: string;
  status: string;
  platform: string;
  last_seen: number;
};
export type Action = {
  id: string;
  device_id: string;
  conversation_id: string | null;
  tool: string;
  arguments: { application?: string };
  permission: string;
  status: string;
  expires_at: number;
  created_at: number;
  result: string | null;
};
