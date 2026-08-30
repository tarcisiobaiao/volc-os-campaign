# Creative Engine — a porta do criativo do VOLC O.S.

**Onde mora:** `volc_ads/criativo/`
**Escopo:** contrato, requisitos por canal, validação, porta do motor, catálogo e adaptadores.
**Fora de escopo:** gerar imagem, gerar vídeo, subir asset no Google. Nada aqui fala com o Google Ads.

Display, Demand Gen e Performance Max não pedem "uma imagem": pedem uma imagem de
proporção declarada, com dimensão mínima, peso máximo e quantidade mínima por papel.
Esta camada existe para que essa exigência seja **dado conferível** antes da geração
paga, e não uma surpresa que chega da API depois de a imagem já ter custado.

---

## 1. O que existe de motor real — inventário com evidência

O grafo declara `cap_creative_engines` como `partial`, com a evidência textual
*"Existência e validação declaradas pelo dono em 26/08/2026. Paths, contratos, entradas,
saídas e provas ainda precisam entrar na curadoria."* Este inventário é a primeira
tentativa de fechar esse buraco. Cada linha traz **onde foi lido**, não o que se supõe.

| # | Motor | Path | Contrato lido | Veredito |
|---|---|---|---|---|
| M1 | **Gerador de imagem do FunnelForge** (`gpt-image-2`) | `funnelforge-migracao/engine/src/funnelforge/adapters/image_openai.py` | port `ImageGenerator` em `ports/services.py`: `generate(prompt, size) -> bytes`, mais telemetria opcional em `last_usage` (`adapters/image_pricing.py`). Chamado em `pipeline/steps.py::step_image` como `deps.image_gen.generate(text, size=img_size)`. Tamanhos em uso: `config/settings.py` → `image_size_lp="1024x1536"`, `image_size_post="1536x1024"`. | **COMPROVADO E ADAPTADO.** Dentro do repositório, contrato explícito, injetável. Ponte em `adaptadores/funnelforge_imagem.py`. |
| M2 | **Fábrica de vídeo VOLC** | `/Users/mac/volc-factory/pipeline/core.py` | Funções reais: `gemini_image`, `gpt_image`, `grok_hook` (i2v), `omni_hook`, `render(ctx, comp)` para Remotion. Hooks dedicados: `veo_hook.py` (Veo 3.1, AI Studio + Vertex), `wan_hook.py` (Wan 2.2 via Replicate), `gen_images.py` (Gemini `gemini-2.5-flash-image`, fallback Pillow). | **EXISTE E FUNCIONA — NÃO ADAPTÁVEL HOJE.** Ver dependência **D3**. |
| M3 | **Projeto Remotion `retenx-video`** | `/Users/mac/Desktop/retenx-video` | 770 linhas de cena própria (`Main.tsx`, `scenes.tsx`, `lib.tsx`); `package.json` só expõe `remotion studio` / `remotion bundle`. README é o do template. | **COMPOSIÇÃO, NÃO MOTOR.** Não tem entrada programável nem contrato de saída. |
| M4 | **Processador de imagem Pillow** | `funnelforge-migracao/engine/src/funnelforge/adapters/images_pillow.py` | `to_webp` e `screenshot_to_webp` (corte determinístico por ALTURA, redimensionamento por largura). | **PARCIAL.** Converte e redimensiona; **não recorta por proporção** — ver **D1**. |

Por que M2 não virou adaptador, apesar de funcionar: ele está **fora do git** (não há
`.git` em `/Users/mac/volc-factory`), fora do repositório, carrega segredo por caminho
absoluto de um terceiro projeto (`.../aprova-plataforma-alvo-hybrid/materials/.env`), e a
API é de *runner* (`ctx = core.setup(slug)`, escrita em disco por convenção), não de port.
Escrever um adaptador contra isso hoje seria fixar no VOLC O.S. um acoplamento a um
diretório da máquina do dono. A decisão é do dono e está registrada como **D3**.

