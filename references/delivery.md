# PDF / Image Delivery to Telegram

**Pattern (agent delivery)**

- Use the project's messaging tool with an explicit `target` configured for the
  operator's environment (e.g. a Telegram chat/topic the operator owns).
- Prefer: `send_message(action='send', target='<operator-configured-target>', message="text\n\nMEDIA:/path/to/file")`
- Never use bare `MEDIA:` in final responses without a configured target.
- Never omit `target`.

Configure delivery targets in local operator config; do not hard-code personal
chat IDs, usernames, or topics in the public repository.
