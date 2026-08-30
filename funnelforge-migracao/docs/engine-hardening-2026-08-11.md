# Hardening factual e editorial do motor — 2026-08-11

## Veredito

O problema não era apenas a configuração. Os defeitos 1, 2, 3, 4, 5 e 7
tinham caminhos reais até a publicação. O defeito 6 estava parcialmente
coberto por prompt/validator e pelo CSS do site, mas não por um contrato final.
No item 8, três listas vazias foram interpretadas incorretamente como ausência
de validação: LP, judge e widget já tinham gates diretos fora do `Runner`.

O endurecimento ficou em três camadas:

1. pesquisa factual tipada e fail-closed;
2. contratos determinísticos de conteúdo e apresentação;
3. gate sobre o rascunho pós-widget e sobre o artefato exato pós-decorações que
   seria enviado ao WordPress REST.

O grafo, `phrase_registry`, `research_hosts`, `sanitize_widget_block` e
`step_screenshot` foram preservados.

## Diagnóstico por defeito

| # | Onde deveria parar | Por que passava | Contrato implementado |
|---|---|---|---|
| 1. Fato sem procedência | `domain/models.py`, `step_research`, `step_write` e gate final | `ResearchFacts` não distinguia nota qualitativa de fato publicável; `sparse=True` não falhava a etapa | `VerifiedFact` exige valor, unidade, fonte primária HTTPS, dispositivo, vigência e verificação. Pesquisa esparsa falha. Fonte crítica precisa resolver ao vivo. Redator não roda após `research FAILED`. Número/prazo/norma no conteúdo precisa casar com fato resolvido e citar a URL. |
| 2. `<p>` em raw HTML | `sanitize_widget_block`, biblioteca Gutenberg e gate final | não havia contrato estrutural; procurar só `<p>` perderia `<p class=...>` | `<p\b` é proibido em qualquer `wp:html`, inclusive com atributos. Widget usa `div`/`span`; a allowlist não contém `p`. |
| 3. Texto direcional + anúncio | enhancer, `ad_interaction` e configuração de anúncios | o motor não recebia as âncoras de parágrafo e instruções posicionais ficavam fora do componente | `ads.paragraph_anchors` é entrada de projeto. O enhancer mantém uma janela plana até depois da última âncora. Copy como “responda abaixo” fora do widget falha. |
| 4. CTA enganoso | `cta_style` | a lista de verbos cobria termos isolados, não a relação label/href | `cta_destination_mismatch` detecta verbo de ação + menção a app/site/canal externo + href interno. “Ver como consultar…” continua permitido. |
| 5. Outline invisível | contrato final | não havia regra sobre `is-style-outline` | `outline_button` impede publicação. |
| 6. Blocos colados | `bridge_before_cta`, contrato final e CSS | o writer já desaconselhava empilhamento, mas a última transformação não era revalidada | grupos `wp:buttons` consecutivos falham; grupos `wp:group` irmãos exigem margem explícita no segundo. O CSS continua sendo a defesa de renderização do tema. |
| 7. Parede de texto | declaração de engajamento, prompt e `visual_contract` | a biblioteca oferecia blocos, mas a escolha era probabilística e não havia mínimo semântico | o tipo da pergunta determina os blocos obrigatórios; o Runner recebe feedback e tenta novamente. Imagem continua pertencendo a `step_image`/`step_screenshot`, não é inventada pelo enhancer. |
| 8. Config desalinhada | `config.yaml`, `SiteConfig`, `same_domain` e `build_official_links` | CNPJ era placeholder; a preferência oficial era de outro funil; a preferência também autorizava host | CNPJ real validado por dígitos; preferências FGTS; `same_domain` ignora a lista estática e autoriza só hosts da pesquisa; fallback curado não pesquisado foi removido. |

## Camada factual

O contrato publicável é `VerifiedFact`:

```text
valor · unidade · fonte_primaria · dispositivo · vigente_desde · verificado_em
```

`dados_validados` continua existindo para compatibilidade e contexto
qualitativo, mas não autoriza número, percentual, prazo, limite ou dispositivo
legal. O fluxo é:

```text
provider/fallback
  -> parse tipado
  -> has_sources + freshness/provenance
  -> verificação ao vivo das fontes dos fatos críticos
  -> research OK
  -> writer recebe fatos
  -> critical_fact_grounding no texto
  -> gate final antes do REST
```

