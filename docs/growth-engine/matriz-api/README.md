# Matriz canônica de operação — Google Ads API v25

Referência de engenharia para o Google Growth Engine do VOLC OS. Descreve **o que a API
realmente permite** por canal: o que se cria, o que se edita, o que exige recriar, o que falha
e como o erro chega de volta.

**Consulta:** 26/08/2026 · **API alvo:** v25 · **SDK inspecionado:** `google-ads` 31.3.0

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| [`comum.md`](./comum.md) | Versão e sunset, modelo de mutate, `validate_only`, `partial_failure`, idempotência, quotas e limites, GAQL, `change_event`/`change_status`, `recommendation`, `customer_status`, conversion goals e Smart Bidding, `status` × `primary_status`, `campaign_criterion` × `ad_group_criterion`, modelo de assets |
| [`search.md`](./search.md) | Canal `SEARCH` — RSA, keywords, `network_settings`, AI Max |
| [`display.md`](./display.md) | Canal `DISPLAY` — RDA, display upload, dynamic remarketing |
| [`demand-gen.md`](./demand-gen.md) | Canal `DEMAND_GEN` — 4 tipos de anúncio, channel controls, product ads |
| [`performance-max.md`](./performance-max.md) | Canal `PERFORMANCE_MAX` — asset groups, signals, brand guidelines |
| [`fontes.json`](./fontes.json) | Legível por máquina: 88 URLs oficiais com data e confiança, mais os **20 pontos NÃO CONFIRMADOS** e onde cada um foi procurado |

Os arquivos de canal **não repetem** o `comum.md`. Leia `comum.md` primeiro.

## Como ler as marcas de confiança

| Marca | Significa |
|---|---|
| `[alta]` | Descriptor/docstring do proto instalado, ou tabela oficial reproduzida literalmente |
| `[média]` | Prosa da documentação oficial, sem tabela normativa |
| `[baixa]` | Inferência a partir de duas fontes oficiais que não se declaram |
| `[NÃO CONFIRMADO]` | Sem fonte oficial. Vem acompanhado do que foi tentado. **Não preencher por memória** |

Fontes citadas como `[S#]`, `[T#]`, `[D#]`, `[G#]`, `[X#]` estão no rodapé de cada arquivo e em
`fontes.json`. `P` = proto do SDK instalado.

## Método

Páginas oficiais baixadas por HTTP e extraídas do corpo do artigo; protos inspecionados por
introspecção de descriptor protobuf e docstring do pacote instalado.
**Nenhuma chamada foi feita à Google Ads API.** Nenhum segredo foi lido ou versionado.

## Cinco coisas que valem saber antes de abrir qualquer arquivo

1. **O SDK local está uma minor atrás da API viva.** A v25.1 saiu em 19/08/2026 e o pacote
   31.3.0 não contém suas adições (verificado campo a campo). Ver `comum.md` §1.
2. **`partial_failure` é inutilizável em toda criação de estrutura nova**, porque IDs temporários
   e `partial_failure` são mutuamente excludentes por regra oficial. Em PMax ele é explicitamente
   não suportado. Ver `comum.md` §4 e `performance-max.md` §2.
3. **A API não oferece idempotência.** É problema da aplicação. Ver `comum.md` §5.
4. **`AdGroupAd.ad` é imutável**: nos três canais com ad group, "editar anúncio" não existe — só
   substituir. Ver `search.md` §3.
5. **Display é o canal órfão de documentação**: não existe guia oficial de criação de campanha
   Display, e as specs de criativo do RDA só existem no proto. Ver `display.md` §0.
