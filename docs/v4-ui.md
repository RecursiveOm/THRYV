# V4 interface cleanup

This is a frontend-only refinement of V4. Tools, permissions, confirmations, OAuth,
voice processing and backend APIs retain their existing boundaries.

- The sidebar contains searchable conversations, selection state and grouped utilities.
  On phones it becomes a dismissible drawer with focus containment and Escape support.
- Chat keeps messages, relevant confirmations/results, the input and a contextual device
  picker. Decorative sidebar copy, the extra active-conversation box and verbose greeting
  and loading copy are removed.
- Settings is a full-page view with General, Voice, Appearance, Provider, Devices,
  Workspaces, Connected Apps, Memory, Privacy and Account sections. Hash URLs support
  reload/back navigation and retain the selected conversation. Unsaved drafts remain
  while navigating within the app. Reloading does not persist unsent drafts.
- Talk stays beside the composer. Read reply, automatic spoken replies and fixed-keyword
  Wake Beta settings are grouped under Voice options and also available in Settings.
  Finish/Cancel/Stop and live microphone status remain visible when relevant. A single
  voice controller renders into either surface; navigation does not create another mic
  owner. Active voice status remains visible while another settings section is open.
- Light, Dark and System themes use shared surface/text/border/status tokens. The theme
  persists on this browser, follows system changes in System mode, and syncs across tabs.
  Automatic voice replies persist locally per account; the wake toggle continues using
  the existing account-owned server setting. These preferences contain no credentials.
- Workspace setup instructions are behind an explicit disclosure. Exact action arguments,
  proposed edits, captured results, permission labels and approval controls remain intact.

Browser checks use synthetic accounts and mocked provider/desktop effects. Theme, draft,
conversation navigation and voice preference tests run on desktop and mobile alongside
existing chat, provider, device/action, memory, workspace, integration and wake/VAD tests.
Visual checks cover light/dark chat and mobile settings. The full backend suite is not
needed for this change; no backend or Companion files were modified.
