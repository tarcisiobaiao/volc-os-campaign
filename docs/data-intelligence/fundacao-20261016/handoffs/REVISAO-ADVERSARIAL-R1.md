# Revisão adversarial R1 — alvo `d4475d30` (diff `b6e85974..d4475d30`)

Revisor independente, somente leitura (cópia via `git archive` em `/private/tmp/claude-502/r1-scratch/`,
cluster PG16 próprio, scripts de prova em `r1-scratch/{pg,py,fuzz}/`). Suíte de referência: 471 verdes.
Contagem: 26 achados confirmados (1 bloqueante, 6 altos, 13 médios, 6 baixos), 5 hipóteses, 2 lentes sem
achado (autorização/gasto e mutação externa). A resposta a cada achado está em
`RESPOSTA-R1.md` (mesma pasta).

## Confirmados

| # | Sev. | Onde | Achado | Prova (resumo) | Correção sugerida | Dono |
|---|---|---|---|---|---|---|
| F1 | bloqueante | `dil_obs_0001:404,515` | "Nunca retroativo" não é forçado: `lote.recebido_em` é declarado pelo escritor; `as_of` passa a mostrar no passado o que o banco recebeu hoje | `pg/t_retro.py`: lote com `recebido_em` em jan, obs `available_at` jan → `inserido`; `as_of('2026-02-01')` mostra o valor | exigir `available_at >= payload_bruto.recebido_em` (relógio do banco) ou `lote.recebido_em := now()`; teste com lote no passado recusado | A |
| F2 | alta | `dil_obs_0001:43` | `GRANT dil_obs_dono TO CURRENT_USER` nunca revogado: papel não-superusuário que aplicou a migration faz UPDATE/TRUNCATE | `pg/t_dono2.py`: `SET ROLE dil_obs_dono` → UPDATE e TRUNCATE ok | `REVOKE` no fim de 0001/0002; documentar membros; alerta de DDL | A |
| F3 | alta | `registrar_observacao :508-524` | linhagem solta: run/fonte/coletor/schema não conferidos contra run/lote; lote de run finalizado recebe observação | `pg/t_linhagem.py` → `inserido` com tudo divergente | derivar fonte/coletor/schema de run/lote e exigir igualdade | A |
| F4 | alta | `adaptadores.py:251,344` | moeda inventada a montante (`'USD'` default JoinAds; `'BRL'` fixo v21) aceita como `observed` | `py/t_adapt.py` | moeda só com prova; senão `invalid moeda_nao_provada` | A |
| F5 | alta | `juncao.py:55-64,271-277` | junção soma receita sem identidade de linha (endpoint, grão, versão) → dupla contagem | `py/t_dup.py`: 2× a verdade | chave de linha; recusar grão misto e duplicata; exigir `as_of` antes | C |
| F6 | alta | `juncao.py:260-262,292-304` | null→0 em cliques; zero de sessões afirmado sem sensor no site; junção emite sessões em grão que `graos.MATRIZ` diz `nao_atribuivel` | `(a)`, `(b)` em `py/` | cliques None → ausente; zero de sessão só com sensor comprovado por site; chamar `exigir_grao` | C |
| F7 | alta | `volume.py:108`, `cenarios.py:47,51` | quota Google Ads subestimada ~3×: coletor v21 faz 4 GAQL/conta/execução | recalculado: agenda atual 92 ops/dia/conta → 163 contas (não 468); D0 10 min → 25 (não 94) | `consultas_por_execucao=4`; regenerar `MODELO.md` | B |
| F8 | média | `0001:126-130,355-374` | run finalizado com contagens NULL/incoerentes aceito; retry de `finalizar_run` erra | `pg/t_run.py` | `IS NOT NULL`; contagens pelo banco; finalizar idempotente | A |
| F9 | média | fronteira SQL | SQL aceita o que o Python recusa (instante sem offset, `5e0`, conta numérica, controles, `ingested_at < available_at`); Python no macOS aceita timezone com caixa errada | `pg/t_div.py` | offset ISO obrigatório; mesmas regras de texto no SQL; timezone contra `available_timezones()` | A |
| F10 | média | `coletor.py:108-109,214-216` | coletor perde A→B→A; equivalência serial×paralela só aparente | `py/t_coletor.py`, `py/t_par.py` | reusar reafirmação do `Registro`; comparar `as_of` em cortes | B |
| F11 | média | `coletor.py:156-167,265-333` | `dry_run` grava heartbeat/recibo/dead letter; trava por nome de método aceita `cliente.mutate` | `(f)`, `(g)` | sink nulo em dry_run; trava por capacidade | B |
| F12 | média | `coletor.py:271-301` | fonte presa impede o processo de terminar (threads não-daemon) | `py/t_hang.py`: processo sai após 20 s | timeout no cliente ou subprocesso | B |
| F13 | média | `04` × recibo | 04 usa 851 B/linha (real 1.140 B); 89,4% vs 95,7% é 2,4× em linhas distintas | recibo 2ª rodada | regenerar com bytes reais; reportar razão de distintas | B |
| F14 | média | recibo, `01:95,246` | viés de sobrevivente: "todas kv numéricas" é garantido pelo normalizador; 01 ainda trata H1 como aberta | `joinads_v2_normalize.js:69,173-178` | refutação só pela razão kv/earnings; atualizar 01 | I |
| F15 | média | `adaptadores.py:351` | substituição de chave mascarada a montante (normalizador força `custom_key`); adaptador só detecta com pedido e devolvida | `(j)`, `(k)` | detectar ausência/forçamento; documentar limite | A |
| F16 | média | `asof.py:85-92` | agregação padrão soma `partial` num total `medido` | `py/t_agreg.py`: 1% de cobertura → `medido` | partial fora do total por padrão; expor cobertura | A |
| F17 | média | `adaptadores.py:92-95`, `normalizador.py:178-182` | cobertura `partial` fabricada linearmente pelo relógio; CHECK impede "desconhecida"; mutação M11 sobreviveu | — | cobertura desconhecida representável; não fabricar | A |
| F18 | média | `chave_campanha.py:85` | surrogate cortado no limite de 40 → `UnicodeEncodeError` derruba a junção | prova direta | usar `_js_len` | C |
| F19 | média | `juncao.py:324-344` | denominador de cobertura de receita mistura universos | `(c)`: 1/10 sem aviso | separar universos; avisar | C |
| F20 | média | testes | 10 de 20 mutações sobreviveram (M1–M7, M11, M13, M18); cluster de teste `--no-locale` esconde collation | tabela abaixo | testes que matem cada sobrevivente; cluster com locale UTF-8 | A, C |
| F21 | baixa | `0001.down:11` | `DROP SCHEMA … CASCADE` apaga objetos fora do schema | view `public.painel_receita` apagada | down sem CASCADE ou com checagem de dependentes | A |
| F22 | baixa | `0001` | não reaplicável por não-superusuário se papéis já existem | `permission denied to grant role` | tratar papéis existentes | A |
| F23 | baixa | `colisao.py:99` | `custon_key` ignorado quando `custom_key` é null (`.get` ≠ `??`) | prova direta | semântica do `??` | C |
| F24 | baixa | normalização | "idêntica ao JS" só até Unicode 15.1 (Node 26 = Unicode 17) | 3.536/4.000 vetores Unicode 16/17 divergem | ressalva no doc | C |
| F25 | baixa | vários | dados reais versionados: customer_id, campanha, conta/container GTM, domínio, valores monetários em 04/05 | varredura | sanitizar; ampliar varredura | B, C, I |
| F26 | baixa | benchmark | amostra fina (n=15) e corte seletivo; `as_of` medido não é o `DISTINCT ON` global | `pg_medicoes.json` | reportar tudo; medir o as_of real | B |

