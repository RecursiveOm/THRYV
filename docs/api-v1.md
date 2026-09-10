# V1 API contracts

Local server: `http://localhost:8000`. Account writes require the session cookie plus `Origin: http://localhost:3000` and `X-THRYV-Request: 1`. Never pass tokens or keys in URLs. All API responses are `Cache-Control: no-store`. Controlled errors have `{ "error": { "code": "...", "message": "..." } }`; UI uses its own fixed error copy.

## Account and provider

| Method/path | Request | Result |
| --- | --- | --- |
| POST `/api/auth/register` | JSON `email`, `password` | 201 account metadata; does not sign in |
| POST `/api/auth/login` | Form `username` (email), `password` | 204 + HttpOnly session cookie |
| POST `/api/auth/logout` | None | 204; invalidates current session |
| GET `/api/account` | None | `id`, `email`, `provider_connected`; never a key |
| POST `/api/account/provider` | JSON `api_key`, `consent_to_store: true` | Verify and encrypt own key |
| DELETE `/api/account/provider` | None | Remove own saved key |
| GET `/api/account/permissions` | None | Fixed tool names/permissions/targets, unknown tools BLOCKED |

## Conversations

| Method/path | Behavior |
| --- | --- |
| GET `/api/conversations?offset=0` | At most 50 owned chats, newest activity first |
| POST `/api/conversations` | Optional `title` (120 chars), returns new owned ID |
| GET `/api/conversations/{id}` | Owned title/metadata + up to 100 recent turns, chronological |
| POST `/api/conversations/{id}/messages` | `message` (1–8000 chars), UUID `request_id`, optional UUID `device_id` |
| DELETE `/api/conversations/{id}` | Delete owned chat/turns; reject while a reply/action is pending; keep action audit |

Sending a message returns `message`, `truncated`, and optional `action`. Stored history is assembled by the server, not accepted from this endpoint. Reusing the same request ID and text retrieves the existing response without calling the model again; different text with that ID fails. A conversation has one bounded generation lease. After a stopped/failed wait, inspect the saved chat and actions before manually retrying. The legacy stateless `/api/chat` endpoint remains separate.

## Devices and actions

| Method/path | Behavior |
| --- | --- |
| GET `/api/devices` | At most 100 owned devices with online/offline/revoked status and last seen |
| POST `/api/devices/pairing` | One secret pairing `token`, `expires_in: 300` |
| DELETE `/api/devices/{id}` | Revoke own device credential; cancel pending work |
| GET `/api/actions` | At most 100 owned audit records, lazily expire overdue actions |
| POST `/api/actions` | Direct authorized action request: UUID `request_id`, UUID `device_id`, `tool`, validated `arguments` |
| POST `/api/actions/{id}/decision` | Strict boolean `allow`; initiating account/session only, single-use |

The direct action API follows exactly the same registry/ownership/confirmation rules as the orchestrator. The browser normally obtains action requests through chat. Action statuses: `pending_confirmation`, `queued`, `running`, `succeeded`, `failed`, `cancelled`, `expired`. `pending_confirmation` lasts 120 seconds; dispatch/execution lasts 30 seconds. Offline means no valid heartbeat in 15 seconds. Opening Chrome/VS Code always requires CONFIRM; basic system information is SAFE.

## Companion (independent scoped bearer credential)

| Method/path | Behavior |
| --- | --- |
| POST `/api/companion/pair` | Secret `token`, `name` (1–80 safe chars), `platform`; returns `device_id` and secret `credential` once |
| POST `/api/companion/poll` | Authenticate device, heartbeat, atomically claim at most one queued action |
| POST `/api/companion/actions/{id}/authorize` | Recheck that own action is running, unexpired, and device is not revoked |
| POST `/api/companion/actions/{id}/result` | Submit a fixed result `code`; optional bounded OS/architecture enums |

All routes after pairing require `Authorization: Bearer <device credential>`. Pairing requires the single-use capability, not an account cookie or user ID. Device credentials cannot use browser account routes. Poll returns `{ "action": null }` or an action containing ID, tool, arguments, and expiry. The poll claim is never automatically redelivered.

Result codes: `application_opened`, `application_missing`, `launch_failed`, `launch_unconfirmed`, `unsupported_platform`, `system_info`, `timeout`, `blocked`, `execution_uncertain`. Raw stdout/stderr, arbitrary error strings, and fabricated success types are rejected. The backend verifies result/tool compatibility and accepts only one result before expiry. A valid Companion is trusted to report what it observed.
