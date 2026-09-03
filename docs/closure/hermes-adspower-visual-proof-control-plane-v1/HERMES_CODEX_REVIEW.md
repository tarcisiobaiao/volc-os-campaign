# HERMES_CODEX_REVIEW — delta real

**Modo:** revisão focal Bia/OpenAI-Codex sobre o delta produzido pelo executor Claude, antes da correção única.  
**Escopo:** arquivos modificados/untracked da branch `sprint/hermes-adspower-visual-proof-control-plane-v1`.  
**Não é revisão cross-provider.** Gemini é tratado separadamente e sua ausência não bloqueia.

## Achados

| ID | Categoria | Classificação | Evidência | Ação |
|---|---|---|---|---|
| HCR-001 | Exposição de referência privada no frontend | bloqueante reproduzido | `ProntidaoVisual.tsx` renderizava `<span title={artefato.referencia}>`, expondo `vpartifact://...` inteiro no DOM, contrariando o contrato de hash curto | removido atributo `title`; teste agora recusa `vpartifact://` no HTML |
| HCR-002 | Caminho absoluto em saúde do broker | importante reproduzido | `ConfiguracaoDoBroker.saude()` publicava `artefatos_dir` absoluto; não é segredo, mas revela layout do host isolado | substituído por marcador `artefatos: diretorio_privado_configurado`; teste recusa `artefatos_dir` e `tmp_path` na saúde |
| HCR-003 | Segredo em log/erro/recibo/JSON público | refutado | E2E varre sentinela e token sintético em recibos/log/saúde; script estrutural varre material de credencial | sem ação adicional |
| HCR-004 | SSRF/redirect privado/DNS fail-open | refutado no núcleo hermético | domínio valida URL inicial, DNS injetado, IPs privados/link-local/metadata/multicast e redirect privado; E2E cobre casos | sem ação adicional |
| HCR-005 | Broker público/autenticação fraca/token em query | refutado | bind exige IP literal loopback; Bearer obrigatório; compare_digest; rotas recusam path extra; log HTTP suprimido | sem ação adicional |
| HCR-006 | Owner/profile arbitrário/operação fora da allowlist | refutado | `user_id` e localizador só na allowlist; payload recusa extras; owner/ativo/operação/credencial checados antes de resolver segredo | sem ação adicional |
| HCR-007 | Idempotência/concorrência/lease/cleanup | não bloqueante | lease em memória e cleanup sob exceção testados; durabilidade multi-processo declarada como limitação | handoff de persistência futura |
| HCR-008 | Screenshot inexistente/timeout técnico como aprovado | refutado | avaliação automática só produz `eligible_for_human_review`, `needs_correction` ou `indeterminate`; `approved` exige humano | sem ação adicional |
| HCR-009 | Processo/browser abandonado | não verificável para real; refutado no fake | fake e broker usam context managers; driver real recusa; cleanup de perfil aberto pelo próprio processo é testado | checkpoint externo futuro |
| HCR-010 | Hermeticidade | refutado após correção | `scripts/provar_visual_proof_hermetico.py` retorna `veredito: hermetico`, 21 provas, 0 falhas | sem ação adicional |

## Rodada corretiva única

Aplicada somente para HCR-001 e HCR-002. Nenhuma terceira execução Claude foi aberta.