## Hipóteses (não reproduzidas)

- H1 linhas repetidas no mesmo lote JoinAds (top_url, earnings por advertiser/network fora da chave) → `ConflitoIdempotencia`/`VersaoAmbigua` derruba o replay. Teste: `SELECT batch_key, endpoint, land_uri, advertiser, network, count(*) … HAVING count(*)>1`.
- H2 surrogate solto do sensor recusado pelo jsonb no volc-ingest → lote de até 20 eventos perdido.
- H3 retry concorrente sob REPEATABLE READ → `unique_violation` em vez de noop.
- H4 `registrar_observacao` sem `FOR SHARE` no run → contagem errada com `finalizar_run` concorrente.
- H5 janela de 7 dias do `lb.sql` mais curta que a vida do coletor de termos → 89,4% não é regime estável.

## Mutações (20; 10 sobreviveram)

Sobreviveram: M1 `ck_obs_janela_fechada`; M2 `source_updated_at <= available_at`; M3 trava de `recebido_em`
futuro; M4 `ck_run_contagens`; M5 conferência do payload do lote; M6 `COLLATE "C"`; M7 `<=`→`<` no noop
(`registro.py:109`); M11 cobertura constante; M13 `custom_key` sem strip; M18 sem regex de inteiro (erro de
cast mascara a guarda). Mortas: M8, M9, M10, M12, M14, M15, M16, M17, M19, M20.

## Contraprovas (tentado e não refutado)

`as_of` Python×SQL (empate, A→B→A); chaves Python×SQL com acento/offset/microssegundo; papéis sem
privilégio (escritor, leitor, anon, authenticated, PUBLIC), RLS forçado, SECURITY DEFINER com
`search_path=''`; normalização vs JS real (0/6.003 em Unicode ≤ 15.1; `parse_query` 0/8.000); zero em grãos
não-campanha da v21 é omissão proto3 (`zero_confirmed` defensável); retry/timeout do coletor não duplicam;
12 citações ref:linha do inventário exatas; aritmética do modelo de capacidade consistente (defeito nas
entradas); linguagem sem "validado/operacional/state of the art"; unicidade do particionamento 0002;
nenhum caminho novo até mutate, UPDATE em produção, deploy, webhook ou gasto.
