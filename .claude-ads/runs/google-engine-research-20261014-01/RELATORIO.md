# Motor de campanhas VOLC: estado real e pesquisa de bibliotecas

Pesquisa e verificações: 14/10/2026, referência de data America/Sao_Paulo.
Base auditada: `main @ fb446595`. Escopo: Google Ads primeiro, fronteira Meta identificada.

## Veredito

O VOLC já possui o núcleo de um motor Google Ads: contratos de entrada, quatro construtores, prova pela API, executor, recibos, ledger, reconciliação, coleta e gestão assistida. A etapa incompleta é fechar essas capacidades num percurso operacional reproduzível com os dados, a identidade, o destino e a mensuração reais.

Não recomendo trocar o motor por um conjunto de repositórios nem instalar todas as bibliotecas pesquisadas. A menor composição nova é um adapter Gemini para o harness, usando os contratos existentes, e testes de estado/contrato selecionados. Planejamento e análise contextual podem usar LLM; dinheiro, identidade, execução, hashes e reconciliação continuam determinados pelo código e pela configuração do operador.

Não há biblioteca que garanta ausência absoluta de erro ou aprovação de anúncio. O objetivo verificável é detectar falhas, localizar sua causa, preservar trabalho aproveitável e retomar sem duplicar campanhas ou inventar resultados.

## 1. O que foi verificado nesta rodada

- O diretório inicial do chat é um checkout antigo (`wip/original-worktree-pre-qg-real-20261007 @ 314c3e4b`) com muitas alterações locais. Foi preservado. A análise usou o checkout consolidado em `main @ fb446595`.
- Grafo consultado antes da inspeção de código; check inicial `current:true`, por digest de insumos.
- 460 testes focados passaram, zero falhas, em 3,86 s. São testes herméticos dos construtores Search/Display/Demand Gen/PMax, dos portões de escrita e da independência do CPC estimado. Existem 930 avisos de depreciação/configuração; suíte verde não significa ausência de dívida técnica.
- Leitura atual pela integração v25 real: conta operacional habilitada, moeda BRL, fuso America/Sao_Paulo; uma campanha Search ENABLED e quatro PAUSED. Nenhuma mutação.
- Metas padrão da conta relidas: PURCHASE/WEBSITE biddable=false; DOWNLOAD/APP biddable=true. Isso não descreve sozinho a meta efetiva de cada campanha: metas específicas e customizadas precisam ser consideradas.
- Uma chave Gemini já está presente no carregador do backend. Apenas presença e referências de configuração foram observadas; validade, acesso a modelo e cota não foram testados. Nenhum valor foi exibido e nenhuma inferência paga foi feita.
- Ambiente `backend/.venv`: Python 3.14.6, google-ads 33.0.0, Pydantic 2.13.4, HTTPX 0.28.1. google-genai, google-adk, Hypothesis e Schemathesis não estão instalados nesse interpretador. Isso não prova ausência em outros ambientes do projeto.

Provas da rodada: `tests.xml` e `leitura-google.json`, nesta pasta.

## 2. Capacidade versus prova operacional

| Frente | O que existe | Prova disponível | O que não foi demonstrado |
|---|---|---|---|
| Search | Contrato, RSA, keywords, assets, payload, validate_only, criação pausada | Builder aceito na API; evidência de 09/10 de caminho HTTP com oportunidade e conjunto pago reais, 44 operações; identidade do backend substituída por admin de teste | Percurso autenticado completo com sessão real, destino aprovado e nascimento/releitura pelo cockpit nesta rodada |
| Display | Builder RDA, imagens no grafo e configuração | Validate_only real de 09/10, nove operações; mídia de ensaio | Mídia aprovada para Google e canário de criação autorizado |
| Demand Gen | Builder multi-asset/vídeo, contratos e prova | Validate_only real de 09/10, nove operações; mídia de ensaio | Percurso produtivo de mídia, autorização do canal e orçamento compatível com requisitos aplicáveis |
| PMax | Asset groups, payload e separação de prova técnica/lançamento | Validate_only real de 09/10, 25 operações | Metas efetivas, volume/sinal e mídia produtiva suficientes para o plano de lançamento |
| Leitura/coleta | Famílias GAQL, recibo, persistência e retomada | Leitura atual de conta/campanhas/metas nesta rodada; evidência histórica de coleta idempotente | Agenda recorrente de produção saudável e cobertura atual de todas as famílias não auditadas ao vivo hoje |
| Gestão | Propor, aprovar, validar, aplicar e reler | Código e evidência histórica de validate_only de ações; testes locais | Regra publicada, migrations e operação completa em produção não foram rechecadas hoje |
| Autonomia | Ponto central de autorização | `NIVEIS_QUE_APLICAM_SEM_HUMANO` está vazio no código | Gestão financeira autônoma, proponente automático e teto acumulado diário não estão demonstrados |
| Meta | Compilador, executor HTTP, contratos e reconciliação próprios | Inspeção de fronteira e código | Auditoria remota e canário Meta não realizados neste escopo |

