# BEFORE-AFTER — por superfície

## 1. Manifesto de canal (backend → navegador)

| | |
|---|---|
| **Problema anterior** | O manifesto de Performance Max viajava para o navegador dizendo *"não há construtor de campanha para Performance Max — o engine levanta exceção"*, enquanto os portões do **mesmo payload** diziam que o canal planeja e que a criação está retida. |
| **Mecanismo** | `plataforma.py` é escrito à mão e não importa o engine (por contrato). Nada obrigava a frase a acompanhar `perfil.py`, que referencia `planejador=pmax.planejar` desde a fatia de planejamento. A frase envelheceu sozinha. |
| **Correção** | A indisponibilidade passa a nomear o **registro do executor** como impedimento, e separa *criar* de *provar por validate_only*. |
| **Evidência** | `test_o_manifesto_nao_nega_construtor_de_canal_que_planeja` lê por AST quais canais têm planejador e falha se o manifesto deles afirmar ausência de código. |
| **Impacto** | O operador para de ser mandado a quem escreve o engine para destravar uma decisão de produto. |
| **Limitação** | A prova cobre a classe "afirmar ausência de código". Um texto novo que erre de outro jeito passa. |

## 2. Contrato TypeScript do manifesto

| | |
|---|---|
| **Problema anterior** | Dois tipos para o mesmo objeto de resposta, já divergentes em três campos: `sabe_provar` opcional num e obrigatório no outro, `plataforma` estreito num e `string` no outro, `capacidades` idem. |
| **Mecanismo** | `lib/trafego/canais.ts` nasceu depois e redeclarou em vez de importar. Nada no build compara os dois. |
| **Correção** | `ManifestoDoCanal` vira alias do tipo canônico. `sabe_provar` deixa de ser opcional — o Python o emite em toda resposta. |
| **Evidência** | 5 casos que leem a FONTE. Uma prova de atribuição passaria mesmo com duas declarações divergentes. |
| **Impacto** | 12 erros de tipo apareceram — todos em fixtures que montavam um manifesto que o servidor não sabe emitir. |
| **Limitação** | A coerência com o Python continua garantida por testes de travessia (AST), não por geração. |

## 3. Aba **Criar** — o veredito

| | |
|---|---|
| **Problema anterior** | O estúdio lia capacidades, vocabulário e trava, e **não lia `GET /canais`** — onde mora o veredito. A lista de etapas era um `<ol>` não interativo; o próprio cabeçalho declarava "não monta pedido, não chama /provar e não chama /subir". |
| **Mecanismo** | Manifesto responde "este canal SABE criar?"; portão responde "e EU posso, agora, e se não, por quê?". Display responde `sabe_criar: true` **e** `criavel_pausada: BLOQUEADO`. |
| **Correção** | `JornadaDoCanal` desenha os quatro portões com causa, origem → *a quem pedir*, revalidação e data de observação. Abaixo, as treze etapas — construídas, testadas e até então importadas só por testes. |
| **Evidência** | 19 contraprovas + 104 capturas. |
| **Impacto** | A pergunta "dá para fazer alguma coisa aqui hoje?" passa a ter resposta em quatro linhas, com a porta certa para cada recusa. |
| **Limitação** | A jornada é **leitura**. Ela não monta pedido — `campos_do_pedido` é vazio para PMax e o caminho HTTP de Display não carrega imagens. |

## 4. A etapa de ativação

| | |
|---|---|
| **Problema anterior** | Fechava com *"não há campanha criada para ligar"* — dependência de **sequência**. Bastava responder `criacao` para a etapa abrir. |
| **Mecanismo** | `montarConversa` recebia manifesto, papel e trava, e **não** os portões. Recriava elegibilidade no navegador. |
| **Correção** | Os portões mandam nas três etapas finais. Nenhuma resposta do operador reabre o que o servidor fechou; sem portão lido, a regra local continua conservadora. |
| **Evidência** | Três casos, incluindo a prova direta na máquina com `respostas.criacao` preenchido. |
| **Impacto** | A promessa falsa mais cara da tela deixa de existir: `ativavel` é BLOQUEADO em **16 de 16 células** medidas. |
| **Limitação** | A ordem local ainda decide entre etapas que o servidor permitiu. |
| **Origem** | Revisão adversarial, lente 1 — **bloqueava o aceite**. |

