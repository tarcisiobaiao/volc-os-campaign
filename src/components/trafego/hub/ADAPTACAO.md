# Adapter visual do Hub — U0 / H0

Este arquivo é o ponto exato de adaptação. `src/types/trafego.ts` continua
sendo a verdade do contrato compartilhado. Nada aqui é segunda verdade
dentro dos componentes: a tela fala o vocabulário de `hub/contrato.ts`, e estas
funções traduzem URL ↔ filtros.

O contrato `VERSAO_INVENTARIO = 2` já atende o Hub. Não há alias de payload,
não há ordenação local, não há recurso de detalhe improvisado a partir da lista.

## O que o adapter ainda faz

| Tela | Contrato | O que o adapter faz |
|---|---|---|
| Histórico oculto no padrão | `incluir_historico` default `false`; `totais.operacionais` / `historicas` / `geral` | a lista operacional não pede histórico; o botão lê `historicas` |
| Canal Performance Max | `PERFORMANCE_MAX` | `PMAX` só entra como alias legado (`canalCanonico`); URL e consulta emitem o canônico |
| Vídeo e Shopping | `VIDEO`, `SHOPPING` no inventário; sem manifesto | a tela os nomeia; o Hub não os opera |
| Aba Preparar | `aba=oportunidades` no endereço antigo | `abaDaUrl` mapeia o alias; o rótulo é Preparar |
| Reconciliação | objeto `reconciliacao` no quadro, ou `null` | `null` falha fechado (`pendente`); só `sem_campanha` + `pode_montar` libera montar |
| Meta Ads | sem endpoint | `MetaNaoConfigurada`; não consulta o inventário Google fingindo Meta |

## O que saiu deste adapter

- **Ordenação local.** A ordem chega pronta (`customer_id` → `ordem_operacional` → `volc_campaign_id`). `ordenarCampanhas` foi removido: reordenar a fatia paginada discordava do servidor.
- **Página canônica improvisada.** `CampanhaCanonPage` liga em `pautadorApi.campanhaCanonica(volcCampaignId)`. 404 é "não encontrada"; o resto é indisponibilidade. Não percorre o inventário, não aceita `campaign_id` externo, não consulta o Google Ads, não escreve.
- **"Confirmar vínculo ainda não tem endpoint."** O cliente existe. A tela oferece confirmação e bloqueia montagem; não dispara escrita na conta de anúncio.

## O que a tela recusa

- Detectar FGTS ou Maquininha pelo nome. Existente = `reconciliacao` declarada. `null` bloqueia montagem. `campanhas_lancadas` isolado nunca libera.
- Inventar desempenho, orçamento ou ação em canal sem manifesto. `manifesto: null` não vira capacidades zeradas.
- Chamar mutate Google, webhook n8n, `service_role` ou guardar token no browser.
- Escrever `5` ou `79` na interface. Os totais vêm da leitura.
- Tratar `null` como `0`.

## Rota fora do ownership estrito

`src/App.tsx` ganhou `/trafego/campanhas/:volcCampaignId` — sem isso o chassi
H0 não navega. Nenhum outro arquivo fora de `pages/`, `components/`, `hooks/`
foi alterado por esta frente.

## Quando o contrato avançar

1. Meta real → `perfilDoCanal('meta')` passa `integrado: true` e a aba deixa de montar `MetaNaoConfigurada`.
2. Confirmação de vínculo nesta tela → POST em `pautadorApi.confirmarVinculo` sem `confirmado_por` no corpo.
