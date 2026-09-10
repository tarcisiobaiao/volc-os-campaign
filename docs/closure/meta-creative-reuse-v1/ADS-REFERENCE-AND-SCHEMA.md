# Anúncios por conjunto, inspiração visual e schema oficial

Data: 2026-09-08. Branch: `execution/volc-os-operacao-80-20`.
HEAD base da rodada: `be4483b19f62d638909ca22ee523ec92816e1d14`.
Estado: **PARTIAL**. Alterações locais não commitadas, preservando o rebranding e os trabalhos anteriores na mesma árvore. Sem push.

## Entregue nesta rodada

- Etapa de criativos organizada por conjunto selecionado, com contagem de anúncios, inclusão explícita no conjunto e edição isolada. A filtragem preserva o índice original do rascunho: editar o segundo conjunto não altera o primeiro.
- Reutilização cria outro anúncio, mantém o original e exige revisão das declarações de uso. Nomes internos ficam em detalhes. Seletor redundante individual/lote/flexível removido da jornada normal; estados antigos incompatíveis continuam explicados, não convertidos silenciosamente.
- Imagem opcional com escolha explícita entre inspiração visual, fotografia preservada e reinterpretação. Não existe seleção automática de colagem. Reabrir a operação exige escolher o uso antes de um novo plano.
- `referencia_visual` integra contrato selado, execução Python e multipart `/v1/images/edits`, com `gpt-image-2` e `quality=medium`. A referência é enviada como bytes; sua finalidade é estilo/paleta/composição, não identidade, fatos ou texto. O briefing aprovado prevalece. O compositor de colagem não é chamado neste modo.
- O adapter OpenAI passou a declarar explicitamente suporte a referências; adaptadores sem essa capacidade falham antes da geração.
- CSS da jornada limita a coluna ao viewport; ações quebram linha em telas estreitas.

Inspiração é uma instrução ao modelo, não garantia de ausência de semelhança. Revisão humana, direitos de uso e política permanecem necessários antes de mídia paga. Nenhuma imagem de referência real foi gerada nesta rodada.

## Supabase oficial: aplicação realizada

Destino único: `https://database.agenciavolc.com.br`. Autoridade conferida pelo script do repositório antes da operação. Backup de schema realizado no servidor, sem exportar tokens/dados para o repositório. Aplicação por arquivos exatos via `psql -v ON_ERROR_STOP=1`, nunca por glob.

| Arquivo em `supabase/migrations/` | SHA256 | Resultado |
| --- | --- | --- |
| `v15_01_meta_ads_read_model.sql` | `2343deefdf82f7b641ed68996d833ddfda1a4a632b34fe8bb27e0500af2e595d` | Aplicado |
| `20260904183418_meta_create_paused_executor.sql` | `1bd2c4e004bd418713a3126dd7c403f79c4a42c6927b1fb2aef84d2f96a4d9ce` | Aplicado |
| `20260907120000_meta_recovery_snapshot.sql` | `26b031da6847fdefc2d29bdfc7e9b49e7c9580f27db2951d656865c76a9920c5` | Aplicado |
| `20260907190000_meta_worker_fencing.sql` | `2fc1857a8f0501e4ba4f2f3f41dc45acdba2664e489113e18710b857f8cd68ce` | Aplicado |
| `20260908224044_meta_reference_visual.sql` | `0905199614379c1493901dec94ffc7d9e7967c0ca2aad41021d84b66e57de923` | Aplicado |

`v13_01` já existia e NÃO foi reaplicada. O perfil `CREATE_ONLY` foi conferido contra o catálogo físico oficial: `PERFIL_ATUAL`, `CREATE_ONLY: conferido`, exit 0. A constraint física `criativo_job_modo_composicao_valido` foi relida e inclui `referencia_visual` junto aos três modos anteriores. Nenhuma outra migration foi aplicada nesta rodada. Isso não afirma instalação dos perfis de sincronização/Insights completos.

O leitor de catálogo ganhou cast explícito de `relkind::text`, pois a concatenação `text || "char"` era ambígua no PostgreSQL oficial. O manifesto de schema foi reconciliado com essa aplicação e as contagens de arquivos rastreados.

## Verificações

- SQL local descartável: 38 verificações, incluindo ciclo, RLS/grants, recuperação e fencing; zero falhas. Não é uma campanha real.
- Backend focal: 149 passed (`test_criativo_studio_adaptador`, `test_criativo_motor_openai`, `test_criativo_execucao`, `test_schema_perfil_meta`). Transporte OpenAI dublê, sem rede/pagamento.
- Frontend final: 44 passed (29 criador V2, 2 referência visual, 8 assistente, 5 vínculos de conjuntos).
- Build de produção: passou, 11,96 s; avisos de tamanho de bundle e classes de animação ambíguas persistem no design global.
- TypeScript pelo projeto correto: 76 erros globais; nenhum nos domínios `pages/trafego`, `features/creative-studio`, `components/trafego/meta`. Não é gate global verde.
- Chrome headless, componente de página real com dados de teste e Layout isolado: teclado, isolamento entre conjuntos e seis capturas 375/768/1440 × claro/escuro, sem erro de runtime nem overflow horizontal. Não equivale a QA autenticado com ativos reais. Capturas locais em `/private/tmp/meta-ads-stage-<largura>-<tema>.png`; runner `/private/tmp/qa-meta-ads-stage.mjs`.
- Scanner de segredos e `git diff --check`: sem achados nesta rodada.

## O que continua impedindo o lançamento completo

1. O criador usa V2 para múltiplos conjuntos e recursos avançados. As rotas existentes de aprovação/criação executam V1; V2 compila/valida, mas ainda não possui executor de criação. Instalar o SQL V1 não resolve esse contrato. Não converter para V1 descartando conjuntos/atribuição.
2. Pack/seleção do Estúdio ainda não completa avaliação de política → registro de mídia na conta → vínculo aos anúncios. Selecionar o pack não significa que suas imagens estão no payload final.
3. Não houve canário de criação de campanha, upload de mídia ou geração paga da nova referência. Flags de processo, autorização por conta, validação e revisão de política NÃO foram forjadas nem dispensadas.
4. O serviço local não equivale a worker hospedado/always-on. Persistência do schema não comprova operação autônoma em produção.

Próxima prova: operador anexa referência e escolhe **Usar como inspiração visual**, sela o plano de uma peça/um formato e confirma o custo na interface. Verificar job, modelo, arquivo, procedência e imagem final. Depois concluir o executor V2 e a ponte de mídia antes do canário PAUSED.

Memória: P11-T02/P11-T03/P11-T04 permanecem `partial`; nós `cap_meta_ads`, `cap_creative_engines`, `system:motor-imagem-volc` e `concept:composicao-hibrida-fotografia` recebem esta evidência. O grafo é reconstruído pelo wrapper oficial após a integração.