---

## 2. O que foi construído

```
volc_ads/criativo/
  contrato.py       Asset, Procedencia, Origem, TipoDeAsset, EspecificacaoDeAsset,
                    TetoCombinado, ExigenciaDeCanal, Violacao, Classe, Falha, LoteDeAssets
  requisitos.yaml   as exigências por canal, como DADO
  requisitos.py     lê o YAML e resolve de quem é cada número
  validacao.py      asset e lote contra a exigência — todas as violações
  porta.py          Protocol MotorDeCriativo + erros tipados
  catalogo.py       deduplicação por conteúdo, papéis, intenções, variantes
  adaptadores/
    falso.py               motor determinístico que erra sob encomenda
    funnelforge_imagem.py  ponte para o port ImageGenerator (M1)
  testes_requisitos.py · testes_validacao.py · testes_catalogo.py · testes_motor.py
```

O vocabulário reaproveita o de `volc_ads/copy/` de propósito: `Classe` decide o **remédio**
(é o que uma cascata de retry consulta), `Achado`/`Violacao` cita a regra, `Falha` é dado e
não exceção. Não há um segundo vocabulário para a mesma ideia.

### As decisões que valem ser lidas antes de mexer

**Identidade interna ≠ id do Google.** `Asset.identidade` sai do hash do conteúdo e existe
antes de qualquer chamada externa; `id_externo` é o `resource_name` e começa `None`,
carimbado por `Catalogo.carimbar_id_externo`. É a mesma lição que o Hub de Tráfego pagou
para aprender com as campanhas de dois donos.

**Duplicata devolve o existente, não levanta.** Um motor determinístico gerando de novo a
mesma coisa é o caminho *normal*, não o excepcional. E o mesmo arquivo em dois papéis
(1:1 servindo como logo e como imagem quadrada) é **um** asset com dois papéis — para a
API é um `ImageAsset` só.

**Procedência é do arquivo, e o arquivo é o mesmo.** Quando o mesmo conteúdo reaparece com
outra procedência, vale a **primeira**, e a divergência é dita na observação. Sobrescrever
apagaria o prompt que de fato produziu o arquivo — a única coisa que permite repetir um acerto.

**Desconhecido é `None`, nunca `0`.** O construtor de `Asset` recusa `largura=0`. Medida
ausente vira violação de classe `MEDIR_ANTES`, nunca aprovação por omissão.

**`resultado.ok` olha só as violações DO LOTE.** Um asset reprovado é perda conhecida e já
saiu; 19 imagens boas e 1 ruim são um lote publicável. Se a perda deixou buraco, ele
reaparece como `Q1.faltam` — porque a contagem mínima é feita sobre os **aprovados**, não
sobre os entregues.

**A porta tem dois passos** (`solicitar_geracao` → id, `receber` → resposta) porque Veo e
Remotion não são síncronos. Motor síncrono cumpre o contrato guardando o resultado debaixo
do id: custa uma linha e não mente sobre latência.

**Erro tipado carrega `permanente`.** `False` = retentar o mesmo insumo pode dar certo
(429, 5xx, fila). `True` = vai errar igual (400 de política, formato não suportado). Mesma
lição de `copy/ciclo.py`: retentar política não é ineficiência, é chamar atenção.

---

## 3. Os números: quem é dono de quê

A matriz oficial do Agente A aterrissou durante esta entrega e **substituiu** os
provisórios. O estado depois da troca:

| Número | Fonte | Estado |
|---|---|---|
| Display — dimensão, proporção, contagem | `matriz-api/display.md` §3 (proto `ResponsiveDisplayAdInfo`) | **Oficial** |
| Display — **peso máximo e toda spec de vídeo** | — | **`[NÃO CONFIRMADO]` → `null`** |
| Demand Gen — imagens, logo, vídeo, texto | `matriz-api/demand-gen.md` §3 (proto) e §4 (Help Center) | **Oficial** |
| Performance Max — tabela completa | `matriz-api/performance-max.md` §4 | **Oficial** |
| Caractere e contagem de Display/Demand Gen | `volc_ads/campanha/limites.yaml` (Agente C) | **Oficial**, e o dono continua sendo ele |
| Vídeo (canal) | — | **PROVISÓRIO** — a matriz ainda não cobre |

### A correção que a matriz impôs, e por que ela importa

A tabela completa que o Google publica — mínimos, máximos, proporção, dimensão e
**5120 KB de peso máximo** — é a de **Performance Max**. Ela **não vale para Display**:
para o RDA o guia oficial remete ao Help Center sem publicar os números, e o proto declara
dimensão, proporção e contagem mas **não** declara peso nem spec nenhuma de vídeo.

Os provisórios desta camada tinham emprestado exatamente esses dois números. Foram
substituídos por `null`, e o validador simplesmente não checa o que a especificação não
sabe — há teste para isso (`test_o_que_a_especificacao_nao_sabe_ela_nao_cobra`).

**Ausência é a resposta certa; número emprestado é pior que campo vazio.** Um lote que
valida contra o teto errado passa localmente e é recusado pela API depois, com o erro
apontando para o asset e não para a regra que o reprovou — o operador vai procurar defeito
na imagem, e o defeito está na tabela.

Outras seis correções vieram junto: o RDA **não tem** slot de imagem de retrato; **logo não
é obrigatório** no Display (é recomendado, e vira aviso `Q3.abaixo_do_recomendado`); o
`long_headline` do RDA é **obrigatório e singular**; Demand Gen ganhou o slot **9:16** de
Shorts e um logo com teto **próprio** de 150 KB e piso de 144×144 — não os 5 MB das outras
imagens da mesma tabela; em Performance Max o `LANDSCAPE_LOGO` vai a 20 e o `YOUTUBE_VIDEO`
a 15, não a 5.

Os tetos **combinados** estão modelados como tal (`TetoCombinado`): 15 somando imagem de
marketing + quadrada no Display, 5 somando os dois logos, 20 somando as quatro orientações
no Demand Gen. Um validador que conte cada tipo isoladamente aceita 15+15 e a API recusa o
payload inteiro. `Q4.teto_combinado` é **erro**, não aviso, e por isso: cortar o excedente
exigiria escolher qual imagem sai, e essa decisão é de quem encomendou o lote.

Entrou também `caracteres_de_pelo_menos_um`, para a regra de conjunto do PMax — ao menos uma
`DESCRIPTION` com 60 caracteres ou menos, senão `SHORT_DESCRIPTION_REQUIRED`. Cinco
descrições de 90 são todas válidas individualmente e o asset group é recusado assim mesmo.

### Como trocar quando um número mudar

Substituir o valor em `requisitos.yaml` e a `fonte` do canal. Nenhum código muda —
`requisitos.py` só lê. Onde a matriz confirmar um número que já tem dono em `limites.yaml`,
**não duplicar**: preencher `limites_chave` ou `quantidade_chave` e deixar o dono ser o dono.
`EspecificacaoDeAsset.fonte_dos_numeros` sempre diz qual das fontes entrou, e um teste
garante que nenhuma especificação sai sem fonte.

---

## 4. Dependências objetivas que restam

Cada uma é uma coisa só, com dono e critério de pronto.

**D1 — Recorte determinístico por proporção.** *Dono: esta camada, próxima entrega.*
O gpt-image entrega 1:1, 1.5:1 e 0.67:1; o Google pede 1.91:1, 1:1, 4:5 e 9:16. Só o quadrado
bate. Sem um passo de recorte, toda imagem paisagem e retrato nasce reprovada em
`D3.proporcao` (classe `SANEAVEL_EM_CODIGO` — a classe já diz que o conserto é local). O
`ImageProcessor` do FunnelForge converte para webp e corta por altura; **não** recorta por
proporção. *Pronto quando:* um asset 1536×1024 gerado pela ponte passa na especificação de
`IMAGEM_MARKETING` sem intervenção humana.

