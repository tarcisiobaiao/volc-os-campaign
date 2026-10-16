# Revisão adversarial R2 — alvo `962b868c` (final)

Revisor independente, somente leitura (cópia via `git archive` em `/private/tmp/claude-502/r2-scratch/alvo`,
clusters PG16 próprios, provas em `r2-scratch/probes/`). Suíte na cópia: 877 passed, 2 skipped (um exige `.git`).
Contagem: 23 achados (20 confirmados: 3 altos, 12 médios, 5 baixos; 3 hipóteses/inferências); lentes de
autorização/gasto e mutação externa sem achado. Não verificado: seção simulador do shadow regerada, os 7 cenários
excluídos do shadow, o commit `3d0ad977` (posterior ao alvo), F17/F18/F24 só por suíte e leitura, PostgreSQL 15.
A resposta a cada achado está em `RESPOSTA-R2.md`.

## Verificação da R1

| # | Veredito R2 | # | Veredito R2 |
|---|---|---|---|
| F1 | corrigido (efeito colateral G20) | F14 | corrigido |
| F2 | **parcial** (G1) | F15 | corrigido |
| F3 | corrigido | F16 | corrigido |
| F4 | corrigido no adaptador (ressalva G22) | F17 | corrigido (não reproduzido) |
| F5 | corrigido no shadow; parcial na API (G14) | F18 | corrigido (não reproduzido) |
| F6 | corrigido | F19 | corrigido em C; regressão de classe em G (G8) |
| F7 | corrigido (162 contas) | F20 | corrigido para os mutantes da R1 (14/14 SQL mortos); D/F/G/E: G13 |
| F8 | **parcial** (G6) | F21 | corrigido |
| F9 | corrigido (22 casos, 0 divergências) | F22 | corrigido com ressalva (G1) |
| F10 | corrigido | F23 | corrigido |
| F11 | corrigido | F24 | corrigido |
| F12 | corrigido (processo sai em 0,41 s) | F25 | **parcial** (G17) |
| F13 | **parcial** (05/04 defasados — G18) | F26 | corrigido |
| H1 | refutada nos dados atuais | H4 | corrigido |
| H2 | **não tratada** (G19) | H5 | confirmada e documentada |
| H3 | corrigido | D1 | corrigido; **regressão** no caminho real do shadow (G2) |
| D3 | corrigido (defeito distinto na quarentena, G11) | D2' | implementado com defeitos (G4, G5, G23) |

## Achados

