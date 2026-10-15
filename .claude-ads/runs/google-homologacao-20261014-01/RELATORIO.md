# Homologação Google Ads — quatro canais (14/10/2026)

Run `google-homologacao-20261014-01`, sobre o commit `ea3b86b4`. Um integrador, `main`.
O que esta rodada não fez:
- **Nada criado:** nenhum recurso real no Google.
- **Sem escrita fora do código:** nenhuma no Supabase ou no WordPress.
- **Sem nova geração de LLM:** reaproveitada a copy Gemini salva em 14/10.
- **Sem infraestrutura nova:** nenhuma migration, deploy ou push.

Preexistente e de outra sessão, preservado sem tocar:
- `volc-os-workbook/ROADMAP-VIVO.json` (P06/P07/P14);
- `docs/volc-os-graph/curadoria-operacional.json`;
- grafo gerado e inventário de repositório;
- `docs/architecture/ADR-CICLO-ECONOMICO-COMPRA-MONETIZACAO.md`, `docs/reference/buy-sell-loop/` e `.claude-ads/runs/buy-sell-loop-20261014-01/`;
- `funnelforge-migracao/engine/runs-canario/`.

## Matriz

| Canal | Caminho testado | Google validate_only | Request ID | Lacuna |
|---|---|---|---|---|
| Search | `POST /api/trafego/provar` real, em processo, identidade substituída e declarada; oportunidade 106, conjunto aprovado (cluster 10), copy Gemini salva | **aceito**: 40 operações. O espião confirmou `validate_only=true` e `partial_failure=false`, e o hash recalculado das operações enviadas = recibo (`a3b85ccc…`). Conta relida sem mudança | `yfaLR3S6gKa_TI0Gb4xP2g` (02:26 UTC de 15/10) | O selo foi retido porque o destino LP 2477 está em rascunho (HTTP 404). **Falta insumo**: a página publicada. Não existe página pública congruente com "Gás do Povo" no site |
| Display | mesma rota | **não chamado**: recusa interna antes da rede (422 `PARAMETRO_DO_OPERADOR_AUSENTE`) | — | **Falta autorização financeira** do operador para Display (verba + CPC/estratégia). **Falta insumo**: imagem paisagem 1,91:1 + quadrada 1:1 aprovadas com finalidade Google — há 0; o Estúdio só tem peças 1080×1350/1080×1920 aprovadas para Meta, e a conta só tem 1 imagem 1024×1024 |
| Demand Gen | mesma rota | **não chamado**: 422 `CAMPO_OBRIGATORIO` (`demand_gen`, `assets_demand_gen`) | — | **Falta insumo**: mídia (par paisagem+quadrada e 1–5 logos, ou vídeo YouTube + logo) aprovada para Google. **Falta autorização**: flag `VOLC_DEMAND_GEN_VALIDATE_ONLY` desligada neste servidor, e verba |
| PMax | mesma rota | **não chamado**: 422 `CAMPO_OBRIGATORIO` (`pmax`, `assets_pmax`) | — | **Falta insumo**: imagens+logo por asset group. **Falta autorização**: flag `VOLC_PMAX_VALIDATE_ONLY` e verba. **Barreira interna**: o portão de mensuração lê `include_in_conversions_metric=false` nas ações primárias, mas a conta usa metas personalizadas que o VOLC ainda não lê |

- **Validação técnica não é homologação operacional.** O validate_only aceito do Search não prova anúncio aprovado, campanha criada, veiculação ou ROI. Os três canais com mídia não foram homologados nesta rodada.
- **O que não foi reaproveitado, de propósito:** os banners de ensaio e a verba de teste da prova de 09/10. Seriam fixture e autorização inventada.

## Bloqueios do destino (card 106) por natureza

