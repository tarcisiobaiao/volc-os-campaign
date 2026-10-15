# Mapa real do caminho Search — medido em 14/10/2026

> **Errata (homologação de 14/10, run google-homologacao-20261014-01):** os "bloqueios" de CNPJ, contato e divulgação do card 106 foram emitidos sobre o HTML vazio de um 404. Não são fato sobre o site e são `interpretacao_volc`, não exigência do Google. O único bloqueio de plataforma é o destino indisponível (rascunho). A varredura foi corrigida.

Classe de cada evidência: `leitura real`, `validate_only real`, `sessão real (leitura)`,
`código`, `fixture`. Nada foi criado, ativado ou gravado no banco.

| # | Etapa | Onde mora | Estado medido hoje | Buraco |
|---|---|---|---|---|
| 1 | Oportunidade + conjunto pago | `pautador_ponte.carregar` → `portao_conjunto_pago.criterios_do_cluster` | leitura real: dos 6 clusters recentes, **só a oportunidade 106** passa no portão (14 keywords, 5 subintenções). 65/73/74/104: cluster do n8n sem contrato (`N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`); oportunidade 1: `CONJUNTO_PAGO_NAO_APROVADO` | **dados**: falta conjunto aprovado pelo motor Python nas demais oportunidades |
| 2 | LP / contexto | cockpit (`origem`, `texto_da_lp`, `promessa_da_lp`); portão de destino em `/provar` | 106: LP 2477 em **rascunho** (HTTP 404 público), URL provisória `?post_type=r&p=2477`; bloqueios do destino: divulgação de monetização, contato/privacidade, CNPJ do operador | **conteúdo/operação**: publicar a LP e as páginas de identidade do site. Não é código |
| 3 | Proposta Gemini | antes: `harness/search.py` montava Brief próprio, fora do portão. **Agora**: `harness/canonico.py` escreve só texto e entra pela rota | validate_only real: 1 geração `gemini-3.8-flash` (servido = pedido), 2.440 tokens, 6,06 s, ~US$ 0,0036 estimado | proposta assistida é CLI; no cockpit a copy vem da cascata `/copy` (até 8 rodadas) — dois geradores de copy coexistem |
| 4 | Grupos / copy | `Escolha(conjunto_unico=True)` na rota (doutrina P7) | a rota colapsa o conjunto em **um** grupo; `SubIntencao.rsa` (RSA por grupo) só é alcançável no modo laboratório | decisão do dono: copy por intenção exige rever P7 ou um eixo de experimento; não mudei a doutrina |
| 5 | Configuração explícita | `ProvarEntrada`, `_exigir_parametros_do_operador` | verba/CPC obrigatórios (422 sem eles); o harness exige verba, CPC, estratégia e rede sem padrão | — |
| 6 | Builder | `subir.preparar` → `perfil.montar` → `search.construir` | avisos visíveis no sucesso: descrição de sitelink com 36 caracteres descartada; repetição de palavra entre títulos (política 14848296) | a cascata de 09/10 produziu sitelink fora do limite — o builder segura, mas a origem do texto não conhece o limite |
| 7 | validate_only | `gads.client.validar_mutacoes` | **validate_only real** pela rota: 42 ops (replay da copy de 09/10) e 40 ops (copy Gemini), request IDs `d-cek3xx80tm8NJ2Xj4IKg` e `SDeAi8SZ8xFRhKFHxNBWuQ` | **fechado nesta missão**: o aceite agora devolve `prova_google` (request ID, versão, instante) pela rota, nos 4 canais |
| 8 | Selo / plano | `Selo` + barreira 3 (destino) | selo **retido pelo destino** nos dois casos; `plano_impressao=null` | correto; depende do item 2 |
| 9 | Executor / recibo | `/subir`, `subir.subir`, ledger | não exercitado (escrita não autorizada) | trava, canário, admin e destino continuam exigidos |
| 10 | Leitura de conferência | `harness/capture.snapshot`; `releitura_por_canal` pós-criação | leitura real antes/depois: 5 campanhas, 8 anúncios, **idênticos** | releitura cobre campanhas/anúncios/orçamento/estratégia, não toda configuração da conta |
| 11 | Cockpit / mensuração | `/plano-de-mensuracao`, inventário | **sessão real (leitura)**: a tela do operador chamou 9 rotas autenticadas no backend desta missão, todas 200; sem token, 401 | `/provar` e `/subir` autenticados pela tela não foram exercitados (o assistente grava decisões; destino em rascunho). Metas personalizadas ainda não lidas (fila de 09/10, item 3) |

## O que mudou no código (P0)

1. `volc_ads/subir.py`: `ProvaGoogle` + `Preparo.prova_google`. O `validate_only`
   aceito passa a carregar o request ID da RPC (o interceptor já existia em
   `gads.client`, sem chamador canônico). Fica fora do `Selo`: o selo continua sendo
   só a impressão do payload. Na autocorreção, vale o id da chamada que aceitou.
2. `backend/app/trafego/projecao.py`: `preparo.prova_google` na resposta de `/provar`.
3. `volc_ads/harness/canonico.py`: proposta Gemini → corpo de `/provar` → rota real
   em processo, com contexto lido pelo mesmo carregador/portão, fotografia da conta
   antes/depois, reparo só para texto recusado, custo estimado com preço declarado.
4. Duplas de teste com assinatura estrita de `validar_mutacoes` aceitam o kwarg novo.

## O menor próximo passo que destrava dinheiro

Publicar a LP do card 106 (ou escolher outra oportunidade com conjunto aprovado e LP
publicada) e completar as páginas de identidade do site. Sem isso nenhuma
oportunidade de produção chega a `plano_impressao` — e isso não se resolve com código.
