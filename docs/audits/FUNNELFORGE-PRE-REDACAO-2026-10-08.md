# Inteligência pré-redação — 08/10/2026

Missão executada exclusivamente na main consolidada `47b66d9`, em
`volc-os-campaign-qg-real-20261007`. Sem branch, worktree, subagente ou segundo
motor. Implementação opt-in pelo card completo (`--card-pre-arquitetura`).
O V1 mantém os prompts e a sequência cobertos pelo ouro existente.

## Causa e baseline

O levantamento read-only de 19 estados/recibos está em
[FUNNELFORGE-PRE-REDACAO-BASELINE-2026-10-08.json](FUNNELFORGE-PRE-REDACAO-BASELINE-2026-10-08.json).
Os estados finais não permitem contar bloqueios transitórios apagados por
retomadas; não se presume que cada run corresponde a uma execução independente.

No Gás do Povo `guia-gas-do-povo-20261008-134021`, as cinco páginas tinham
**zero requisitos factuais explícitos** na arquitetura. O compilador precisava
derivá-los depois. O motor contabiliza **39 chamadas de LLM**: engajamento 1,
pesquisa 4 (duas operações de duas chamadas), briefing 5, redação 6, SEO 5,
widget 3, revisão 5, prompt de imagem 5, revisão de imagem 5. Houve ainda cinco
gerações de imagem. As três chamadas históricas de arquitetura são anteriores
àquele run; com elas, a cadeia registrada soma 42 chamadas de LLM.

A fase paralela durou **516,349 s**, pico 3. Somar latências individuais não
mede duração total: o mínimo reconstruível pela soma das etapas seriais
engajamento/dossiê e da parede paralela é 653,313 s; a parede integral não foi
registrada. O ledger retorna US$ 0,5703025, mas o custo ChatGPT-plan é **não
informado**; o ledger não representa o custo integral. Houve uma retentativa
de redação (`cross_domain`, p4), dois microajustes factuais (p3/p4) e um de
congruência de destino (p5). A cobertura final foi 4 ready / 1 review, com
5/5 rascunhos preexistentes no WordPress. Nenhum deles foi alterado nesta missão.

Separação causal:

- **Arquitetura:** requisitos previsíveis ausentes, correções humanas no
  esqueleto, loops/referências inválidas nos canários anteriores, CTA corrigido.
- **Writer/contrato:** número fora dos fatos, número sem lastro compatível,
  citações ausentes e links externos indevidos nos recibos anteriores.
- **Provider/transporte:** classificados separadamente nos logs; ausência de
  recibo não é prova de ausência de falha. No último run não há erro de
  transporte registrado no log principal.
- **WordPress:** publicação anterior em draft é evidência de transporte e
  persistência, não de qualidade editorial ou visual.
- **Visual:** inspeção autenticada com tema/plugins/anúncios continua pendente;
  não há métrica comercial demonstrada.

## Delta no único motor

Antes: arquitetura → pesquisa global → complementos por página → briefing
pago por página → redação → SEO pago → widget pago → revisão paga por página.

Depois, com card completo: PAA/sinais próprios → pesquisa global grounded →
brief tipado compacto → arquiteto compartilhado com o backend → portão de
esqueleto → complemento factual único em lote → consolidação do dossiê →
pacotes isolados por SHA-256 → redação configurável com 1–3 workers → SEO
determinístico → revisão semântica em lote → integridade técnica final.

O arquiteto recebe intenção, demanda, clusters com IDs estáveis, proveniência,
lacunas, contexto editorial e fatos candidatos com fontes. O mesmo brief é
preservado no contrato de arquitetura entregue ao revisor. Requisitos, valor
exclusivo, próxima dúvida, links, ativos e plano visual pertencem à arquitetura.
O writer recebe a projeção congelada da própria página e o contexto mínimo
dos destinos; não recebe o card nem o dossiê inteiro. A leitura on-demand foi
retirada deste caminho: seu orçamento de novas pesquisas por página é zero.
O complemento ocorre uma vez, deduplica requisitos e falha de forma branda.

As ferramentas continuam usando o contrato de ativos existente. Neste delta,
o pacote sinaliza `fallback_sem_js` e `human_review` quando há ativo pedido;
o writer apresenta somente o fallback declarado. Não há geração extra de
widget nem promessa de interação inexistente. Isso é uma limitação explícita,
não um widget implementado. Não se recomenda publicação automática desse caso.

## PAA

