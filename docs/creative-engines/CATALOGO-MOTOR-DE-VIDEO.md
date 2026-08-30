# Motor de Vídeo VOLC — catálogo vivo

Atualizado em 26/08/2026. Fonte externa auditada em modo somente leitura:
`/Users/mac/Desktop/Volc Mídia Global/motor-video`.

## A resposta curta

O Motor de Vídeo já é um sistema criativo real. Ele possui contrato, 15 skins,
15 nichos, 14 vozes, 17 formatos, composição em Remotion, áudio, legendas,
fontes de assets, regras de licenciamento, QA técnico, QA visual e um portão de
publicação. A fábrica externa contém **38 renders finais observados**, todos em
1080×1920, com H.264 + AAC: 20 têm relatório de QA técnico, quatro têm QA visual
e dois chegaram a um snapshot congelado de publicação.

Isso ainda não significa que o VOLC O.S. já consegue pedir um vídeo. O código
organizado vive em `motor-video`, mas os artefatos e o workspace executável
continuam em `/Users/mac/volc-factory`. Não há adaptador `MotorDeCriativo`, job
persistido, fila, storage ou tela no produto. Também não há prova de render
integral iniciado a partir da própria raiz organizada.

## Como ler os estados

| Marca | Significado |
|---|---|
| **Executado** | Existe MP4 ou relatório verificável na fábrica externa. |
| **Implementado fora do OS** | Há código e contrato, mas ele não está ligado ao produto. |
| **Documentado** | A regra ou o destino existe como desenho; pode não ter execução. |
| **Pendente** | Falta integração, prova, adaptação ou decisão. |

## O que o motor realmente faz

```text
tema + fatos + identidade + canal
  → contrato resolve nicho, skin, voz, hook e arco
  → roteiro e cenas
  → hook em vídeo, avatar ou imagem
  → assets IA / Wikimedia / Pexels / still editorial
  → voz + trilha + efeitos
  → composição Remotion 9:16
  → legendas e acabamento FFmpeg
  → QA técnico
  → QA visual nos frames importantes
  → congelamento de props, ledger, timings e hashes
  → metadados, créditos, disclosure e pacote de publicação
```

O valor não está em um único gerador. Está na combinação de conteúdo variável
com uma estrutura determinística e auditável.

## As três famílias de gancho

| Modo | Skins | O que significa |
|---|---:|---|
| `grok` | 8 | Um serviço de vídeo via KIE produz o hook; a sequência continua no compositor. |
| `imagem` | 5 | O gancho nasce como imagem; movimento, texto, som e progressão vêm do motor. |
| `omni` | 2 | Avatar/Omni abre o vídeo com fala curta e calibrada. |

Esses modos não são vídeos completos concorrentes. São entradas diferentes para
a mesma esteira de voz, cena, composição, QA e publicação.

## Contrato criativo

O arquivo `contrato/motor/mapa.json`, versão **1.2.1**, é a autoridade legível por
máquina. No input mínimo, o schema exige somente `tema`; os demais campos — slug,
nicho, skin, voz, idiomas, duração, hook, beats, elementos, fatos, assets reais,
identidade, CTA, publicação e compliance — são opções fechadas que o resolvedor
expande ou deriva. Essa diferença permite intake simples sem aceitar campos
arbitrários.

O mapa registra 15 regras globais. As mais importantes para o VOLC O.S. são:

- fato sensível pede duas fontes, ou linguagem qualificada;
- vídeo de terceiro é proibido; still real exige licença e crédito;
- rosto real só entra por Wikimedia CC/PD ou still editorial autorizado;
- cena IA pede disclosure e registro de conteúdo sintético;
- zero gore e selo de reconstituição quando aplicável;
- todo asset deve aparecer no ledger;
- QA reprovado aborta o build;
- MP4 aprovado ainda não é publicável sem o portão de metadados;
- ausência de asset no ledger bloqueia a publicação.

## Quinze skins operacionais

