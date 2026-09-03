# Remaining risks

- **Live n8n not inspected**: mission hard stop forbids importing/altering live n8n. Versioned workflows are covered; a manually edited live workflow remains outside this branch's proof.
- **In-process malicious code can call `emitir()` with invented semantic strings**: no HMAC prevents the same process from asking the authority to sign lies. Mitigation here is structural: production emitters outside `POST /api/trafego/subir` fail `scripts/gate_autoridade_de_nascimento.py`.
- **Structural scanner is not whole-program analysis**: it catches direct imports/attributes/SDK tokens in Python files and known workflow tokens. It is a guardrail, not formal verification.
- **Activation remains out of scope**: this lane proves birth is PAUSED and no implicit activation exists in the touched path; it does not create an activation authority.
- **Inherited stale assertion fixed in `volc_ads/testes_subir.py`**: base already failed `caso_nada_pede_sozinho` because `subir.py` imports `isencao`; takeover corrected the test to assert the narrower safety contract.