`adapters/attention_matrix.py` importa o sensor real
`backend/app/motor_pautas/sensores/dataforseo.py` e chama
`perguntas_do_paa` e `cabeca_editorial_do_paa`. Reusa SERP do card ou cache
recente (7 dias); se necessário, usa a classe `Cliente` existente com depth=10,
uma chamada e nenhum retry. Sem credencial, localização ou PAA, segue com a
lacuna registrada. PAA e termos de busca são sinais de intenção: nunca são
promovidos a fatos. Agrupamento é conservador; semântica ampla permanece
julgamento do arquiteto, sem criar uma página por pergunta automaticamente.

## Classificação dos gates

| Momento | Gates e finalidade |
|---|---|
| Antes do arquiteto | Proveniência de demanda, separação PAA/fato, sinais ausentes, pesquisa grounded, fontes candidatas |
| Antes do writer | Jornada/referências/loops, entrega exclusiva, sobreposição comprovada, requisito previsível, próxima dúvida, CTA concreto e destino, plano visual/ativo, cobertura factual, conflito central, SHA dos pacotes |
| Depois da redação | HTML/Gutenberg, segurança, integridade contra pacote, números inventados, política, URLs realmente escritas, segurança/lastro do widget, recibo do revisor, SEO/JSON-LD visível, render/build e compatibilidade de publicação |
| Duplicação retirada no caminho novo | Briefing LLM por página, pesquisa independente por página, SEO LLM por página, revisão LLM por página, classificador de engajamento pago antes de escrever |

A revisão global existente confere os links efetivamente escritos e não muda
jornada. A revisão semântica batched usa os contratos/políticas/notas e patcher
V2 existentes; reduz chamadas, sem alegar redução comprovada de tokens.

## Experimento JEV