| # | Sev. | Onde | Achado | Prova | Dono |
|---|---|---|---|---|---|
| G1 | alta | `dil_obs_0001:58-87,979-985` | aplicador NOSUPERUSER CREATEROLE mantém ADMIN OPTION em `dil_obs_dono`, re-grant → DISABLE TRIGGER e TRUNCATE | `probes/q_f2.py` | A |
| G2 | alta | `shadow/real.py::deduplicar` | dedup própria do caminho real quebra D1 (leitura antiga atrasada vence) | `probes/p_dedup.py` | D |
| G3 | alta | `shadow/kernel.py::bloqueios_para`, `shadow/snapshot.py::_juntar_dia` | portão de cobertura aprova `reduzir_verba` quando earnings está ausente/`unavailable`; sem teste (mutante D1 sobrevive) | `probes/p_kernel.py` | D |
| G4 | média | `registro.py` (`_conf_por_natural`), `dil_obs_0001:774-784` | retry de leitura confirmada com conteúdo diferente vira versão em silêncio (regra 1 promete conflito) | `probes/p_conf.py`, `q_g.py` | A |
| G5 | média | `test_schema_pg_desempenho.py:23-62` | bytes de D2' medidos com ids de 1 caractere; com ids realistas 1.029 B/valor (+30%) e 344 B/confirmação (+62%) | `probes/q_bytes.py` | A, B |
| G6 | média | `dil_obs_0001:478-485,563-574`; `dq_obs_dead_letter`; `ponte_observacao.py:138` | dead letter aceito depois do fechamento; run só com dead letters fecha `succeeded`; view e Python dão `ok` | `q_core.py` | A, G |
| G7 | média | `dq_02::dq_obs_status` | conta versões, não estado vigente; mutantes G4/G7 sobrevivem | `q_g.py` | G |
| G8 | média | `qualidade/reconciliacao.py`, `dq_01:329-365` | reconciliação mistura universos de domínio (classe de F19) e pode mascarar cobertura baixa como `ok` | `probes/p_recon.py` | G |
| G9 | média | `scripts/fundacao_modelos_causal.py:113`; `08` §5 | critério de H5b reduzido em relação ao pré-registro; H5b deveria sair não suportada | dados do JSON | F |
| G10 | média | `scripts/fundacao_modelos_alocacao.py:5,37-38`; `08` §0 | M10 usa verdade do mundo, com dias imaturos, como histórico de decisão; §0 conta M10 como aprovada | leitura | F |
| G11 | média | `shadow/fluxo.py` (quarentena) | quarentena ressuscita versão superada | `probes/p_quar.py` | D |
| G12 | média | `shadow/snapshot.py::construir_snapshot` | custo campanha×dia com dimensões: pega item arbitrário | `probes/p_dims.py` | D |
| G13 | média | testes D/F/G/E | 8/25 mutações sobrevivem (D1, D6, D7, D10, F4, G4, G7, E3); guardas de hash mascaram | — | D, F, G, E |
| G14 | baixa/média | `identidade/juncao.py:338,480` | guarda de futuro opcional para custo/earnings sem `disponivel_em` | `p_juncao.py` | C |
| G15 | média | `06` §2, §7.2, §10; HANDOFF-D:28; `snapshot.py:5` | 06 defasado em relação aos resultados regerados; `--verificar` não cobre a seção simulador | comparação | D |
| G16 | média | `CURADORIA-DELTA-20261016.json`, `aplicar_curadoria_delta.py` | delta gerado em `4920172a` grava fatos superados (as_of não inlinado, 1.084 B, D2); aplicador não confere `base_sha256_campo_anterior` | leitura | I |
| G17 | baixa | `qualidade/sintetico.py:28`; `shadow/linhas_formato_real.py`; 00/01/receipts; 01/07/`calibracao.py` | domínio real do cliente, prefixo da campanha real, container GTM e nome do cliente em arquivos versionados | varredura | G, D, E, I |
| G18 | baixa | `05:143,154`, `04` §1/§5 | 04/05 defasados (possivelmente resolvido por `3d0ad977`) | leitura | B/I |
| G19 | baixa | `918e9571:supabase/functions/volc-ingest/index.ts:51` | H2: `.slice` pode cortar surrogate e o jsonb recusa o lote (fora do código da missão) | reproduzido no PG | I (risco) |
| G20 | baixa | `dil_obs_0001:537-546` | retry de `registrar_lote` após 5 min com o `recebido_em` original falha; `NULL` aceito | `q_core.py` | A |
| G21 | baixa | `REVISAO-ADVERSARIAL-R1.md:7`; `00` §8; shadow | referências a arquivos inexistentes; hipótese: exclusão não justificada de 7 cenários no shadow | leitura | I, D |
| G22 | hipótese | `shadow/linhas_formato_real.py` | fixture "formato real" fabrica a prova de moeda no payload | — | D |
| G23 | inferido | `ponte_observacao.py:88` | G ignora `n_confirmadas`; run só de confirmações vira "0 linhas" | leitura | G |

## Contraprovas

A: 14/14 mutações SQL mortas; F1, F3, F8 (núcleo), F9, F21 corrigidos; sem regressão do `as_of`. Coletor: F11, F12.
Junção: F5, F6, F19, F23. Views: `security_invoker` em todas, anon negado, escritor não lê `observacao`, sem
`sid`/`pid`. Recibos de G reproduzem o 09 §7. Shadow: `--verificar` bate para provisório e gates; 06 §7.1 bate.
Model Lab: pré-registro commitado antes do código e dos resultados (`eda4f041` 09:56, código 10:13, resultados
11:23); H1a, H1b, H1c, H2, H3, H4, H7, H8, H9, H10, H12 batem com os critérios. Simulador: performance do 07 bate.
Capacidade: quota de B confere. Delta: nada vira `done`; sem id real nem valor no texto; `P06-T08 → risk` e
`P14-T07 → partial` defensáveis (o segundo só após integração).
