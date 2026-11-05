# Tests

Executable specifications linked from unit tests via `@lat` comments. Add `require-code-mention` frontmatter when every leaf section must have a matching code ref.

Market catalog policy specs were removed with the `cursor/market-policy-1102` revert; reintroduce them when that feature lands again.

## Mail expert connector

Unit coverage for the personal-mailbox gateway used by Mail Expert.

### Structured search and BODY.PEEK

`search_emails` builds IMAP criteria from structured filters and pages newest-first via `offset`/`limit`. `read_email` uses `BODY.PEEK[]` and returns an `octop_ui` envelope, with plain `body` plus sanitized `body_html`.

### Two-phase send confirmation

Dry-run issues a one-shot token; confirm consumes it once; replay fails. HITL `when` only matches calls that include `confirmation_token`.

### Plugin host read bridge isolation

The host bridge denies write tools, guides when no personal instance exists, and never returns credential fields in the payload.
