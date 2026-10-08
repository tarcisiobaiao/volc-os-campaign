# FunnelForge — lucro por visita: A/B enxuto no Gás do Povo (08/10/2026)

Missão "performance first, policy safe": o alvo é o maior lucro esperado por
visita dentro de intenção, valor real por página, progressão honesta e
política. Este registro cobre o delta no motor existente e o único A/B real.
Nenhuma publicação, deploy, push ou mutação externa. Nenhuma API faturada.

## Gargalo real (antes)

Medido no artefato congelado `gas-do-povo-20261008-pre-redacao-pos-fix-final-20261008`
(arquitetura A, gpt-6-sol) e no A/B do escritor (`FUNNELFORGE-WRITER-AB-2026-10-08.md`):
o problema estava a montante do redator.

- O arquiteto não tinha onde declarar a **tensão residual** nem o **CTA por
  origem**: o rótulo do botão era o `cta_label` do destino, igual de qualquer
  página. Os prompts mandavam manter "rótulo igual para entrega igual".
  Resultado em A: 15 botões, 5 rótulos distintos, 3 repetidos na mesma página.
- Saída oficial `boa` ia para o hero mesmo com dúvida interna aberta (p3 e p4
  abriam com "Ver orientação no site externo de MDS").
- `emotional_objective` era uma lista do que evitar ("sem criar expectativa…").
- O revisor podia segurar página por nota subjetiva (`cta_discipline`,
  `useful_delivery` < 7).
- O Pautador não chegava ao arquiteto: o motor lia `dores_observadas` de um
  contrato que ninguém escreve (`contexto_de_leitura` real é
  `{perguntas_paa, tensao}`).

## Desenho do A/B

| | A (atual) | B (profit-first) |
|---|---|---|
| Brief, fatos, dossiê, tema, teto de páginas | os do run congelado | os mesmos; orientação do card pede as mesmas 5 páginas/`duvida_id` para reaproveitar o dossiê |
| Arquiteto | registrado (gpt-6-sol, prompt de HEAD) | 1 chamada nova (gpt-6-sol, prompt atual), mesma ponte e portão |
| Redator | chatgpt/gpt-6.1-sol, prompts de HEAD (p2–p5 do A/B do escritor; LP gerada aqui com os templates exportados de HEAD) | chatgpt/gpt-6.1-sol, prompts atuais, 3 workers |
| Revisão | — | `revisar_lote` (1 chamada, gpt-6.1-sol) |
| Juiz cego | gpt-6-astra, high, temperatura 0, funil inteiro, 2 ordens (A/B e B/A) | idem |

Harness: `funnelforge-migracao/engine/runs-canario/ab-lucro-gas-20261008/run_ab.py`
(`--dry` prova o encanamento com zero chamada; `--real` tem trava de execução
única). Recibo: `runs-canario/ab-lucro-gas-20261008/real/recibo.json`; páginas
julgadas em `real/paginas_A.json` e `real/paginas_B.json`.

Nota de ambiente: outra sessão editava o mesmo checkout durante a rodada
(`routing.py` passou a descartar arestas regressivas entre soluções no caminho
com brief; `esqueleto.py` isenta a pré-sell de requisitos). B rodou com essas
alterações carregadas. Elas mudam topologia, não copy; não fazem parte deste
commit.

## Execução

10 chamadas (teto 12), todas pelo plano ChatGPT, modelo servido = pedido,
sem fallback, pico de 3 workers, 494 s de parede.

| # | Etapa | Modelo | Latência | Tokens (entrada/saída) |
|---|---|---|---:|---:|
| 1 | LP de A (prompts de HEAD) | gpt-6.1-sol | 36,0 s | 9.531 / 1.571 |
| 2 | Arquiteto B | gpt-6-sol | 234,9 s | 6.098 / 9.682 |
| 3–7 | Redação B, p1–p5 (3 workers) | gpt-6.1-sol | 26,8–56,2 s | 10.361–15.948 / 1.443–2.424 |
| 8 | Revisão em lote B | gpt-6.1-sol | 82,9 s | 107.314 / 4.520 |
| 9–10 | Juiz cego, duas ordens | gpt-6-astra | 31,9 s e 29,7 s | 12.996 / 1.117 e 961 |