| Skin | Formato principal | Hook | Voz | QA | Situação do QA |
|---|---|---|---|---|---|
| gossip | novela | omni | fofoqueira natural | base | definido |
| holerite | holerite | omni | amigo contador | wow_v2 | definido |
| corta | corta | grok | documentarista grave | wow_v2 | definido |
| arquivo | arquivo | grok | documentarista grave | wow_v2 | definido |
| main | news | grok | âncora urgente | base | definido |
| esoterico | esotérico / horóscopo | grok | mística | base | runner pede retrofit |
| lendas | lenda | grok | documentarista grave | base | alvo viral_docu_v1 ainda não aplicado |
| copa | copa | grok | narrador esportivo | base | runner pede retrofit |
| achadinhos | achadinhos | grok | fofoqueira natural | base | runner pede retrofit |
| tribunalzap | tribunal_zap | imagem | âncora urgente | wow_v2 | definido |
| relatoproibido | relato_proibido | imagem | sussurro confissão | wow_v2 | definido |
| cartasperdidas | cartas_perdidas | imagem | documentarista grave | wow_v2 | definido |
| causafamilia | causa_familia | imagem | âncora urgente | viral_docu_v1 | definido |
| brigaestado | briga_estado | grok | âncora urgente | wow_v2 | verificar integração |
| promo | promo | imagem | âncora urgente | base | runner pede retrofit |

## Os 17 formatos no filesystem

Cinco têm documentação, runner, compositor e som próprios completos:
`briga_estado`, `corta`, `esoterico`, `holerite` e `tribunal_zap`.

Os outros 12 não devem ser descartados. Eles têm runners e, em vários casos,
reutilizam compositor ou som compartilhado. O snapshot preserva os gaps sem
confundir “compartilhado” com “ausente”:

| Formato | Runner | Design | Compositor próprio | Som próprio | Observação |
|---|---:|---:|---:|---:|---|
| achadinhos | 2 | não | sim | não | skin e runner padrão existem |
| arquivo | 1 | não | sim | sim | contrato completo; falta design local |
| briga_estado | 1 | sim | sim | sim | completo no filesystem |
| cartas_perdidas | 1 | não | sim | sim | falta design local |
| causa_familia | 1 | não | sim | sim | falta design local |
| copa | 1 | sim | sim | não | som base compartilhado |
| corta | 1 | sim | sim | sim | completo e bilíngue |
| esoterico | 1 | sim | sim | sim | completo; QA do runner pede retrofit |
| fofoca | 1 | sim | sim | não | formato experimental separado de gossip |
| holerite | 2 | sim | sim | sim | completo no filesystem |
| horoscopo | 1 | não | não | não | reutiliza a skin esotérica |
| lenda | 1 | sim | sim | não | som terror compartilhado |
| news | 3 | sim | sim | não | runner padrão + entretenimento + solo |
| novela | 1 | sim | não | não | compartilhamento declarado |
| promo | 1 | não | sim | não | runner e contrato; QA pede retrofit |
| relato_proibido | 1 | não | sim | sim | falta design local |
| tribunal_zap | 1 | sim | sim | sim | completo no filesystem |

## Fontes e providers observados

O `.env` não foi lido nem copiado. O inventário só registra nomes de configuração
do `.env.exemplo` e referências no código:

- Gemini: TTS, imagem e visão usada no QA visual;
- OpenAI: cenas com `gpt-image-2`;
- KIE: hooks em vídeo por modelos como Grok/Veo/Kling;
- Pexels: b-roll com avaliação, limiar e duração limitada;
- Wikimedia: stills CC/PD com crédito;
- Remotion: composição visual;
- FFmpeg/ffprobe: áudio, acabamento e prova técnica.

O contrato contém custos de referência, não fatura medida: Omni ~US$0,10/s,
Grok por clipe de 6s, GPT Image low ~US$0,02–0,04, Gemini Image US$0,039;
Wikimedia e Pexels sem custo de geração, mas com obrigações de uso/crédito.

## Gates que já existem

### QA técnico

Usa os thresholds canônicos:

- silêncio mínimo 0,30s e retenção 0,13s no tighten;
- cobertura de legendas ≥ 0,85;
- densidade de legenda entre 1,6 e 4,2;
- loudness alvo -14 LUFS ±2,5;
- true peak -0,8 dBTP.

### QA visual

Extrai frames nos momentos de maior risco e pede julgamento visual sobre legenda
cortada, card sobre rosto, emoji errado, selo cortado, texto ilegível, artefato
de IA e força do hook. O relatório guarda hash do MP4 e cobertura dos checks.

### Publicação

