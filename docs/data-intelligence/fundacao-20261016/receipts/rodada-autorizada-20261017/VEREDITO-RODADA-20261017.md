# Veredito — rodada autorizada (itens 1, 2 e 9)

Branch `lab/data-foundation-20261016`, local, sem push. Recibo completo com consultas, hashes e comandos:
`RECIBO-RODADA-AUTORIZADA-20261017.md` (mesma pasta). Legenda: **D** demonstrado, **I** inferido,
**H** hipótese, **NT** não testado.

## 1. Replay real

**D.** Snapshot read-only de 16/10 23:00 BRT (175 linhas v21 `campaign_day`, 200 JoinAds v2), 36 cortes horários,
6 políticas, ledger íntegro. Nenhuma política saiu de `insuficiente`:

| Política | Resultado nos 36 cortes | Motivo |
|---|---|---|
| manter | manter | baseline |
| equal | insuficiente | 1 campanha ativa: nada a realocar (29 cortes); sem custo D-1 fechado (7) |
| greedy conservador | insuficiente | idem |
| regra de margem madura (e guardião 72 h) | insuficiente | 0 de 3 dias maduros |
| anti-baseline null → zero | pausar 180 vezes, **180 bloqueadas pelo kernel** | cobertura de receita não comprovada ou baixa |

A anti-baseline foi recusada. No modo estrito ela pausaria até as 4 campanhas sem linha de métrica como
"campanha morta"; na variante com moeda atestada, também a ativa, por margem imatura negativa calculada com câmbio
**hipotético** (não é evidência econômica). A auditoria metamórfica null × zero foi inconclusiva (só 1 corte das
07 h com lacuna).

**Só sintético:** regret, drawdown, lucro contrafactual e "margem madura perde para equal". Em dado real não há
verdade contrafactual, e o histórico de custo tem 3 dias. **I:** a regra madura só pode agir a partir de 20/10, se
custo e receita fecharem.

## 2. Cobertura real custo × receita

**D.** Custo existe de 14 a 16/10; receita de 08 a 16/10. A junção campanha × dia funciona: o único valor kv da
JoinAds casa com a única campanha `ENABLED`. Razão kv/earnings recomputada das linhas: 0,968–1,000 em 08–16/10.
Pelo contrato estrito a cobertura comprovada cai muito:

- moeda não provada em nenhuma das duas fontes (o payload não declara moeda; a coluna é BRL fixo ou USD por
  default), então 100% do custo e da receita saem `invalid` no modo estrito;
- o `earnings` da JoinAds chega com até 17 casas decimais e o adaptador recusa abaixo de micro, o que deixa o
  denominador indisponível em 5 de 9 dias (inclusive 15/10).

Com a moeda como hipótese, só 14/10 (0,968) e 16/10 (1,000) ficam comprovados entre os dias com custo.

## 3. Impacto real de null × zero

**D.** 140 de 175 linhas (80%) são zero sem linha de métrica: 4 campanhas, todas `PAUSED`, 12 de 15 células
campanha-dia. A campanha ativa tem linha de métrica em todas as leituras. Hoje o impacto em decisão é nulo,
porque o kernel bloqueia e as campanhas estão pausadas. **I:** o risco fica material quando uma campanha ativa
perder a linha de métrica; ela apareceria como gasto zero confirmado.

## 4. Runs presos

**D.** Continuam 3, todos do coletor de termos e keywords, presos desde 15/10 11:46–11:48 BRT (~35 h), com 2.242
lotes cada e sem `finished_at`. Têm 0 linha `campaign_day`: o replay com e sem eles é idêntico (mesmo sha). O efeito
fica em frescor e saúde e em qualquer leitura que filtre por run concluído (6.726 observações de termos).

## 5. Perda de campaign_id no Sensor v3.1

**D.** A v36 está live, e o HTML do Sensor v3.1 e do WEBS Wrapper v2 tem sha256 igual ao repositório em `db65a78a`.
A causa é a mesma da v3.0: a regex `/\+?\d[\d\s().-]{8,}\d/` de `clean()` casa qualquer sequência de 10 ou mais
dígitos, e `utmValue()` descarta o valor inteiro quando `clean` o altera. O diff v3.0 → v3.1 só acrescentou
`seq`. Em produção: v3.0 teve 0 de 32 sessões pagas com `utm.campaign`; v3.1 teve 0 de 13 (16/10 13:05–22:57).
**I:** nos containers v35 e v36 só o WEBS Wrapper chama `setTargeting`, e ele aplica o mesmo filtro. Então o id
numérico que chega à JoinAds vem de fora do GTM.

## 6. Workflows n8n

**D.** 382 workflows, 72 ativos; só 1 ativo tem error workflow, e não é coletor de mídia nem de receita.

- **Canônicos ativos e sem error workflow:** Google D0 (19 ok, 1 erro nas últimas 20), D-1 (4 ok), termos (13 ok,
  3 erros), JoinAds intradiário (18 ok) e JoinAds D-1 (5 ok, 1 erro).