| Natureza | Item | Fonte |
|---|---|---|
| Plataforma (Google) | `DESTINO_INDISPONIVEL_PUBLICAMENTE`: a página respondeu 404 (rascunho) | Destination requirements: o destino precisa funcionar |
| Regra interna | nenhum emitido para o 404. `IDENTIDADE_OPERADOR_AUSENTE`, `IDENTIDADE_CONTATO_AUSENTE` e `DIVULGACAO_DE_MONETIZACAO_AUSENTE` são `interpretacao_volc`; só podem nascer de página lida e continuam bloqueando quando a página é lida sem eles | contrato `FUNDAMENTO_POR_CODIGO` |
| Desconhecido | identidade, alegações e divulgações, originalidade/congruência, serviços governamentais, redirect/cloaking (não lidos); deriva ao vivo (não aplicável) | `destino.por_natureza.desconhecido` |
| Erro técnico | nenhum (a leitura concluiu: o servidor respondeu 404) | — |

**Correção feita:** até esta rodada, a varredura de identidade emitia CNPJ, contato e divulgação "ausentes" sobre o HTML vazio do 404, ao lado do próprio status `unavailable`. Agora página sem texto vira desconhecido, sem afirmar ausência, e continua reprovando. A resposta do `/provar` ganhou `destino.por_natureza` com as quatro listas, e a `DestinoIlegivel` distingue "respondeu sem servir a página" de "leitura falhou".

## Caminhos do operador

| Caminho | O que faz | Provado nesta rodada |
|---|---|---|
| Harness `canonico.py` (CLI) | Gemini escreve só a copy; o pedido passa pela rota real em processo | sim (14/10); hoje, replay sem nova geração |
| Copy pela interface | `POST /copy` → cascata `volc_ads/copy` (até 8 rodadas, grava no banco) → o operador edita | não exercitado (seria LLM pago e escrita no banco) |
| Rota com identidade substituída | o mesmo código da rota real, sem sessão | sim (Search, validate_only) |
| Produto autenticado | front `:8080` → backend `VITE_PAUTADOR_API_URL=:8011` (o `start-dev.sh` sobe só a `:8010`) | só leituras (9 rotas, 200; sem token, 401). O `/provar` pela tela não roda: a tela `Lancamento` não chama a prova quando o destino não está apto, e o assistente grava decisões no "resumo persistente" |

- **O que chega ao produto:** o request ID agora aparece no juiz "google" da tela (`Lancamento.tsx`), e `destino.por_natureza` está na resposta JSON.
- **O que não chega:** a tela não mostra `por_natureza`, e o harness não é botão do cockpit (pendência: a geração de copy pela interface é a cascata, não o harness).
- **Menor autorização** para o teste autenticado completo: permissão para o assistente gravar decisões do card no Supabase, mais o destino publicado. Sem o destino, a tela para antes do Google, por desenho.

## Testes

- Testes focados de backend: 58 arquivos (tráfego, barreiras, política de destino, segurança, reauditoria, canário) → 1.883 passaram, 2 falharam (herdadas, abaixo).
- `volc_ads` inteiro: 1.599 testes, todos verdes.
- UI: `prova-honesta` + `lancamento` → 20 testes, verdes; `tsc -p tsconfig.app.json` sem erro nos arquivos tocados.
- Contraprova sem dublê de identidade: `/provar`, `/subir` e `/trava` sem token ou com token inválido → 401.
- Garantias cobertas:
  - validate_only não chama o executor: portões de escrita e capacidades;
  - erro parcial não vira sucesso: `testes_lote` mais o validate_only real de 14/10 (22/30 com erro);
  - CPC estimado não decide dinheiro: `test_cpc_estimado_alterado_nao_muda_brief_nem_payload_do_search`;
  - o recibo bate com o payload: teste novo e espião real.
- **Herdadas que tocam segurança:**
  - `test_canario_pedido_aprovado` 4/6b: a `chave_intencao` do dossiê v10 não se reproduz, porque o hash do plano aprovável inclui os 21 campos que `ProvarEntrada` ganhou depois. Efeito: aprovação antiga não autoriza o pedido atual (recusa a mais); alterar verba ou CPC muda a chave. Não abre escrita. Menor ajuste: versionar a chave ou regravar o dossiê com aprovação humana nova.
  - `test_creative_reuse_packs` / `test_criativo_contexto_pagina`: na suíte inteira respondem 503 "autenticação indisponível" porque outro módulo apaga as variáveis do Supabase. Isolados, dão 401. Continuam recusa.
