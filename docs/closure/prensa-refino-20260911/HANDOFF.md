# PRENSA — refino pós-Claude, 11/09/2026

## Resultado

**Candidato local validado tecnicamente; homologação estética e integração automática pendentes.**

Preservados os commits `fdb0fa7` e `678d5d8`. Trabalho sobre o worktree operacional, sem tocar as alterações paralelas de meta-adk-loop/VarinhaDeCopy. Nenhum modelo, geração paga, token, banco ou anúncio foi usado nesta rodada. Container original não foi reiniciado/reconstruído; código candidato executou em diretórios isolados no seu `/tmp`.

## Correções e evidências

| Achado | Correção / prova |
| --- | --- |
| Contraste podia medir recorte diferente do exibido | Fonte única na camada image, não no scrim. Fixture com esquerda preta/direita branca reprova a leitura otimista da cópia antiga. Recibo identifica camada, cover e posição. |
| Teste de shrink só inspecionava a spec | Chrome: título99→59px na zona menor; apoio39px e CTA32px preservados. Zona impossível reprova. |
| Peso declarado diferente do pintado | Fixture declara400 e pinta wght800: recibo agora devolve800. Runs também registram variação. |
| Borda dura e empilhamento de alpha | Máscara com patamar interior e transição exterior. Screenshot sintético: borda99/100px passou de149/127 para128/127; miolo permanece127 em branco+preto50%. |
| Catálogo inteiro embutido | 3 arquivos por peça: documento2.006MB, cartaz1.090MB contra5.551MB do catálogo anterior (bytes antes do base64; redução64–80%). Defaults itálicos dos runs cobertos por teste. |
| CTA e apoio com mesmo piso no banner | CTA mínimo32px; apoio mínimo24px. Os recibos registram os tamanhos reais. |
| Sangria pintada por baixo | Ordem de text-shadow corrigida; teste anterior agora exige sangria primeiro. |
| Regressão spec_news só provada em unidade | Spec original+tokens originais+fundo existente passaram resolve→Chrome→PNG, sem modificar originais. |

## Provas executadas

- TDD: 9 falhas esperadas antes dos consertos; prova de máscara falhou no Chrome antigo com salto22 níveis sRGB na borda e passou na nova implementação.
- 92 testes focais passaram: `services/prensa/tests`, tradutor e direção.
- Suíte criativa ampliada: **1204 passed, 62 skipped, 4 failed**. Mesmos quatro nomes registrados na base: autenticação503 sem configuração Supabase de teste, FastAPI diferente do pin, OpenAPI golden divergente dessa toolchain e teste estático de storage/publicar_artefato. Não se declara suíte inteira verde.
- **8/8 peças + spec_news**: nove PNGs e nove recibos DOM `ok:true`. Mesmo Chrome **153.0.8010.36**, x86_64; sem trocar plataforma nem diminuir gates.
- Mesmas oito cenas pagas, SHA de cada fundo e igualdade de headline/complemento/CTA no manifesto. Nenhuma copy reescrita nesta comparação; checklist conservado pelo tradutor.
- Três replays aprovados durante o ajuste, sendo o último a entrega com CTA32 e comparação em três colunas. O teste adicional final dos defaults itálicos cobre uma combinação não usada nesse lote.

Prancha final: `entregaveis/prensa-refino-20260911-handoff/comparacao.html`. Inclui original v1, v2 resgatada pelo Claude e refinamento; manifest, logs, prova_chrome.json, acervo.json, specs e recibos. Exportada também para a pasta de estudo do operador: `/Users/mac/Desktop/RUN-REAL-PEDEMEIA/7-refino-v2-20260911/`.

Reproduzir (diretório de saída precisa ser novo):

```sh
/usr/local/bin/python3 tools/prensa/replay_direcao.py \
  --source /Users/mac/Desktop/RUN-REAL-PEDEMEIA \
  --output /private/tmp/prensa-novo-replay
/usr/local/bin/python3 -m pytest services/prensa/tests \
  backend/tests/test_criativo_prensa_direcao.py \
  backend/tests/test_criativo_prensa_tradutor.py -q
```

O replay exige container `volc-prensa` em execução com Chrome/fontes e o fundo legado `out/bg_news.png`. Não tenta gerar material ausente. O código Python de staging e os logs ficam juntos da entrega; chamadas de subprocess têm timeout.

## Julgamento visual e próximos critérios

A borda do véu perdeu o corte abrupto; CTA horizontal ganhou corpo. A composição continua com cartelas e regiões editoriais: o cartaz4x5 ainda mostra uma área clara forte, e o checklist lateral é heurístico. O teste sintético prova continuidade/alpha, **não beleza**. A prova real exercita documento e cartaz, não todo o catálogo.

Não habilitei `colocacao.auto` como se fosse detecção de sujeito: o solver legado não oferece essa garantia. Não há gate por glifo sobre a foto final, oclusão ou perspectiva física. `opsz` não existe nos displays Archivo/Barlow; o suporte do renderer não cria um eixo inexistente. Não prometemos CTR nem que PRENSA superou a tipografia da IA.

Direção permanece **opt-in nas duas portas**, `skin_da_familia(..., versao_direcao="2")` e `traduzir(..., versao_direcao="2")`. Não houve implantação na UI nem mudança no contrato HTTP de `/render`.

Memória operacional: `P11-T22` **partial**, relacionado a `P11-T17`; nó `doc:prensa-direcao-v2` → `system:prensa`. Skill documentation-and-adrs orientou o registro dos limites, das decisões e das provas, sem promover a tarefa a done por contagem de testes.