`publicar.py` aplica `freeze → gen → check → pack → log`. O snapshot congela
props, ledger, timings, QA e QA visual e impede que um relatório de outro render
seja reutilizado. Licença, créditos, disclosure e conteúdo alterado são gates,
não notas decorativas.

## Evidência de execução

Na raiz `out` da fábrica externa foram observados 38 MP4s finais. Todos são
1080×1920, 30 fps, H.264 com áudio AAC. As durações variam de 15,2s a 64,3s.

- 20 possuem QA técnico;
- 4 possuem QA visual;
- 2 possuem snapshot de publicação (`short_mei` e `short_odete`);
- `short_relato_proibido` tem QA técnico **FAIL** e não pode ser apresentado
  como saída aprovada;
- os quatro relatórios visuais observados estão em WARN, não PASS;
- `short_mei` e `short_odete` provam o mecanismo de congelamento, mas não provam
  que todo o parque está pronto para publicação.

O inventário completo de cada MP4, duração, codec, QA e snapshot está em
`snapshots/motor-video-2026-08-26.json`.

## Destinos: o que é real hoje

O runtime provado é vertical 9:16, orientado a Shorts, Reels e TikTok. Existem
perfis de canal para Corta PT, Cut EN e Foco Genial PT.

As pastas `destinos/pmax`, `display`, `demandgen`, `youtube` e `organico` existem,
mas seus arquivos declaram que a adaptação ainda falta. Portanto:

- o motor pode fornecer matéria-prima valiosa para Google e Meta;
- isso **não** prova que já entregue todos os formatos, pesos, durações e codecs
  exigidos por cada tipo de campanha;
- o empacotador de destino deve nascer separado da skin narrativa;
- requisitos devem vir do contrato canônico de canal do VOLC O.S., não ser
  copiados de memória para o motor.

## Como integrar sem perder o patrimônio

Não copiar `/Users/mac/volc-factory` inteiro para o backend e não chamar scripts
por path absoluto. O alvo é um runtime separável atrás da porta interna já
existente:

```text
Hub / Briefing
  → backend autenticado
  → CreativeJob persistido
  → adapter MotorDeCriativo VIDEO
  → worker do Motor de Vídeo
  → storage de assets, MP4s e provas
  → empacotador por destino
  → revisão humana
  → validate_only / preview
  → publicação autorizada
```

### Ordem segura de extração

1. Tornar `motor-video` executável com workspace configurável, sem depender de
   `/Users/mac/volc-factory` ou `/opt/homebrew/bin/ffmpeg`.
2. Provar uma fixture offline do contrato até o compositor e gates sem rede.
3. Empacotar um worker com job idempotente, progresso e cancelamento.
4. Implementar o adapter `MotorDeCriativo` para `VIDEO`.
5. Persistir contrato, versão, providers, custos, hashes, ledger, QA e aprovação.
6. Entregar primeiro o destino 9:16 orgânico/Meta, que já corresponde à prova.
7. Criar pacotes próprios para Demand Gen, PMax e campanhas de vídeo conforme
   o contrato oficial de cada canal.
8. Só depois permitir upload/publicação, sempre com confirmação explícita.

## Critérios de aceite da primeira vertical

- um job nasce no VOLC O.S. sem chave no navegador;
- o job registra skin, hook, voz, idioma, contrato e versões;
- execução não depende de path absoluto da máquina do autor;
- retry não duplica custo nem publicação;
- MP4, props, timings, ledger e QAs ficam ligados ao mesmo job;
- FAIL técnico ou visual bloqueia promoção;
- WARN exige aceite humano com motivo;
- um formato falhar não apaga os demais;
- o primeiro pacote é conferido no destino em `validate_only` ou preview;
- nenhuma publicação ou mutação ocorre sem autorização humana.

## Dívidas registradas sem maquiagem

- 12 dos 17 formatos não têm todos os quatro artefatos próprios;
- cinco skins têm indicação de retrofit/verificação de QA;
- somente quatro de 38 MP4s têm QA visual observado;
- somente dois têm snapshot congelado;
- um MP4 tem QA técnico FAIL;
- destinos publicitários ainda são placeholders;
- a fábrica executável continua fora do repositório;
- o VOLC O.S. ainda não possui adapter, fila, persistência ou tela de vídeo.

Essas dívidas não diminuem o patrimônio. Elas impedem apenas que patrimônio
externo seja confundido com capacidade operacional já plugada.
