---
lat:
  require-code-mention: true
---

# Tests

Executable specifications for market governance and related unit coverage.

## Market catalog policy

Unit coverage for [[domain#Market governance|MarketCatalogPolicy]] mode gates, allowlist resolution, and audit recording.

### Off mode blocks market

`market_mode=off` raises `MARKET_DISABLED` before any catalog or install call.

### Public mode allows install

`public` mode permits skill and skillset install without consulting allowlist rules.

### Mirror only blocks remote catalog

`mirror_only` forbids remote catalog browse while still allowing install-by-slug for mirroring.

### Allowlist default deny

With no matching rules, allowlist mode denies install (default-closed).

### Group rule overrides global

A group allow overrides a global deny for members of that group; non-members stay denied.

### Deny beats allow at same priority

When allow and deny share priority, deny wins.

### Skillset children filtered

Installing a skillset also requires every listed child skill slug to pass the same allowlist.

### Filter skillset items

List/browse filters drop skillset cards whose slug is not allowed.

### Audit record

`record()` forwards market actions to the audit sink without failing the request path on sink errors.