## 5. O CTA por canal

| | |
|---|---|
| **Problema anterior** | O rótulo saía de `manifesto.sabe_criar`, então Display era convidado a *"Começar campanha"*. |
| **Mecanismo** | A porta é uma só e monta Search: `NovaCampanhaPage.tsx:414` envia `canal: 'SEARCH'` fixo. O manifesto dizia a verdade sobre o CANAL; o rótulo mentia sobre a PORTA. |
| **Correção** | Canais não-Search passam a dizer *"Preparar por Search"*, com o motivo. |
| **Evidência** | Dois casos, um deles canal a canal. O teste anterior **fixava a promessa falsa**. |
| **Impacto** | O operador deixa de descobrir a troca dentro de um formulário que pede keywords. |
| **Limitação** | O convite continua levando a Preparar. A porta multicanal não existe. |
| **Origem** | Revisão adversarial, lente 4. |

## 6. Navegação para a página canônica

| | |
|---|---|
| **Problema anterior** | O ÚNICO caminho de entrada era `<a href="/trafego/campanhas/:id">` numa linha expandida do inventário. |
| **Mecanismo** | Âncora crua não navega na SPA: recarrega o documento e refaz **todas** as leituras do Hub. O mesmo valia para `cockpit_href`, que o servidor monta como `/dashboard/campaign/:id`. |
| **Correção** | Os dois viram `<Link>`. |
| **Evidência** | Uma varredura que falha se qualquer `<a href>` em `components/trafego` ou `pages/trafego` apontar para rota interna. |
| **Impacto** | Abrir uma campanha deixa de custar o inventário inteiro. |
| **Efeito colateral revelador** | 48 montagens de teste passaram a exigir `MemoryRouter`. Elas montavam em qualquer lugar **porque a navegação era a errada**. |

## 7. Repetição na lista de etapas

| | |
|---|---|
| **Problema anterior** | Um canal sem construtor devolve treze etapas bloqueadas pela **mesma** frase, e a lista imprimia a frase treze vezes. |
| **Mecanismo** | Só apareceu ao montar o componente pela primeira vez. Ele estava testado — os testes montavam poucos passos. |
| **Correção** | Causa única é dita uma vez, no cabeçalho. Causas **diferentes** voltam linha a linha, porque aí a diferença é a informação. |
| **Evidência** | Dois casos, um para cada lado. |
| **Impacto** | O nome da etapa — a única informação nova de cada linha — volta a ser legível. |

## 8. A bancada visual no bundle de produção

| | |
|---|---|
| **Problema anterior** | A rota de QA ia para o build de produção: `assets/BancadaVisual-*.js`, com as fixtures dentro. |
| **Mecanismo** | O Rollup monta o grafo de módulos a partir de cada `import()` **antes** da eliminação de código morto. Guardar a rota com `import.meta.env.DEV` elimina o ramo; guardar o `React.lazy` elimina a chamada; nenhum dos dois elimina o chunk. |
| **Correção** | `vite.config.ts` troca o módulo por um substituto vazio quando `mode === 'production'`. |
| **Evidência** | `gate_bancada_fora_do_bundle.py` roda `vite build` e varre a saída. **Provado ao contrário**: com o alias desligado ele acusa o arquivo e sai 1. |
| **Impacto** | Ferramenta de conferência deixa de ser publicada. |
| **Lição** | A prova de FONTE passava. Ela prova o mecanismo, não o resultado. |
