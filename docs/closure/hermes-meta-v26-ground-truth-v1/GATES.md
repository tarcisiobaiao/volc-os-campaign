# Gates

Required before acceptance:

- all JSON artifacts validate with `python3 -m json.tool`;
- capability IDs unique;
- every capability-matrix ID maps exactly once to an existing security capability;
- uploads and rename have separate security capabilities;
- UI fields have server ownership and an API binding; canonical navigation emits `rede=meta`;
- Insights grain includes provider, account, object level/id, date, attribution window and breakdown key;
- asset import reuses `criativo_master`; Meta upload IDs live only in account-scoped associations;
- no contradictory duplicate endpoint claims within matrix;
- mutable capabilities require explicit approval, idempotency and read-back;
- scanner de segredos passes;
- scanner of raw IDs in closure passes;
- `git diff --check` passes;
- Roadmap, graph and curation unchanged;
- zero external mutation confirmed.

This mission must not run unrelated large test suites.
