---
name: business-ui-forms
description: Use Business UI cards for external published forms. Never assert submit success.
---

# Business UI forms

When the user wants to fill an official business form (for example recruiting two implementation consultants):

1. Call `business_ui_draft` with a **logical** `form_ref` (never a URL) and a short summary.
2. Do **not** say the document was created or submitted. The card is an unclaimed draft.
3. The user must click 核对并编辑. Ownership is bound only after an authenticated Host action.
4. Never put secrets, authorization codes, or tickets in chat.

Administrators configure approved connections with `business_ui_connections`.
