# Assistente Criativo — correção visual local

Base: `4227275abcecf38ce9dff6f08d42f257caecb8cb`.
Branch: `execution/volc-os-operacao-80-20`. Sem branch/worktree nova, sem push.

## O que inspecionar

Abra `/trafego/meta/assistente-criativo?view=briefing` em localhost:8080.
A composição do Aprova foi adaptada para os tokens VOLC: coluna central,
cards compactos, proporções visuais selecionáveis, contexto e fatos da oferta,
quantidade por slider e ação central. Histórico é secundário e só consulta
a API quando aberto; falha de histórico não impede preparar o briefing.

Estratégia, aprovação e produção preservam o transporte autenticado existente.
A galeria lê os jobs vinculados à operação, atualiza trabalhos pendentes por GET,
oferece zoom, seleção e download individual/ZIP. Nenhuma montagem inicia geração.
Erro de leitura não é apresentado como acervo vazio. Mudança de seleção invalida
a apresentação do plano de produção anterior.

## Provas locais

- 26 testes focais de frontend passaram, incluindo galeria e seleção do plano.
- ZIP produzido sem dependência nova, lido pelo `zipfile` independente do Python;
  CRC e bytes de duas entradas conferidos. Paths e nomes repetidos recusados.
- Build Vite passou. TypeScript verificado pelo tsconfig.app.json, não pela raiz
  vazia: 76 erros herdados; sem erro nos arquivos desta frente.
- Chrome headless: componentes reais em Router isolado, Layout substituído somente
  no harness temporário. Larguras 375, 768 e 1440, temas claro/escuro: zero overflow
  horizontal e zero pageerror. Capturas inspecionadas pelo executor.
- Essa inspeção NÃO é um fluxo autenticado completo nem prova de geração paga.
- Zoom, download PNG e download ZIP exercitados no Chrome com fixture técnica
  isolada de um pixel; arquivos recebidos, sem asset fictício no runtime do produto.
- Grafo reconstruído pelo wrapper oficial: `--check` current=true, insumos idênticos.

## Limitações preservadas

- Supabase oficial e v11_05/v11_06/v11_07 não foram alterados nesta rodada.
- Nenhuma imagem paga, chamada Meta/Google Ads ou publicação realizada.
- A referência de destino ainda segue o contrato opaco do engine; não aceita URL
  arbitrária nem afirma que buscou/analisou a landing page.
- O detalhe da operação ainda não projeta decisões persistidas ao frontend;
  aprovação visual é espelho da sessão, e restaurá-la após reload é pendência
  funcional independente. O backend continua exigindo aprovação na produção.
- Downloads reais dependem de jobs e URLs assinadas acessíveis; nenhum asset real
  foi produzido nesta correção. Não há botão de publicação nesta galeria.

P11-T02 e P11-T04, nó `cap_creative_engines`: permanecem **partial**.
Roadmap/curadoria distinguem UI implementada de operação oficial comprovada.
