# Gates

Required before acceptance:

- all JSON artifacts validate with `python3 -m json.tool`;
- capability IDs unique;
- no contradictory duplicate endpoint claims within matrix;
- mutable capabilities require explicit approval, idempotency and read-back;
- scanner de segredos passes;
- scanner of raw IDs in closure passes;
- `git diff --check` passes;
- Roadmap, graph and curation unchanged;
- zero external mutation confirmed.

This mission must not run unrelated large test suites.
