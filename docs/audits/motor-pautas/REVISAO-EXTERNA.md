# Prompt de revisão externa — motor de pautas

> Auditoria datada: evidência de revisão, não contrato de runtime.

Cole tudo abaixo da linha. Vale para Grok, GPT, Claude ou qualquer revisor.

---

Preciso de uma revisão adversarial de um modelo de decisão que estou construindo. Não quero validação — quero saber onde ele está errado.

# 1 · A OPERAÇÃO

Arbitragem de tráfego. Compro clique no Google Ads (Search e Display) e monetizo com anúncios display (AdSense/AdX/GAM) em portais que **explicam** serviços, benefícios e documentos — nunca vendo nada, nunca capturo dado. A receita é a diferença entre o RPM da página e o CPC do clique.

Números reais de um mês medido (junho/julho de 2026, Brasil + LATAM):

```
investido      R$ 461.364
receita        R$ 592.080
ROAS do que consigo parear   1,463  (60.581 pares campanha × dia × placement)
cobertura                    70,9% do investimento
```

O funil é fixo: uma landing page → um hub qualificador → 3 páginas de solução, interligadas por um grafo tipado, acíclico, forward-only. Um funil = ~5 páginas, ~8 mil palavras, produzido por um pipeline automatizado.

**A decisão que importa é qual tema atacar.** Errar o tema custa uma quinzena de produção e verba de teste. É isso que o modelo abaixo tenta resolver.

# 2 · O MODELO

Código: `motor_pautas/espaco.py` — Python puro, só stdlib, 54 testes.

Cada tema é um ponto num espaço de **10 eixos em 3 famílias**, combinados por **média geométrica ponderada** (não aritmética), com **3 portões** que multiplicam o resultado inteiro.

## Família A — DEMANDA HUMANA (por que ela LÊ)

| eixo | mede |
|---|---|
| `ignorancia` | o buraco de conhecimento com que ela chega |
| `engajamento` | quanto tempo de atenção a resposta EXIGE |
| `opacidade` | o quanto a instituição esconde |
| `reposicao` | entra gente nova na condição, ou é a mesma voltando? |

## Família B — ECONOMIA

| eixo | mede |
|---|---|
| `volume` | quantas pessoas por mês |
| `spread` | RPM ÷ CPC, no nível arquétipo × país |
| `densidade` | quantos setores pagariam para falar com essa pessoa |
| `formato_consumo` | naquele país, "como fazer" acontece em texto ou vídeo? |

## Família C — POSIÇÃO

| eixo | mede |
|---|---|
| `vacuo` | quantos já explicaram bem |
| `producao` | custo de manter a página viva |

## Os 3 portões (multiplicam, não somam)

```
engajamento = dado_unico          a resposta esgota em segundos; o anúncio não
                                  chega a ficar visível
ignorancia  = nao_preciso_de_nada não há nada em jogo
formato_consumo = video_social    o "como fazer" acontece em vídeo e mensageria;
                                  o funil de texto não fecha
```

Portão não é peso alto. Com 10 eixos, mesmo o maior peso vale ~15% da influência: um tema `dado_unico` com todo o resto perfeito ainda pontuava 0,546 antes de os portões existirem.

## Decisões estruturais

- **Média geométrica, não aritmética.** A economia é multiplicativa: pressão máxima × resposta que esgota em segundos não vale a média dos dois.
- **Eixo desconhecido fica FORA da conta, nunca vira 0,5.** Abaixo de 3 eixos legíveis, o modelo se recusa a dar índice. Preencher buraco com meio-termo é inventar informação.
- **Os pesos são priores DECLARADOS, não calibrados.** Há um dict `_CALIBRACAO` vazio, com teste garantindo que continue vazio. O porquê está no item 3.
- **A saída é posição + quadrante, nunca probabilidade calibrada.** Quadrantes: `alvo` · `audiencia_pobre` · `mercado_rico_sem_leitura` · `descartar`.

# 3 · O QUE JÁ TESTAMOS E REJEITAMOS — com os números

**Não me proponha nenhuma destas de volta sem um argumento que derrube a medição.** Cada uma foi tentada com convicção e morreu num número.

**Modelo ajustado nos 237 temas da operação.** Regressão logística L2, alvo `lucro > R$3.000`, AUC fora da amostra 0,689. Caiu porque **`spend` sozinho prevê o alvo com AUC 0,971** — o modelo aprendeu em que a equipe decidiu investir, não o que é bom tema. Spend mediano dos "vencedores" R$12.430; dos "perdedores" R$483. A maioria dos perdedores não perdeu: foi descartada antes de ser testada. Também não generalizava: deixando um arquétipo inteiro fora do treino, AUC caía para 0,605.

**Ordenar a pressão psicológica por persistência.** Correlação com desfecho **+0,017** (nada). `direito_latente` 33% de vitória, `compulsao` 11%, com amostras equilibradas — três vezes de diferença na direção oposta à prevista. Reordenando por **ignorância**, a correlação foi para **+0,194**.

