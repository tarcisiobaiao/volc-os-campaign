# Meta Ads — motor de criação e bancada do operador (v1)

Worktree `/private/tmp/volc-os-operacao-80-20`, branch
`execution/volc-os-operacao-80-20`, base `752ca2b6`. Nada foi empurrado,
publicado ou aplicado fora desta árvore.

## O que esta lane fechou

### 1. Dois campos cuja AUSÊNCIA não é neutra

O erro que abriu a missão — *"É necessário especificar True ou False no campo
`is_adset_budget_sharing_enabled` se você não estiver usando o orçamento da
campanha"* — não era um caso isolado. É uma **classe** de campo, e a classe tem
mais de um membro.

| Campo | O que a omissão faz | Estado |
|---|---|---|
| `is_adset_budget_sharing_enabled` | A Meta recusa a criação | já corrigido antes desta lane; conferido, preservado e coberto por teste |
| `targeting.targeting_automation.advantage_audience` | **A Meta assume `1` e liga o Advantage+ Audience sozinha** | corrigido nesta lane |

A prova do segundo é literal: *"Beginning with v23.0, the `advantage_audience`
parameter within `targeting_automation` defaults to `1` ... This behavior
applies only when creating a new ad set"*. O contrato anterior fazia o oposto do
seguro: recusava deixar o operador declarar o campo, e assim garantia a omissão
— e a omissão liga. Agora a escolha é explícita, entra no hash do plano,
aparece na etapa Público em português e é conferida no read-back.

### 2. Um payload que a Meta recusaria

O compilador enviava `destination_type=WEBSITE` num plano `OUTCOME_TRAFFIC`. A
tabela oficial lista, para esse objetivo, apenas `UNDEFINED`, `MESSENGER`,
`WHATSAPP` e `PHONE_CALL`; `WEBSITE` pertence a AWARENESS, LEADS e SALES. O
campo é opcional e tráfego para site é o padrão do objetivo, então ele deixou de
ser emitido. Esta era a próxima recusa que o operador encontraria ao clicar em
validar.

### 3. Saga, read-back e vazamento

- **FALHA só quando a Meta prova recusa.** Antes, qualquer erro no POST marcava
  o passo como `FAILED`. Uma conexão que cai depois do despacho, um corpo
  inválido ou uma resposta sem id podem ter criado o objeto — agora esses casos
  ficam `AMBIGUOUS`, que é o estado que permite reconciliar por leitura.
- **Read-back deixou de aceitar divergência calada.** Passou a conferir
  `account_id`, `buying_type`, `start_time` como instante, `targeting`
  (países, faixa etária, Advantage+) e o `object_story_spec` inteiro do
  criativo, e a recusar um `asset_feed_spec` que apareça sem ter sido enviado —
  que seria criativo dinâmico ligado sem ninguém pedir. Booleano ausente deixou
  de valer `false`.
- **Marcador de dependência virou caminho estrutural.** `resolver_dependencias`
  trocava QUALQUER string com a forma `$campaign.id`. Um conjunto chamado
  `$campaign.id` passava no contrato, entrava no hash aprovado e virava um id
  numérico na criação — objeto diferente do aprovado. Agora a troca só acontece
  em `campaign_id`, `adset_id` e `creative.creative_id`, o contrato recusa texto
  com essa forma exata, e nenhum marcador não resolvido sai do processo.
- **Texto do provedor deixou de carregar segredo.** A sanitização cobria
  `access_token=` e ids numéricos; agora cobre `Bearer …`, `access token: …`,
  tokens `EAA…` e qualquer cadeia opaca longa — que é a forma de um `image_hash`.

### 4. Vídeo: leitura provada, emissão bloqueada com causa

A conta agora é lida também em `GET /act_{id}/advideos`, com os campos
comprovados na referência do nó Video (`id,name,created_time,updated_time,picture`),
e a miniatura passa pelo mesmo proxy autenticado das imagens — prévia real, sem
URL assinada no navegador.

A **emissão** continua bloqueada, e a causa é verificável: `video_data` exige
miniatura por `image_hash` da biblioteca ou por URL própria, e a documentação
proíbe usar a URL do CDN da Meta — que é exatamente a única que a leitura
devolve. Subir uma imagem seria escrita de ativo, não autorizada aqui. A tela
diz isso ao operador nessas palavras.

### 5. Criativo flexível: o bloqueio ficou pequeno e preciso

Está provado: `ad_formats` e `link_urls` obrigatórios, `call_to_action_types`
obrigatório neste objetivo, `images` obrigatório no formato de imagem única com
a chave `hash` (**não** `image_hash`), `is_dynamic_creative` no conjunto,
limites de 30/10/10/5/5/5. Falta uma coisa só: como a Página viaja junto do
`asset_feed_spec` — nenhum exemplo oficial mostra `object_story_spec` e
`asset_feed_spec` no mesmo criativo. A bancada mostra a matriz do que está
provado e nomeia o que falta, em vez de esconder o modo ou fingir suporte.

