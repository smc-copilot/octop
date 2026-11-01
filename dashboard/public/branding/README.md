# branding/

Company-owned dashboard overlay. Core Octop theme files (`theme-vars.css`, `layout.css`, Sidebar) stay untouched.

`index.html` loads `%BASE_URL%branding/enterprise.css` at the end of `<body>` so it wins over hashed CSS.

## Swap logo assets

Drop replacements in this directory (not required for the overlay to work):

| File                        | Use                               |
| --------------------------- | --------------------------------- |
| `logo-horizontal-light.png` | Light-theme wordmark              |
| `logo-horizontal-dark.png`  | Dark-theme wordmark               |
| `logo-mark.png`             | Collapsed sidebar icon (optional) |

Then uncomment the “optional asset swap” block at the bottom of `enterprise.css`. Until those files exist, Octop’s built-in wordmarks are only framed in place.
