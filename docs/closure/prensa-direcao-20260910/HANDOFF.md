# PRENSA: replay controlado, direção v2

## Veredito

**PARTIAL — melhora de legibilidade comprovada; vitória estética sobre a IA não comprovada.**

Base `2cb33f2`, worktree de operação preservado. Sem nova geração de imagem, chamada de LLM, alteração de campanha, banco ou reinício do container. Três rodadas de oito renders offline no Chrome existente; a última tem oito aprovações DOM e oito PNGs.

## O que mudou

- §2.1–2.3: registros Archivo/Source Serif/Mono e Barlow/Inter; catálogo dos dez arquivos existente disponível; métricas hhea fundamentam padding. Renderer respeita variações no papel principal; os displays Archivo/Barlow não têm opsz (correção de precisão após revisão do Claude). Nenhuma necessidade de usar dez fontes simultaneamente.
- §2.3–2.4: piso do apoio protegido por prioridade de shrink; CTA maior; ritmo derivado da escala; âncora composta não quebra no hífen.
- §2.5–2.8: cartaz tem coluna e checklist lateral; documento mantém grade editorial. Tinta escura no plano claro, clara no escuro; véu só na zona medida, com simulação sRGB e target7:1. Vignette e ruído globais não são obrigatórios.
- §3: tratamento desconhecido falha; sombra e sangria compõem sem uma apagar a outra; as letras das colunas v2 passam pela verificação DOM.

## Prova e limites

Atualização em 11/09: [refino pós-Claude](../prensa-refino-20260911/HANDOFF.md), com contraste vinculado ao recorte real, prova comportamental de Chrome e regressão do acervo. A prova abaixo é histórica; foi preservada também em `/Users/mac/Desktop/RUN-REAL-PEDEMEIA/6-direcao-v2/`.

Comparação final local:
`/private/var/folders/n_/pq8ng_k14vsfx82xb9b8b3980000gp/T/volc-prensa-direcao-x89y8jlo/comparacao.html`

O diretório contém `antes/`, `depois/`, specs resolvidas, oito recibos, logs e `manifest.json` com SHA das cenas e igualdade de copy/gates. Nenhum PNG original foi sobrescrito. A igualdade de copy cobre headline/complemento/CTA; checklist aprovado também foi mantido, com outra disposição. Cada formato reaproveita sua própria cena nativa, não um recorte de outra proporção.

Na peça documento4x5: headline108→99px; apoio27→39px; CTA24→36px. Não é simplesmente aumentar tudo: reduzimos a distância entre os papéis e mantivemos a âncora inteira. O checklist agora é legível, mas continua trazendo carga informativa. A direção continua editorial, não produz integração física entre letra e figura.

88 testes focais passaram. Regressão criativa ampliada final:1201 passed,62 skipped,4 failed; os mesmos quatro nomes de falha informados na base (auth503/401, presença estática de publicar_artefato e duas diferenças da toolchain/OpenAPI). Não foram escondidos ou alterados nesta frente.

A medição local usa percentil5 da zona, **não** um pixel gate de glifos. O serviço HTTP não foi ampliado nem implantado: `/render` continua exigindo spec resolvida. `colocacao.modo=auto` não foi conectado ao tradutor; a coluna lateral é hipótese geométrica, não detecção de sujeito. Cinco registros têm vocabulário, mas esta prova real só exercita documento e cartaz. Não se declara todo o catálogo aprovado visualmente.

## Ativação deliberada

Use `traduzir(..., versao_direcao="2")` com `skin_da_familia(..., versao_direcao="2")`. Sem versão na spec, o tradutor continua v1; `versao_direcao="1"` permite gerar a skin antiga. Esta rodada não muda silenciosamente um lote aprovado nem ativa a direção candidata na UI.

Reproduzir sem provider:

```sh
/usr/local/bin/python3 tools/prensa/replay_direcao.py --source /Users/mac/Desktop/RUN-REAL-PEDEMEIA
```

## Julgamento de produto

Não recomendo substituir automaticamente a letra da IA por esta versão. PRENSA ganhou leitura, correção determinística e contraste verificável por zona; as peças de IA ainda integram melhor cena e tipografia. O próximo aceite precisa ser visual, não mais uma contagem de efeitos. Perspectiva, oclusão e letreiro físico seguem no caminho da IA; a PRENSA é candidata para peças em que copy exata e edição sem regenerar a cena são determinantes.

Roadmap `P11-T22` partial, relacionado a `P11-T17`. Nó `doc:prensa-direcao-v2` documenta `system:prensa`. Decisões e achados negativos registrados seguindo a skill de documentação/ADRs.