**D2 — Instância real do `OpenAIImageGenerator` com credencial.** *Dono: quem opera a chave.*
A ponte recebe o gerador **pronto, injetado** — nenhum segredo entra neste pacote, por regra.
*Pronto quando:* uma geração real produz um `Asset` catalogado com `procedencia.custo_usd`
preenchido pela telemetria `last_usage`.

**D3 — Decisão sobre a fábrica de vídeo (M2).** *Dono: o dono do produto.* Três caminhos:
(a) mover `volc-factory/pipeline` para dentro do repositório e versioná-lo; (b) publicá-lo
como pacote instalável; (c) escrever um adaptador que aceite o `ctx` por injeção e nunca leia
`.env` por caminho absoluto. Enquanto não houver decisão, **não existe motor de vídeo ligado**
e `TipoDeAsset.VIDEO` só é exercitado pelo motor falso. *Pronto quando:* existe
`adaptadores/<motor>.py` cumprindo `MotorDeCriativo` para `VIDEO`, com teste sem rede.

**D4 — Os `[NÃO CONFIRMADO]` que sobraram.** *Dono: Agente A.* Peso máximo de arquivo e specs
de vídeo (duração, proporção, resolução) do Display; specs de media bundle; e o canal
**Vídeo** inteiro, que ainda não tem página na matriz — e cujo formato (in-stream, in-feed,
bumper, Shorts) muda duração e textos exigidos sem que essa distinção esteja modelada.
*Pronto quando:* `provisorio: false` também em `VIDEO` e nenhum `null` marcado como não
confirmado em `requisitos.yaml`.

**D5 — Divergência de 30 vs 40 caracteres na headline de Demand Gen.** *Dono: Agentes A e C,
juntos.* `limites.yaml` diz 40 (Help Center) e `matriz-api/demand-gen.md` lê 30 no proto de
`DemandGenMultiAssetAdInfo`. Esta camada **não arbitra**: continua usando o número do dono
(40), porque criar um terceiro medidor seria o pior dos mundos. *Pronto quando:* as duas
fontes concordam, ou uma declara explicitamente que a outra não se aplica. Enquanto isso, um
título de 35 caracteres passa aqui e pode ser recusado pela API.

**D6 — Persistência e linhagem.** *Dono: Agente E (`supabase/migrations/v10_*`,
`backend/app/trafego/lote*.py`).* `Catalogo` é **em memória** por decisão: guardar em banco é
do domínio de Tráfego. O mínimo a persistir para que a pergunta "qual criativo funcionou?"
tenha resposta: `identidade`, `conteudo_hash`, `procedencia` inteira (motor, versão, insumo,
quando, custo), `id_externo`, papéis e intenções, e as `Falha` com `permanente`.

**D7 — Upload do asset (`AssetService`) e devolução do `resource_name`.**
*Dono: Agente C (`volc_ads/campanha/`, `volc_ads/subir.py`).* Esta camada entrega
`ResultadoDeValidacao.aprovados` e espera receber de volta o id externo por
`Catalogo.carimbar_id_externo(identidade, resource_name)`. Fronteira sugerida: quem sobe
**não** decide o que é válido, e quem valida **não** chama a API.

---

## 5. Como rodar

```bash
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign
PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/criativo -q -p no:randomly
```

Nenhum teste desta camada gera imagem, fala com o Google ou usa credencial. O motor falso
(`adaptadores/falso.py`) roda na máquina e **erra sob encomenda** — proporção errada,
arquivo pesado, medida ausente, item recusado — porque um mock que só sabe acertar prova
metade do sistema, e a metade barata.
