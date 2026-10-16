# FINAL-REPORT — Fundação Data Intelligence (missão multiagente, 16/10/2026)

Branch `lab/data-foundation-20261016` (local, sem push, não integrada ao `main`), sobre a 1ª execução do Lab.
Suíte: **879 testes verdes, 1 pulado com motivo** (medição grande opcional). Nada foi escrito fora deste
repositório local; produção foi só lida, com trava `default_transaction_read_only=on`.

## Em uma frase

A fundação existe e está testada: guardar cada leitura como observação histórica, saber o que se sabia em
qualquer instante, juntar custo × receita no grão honesto, rodar decisões em shadow, simular, medir qualidade
e dimensionar — mas **nada foi testado em replay com dado real nem roda agendado**, e as leituras de produção
acharam três defeitos de fonte que valem mais que qualquer modelo.

## O que as leituras de produção mostraram (read-only)

- As fontes append-only **já existem e estão vivas** em produção: Google Ads v21 e JoinAds v2 (o código delas só
  está em branches wip, sem merge-base com `main`).
- A ponte **custo × receita por campanha × dia funciona**: a receita JoinAds com chave de campanha cobre 96,8–100%
  do earnings todos os dias de 08 a 16/10.
- O **Sensor descarta o id da campanha** de todas as sessões pagas (0 de 33): navegação e funil não juntam com
  campanha hoje. Causa provada no código do GTM (filtro de PII ≥ 10 dígitos).
- O coletor Google **grava zero onde não há dado** em 80% das linhas campanha-dia, e **3 execuções estão presas**
  desde 15/10.

## Pronto (construído e testado, na branch)

| Peça | Onde | Estado |
|---|---|---|
| Contrato de observação com 8 estados, relógios, linhagem, chaves, `as_of` | `02`, `fundacao/observacao/` | testado hermeticamente + PostgreSQL descartável |
| Schema append-only candidato com RLS, grants, rollback, particionamento opcional | `migrations_candidatas/dil_obs_000{1,2}` | testado em PostgreSQL descartável |
| Adaptadores das tabelas reais v21 e JoinAds v2 | `fundacao/observacao/adaptadores.py` | testado com linhas sintéticas no formato real |
| Matriz de atribuição e junção que recusa grão falso | `03`, `fundacao/identidade/` | testado hermeticamente; réplica exata do JS do sensor |
| Modelo de volume, quotas e coletor seguro (leitura só, `dry_run`) | `04`, `05`, `fundacao/capacidade/` | testado com sintético + medição em PostgreSQL |
| Simulador com mundo verdadeiro separado da observação, 20 cenários | `07`, `fundacao/simulador/` | testado com sintético |
| Replay `as_of` e shadow engine com ledger | `06`, `fundacao/shadow/` | testado com sintético |
| Model Lab: 14 técnicas com pré-registro e baseline | `08`, `fundacao/modelos/` | testado com sintético |
| Health contracts de qualidade + 19 views candidatas | `09`, `fundacao/qualidade/` | testado hermeticamente; **rodou uma vez read-only em produção** |

## Demonstrado

Idempotência; append-only (inclusive contra o papel dono e o superusuário simulado); null ≠ zero; ausência ≠
falha; replay sem futuro (política trapaceira detectada); reprocessamento tardio; deduplicação; schema drift;
timeout e retry seguros sem prender o processo; nenhuma escrita externa no shadow (varredura e espião);
nenhuma credencial em artefato; nenhuma dependência de `*.supabase.co`; RLS e grants nas migrations
candidatas; rollback; equivalência serial × paralela; equivalência Python × SQL do `as_of`; determinismo byte a
byte dos resultados. Duas revisões adversariais independentes (R1: 26 achados, todos respondidos; R2: ver
`handoffs/REVISAO-ADVERSARIAL-R2.md`).

## Simulado (não é eficácia)

- Nenhuma política de decisão superou `equal` no simulador (resultado negativo, igual à 1ª execução).
- Suportados em sintético: nowcast intradiário do custo D0 (erro 15% do ingênuo); e-BH controla FDR com olhadas
  repetidas; alocação côncava reduz regret, mas o ganho vem de cortar ROAS < 1, não da curva; conformal ACI mantém
  cobertura sob quebra.
- Refutados ou sem ganho: Bornhuetter-Ferguson, EB em campanha nova, CUSUM/BOCPD sobre média móvel, Thompson,
  HGB sobre Ridge; SH/ASHA e surrogate seguem em hold.

## Pendente

Replay com dado real; shadow agendado; correções nas fontes (sensor, zero sintetizado, moeda, runs presos);
decisão de autoridade única do ledger Google; aplicação do delta de roadmap/curadoria e reconstrução do grafo
(bloqueadas pelo classificador de permissões desta sessão; delta validado em
`handoffs/CURADORIA-DELTA-20261016.json`).

## Requer dados

Calibração de maturação, limiares de qualidade e alarme, nowcast e alocação: ≥ 8 semanas de shadow com ≥ 1
campanha ativa. Surrogate: ~50 campanhas × 100 dias. Bandits/OPE: propensão logada (não existe hoje).

## Requer autorização

Lista objetiva em `12-PLANO-DE-PROMOCAO.md` (9 itens). Os dois que destravam mais: exportar o snapshot read-only
para replay real e aplicar o delta de roadmap/curadoria + grafo.

## Números de capacidade (com o schema final)

Agenda atual consome 92 operações Google Ads/dia/conta + 26 fixas → 162 contas no nível Basic. A ×100 com vertical
completa e coleta horária: v21 como está 1,95 TB em 3 anos; política recomendada (largo tipado, dedup, rollup) 30 GB;
`dil_obs` com D2' 2,0 TB (717 GB com termos 1×/dia). `as_of` de ponto 0,02 ms em 1e6 linhas.

## Herdado da 1ª execução

Contrato econômico, replay v0, Stat Lab, swarm e surrogate (vereditos preservados), 172 testes — ver `00` §2.
