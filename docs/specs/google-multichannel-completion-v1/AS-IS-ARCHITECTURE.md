# AS-IS — Google Ads multicanal em 884393b (05/09/2026)

Leitura de código, recibos e documentação oficial. Toda afirmação aponta arquivo:função ou evidência (`EV-*` em `OFFICIAL-API-EVIDENCE.json`). O grafo local foi construído em outro commit e serviu só para navegar.

## 1. As camadas que existem

| Camada | Onde | O que decide | Estado por canal |
|---|---|---|---|
| Brief tipado | `volc_ads/campanha/brief.py` | `Brief`, `ImagensDisplay`, `ImagensDemandGen`, `ImagensPMax`, `ConfiguracaoDemandGen`, `ConfiguracaoPMax`, `ReciboDeMensuracao`, `ReciboAssetAprovado`, `AssetRemotoAprovado` | os três contratos existem |
| Builders | `volc_ads/campanha/{display,demand_gen,pmax}.py` + `comum.py` | um `GoogleAdsService.Mutate` atômico por nascimento, ids temporários por faixa, campanha `PAUSED` | Display: ad group/ad `ENABLED`; Demand Gen: tudo `PAUSED`; PMax: asset group `PAUSED`, opt-out de expansão de URL |
| Perfil/registro | `volc_ads/campanha/perfil.py`, `volc_ads/subir.py` | quem prova (`PROVADORES_POR_CANAL`: SEARCH, DISPLAY, DEMAND_GEN) e quem cria (`CONSTRUTORES_POR_CANAL`: SEARCH, DISPLAY); guarda de import derruba divergência | PMax fora dos dois; Demand Gen só prova |
| Prova e escrita | `volc_ads/gads/client.py` (`validar_mutacoes`, `mutar`), `volc_ads/gads/modo.py` (trava de dois fatores), `subir.py` (`Selo`, `Recibo`, uma tentativa) | `validate_only=True/partial_failure=False`; mutate só com `FORGE_PERMITIR_ESCRITA=1` + `destravar(motivo)` | canal-agnóstico |
| Plano | `volc_ads/campanha/plano.py` | projeção JSON das operações protobuf, códigos de bloqueio estáveis | os quatro canais projetam |
| Fronteira HTTP | `backend/app/routers/trafego.py` | `/provar` (Search, Display via `_montar_plano_display`, Demand Gen via `_montar_plano_demand_gen` + flag), `/planejar-pmax` (local), `/subir` (Search; Display entra mas é recusado pela janela; Demand Gen 403; PMax 422 `PMAX_FORA_DO_EXECUTOR`), `/reconciliar`, `/canais`, `/veredito`, `/remover` | ver `GOOGLE-MULTICHANNEL-CAPABILITY-MATRIX.json` |
| Janela do canário | `backend/app/trafego/canario.py` | conta-laboratório única, canal `SEARCH`, tetos R$20/R$1, rede obrigatória, criação pausada | SEARCH-only |
| Ledger | `backend/app/trafego/ledger.py` + `supabase/migrations/v10_01..v10_04` | abrir → despachar → mutate → fechar/reconciliar; `CHECK` aceita `DISPLAY`, `DEMAND_GEN`, `PERFORMANCE_MAX` | provado em produção só para Search |
| Portões | `backend/app/trafego/{prontidao,contrato_canais,capacidades,plataforma}.py` | lance sem medição recusa Smart Bidding; quatro portões por canal; PMax `criavel_pausada` também exige releitura v12_03 | ver conflitos |
| Ponte criativa | `volc_ads/criativo_ponte.py`, `volc_ads/criativo/requisitos.yaml`, `limites.yaml` | régua por canal, `Linhagem`, recibo tipado, dedup por conteúdo | Display aceita `str` sem recibo |
| Observabilidade PMax | `volc_ads/observabilidade_pmax`, `volc_ads/inteligencia_google/{pmax,releitura}.py`, `v12_03` | sete famílias, cobertura pela mesma régua do builder | migration só em Postgres descartável |
| UI | `src/pages/trafego/NovaCampanhaPage.tsx`, `bancada/paradas/{Display,Demand,PMax}Paradas.tsx`, `Lancamento.tsx`, `lib/trafego/{canais,portoes}.ts` | paradas por canal, fatos travados, prova/planejamento; escada de lançamento só para Search | ver `UI-OPERATOR-CONTRACT.json` |

## 2. O caminho real hoje, por canal

```
DISPLAY     bancada → POST /provar (canal=DISPLAY, assets_display b64) → ponte → display.construir → validate_only ✔ (01/09) → selo
            → POST /subir → canario.exigir recusa (SEARCH-only; rede ausente)  ✘   [OCC-G01/G02/G03]
DEMAND_GEN  bancada → POST /provar (flag on + capacidade) → demand_gen.construir → validate_only ✔ (01/09, budget ≥ mínimo) → selo
            → POST /subir 403 por decisão                                       ✘   [T06]
PMAX        bancada → POST /planejar-pmax (mensuração=None) → pmax.planejar → plano com MENSURACAO_INADEQUADA + PMAX_FORA_DO_EXECUTOR
            → /provar 422                                                        ✘   [T08]
SEARCH      /provar → selo → /subir → ledger → mutate → recibo → read-back      ✔   (referência, EV-17)
```

## 3. O candidato 21fbc3b

Todos os 17 arquivos do candidato são byte-idênticos em 884393b; os dois commits reaparecem na história operacional (b2718e5, e9eb3ee). Não há delta a transplantar (`DIVERGED-CANDIDATE-ADJUDICATION.json`).

## 4. O que a documentação oficial fixa (v25)

- `Campaign.url_expansion_opt_out` não existe em v25; o controle é `asset_automation_settings` com `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION` (`EV-02`, `EV-03`, `EV-04`). O builder PMax já emite esse opt-out; `TEXT_ASSET_AUTOMATION`, `GENERATE_IMAGE_ENHANCEMENT`, `GENERATE_ENHANCED_YOUTUBE_VIDEOS` continuam no default opted-in e page feed herdado não é excluído (`excluded_parent_asset_set_types`).
- `Campaign.status` nasce `ENABLED` por default (`EV-02`); Demand Gen e PMax do VOLC já nascem `PAUSED` em todos os objetos; Display não.
- PMax: asset group e mínimos no mesmo mutate, sem partial failure (`EV-06`); só MaxConv/MaxConvValue (`EV-05`).
- Demand Gen: ad group sem `type_`; mínimo diário por moeda devolvido pela API (`EV-07`, `EV-16`); multi-asset nasce opted-in em três automações de imagem/vídeo (`EV-01`, `EV-03`).
- Display: sem guia oficial de criação; RDA specs só no proto; `control_spec` existe (`EV-08`, `EV-11`).

## 5. Lacunas que decidem a ordem

1. Janela do canário e caminho de `/subir` são Search-only (bloqueiam Display).
2. Portão de lance recusa Smart Bidding sem medição PRONTO, e a conta-laboratório não mede (bloqueia os três).
3. Demand Gen precisa abrir mutação e respeitar o mínimo por moeda.
4. PMax precisa do lote do executor, da trava de URL completa, da ledger v12_03 no oficial e de mensuração válida.
5. Nenhum canal tem gate de identidade de terceiro sobre pixels; o creative-supply-chain define o modo mínimo.

A resposta à questão central está em `EXECUTION-WORKBREAKDOWN.json` (15 tarefas) e `CANARY-SEQUENCE.json` (Display → Demand Gen → PMax).