Transcripts lidos como hipóteses de fornecedor, sem tratar marketing como
calibração. Consultadas somente fontes oficiais TypeSafe:
[introdução](https://typesafe.ai/blog/introducing-system-one-models-and-jev),
[docs](https://api.typesafe.ai/docs), [ReDoc](https://api.typesafe.ai/redoc) e
OpenAPI servido pelo mesmo domínio. O adapter usa `/v1/systemone`, `state` e
`questions` choice, interface de provider, flag `jev_enabled=false`, timeout,
um batch máximo, nenhuma retentativa, recibo pedido/servido e fallback
heurístico. Nenhuma credencial é registrada.

Não havia `TYPESAFE_API_KEY` legitimamente no ambiente: **zero chamada real**.
Quatro rótulos manuais de formato atingem 4/4 na heurística estreita; fixtures
JEV validam transporte/contrato, não medem qualidade do modelo. O classificador
LLM de engajamento existente resolve outro alvo e não tem desempenho comparável
medido neste conjunto. Não foi demonstrada melhora de ranking, classificação,
custo ou latência: **JEV permanece desligado; adoção não recomendada**.

## Referências e limites

Lidos os três transcripts fornecidos, o PDF Pubx 2026 (16 slides, inspeção
visual) e o relatório MiroFish completo. O caminho `/Useads/...docx` não existe;
a cópia de mesmo nome em `/Users/mac/Downloads/` foi utilizada. MiroFish é
simulação qualitativa (0/29 entrevistas), útil para casos de jornada, sem
substituir observação de usuários. Os slides reforçam investigar intenção
antes do conteúdo e medir comportamento antes de promover uma hipótese.

## Validação e canário

**Veredito: parcial, sem aprovação técnica integral da missão.**

Motor: 1.453 testes passaram, 7 skips. Backend afetado: 17 passaram.
O ouro V1 foi conferido sem atualizar nenhum arquivo golden. Os testes novos
cobrem sensor/cache/PAA ausente/agrupamento, separação intenção-fato, brief no
arquiteto e revisor, entrega/loop/CTA resolvido/requisito previsível, lote e
lacuna compartilhada, SHA/cópia isolada/prompt exclusivo, zero writer para
arquitetura inválida, mutação proibida entre workers, fonte indisponível,
JEV desligado/timeout/contrato e publisher proibido.

O único canário real está em
[FUNNELFORGE-PRE-REDACAO-CANARIO-2026-10-08.json](FUNNELFORGE-PRE-REDACAO-CANARIO-2026-10-08.json).

| Medida | Baseline final Gás do Povo | Único canário novo |
|---|---:|---:|
| Chamadas LLM do motor | 39 | 3 (pesquisa 2 + arquitetura 1) |
| Duração de parede | integral não registrada; fase paralela 516,349 s | 241,666 s até recusa |
| Retentativa de redação | 1 | 0 |
| Pesquisas lógicas | 2 | 1 global; complemento não alcançado |
| Páginas planejadas | 5 | 5 no JSON bruto, recusado na carga |
| Pacotes ready/degraded/human_review/blocked | não existiam | 0; congelamento não alcançado |
| Redações | 5 páginas, 6 tentativas | 0 |
| Concorrência observada | pico 3 | não exercitada; configuração 3 |
| Cobertura factual | 4 ready / 1 review | 3 fatos candidatos; cobertura por página não alcançada |
| Custo faturado integral | não informado; ledger parcial US$ 0,5703025 | não informado |
| Escritas externas nesta missão | 0 | 0 |

A resposta do arquiteto usou `fact_id`/`afirmacao` nos requisitos, em lugar de
`id`/`descricao`. O recibo registra `requisitos.0.id: Field required`. O
portão recusou antes do writer: houve zero chamada de redação e zero publicação.
PAA estava ausente nessa referência e não foi o motivo da recusa. Os modelos
servidos foram gpt-6.1-sol na pesquisa e gpt-6-sol na arquitetura, iguais aos
solicitados após remover apenas o prefixo de transporte `chatgpt/`.

Após o canário, o prompt passou a explicitar o schema exato dos requisitos e
a posição dos campos visuais; corrigiu-se também o diagnóstico de arquitetura
recusada e removeu-se duplicação de contexto histórico. Essas correções foram
validadas somente de forma hermética. **Não houve segundo canário.** A carga
inicial do script falhou localmente por ausência do campo vazio `secrets` no
snapshot, antes de autenticação, lock ou qualquer chamada; não se contabiliza
como execução real. Os artefatos da execução real permanecem preservados.

A diferença 39 → 3 não mede aceleração de um funil concluído: o canário novo
parou no esqueleto. Não foi demonstrada redução de custo, tempo de conclusão,
retentativas de texto ou melhora comercial. A arquitetura consumiu 209,979 s
e 30.979 tokens de entrada naquele canário, concentrando a maior parte do
tempo. Compactar o histórico e retirar sua duplicação tem justificativa de
código; o ganho real ainda não foi medido.

Pendências: aderência real ao schema corrigido, complemento/pacotes/redação
paralela/revisão global num funil real completo, geração de ferramentas pelo
contrato congelado (hoje fallback textual + revisão), inspeção visual autenticada
e os demais critérios já pendentes em P10-T22. Nenhuma dessas lacunas autoriza
um segundo canário nesta missão. P10-T22 permanece partial; cap_funnel conserva
o estado de negócio anterior.

## Correção e validação final

Uma rodada posterior corrigiu as lacunas reveladas pelo primeiro canário sem
criar outro motor ou um caminho rápido paralelo. O contrato passa a normalizar
os aliases reais `fact_id`/`afirmacao` para `id`/`descricao`, mas falha fechado
se alias e campo canônico divergirem. A extração também aplica papéis, slugs e
ordinais antes da ponte; a retomada preserva a ordem das páginas; o CTA usa o
rótulo tipado do destino; uma saída oficial desativada pelo dossiê não reaparece
por fallback; e grupos Gutenberg de botões adjacentes são consolidados antes do
gate. O ouro V1 permaneceu intacto.

O canário seco pós-correção
`gas-do-povo-20261008-pre-redacao-pos-fix-final-20261008` chegou à redação
paralela com 5/5 writers aprovados, 10 chamadas no plano ChatGPT, duração total
de 555,455 s e zero publicação. O gate final da LP encontrou uma nova regressão:
seis fontes oficiais externas tinham sido transformadas em links clicáveis no
corpo da página paga. O histórico desse canário permanece imutável e registra a
reprovação corretamente.

A correção final tornou explícito no pacote que fontes externas da LP são
referências em prosa e adicionou uma sanitização determinística recursiva que
remove apenas o link externo, preservando texto e links internos. O artefato
exato reprovado foi recomposto sem nova chamada a modelo: 6 links externos
foram convertidos em prosa e `content_gate_p1` passou com status `OK` e zero
issues. A suíte integral terminou com **1.466 passed / 7 skipped / 0 failed**;
o recorte afetado do backend terminou com **10 passed / 0 failed** e
`git diff --check` passou.

Veredito honesto: o caminho pré-redação está tecnicamente validado pela suíte,
pelo canário real até os writers e pelo replay exato do único gate final que
falhou. Não houve um terceiro canário pago depois da sanitização, publicação,
deploy ou escrita em WordPress/Supabase/Ads. P10-T22 permanece `partial` pelos
critérios amplos já existentes (matriz real de modelos, sinal real e inspeção
visual autenticada), não por uma falha conhecida deste fluxo pré-redação.
