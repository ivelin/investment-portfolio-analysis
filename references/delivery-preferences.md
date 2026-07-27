# Telegram PDF Delivery Preferences (User-Corrected)

User has zero tolerance for repeated delivery failures on PDF reports (Weed the Garden, performance reviews, etc.).

Enforced rule:
- Deliver PDFs as instant native Telegram attachment.
- Use ONLY the bare `MEDIA:/absolute/path/to/file` tag in the final response.
- No surrounding text, no "here is the report", no file paths in prose, no "ready for download".
- The attachment must appear immediately with nothing else in the message.
- This was established after multiple explicit corrections: "Send it correctly", "I don’t have easy access to your file system", "Sick of repeating over and over".

Implementation:
- Generate PDF to /tmp/ first.
- In final response, output exactly: MEDIA:/tmp/Weeding_the_Garden_Report_Improved.pdf (or equivalent path).
- If bare MEDIA fails in context, fall back to send_message with target and MEDIA inside the message body only.

This overrides any generic send_message instructions in the main SKILL.md.