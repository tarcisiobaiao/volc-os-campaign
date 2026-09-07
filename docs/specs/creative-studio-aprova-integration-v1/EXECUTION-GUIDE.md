# Integração Aprova → Assistente Criativo VOLC

## Resultado esperado

Uma jornada operacional no mesmo localhost:8080: escolher destino/formato, preparar
a estratégia de arbitragem, conferir/refinar, aprovar, gerar imagens e selecionar
assets persistidos. Interface Aprova reaproveitada, marca e contratos VOLC preservados.

## Ordem de autoridade

1. Pedido atual do operador e limites de autorização.
2. AGENTS.md, PRODUCT.md e design.md do VOLC.
3. Código operacional atual e contratos canônicos de estratégia, mídia e identidade.
4. SPEC.json desta pasta, que delimita a adaptação.
5. Specs anteriores de creative-supply-chain, meta-creative-p0-reconciliation e
   creative-studio-operating-experience, para detalhes não conflitantes.
6. services/creative-studio/upstream como referência de implementação, nunca como
   contrato de segurança, credencial, política ou regra de arbitragem.

Se uma spec antiga requer reconstrução de todo o Estúdio, isso não amplia esta sprint.

## Preparação

Confirme worktree /private/tmp/volc-os-operacao-80-20, branch operacional e que
53d57746f8ba00461dd1b0d6056a695c89b34c86 é ancestral do HEAD. Pode haver as adições
locais desta preparação em services/creative-studio e docs/specs/creative-studio-aprova-integration-v1.
Elas pertencem à missão: leia e preserve. Não as descarte por estarem não commitadas.
Se houver alterações fora desses paths, identifique o writer antes de sobrepor.

Leia IMPORT-MANIFEST.json. A origem tinha onze arquivos de configuração/doc ausentes:
o snapshot recuperou esses arquivos de seu Git, mas nunca modificou a origem.
Não copie node_modules, .git, .env ou runtime_config.json para “fazer funcionar”.

## CP1: estratégia antes de imagem

Adapte seletor de formatos, formulário e estados do Aprova para componentes do host.
Faça primeiro o fluxo briefing → estratégia → refinamento/aprovação persistidos.
No Hub, botão secundário Assistente Criativo abaixo de Nova Campanha Meta. Não herdar
?modo=demo do link de criação. Usar ProtectedRoute e transporte autenticado FastAPI
já configurado; /api relativo do Vite pode apontar para Node3001, não Python8010.

Feche as lacunas de operação/run e aprovação antes de esconder tudo atrás de um loader.
O agente atual não possui listagem operacional e aguarda LLM dentro da requisição.
Reaproveite jobs existentes ou estenda minimamente a persistência. Não adicione
Redis/Celery/outro servidor apenas por hábito. Retorno202 exige trabalho realmente
durável; tarefa em memória sem recuperação não pode ser rotulada durável.

## CP2: imagens com procedência

Mapeie peças selecionadas e copies sem apagar refs, fatos, grupos ou aprovações.
Escreva contrato de adapter. Reuse providers existentes; porte lógica útil do Aprova
apenas se faltar e teste por transporte fake. Não execute estrategista antigo além
do agente Meta para decidir o mesmo briefing. Não pesquisar claims novos em silêncio.

N conceitos × M formatos são N×M saídas, não N ideias novas. Imponha teto antes dos
inserts e do provider. Reutilize saídas prontas; cancelamento pedido e confirmado são
estados diferentes. Desconectar SSE não confirma cancelamento nem libera retry.

Galeria mostra proporção medida, zoom por teclado, download individual e ZIP com
somente assets autorizados ao dono. Nada de forçar todas as imagens a 4:5.
Reabrir operação precisa continuar mostrando previews válidas, mesmo após expiração
de uma URL assinada; renovar autorização. Não reaproveitar seleção de outra conta.

## CP3: banco e prova real

O estado físico oficial é desconhecido até catálogo SQL. PGRST202/205 não provam
inexistência de tabelas/RPCs. A API operacional única é database.agenciavolc.com.br.
Verifique estado/histórico/grants/funções/ownership da v11_05 e dependências mínimas.

Não aplicar todo diretório de migrations Meta. Não reescrever migration já aplicada.
Preparar manifesto de SQL e hashes; testar usuário A, B e anon, integridade
owner→operação→run→decisão e impedir fabricação de aprovação via REST.
Testar apply→uso→rollback→reapply descartável. Não usar rollback destrutivo no
oficial que já tenha operações sem autorização específica e salvaguarda dos dados.

A v11_05 foi solicitada pelo operador, mas endurecimento/adaptação pode exigir
outro delta: mostrar o conjunto exato antes da janela oficial. Acesso SQL deve
ser provisionado localmente de forma segura, nunca solicitado como segredo no chat.

Sem autorização de geração real, usar fake claramente identificado nos testes.
Preparar pedido de prova com modelo/quantidade/limite de custo; clique em gerar
deve sempre ser explícito. Não testar credenciais nem chamar provider ao montar página.

## CP4: fechar sem looping

- Testes focais: autoridade/owner, ref duplicada, aprovados congelados, multi-formato,
  idempotência, eventos/reconexão, ausência de provider, falha parcial, preview/download.
- Build e TypeScript por delta contra base real. Não defender baseline apenas por
  arquivos não alterados; dependências e fixtures também afetam testes.
- Visual: 375,768,1440; claro/escuro; briefing, progresso, resultado, erro e retorno.
- Um ciclo de correções confirmadas. Reportar bloqueio restante precisamente.
- Atualizar P11-T02/P11-T04 e cap_creative_engines sem promover demonstração a produção.
- Regenerar pelo wrapper do grafo, jamais editar saída gerada.
- Deixar 8080 no ar, links e SHA servidos registrados; sem push/deploy.

Use statuses separados: SOURCE_IMPORTED, LOCAL_FLOW_READY, OFFICIAL_DB_VERIFIED,
LIVE_GENERATION_VERIFIED. Só declare cada um com a prova correspondente.