Os recibos de 09/10 demonstram payloads específicos, não todas as combinações de canal/formato/lance. A documentação oficial distingue teste em contas de teste, leitura em contas de produção e request validation: [Google Ads — Testing](https://developers.google.com/google-ads/api/docs/best-practices/testing).

## 3. Onde estamos patinando

1. **A execução completa ainda depende de costuras operacionais.** O Search já avançou além do bloqueio antigo de conjunto pago; usar só a auditoria anterior levaria a um diagnóstico desatualizado. A prova posterior ainda não cobre a sessão real e a criação/releitura pelo mesmo percurso.
2. **Há documentação antiga misturada a evidência nova.** A matriz de cobertura de agosto ainda descreve SDK 31.3.0, rede implícita e recursos ausentes já tratados depois. Em partes da curadoria, `evidence` antigo e `latest_evidence` dizem coisas diferentes. Código ativo e recibos datados precisam prevalecer conforme a ordem de autoridade do projeto.
3. **Mensuração ainda não representa automaticamente o caixa.** Valores fixos atribuídos a eventos de anúncio não são receita JoinAds/GAM. O plano precisa distinguir conversão técnica, valor sintético e receita reconciliada. Um modelo não corrige essa distinção por inteligência de linguagem.
4. **Existe uma lacuna pequena e útil no recibo de prova.** `gads.client.validar_mutacoes` retorna falha ou None e descarta a identificação de sucesso. O sucesso de `/provar` deveria carregar request ID/metadados disponíveis, hash do pedido, versão e data pelo caminho canônico, sem depender de interceptor externo de auditoria.
5. **O empacotamento precisa corresponder ao ambiente que opera tráfego.** O SDK Google Ads está declarado em requirements-dev e o import do tráfego é tardio. A prova local funciona; é necessário conferir a imagem/worker de implantação que executará tráfego, sem assumir que o backend mínimo já inclui esse SDK.
6. **Autonomia de dinheiro e criação assistida são entregas diferentes.** É possível fechar Search com criação pausada e gestão aprovada antes de resolver otimização financeira autônoma. Não atrelar o primeiro lançamento à implantação de todo o portfólio.

## 4. Bibliotecas e repositórios: seleção para o VOLC

### Núcleo a preservar ou incorporar

| Item | Decisão | Ganho e limite |
|---|---|---|
| [google-ads](https://github.com/googleads/google-ads-python) | Preservar | SDK oficial de protos, serviços e erros. Já instalado e funcionando. Não criar outro cliente de mutação. |
| [google-genai](https://github.com/googleapis/python-genai) | Candidato principal para o harness | SDK oficial Gemini, tipos, structured output, streaming e function calling. Usar para planejar/analisar através de ferramentas limitadas; não substituir a compilação do payload existente. O transporte HTTP atual já funciona: uma migração ampla não é pré-requisito. |
| [Pydantic](https://docs.pydantic.dev/latest/) | Reutilizar | Já existe nos contratos. Valida tipos e estrutura; não prova a verdade da recomendação nem autorização de gasto. |
| [Hypothesis](https://hypothesis.readthedocs.io/en/latest/stateful.html) | Adicionar somente em desenvolvimento, se necessário | Testar sequências: validar → alterar → tentar aplicar; timeout → retomar; duplo clique; revogação. Ganho maior que adicionar milhares de exemplos espelhando implementação. |
| [Schemathesis](https://schemathesis.readthedocs.io/en/stable/) | Opcional, focado | Exercitar OpenAPI do backend local/isolado: entradas inválidas, contratos e respostas. Nunca apontar fuzzing de endpoints mutantes à produção. |
| [RESPX](https://lundberg.github.io/respx/) | Opcional | Falhas e contratos das integrações HTTPX/Gemini/Meta. Não substitui teste de protos/gRPC do Google Ads. |

### Ferramentas oficiais de engenharia e leitura

| Item | Decisão | Ganho e limite |
|---|---|---|
| [Google Ads API Developer Assistant](https://github.com/googleads/google-ads-api-developer-assistant) | Extrair ferramentas e padrões | Validação GAQL, inspeção de objetos/enums, diagnóstico de conversões e coerência de versão. É auxiliar de desenvolvimento; não substitui a engine de negócio. |
| [googleads/google-ads-mcp](https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server) | Leitura opcional | O release documentado é estritamente read-only. Não cria campanha, não muda lances e não pausa. Pode ajudar Bia/Hermes e consultas, mas não fecha o executor. |
| [google/skills](https://github.com/google/skills) | Referência para agentes | Instruções e fluxos de desenvolvimento. Não são capacidades produtivas automaticamente instaladas. |
| [Gaarf](https://github.com/google/ads-api-report-fetcher) | Spike pequeno de leitura | Reutilizar queries e explorar relatórios fora do caminho principal. Já há coletor/ledger próprio: não criar segunda fonte concorrente nem segunda agenda. A árvore Python usa garf-core/garf-io/garf-executors; conferir compatibilidade de versão antes de adotar. |
| [Google ADK](https://adk.dev/evaluate/) | Condicional | Avaliações de saída e trajetória de ferramentas podem ajudar. O projeto já tem harness de desenvolvimento com ADK declarado; ele orquestra CLIs e não é, por si, o runtime de campanhas. Começar sem uma nova malha de agentes. |
| [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/) | Depois do primeiro percurso fechado | Trace por intenção, LLM, compilação, Google, recibo e read-back. Não precisa de uma plataforma nova para registrar inicialmente esses tempos no recibo existente. |

### Padrões que vale extrair, sem instalar outra plataforma

| Projeto | Uso útil | Limite |
|---|---|---|
| [Ads Monitor](https://github.com/google-marketing-solutions/ads-monitor) | Métricas, ausência de entrega e alerta por mudança | Usa Gaarf/Prometheus/Grafana/Alertmanager. O VOLC não precisa instalar tudo para ter um alerta útil. |
| [ARBA](https://github.com/google-marketing-solutions/arba) | Diagnóstico de perda de impression share e componentes de Quality Score | Extrair consultas e evidências. Não promete corrigir rank por aumentar lance. |
| [Negative Keyword Cleaner](https://github.com/google-marketing-solutions/negative_keyword_cleaner) | Procurar negativas existentes que podem bloquear tráfego relevante | Não é fonte de uma lista genérica de novas negativas. Exige contexto e evidência dos termos antes de propor alterações. |
| [Copycat](https://github.com/google-marketing-solutions/copycat) | Exemplos e comparação de geração de RSA a partir de voz e anúncios existentes | Benchmark contra a cascata VOLC; não instalar outra autoridade de copy. |
| [Adios](https://github.com/google-marketing-solutions/adios) | Ciclo imagem → biblioteca → vínculo → experimento | Adaptar apenas o elo ausente de assets aprovados para Google. Não substituir o Estúdio Criativo. |
| [If This Then Ad](https://github.com/google/if-this-then-ad) | Evento externo → condição → ação proposta | Projeto em TypeScript/Apps Script, não biblioteca Python central. Seus acessos e agendas não devem bypassar ledger e executor VOLC. |
| [Topic Mine](https://github.com/google-marketing-solutions/topic-mine) | Dados próprios/tendências como insumo de pauta e copy | Comparar com Attention/Pautador; não duplicar mineração. |

### Estacionar para esta missão

- [Meridian](https://github.com/google/meridian): modelagem de mix de marketing agregado; não fecha criação nem gestão intradiária.
- [FeedX](https://github.com/google-marketing-solutions/feedx): experimento de Shopping feeds; não é harness geral de lançamento Search.
- CRMint/BigQuery/Dataform como nova plataforma de pipelines: só adotar se um requisito real justificar infraestrutura adicional.
- JEV, múltiplos frameworks de agentes e outro revisor genérico: sem evidência incremental, não colocar no percurso crítico.
- [Meta Business SDK](https://github.com/facebook/facebook-python-business-sdk): referência oficial para a próxima etapa Meta. A ausência do pacote no venv não prova defeito: já existe executor HTTP próprio. Adotar apenas se reduzir manutenção e preservar os contratos.

Repositório publicado por uma organização Google não equivale a produto com suporte oficial. Ads Monitor, ARBA, Copycat e Negative Keyword Cleaner, entre outros, declaram essa diferença. Metadados de 17 repositórios foram conferidos na API pública do GitHub; os centrais estão não arquivados e têm licença Apache-2.0. Algumas bibliotecas e SDK Meta exigem verificação específica da licença da distribuição/arquivo escolhido. Hypothesis declara MPL-2.0 no PyPI; Schemathesis MIT; RESPX BSD-3-Clause. Não foi copiado código nem instalado pacote.

## 5. Versões: não abrir uma migração desnecessária

O ambiente operacional local usa `google-ads==33.0.0` e a API explicitamente pinada em v25. O PyPI consultado ainda expunha 33.0.0 como última distribuição. A documentação anuncia v26 em 14/10/2026 e exige SDK Python mínimo 34.0.0 para ela; a tabela mantém v25 com sunset previsto para agosto/2027.

Há diferença entre anúncio da API, atualização de documentação e disponibilização do pacote. Preservar v25 para fechar Search, acompanhar a publicação e fazer migração controlada em outra mudança. Não alterar o default silenciosamente.

Fontes: [compatibilidade de SDKs](https://developers.google.com/google-ads/api/docs/client-libs), [sunset](https://developers.google.com/google-ads/api/docs/sunset-dates), [releases do SDK](https://github.com/googleads/google-ads-python/releases).

## 6. Harness proposto: pequeno e conectado ao motor existente

Fluxo desejado:

`intenção do operador + oportunidade + bucket/LP + limites explícitos`
→ `Gemini gera proposta estruturada`
→ `contratos e builders VOLC compilam`
→ `Google validate_only do payload exato`
→ `diff/revisão contextual localizada quando necessário`
→ `plano revisável`
→ `executor atual cria PAUSED sob autorização`
→ `releitura confere o efeito`
→ `recibo e vínculo no cockpit`.

Ferramentas de leitura e preparação expostas ao modelo devem chamar as funções existentes. O modelo não recebe uma ferramenta arbitrária de Python/shell nem acesso irrestrito a `mutate`. Pydantic/structured output dão forma à proposta, não autoridade para gastar. Os campos financeiros vêm do operador/regras autorizadas; CPC estimado permanece informação de pesquisa, não lance.

Começar com um orquestrador. Uma chamada de planejamento/copy e, quando necessário, uma correção dirigida ao erro material. Não fazer novo web search para cada campo da API nem submeter o mesmo payload dezenas de vezes. Consultar metadados de campo e erros reais antes de inventar correção.

### Casos mínimos que o harness deve provar

1. Search completo com oportunidade, conjunto pago, LP publicada, orçamento/lance declarados e sessão real.
2. Campo técnico ausente ou incompatível: mensagem acionável, sem Google mutate e sem chamada LLM inútil.
3. Seleção, URL, lance ou asset alterado após a prova: plano/hash anteriores não autorizam o novo pedido.
4. Duplo clique/retomada da mesma intenção: um nascimento, mesmo recibo ou reconciliação.
5. Timeout após envio de criação: estado indeterminado e read-back; nenhuma repetição cega. O executor de nascimento já passa `SEM_RETENTATIVA`; preservar e testar.
6. Erro de política/campo em um asset: preservar o restante, apresentar correção localizada sem disfarçar alegação nem prometer aprovação.
7. Campanha criada, mas persistência/read-back falha: pendência explícita recuperável, sem afirmar conclusão.
8. Receita ausente, grãos incompatíveis ou valor sintético: não mostrar lucro comprovado nem usar como base silenciosa de escala.
9. Meta efetiva/customizada, volume e moeda/fuso: conferir a configuração da campanha, não só uma flag legada da conta.
10. Mudanças financeiras sucessivas: teto por ação não substitui teto acumulado; manter autonomia desligada até haver essa capacidade e autorização.

Avaliar separadamente: correção técnica, correção da proposta, ferramentas invocadas, quantidade de chamadas, latência e efeito financeiro real. Um score LLM não substitui pedido aceito pela API ou releitura.

## 7. Ordem para terminar com velocidade

| Ordem | Entrega concreta | Aceite |
|---|---|---|
| 1 | Escolher uma oportunidade e LP realmente utilizáveis para Search; conferir login real e parâmetros | O mesmo pedido passa pelo backend autenticado até validate_only, com recibo completo |
| 2 | Corrigir a telemetria de sucesso da prova e ligar o Gemini às interfaces existentes | Intenção → proposta → payload → request ID/hash rastreáveis; nenhuma mudança não declarada |
| 3 | Fechar um nascimento PAUSED autorizado e o read-back pelo cockpit | IDs, configuração e vínculo batem; repetição não duplica |
| 4 | Importar/reconciliar campanhas existentes e fechar coleta/receita | Campanha existente aparece no cockpit; zero, ausência e falha permanecem distintos |
| 5 | Provar uma edição pequena com aprovação e reversão | Antes/depois, read-back e recibo completos |
| 6 | Só depois Display/Demand Gen/PMax e Meta | Mídia, metas, orçamento e requisitos específicos provados por canal |

Não aplicar migrations, corrigir metas, ativar campanhas ou copiar credenciais em nome desta pesquisa. Essas são próximas execuções, com planos concretos. Esta rodada conclui diagnóstico e seleção técnica, não a implementação do harness.

## 8. Configuração Gemini

O cliente de copy resolve a configuração em `volc_ads.copy.cliente.Config.do_ambiente`: raiz `.env`, depois `backend/.env`, depois `backend/.env.local`, com precedência de variáveis do processo. A propriedade `Settings.resolved_gemini_key` prefere GEMINI_API_KEY sobre GOOGLE_API_KEY.

Para o novo adapter do SDK, passar a chave já resolvida explicitamente ao cliente: o auto-discovery do SDK pode usar precedência diferente entre os dois nomes. Não manter duas chaves divergentes. Nunca usar `VITE_*` para essa credencial e nunca imprimi-la em recibos.

Antes de inferência paga: confirmar catálogo/modelo acessível, parâmetros suportados, cota e teto de gasto. Não usar alias `latest` para uma comparação reproduzível. A chave Gemini autoriza o modelo; OAuth/identidade Google Ads continuam sendo a autorização separada da conta de mídia.

## 9. Memória e limites desta auditoria

Tarefas relacionadas: P04-T04, P04-T07, P04-T09, P05-T04, P05-T05, P05-T10, P06-T03, P06-T08, P09-T15 e P14-T02. Continuam com o estado registrado no projeto; esta análise não promoveu nenhuma tarefa.

Nós relacionados: `cap_search_birth`, Google Ads multicanal, Google Ads MCP e coleta/gestão Google. A curadoria e o roadmap foram lidos, não alterados. Nenhum código produtivo, segredo, campanha, banco ou ambiente remoto foi alterado; sem instalação, push, deploy ou chamada paga de modelo.

As leituras da conta de hoje não verificam migrations ou agendamentos do banco/servidor, políticas dos anúncios, receita, login do frontend ou todos os recursos da API. Fontes públicas foram consultadas em 14/10/2026. Versões, acesso de conta, recursos em beta e orçamento mínimo por canal exigem reconferência quando selecionados para execução.