- **Legados ativos em paralelo:** dois pares de relatório Google Ads (um deles alterado em 16/10 00:54 UTC) e os
  dois relatórios JoinAds.
- **Inativos:** KW Optimization e ORAKUL Auto Adjust.
- **Falhando:** GAM eCPM horário, 20 de 20 em erro.

## 7. Divergências código × GTM × Edge Function × produção

| # | Divergência | Estado |
|---|---|---|
| a | Produção (GTM v36, `volc-ingest`, `raw_events.event_seq` + índice de 5 colunas) = `db65a78a`, que não está em `main` (local `128b93ae` tem só v3.0; `origin/main` = `104bb0d0`) | D |
| b | `volc-ingest` no host = `db65a78a` (gravado 16/10 16:04 UTC, container reiniciado 16:05). Na pasta só há o backup pré-v3 de 15/10; o backup da v3.0 citado no runbook não foi encontrado ali (outras pastas não lidas) | D / NT |
| c | `volc-ingest` ainda corta strings com `.slice(0, max)` (linha 51): o risco R2-G19/H2 do par substituto segue em produção | D |
| d | Os coletores canônicos rodam em produção, mas o código deles só existe em branches wip | D |
| e | Moeda: coletor Google grava BRL fixo; JoinAds, USD por default; nenhum payload declara moeda | D |
| f | `earnings` da JoinAds com até 17 casas decimais (artefato de float a montante) | D |
| g | Co-autoridade real: canônico e legado de Google Ads e JoinAds ativos ao mesmo tempo | D |

## 8. Delta de roadmap e grafo

**D.** O delta foi reconciliado com `db65a78a` sem sobrescrever P06-T07, P08-T01, P08-T07, `cap_behavior` e
`concept:tracking_control_plane`: esses campos foram importados idênticos e o delta só acrescenta. Foram 39 trocas
explícitas, 4 guardas recalculadas e P08-T12 removida, porque a dedup por segundo já foi corrigida em produção e o
item 7 não foi refeito. A guarda de sha passou sem force.

Resultado: 212 tarefas, 16 novas, nada `done`. P06-T08 → risk; P14-T07 e P14-T11 → partial. Grafo reconstruído pelo pipeline oficial; `--check` → `current: true`.
O grafo é corrente só nesta branch, não no global nem no `main`. Nota: o próprio delta diz que P14-T07 só vira
partial junto com o merge do código em `main`. Na branch isso vale como candidato; se a branch não for mesclada,
esse estado não sobe.

## 9. Proposta mínima para os itens 5 e 6 (não executada)

**Item 5, coletor Google no n8n**, em cópia inativa antes de ativar; rollback pela versão exportada do workflow.

1. Gravar métrica só quando houver linha de métrica. Sem linha, gravar `metrics` sem a chave e um motivo, nunca 0.
2. Pedir `customer.currency_code` na GAQL e gravar a moeda devolvida.
3. Criar um error workflow e ligá-lo aos 5 canônicos.
4. Criar um reaper: run `running` sem lote há mais de 60 min vira `abandoned` com motivo, sem apagar. Isso é
   escrita em produção e precisa de autorização própria.
5. JoinAds: quantizar a receita para micros no normalizador (half-even) e guardar a string original no payload.

Prova: `dq_zero_sintetizado` "sem linha" em 0% por 7 dias, e o replay estrito sair de `invalid` sem moeda atestada.

**Item 6, GTM**, partindo da v36 e preservando `event_seq`, WEBS Wrapper, consentimentos, triggers e tags de
conversão. Em `utmValue` (sensor) e `safeValue` (wrapper), isentar só `utm_campaign` e `utm_content` quando o
valor casar `^\d{6,20}$`; o filtro atual continua para todo o resto.

- Revisão de privacidade: 11 dígitos podem coincidir com um CPF sem formatação. A mitigação é a restrição por chave
  mais a conferência contra o registro de campanhas no servidor.
- Rollback: v36.
- Canário: sessões pagas com `utm.campaign` numérico > 0, lidas read-only.

**Decisão recomendada, sem mutação financeira:** nenhuma ação de verba, pausa ou lance. Fazer primeiro o item 5,
porque sem moeda provada e sem null no lugar de zero o replay real não sai de `insuficiente`. Depois, o item 6.
Por último, uma leitura read-only diária para acumular as 8 semanas de que a calibração precisa; isso exige nova
autorização.

## 10. Zero escrita em produção

**D.** 6 sessões psql, todas RR READ ONLY com ROLLBACK e `default_transaction_read_only=on`. No host, SSH só com
`ls`, `sha256sum` e `docker inspect`, sem restart. GTM e n8n só com GET; houve apenas a renovação do token OAuth.
Nenhuma migration, publicação, alteração de workflow, push ou merge. Os artefatos foram removidos depois do replay
e a árvore ficou limpa (`git status` vazio).
