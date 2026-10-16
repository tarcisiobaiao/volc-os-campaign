# Resposta à revisão R1 (consolidada pelo integrador)

Detalhe por frente, com teste que falha antes e passa depois: `HANDOFF-A.md` §7–§7.2, `HANDOFF-B.md` §8,
`HANDOFF-C.md` "Resposta à R1", `03-MATRIZ-DE-ATRIBUICAO.md` §9. Verificação independente: tabela da R2 em
`REVISAO-ADVERSARIAL-R2.md`.

| # | Resposta | Verificação R2 |
|---|---|---|
| F1 | `available_at` ≥ primeiro recebimento dos bytes pelo relógio do banco (`dil_obs._agora()`); `lote.recebido_em` é o relógio do banco | corrigido |
| F2 | membresia do aplicador revogada; na R2, só superusuário aplica (G1) | parcial na R2 → corrigido em G1 |
| F3 | fonte/coletor/schema conferidos contra run/lote; run finalizado não recebe | corrigido |
| F4 | moeda só com prova (`moeda_nao_provada`/`moeda_divergente`) | corrigido |
| F5 | identidade de linha na receita; grão misto, duplicata e futuro recusados; na R2, futuro obrigatório também para custo/earnings (G14) | corrigido |
| F6 | cliques None → `nao_coletado`; sessões `nao_atribuivel` pela matriz; zero de sessão só com sensor no host | corrigido |
| F7 | 4 GAQL por conta + listagem fixa: 92 + 26 ops/dia → 162 contas no Basic | corrigido |
| F8 | contagens NOT NULL e coerentes; finalizar idempotente; na R2, dead letter após fechamento recusado (G6) | parcial na R2 → corrigido em G6 |
| F9 | entrada `json` textual, offset ISO, tipos estritos, controles recusados; timezone com caixa exata | corrigido |
| F10 | coletor grava pelo `Registro`; equivalência serial × paralela por `as_of` em cortes | corrigido |
| F11 | `dry_run` com sink nulo; trava por capacidade (cliente só de leitura) | corrigido |
| F12 | timeout que não prende o processo | corrigido |
| F13 | bytes reais (1.140 B) adotados; redundância 89,4% contestada com prova (idade do coletor, H5) | parcial (docs 04/05) → corrigido no integrador |
| F14 | refutação de H1 só pela razão kv/earnings; 01 e recibo atualizados | corrigido |
| F15 | `custom_key_ausente`/`custom_key_forcado_upstream`; limite documentado | corrigido |
| F16 | `partial` fora do total por padrão | corrigido |
| F17 | cobertura desconhecida representável; nada fabrica cobertura linear | corrigido |
| F18 | `_js_len` com surrogatepass | corrigido |
| F19 | universo earnings ∩ kv coletado; na R2, mesma regra na reconciliação de G (G8) | corrigido |
| F20 | mutantes M1–M7, M11, M13, M18 mortos; cluster UTF-8 | corrigido para os mutantes da R1 |
| F21 | `down` recusa com dependentes fora do schema | corrigido |
| F22 | reaplicável com papéis existentes; na R2, só superusuário | corrigido |
| F23 | semântica `??` | corrigido |
| F24 | ressalva Unicode 15.1 × 17 | corrigido |
| F25 | ids reais retirados dos arquivos atuais (C, B, integrador); histórico ainda tem ids (decidir squash antes de push) | parcial → R2-G17 corrigido nos arquivos |
| F26 | amostras maiores e todas as medições publicadas; `as_of` global medido | corrigido |
| H1 | 0 grupos repetidos em produção (4ª rodada) | refutada nos dados atuais |
| H2 | registrado como risco (11 §5); fora do código da missão | não tratada no código (fora de escopo) |
| H3/H4 | READ COMMITTED + `FOR SHARE`/`FOR UPDATE`; duas sessões | corrigido |
| H5 | coletor de termos com ~21 h de vida; 04 §3 | confirmada e documentada |
| D1–D3 | vigente = maior `observed_at`; reafirmação removida; ambiguidade independente da ordem | corrigido (regressão do caminho real do shadow corrigida em R2-G2) |
| D2' | versão só quando o estado muda; confirmações estreitas | implementado; defeitos G4/G5 corrigidos |