Portão de esqueleto de B: OK, zero bloqueante. Redação B: 5/5 OK (p2–p4 com
o localizador `cta_execution`, que vai ao revisor e não bloqueia). Revisão B:
4 aprovadas, p3 em revisão humana por motivo **material**: o redator digitou a
URL oficial com erro (`saiba-com-ter` × `saiba-como-ter`, link quebrado) e a
meta description herdou uma instrução do arquiteto ("A página deve expor…").

## Resultado

Proxies estruturais (determinísticos, mesmos fatos):

| | A | B |
|---|---:|---:|
| Botões / rótulos distintos | 15 / 5 | 12 / 10 |
| Rótulos repetidos na mesma página | 3 | 0 |
| CTA genérico | 0 | 0 |
| Saída oficial no hero com dúvida aberta | p3, p4 | nenhuma |
| Tensão residual declarada | 0 / 5 | 4 / 5 (a terminal não precisa) |
| CTA por origem declarado | 0 | 9 links |
| Palavras (p1…p5) | 920, 443, 645, 749, 549 | 1004, 542, 752, 826, 600 |

Juiz cego (média das duas ordens, 0–10 por critério; total em 100):

| Critério | A | B |
|---|---:|---:|
| conexão com a intenção | 7,5 | 7,5 |
| desejo de continuar | 4,5 | 5,5 |
| força emocional | 3,0 | 3,5 |
| clareza | 7,0 | 7,0 |
| especificidade | 9,0 | 9,0 |
| congruência do CTA | 8,0 | 8,5 |
| valor entregue | 7,0 | 7,5 |
| diferenciação | 6,0 | 6,5 |
| potencial de profundidade | 8,0 | 8,0 |
| policy safety | 10 | 10 |
| **total** | **70,0** | **73,0** |

B venceu nas duas ordens (75 × 69 com A primeiro; 71 × 71 com B primeiro, e o
juiz escolheu B pela continuidade). Motivo recorrente: em A, os CTAs de
retirada e CadÚnico interrompem explicações antes de concluí-las; em B, cada
continuação parte de um obstáculo concreto. Policy safety igual (10): a copy
mais persuasiva não custou segurança.

**Leitura honesta.** A melhora estrutural é clara e repetível (é o código que
a garante). A melhora percebida é pequena (+3 em 100, uma ordem empatada em
nota) e vem de progressão e congruência, não de emoção: desejo de continuar
(5,5) e força emocional (3,5) seguem baixos nos dois. Os dois juízes apontam o
mesmo gargalo restante: a primeira dobra da LP e da pré-sell é abstrata e
ambas repetem a triagem. Em B, o arquiteto (gpt-6-sol) ainda escreve
`emotional_objective` com "Hipótese:" e `resposta_imediata` como instrução
("A página deve expor…") em vez da resposta. Isso não prova ganho de negócio.

## Limitações e próximo passo

- Uma rodada, um tema, um juiz LLM: benchmark offline, nunca portão.
- Prova de negócio exige dado real por sessão: receita, custo e margem por
  sessão, páginas por sessão, continuidade, CTR por CTA, saída por página, ad
  views, RPM, tempo útil, avanço por caminho, retorno à SERP e conversão.
- Defeitos vistos e NÃO corrigidos aqui (fora do menor delta):
  1. o portão do redator não confere href de corpo contra as URLs autorizadas;
     o revisor pegou, o código não;
  2. a meta description pode herdar instrução do arquiteto;
  3. o arquiteto ainda escreve a primeira dobra como instrução; o próximo teste
     barato é o arquiteto em gpt-6.1-sol com o mesmo contrato.