**Teoria da Perspectiva (Kahneman) como prior.** A literatura diz que perda pesa ~2× o ganho. Medido nas nossas tensões: **1,06× numa rodada e 0,69× na outra** (invertido). O motivo é conceitual: Prospect Theory descreve **escolha sob risco**; aqui se mede **leitura**. O mesmo vale para o Fogg Behavior Model, que descreve *agir*, não *ler*.

**Loewenstein (hiato de informação) como curva.** Prevê U invertido, com pico no hiato moderado. Medido: **monotônico decrescente**, pico no hiato máximo (1,68× e 1,52×). Mas o teste produziu o achado mais limpo: `curiosidade pura` deu **0% de vitória em duas rodadas** — hiato máximo e nada em jogo. Foi isso que virou o portão de ignorância.

**IAB como feature.** Três variáveis derivadas da taxonomia pioraram o AUC fora da amostra (−0,011 a −0,013). Ficou como camada de classificação e interoperabilidade, não de pontuação.

**`spread` como média nacional.** Pearson **−0,266** contra os mercados medidos. Média de país dilui o nicho no run-of-network. A unidade correta é arquétipo × país.

**Trava de concordância entre duas declarações independentes.** A evidência era boa (r=+0,135 onde concordam vs −0,032 onde discordam), mas não foi implementada: concordância pode medir só **facilidade do item**, selecionar por ela **encolhe a amostra e infla correlação**, e dois agentes do mesmo modelo não são independentes de verdade.

**O limite de resolução da base:** n=235, erro padrão da correlação **0,065**. Diferenças menores que ~0,13 são indistinguíveis de ruído. Continuar afinando contra esses 237 temas é ajustar ruído.

# 4 · A EVIDÊNCIA MAIS RECENTE

Rodei o modelo contra o scorer que já existe no meu sistema — uma nota de arbitragem que é `volume×0,25 + rpm×0,40 + concorrência_invertida×0,35`, multiplicada por confiança e tier — nas mesmas 20 entidades de finanças/Brasil.

**Correlação de Spearman entre os dois ranqueamentos: −0,092.** Zero.

Duas discordâncias grandes:

- **IPVA**: tier A, 1,8 milhão de buscas/mês (o maior volume das 20). O modelo dá **0,005** e barra: a resposta é um dado único e o eCPM é baixo.
- **Home Equity**: tier B (o mais baixo), 85 mil buscas. O modelo põe em 3º de 20: vácuo virgem, ignorância máxima, eCPM premium.

# 5 · O QUE EU JÁ SEI QUE ESTÁ FRACO

- O modelo assume **Google** como buscador. Na Coreia é Naver, na Rússia Yandex, na China Baidu.
- `formato_consumo` por país vem de **tabela escrita à mão**. É estimativa, não medição.
- Na fase de descoberta, `volume`, `spread`, `vacuo` e `densidade` são **palpite de LLM**. Só viram medição depois da mineração de keywords.
- Os 5 eixos "declarados" (`ignorancia`, `engajamento`, `opacidade`, `formato_consumo`, `producao`) dependem de um agente classificar bem. A primeira rodada falhou por concentração (149 de 235 casos no mesmo rótulo); uma rubrica ancorada levou `densidade` de −0,035 para +0,208.

# 6 · O QUE EU QUERO DE VOCÊ

Responda nesta ordem, e seja específico:

**1. A objeção mais forte.** Uma só — a que mais provavelmente faz o modelo falhar na prática. Não me dê uma lista de cinco preocupações médias.

**2. O que você DELETARIA.** Qual dos 10 eixos você tiraria, e por quê ele não está pagando o próprio custo de declaração? Um modelo com menos eixos que decide igual é melhor.

**3. A média geométrica está certa?** Ela pune desequilíbrio com força. Existe caso real de arbitragem em que um eixo baixo é compensável e eu estou matando o tema à toa?

**4. Os pesos.** Estão declarados, não calibrados, porque calibrar contra lucro contamina (ver item 3). Se você calibraria mesmo assim: **contra qual alvo**, e como evitaria a contaminação que o `spend` com AUC 0,971 causou?

**5. O que não estou medindo e deveria.** Só se você puder dizer **como medir** com dado obtenível — não me proponha um eixo que exige um estudo que eu não vou fazer.

**6. Portão ou peso.** Os 3 portões estão certos como binários? Algum deveria ser gradiente? Falta algum portão?

## Regras da resposta

- **Elogio só com especificidade.** Se algo está certo, diga *o quê* e *por quê* isso resolve um problema real. "A abordagem é sólida" não me serve para nada.
- **Se discordar da minha interpretação de um número, diga.** Eu posso ter lido errado a minha própria medição — já aconteceu três vezes neste projeto.
- **Prefira estar errado e específico a estar seguro e vago.** Uma hipótese falsificável vale mais que uma ressalva prudente.
