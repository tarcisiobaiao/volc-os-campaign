# Meta MCP Boundary

Official source: https://developers.facebook.com/documentation/mcp (updated Jun 12 2026, read 2026-09-04).

Allowed: developer documentation search, app/compliance/status assistance under explicit Read scopes.

Not allowed as VOLC data plane: production campaign sync, token resolution, mutating campaigns, uploading assets, budget/bid changes, activation.

Risk: Meta docs warn that AI agents act with granted scopes and can be manipulated by prompt injection in untrusted content. Therefore Manage scope is blocked until separate controls exist: isolated dev app, scoped account, human approval, command allowlist, audit log, and no untrusted content in same agent context.