Se não houver fonte, a pesquisa fica `FAILED`; não há texto “com menos prova”.
Se houver fato crítico sem verificador ou com URL que não resolve, a pesquisa
também falha. Se o modelo escrever uma Resolução, valor, percentual ou duração
que não aparece num fato resolvido, o conteúdo falha. Mesmo um fato válido
falha se sua `fonte_primaria` não estiver citada no artefato.

## Vocabulário visual determinístico

| Engajamento | Blocos mínimos |
|---|---|
| `condicional` | `wp:details`, `wp:columns` |
| `sequencial` | `wp:details`, `wp:list` |
| `comparativo` | `wp:details`, `wp:table`, `wp:columns` |
| `diagnostico` | `wp:details`, `wp:columns` |
| `dado_unico` | `wp:details`, `wp:table` |

O classificador humano/LLM continua tendo precedência. Saída ausente ou fora do
vocabulário usa H1, objetivo e estrutura para inferência semântica. Foi removida
a escolha por `sha1(run_id)`/posição: duas páginas com a mesma forma de pergunta
podem receber a mesma ferramenta porque a utilidade vence diversidade cosmética.

`wp:image` não é exigido do redator: a imagem destacada e o print oficial são
inseridos por etapas que possuem a URL/arquivo real. Obrigar o writer a emitir
`wp:image` criaria placeholder ou URL inventada.

## Crítica ao protótipo `blocos.py::validar()`

Partes aproveitadas:

- proibição de copy direcional fora do componente;
- relação entre CTA e destino;
- rejeição de outline e de blocos consecutivos;
- exigência de diversidade estrutural.

Correções feitas:

- a busca é `<p\b`, portanto captura atributos;
- não se aceita `<p>` algum em raw HTML, não apenas o vazio;
- “qualquer parágrafo antes do widget” era amplo demais: prosa editorial normal
  não é indução; o gate procura imperativo posicional;
- domínio não é hard-coded no validator;
- cores e URLs não são inferidas do HTML; pertencem às rotas tipadas;
- regex de contagem de blocos foi substituída por requisitos ligados ao
  `engajamento`, evitando premiar quantidade sem função;
- as regras rodam de novo depois de normalize/widget e depois das decorações de
  publish, não apenas sobre a primeira resposta do modelo.

## O que foi deletado ou deixou de decidir

- fallback de `official_entry_points` quando a pesquisa não trouxe URL;
- autorização externa por `allowed_external` no `same_domain`;
- sorteio de arquétipo por hash do `run_id` e ordinal;
- `<p>` na allowlist e nos exemplos de raw HTML;
- degradação silenciosa de pesquisa `sparse`;
- publicação sem widget quando a feature está ligada e a semântica exige um
  (a exceção explícita é `dado_unico`).

Não foram adicionados validators artificiais a `steps.widget`, `write_p1` ou
`judge`: essas listas vazias são intencionais. O widget usa sanitização direta
mais gate final; a LP usa schema/template e factual grounding; o judge é
parseado em `Verdict` e tem gate existencial próprio. Duplicar esses contratos
no `Runner` aumentaria superfícies divergentes sem aumentar segurança.

## Modos de falha esperados

O primeiro modo de falha provável é disponibilidade/falso negativo da fonte:
uma página oficial pode bloquear Chromium, mudar URL ou responder com erro
temporário. O primeiro sinal será `research_pN FAILED` com
`fact_source_unreachable` (ou `fact_source_verifier_missing`), antes de qualquer
chamada ao redator.

O segundo é sobrebloqueio lexical no `critical_fact_grounding`: um prazo
editorial legítimo pode ser lido como fato crítico, ou uma grafia equivalente
ao fato pode não casar literalmente. O sinal será
`ungrounded_critical_claim` no retry do writer/content gate. A correção correta
é melhorar o normalizador/estrutura do fato, não relaxar para aceitar qualquer
número.

O terceiro é o classificador semântico escolher um eixo inadequado. O primeiro
sinal será uma sequência de retries com `missing_semantic_block`, ou um widget
correto tecnicamente mas pouco útil. A telemetria por arquétipo deve mostrar
baixa interação; isso pede ajuste nos sinais de `infer_engajamento`, não volta
ao sorteio.

Risco residual deliberado: `step_screenshot` continua best-effort. Um print
ausente não torna o texto falso e, por decisão anterior, não bloqueia a página.
Já um fato sem fonte, widget prometido ausente ou estrutura editorial inválida
bloqueia o REST.
