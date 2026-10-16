# Resposta à revisão R2 (consolidada pelo integrador)

Detalhe por frente, com teste que falha antes e passa depois: `HANDOFF-A.md` §8, `06-REPLAY-E-SHADOW.md` e
`HANDOFF-D.md`, `08-MODEL-LAB.md` §16 (errata) e `HANDOFF-F.md` §9, `09-OBSERVABILIDADE.md` §10 e `HANDOFF-G.md` §8.
Não houve terceira revisão independente: a verificação destas respostas é a suíte (914 verdes, 1 pulado) e as
provas da R2 reexecutadas pelas frentes.

| # | Resposta | Prova |
|---|---|---|
| G1 | só superusuário aplica/desfaz 0001/0002; WARNING com o `REVOKE` para membresias prévias | `test_r2_g1_nao_superusuario_nao_aplica_e_nao_fica_com_admin_option` |
| G2 | `real.deduplicar` passou a usar o `Registro` D2' | `test_g2_*` (todas as permutações); `p_dedup` dá 5.000.000 |
| G3 | cobertura sem `/earnings` (ausente ou `unavailable`) bloqueia ação de verba; fração < 9/10 bloqueia | `test_g3_*` (4 modos) |
| G4 | retry de leitura confirmada com conteúdo diferente → `ConflitoIdempotencia` (Python e SQL) | `test_r2_g4_*` |
| G5 | bytes remedidos com ids reais: 1.158 B/valor, 276 B/confirmação; `run_id` saiu da confirmação; projeção ~2,5 TB em 3 anos a ×100 | `test_schema_pg_desempenho.py`, HANDOFF-A §8 |
| G6 | schema recusa dead letter em run fechado e run com dead letter fechando `succeeded`; view e ponte alertam `so_dead_letter`/`dead_letter_apos_fechamento` | `test_r2_g6_*`, `test_g6_*` |
| G7 | `dq_obs_status` lê o estado vigente por `observacao_as_of(agora)` | `test_qualidade_r2.py` |
| G8 | reconciliação JoinAds por domínio × dia, só onde há earnings e kv (Python e SQL); contrato da view mudou (uma linha por domínio × dia) | `test_qualidade_r2.py` (4 cenários, inclusive mascaramento) |
| G9 | H5b exige as duas condições pré-registradas → **refutada** (errata datada; resultado antigo preservado) | `results/fundacao/modelos/errata_20261016/` |
| G10 | M10 decide com o painel `as_of` maduro; H10a suportada, H10b refutada; 08 §0 conta M10 como parcial | idem |
| G11 | fato com topo ambíguo sai do corte e vira bloqueio `versao_ambigua` da entidade | `test_g11_*` |
| G12 | custo campanha×dia só com dimensões → `invalid` e bloqueio; total sem dimensões vence | `test_g12_*` |
| G13 | mutantes D1, D6, D7, D10 (D), F4 (F), G4, G7 (G), E3 (integrador) mortos por teste de comportamento | `test_shadow_*`, `test_modelos_dados.py`, `test_qualidade_r2.py`, `test_simulador_r2.py` |
| G14 | guarda de futuro obrigatória para custo e earnings na junção | `test_g14_*` |
| G15 | 06 e HANDOFF-D com os números do JSON; `--verificar` cobre provisório, gates, versão do código e simulador | `fundacao_shadow.py --verificar` |
| G16 | delta regerado no HEAD final com `base_sha256_campo_anterior`; aplicador confere a guarda contra o estado anterior ao delta | `CURADORIA-DELTA-20261016.json`, `aplicar_curadoria_delta.py` |
| G17 | domínio do cliente, prefixo da campanha real, container GTM e nome do cliente trocados por placeholders nos arquivos atuais; histórico ainda os contém | varreduras de C, G, D |
| G18 | 05 com a redundância medida; 04 marca números antigos como histórico | integrador |
| G19 | registrado como risco (11 §5); fora do código da missão | — |
| G20 | retry do mesmo lote é NOOP antes de conferir `recebido_em`; `recebido_em` NULL aceito (banco carimba) | `test_r2_g20_*` |
| G21 | referências corrigidas (este arquivo e `RESPOSTA-R1.md` existem; `FINAL-REPORT.md` existe); shadow roda 19 de 20 cenários (`escala_10x` só mede volume) | script do shadow |
| G22 | documentado (06 §9) e testado: v21 sem moeda no payload → custo `invalid moeda_nao_provada`, nenhuma política corta | `test_shadow_real.py` |
| G23 | ponte conta `n_inseridas + n_confirmadas` | `test_g23_*` |