### 6. A bancada deixou de ser um produto à parte

A página tinha um cabeçalho escuro montado à mão (`bg-[#101524]`, gradiente
`cyan-400/violet-500/red-500`, `shadow-xl`, `rounded-2xl`) — nada disso é token
do produto, e as três cores não são a aurora VOLC. Ela agora usa o **mesmo
vocabulário da bancada de lançamento Google** (`NovaCampanhaPage`):
`bancada-command-deck`, `bancada-command-topline`, `bancada-route`,
`bancada-stage`, `bancada-grid`, mais as peças de `components/trafego/bancada`
(`AcaoDominante`, `PainelDeBloqueio`, `BlocoDeEvidencia`, `LinhaDeFato`,
`ChipDeEstado`, `Pedido`).

O que mudou para o operador:

- **Quatro estados por etapa**, com glifo + palavra + descrição audível:
  pendente, pronto, bloqueado, validado. Nunca só cor.
- **Uma ação dominante por região**, com TODAS as faltas impressas na tela e
  ligadas por `aria-describedby`. O botão "Criar campanha pausada" desabilitado
  saiu: um primário morto sugere que o ato existe e está indisponível — ele não
  existe.
- **O nome da variável de ambiente sumiu da tela.** No lugar, a razão em
  português, servida pelo backend junto da capacidade.
- **Resumo persistente do pedido** na lateral, com fonte por linha e ausência
  declarada em vez de zero inventado.
- **Revisão mostra a tabela das operações** que serão enviadas, e o resultado da
  validação vem rotulado como **parcial**, nomeando o que NÃO foi validado.
- **Erro da Meta traduzido** preservando código e subcódigo.

### 7. Defeitos de rascunho que custariam dinheiro ou uma recusa

- **`10.00` virava R$ 1.000,00.** O parser apagava todos os pontos antes de
  trocar a vírgula. Agora o separador decimal é o último separador digitado,
  `1.000` continua sendo mil em pt-BR, e a tela devolve ao operador o valor que
  entendeu antes de qualquer compilação.
- **`variation_key` colidia.** A chave vinha de `variations.length + 1`: remover
  a linha do meio e adicionar outra recriava uma chave existente, e o backend
  recusava o lote inteiro. Agora é a primeira chave livre da sequência, e os
  nomes de criativo e anúncio também são desambiguados.
- **"Individual" era só um rótulo.** O modo não truncava o rascunho: um lote de
  três continuava sendo enviado inteiro. Agora o modo governa o que é emitido.
- **Compilação sobrevivia à releitura de ativos.** Trocar de conta podia mudar
  Página e imagem sem invalidar o plano já compilado. Agora invalida.
- **Resposta atrasada podia marcar como validado um rascunho já editado.** Cada
  chamada carrega um selo e a resposta obsoleta é descartada.

### 8. A migration candidata ganhou manifesto e um ciclo que a exercita

`scripts/provar-ciclo-meta-create-paused.sh` aplica, **usa**, reverte e reaplica
a autoridade durável num PostgreSQL 15 descartável — o ciclo que não existia
para esta migration. Usar não é enfeite: as RPCs são chamadas em **notação
nomeada**, com os mesmos nomes de parâmetro que `registro.py` envia, então um
rename deixa de passar verde.

O ciclo encontrou um defeito real na primeira execução: o default ACL do
Supabase concede `ALL` em `public`, e a migration revogava apenas de
`anon`/`authenticated`. `service_role` podia gravar recibo direto na tabela,
contornando as RPCs transacionais que são a única autoridade da saga. Corrigido.

A aprovação passou a carregar `steps_expected`: o manifesto imutável do plano.
Um `approval_id` válido para quatro operações não aceita mais preparar um
`creative:extra`, o ordinal é a posição no manifesto (não o próximo número
livre) e um passo só é preparado depois que o anterior está `CREATED`.

## Matriz de modos

| Modo | Estado | Prova |
|---|---|---|
| Individual estático | disponível | compila, valida raízes, 1 criativo + 1 anúncio, tudo PAUSED |
| Lote estático 1–10 | disponível | chave e nomes únicos, hash sensível à ordem, um par por linha, recibo por variação |
| Vídeo | leitura sim, emissão **bloqueada** | inventário e prévia reais; `video_data` exige miniatura que a doc não permite obter por leitura |
| Flexível/dinâmico | **bloqueado** | contrato provado menos a rota da Página; nenhum payload é emitido |

## O que continua proibido e continua ausente

Zero `mutate` na Meta. Zero criação. Zero ativação. Nenhuma rota de
`create_paused` ou de aprovação foi montada. Nenhuma migration oficial foi
aplicada. Nenhuma escrita no Supabase oficial. Nenhum `push`.
