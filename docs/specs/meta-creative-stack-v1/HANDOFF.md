# Meta creative stack: integração local parcial

Base desta rodada: `ec518470396451a24703f7e28cd09d06d5578124`. O motor do terminal (`969b69c`) já era ancestral; não houve merge, nova branch ou worktree.

## O que mudou

- Copy externa pode ser aprovada na estratégia e enviada ao rascunho da campanha integrada. O iframe envia apenas refs; o backend lê conteúdo e aprovações do dono. A pessoa escolhe qual anúncio terá texto substituído. A confirmação reconfere o snapshot, recusa revogação/mudança e invalida plano e atestações da combinação anterior.
- A exportação recusa peça/copy ausente, duplicada, não aprovada, alterada, grupo divergente, lote inválido, CTA incompatível e histórico saturado. Não registra imagem, não persiste linhagem nova no plano e não autoriza campanha.
- A tela e a capacidade flexível deixam de publicar limites DCO como se fossem regras flexíveis v26. O guia fornecido descreve `creative_asset_groups_spec` no anúncio e exemplos v25. Implementação e prova v26 continuam pendentes.
- Corrigida a alegação de inexistência de exemplos oficiais de custo por imagem. Existem exemplos de custo de saída; não temos estimador total para nossos canvases/entradas. Estimativa continua desconhecida, nunca zero nem teto garantido.

## Chave e teste do motor

No ambiente operacional atual, coloque `OPENAI_API_KEY=<sua chave>` em `backend/.env` da mesma pasta que serve o backend. O caminho absoluto foi conferido na sessão: `/private/tmp/volc-os-operacao-80-20/backend/.env`. Não crie outra pasta de trabalho.

Não use prefixo `VITE_`, não coloque a chave no frontend, não envie por chat e não a versione. O arquivo está ignorado pelo Git. Configurações de processo têm precedência; `.env.local` também pode sobrepor `.env`. Não imprimir valores ao diagnosticar.

Após salvar, reinicie somente o backend pelo procedimento existente em `start-dev.sh`, depois de `python3 scripts/verificar_autoridade_supabase.py`. O reload de código não garante recarga de `.env` e Settings é cacheado. Motor esperado: `openai-gpt-image-2`, modelo `gpt-image-2`, qualidade `medium`.

A chave sozinha não prova acesso ao modelo, schema oficial, persistência nem storage. Não houve geração paga nesta rodada. Primeiro teste real deve ter autorização delimitada a um conceito e um formato, conferir o plano de gasto e verificar job/master/rendition, hashes, download e retomada. `v16_01`, persistência real, gate R01 e registro na Meta permanecem checkpoints separados.

## Documentação recebida

`EVIDENCE.json` separa conteúdo fornecido pelo operador de páginas consultadas diretamente e documentos ainda ausentes. `STACK.json` contém a sequência, autoridades e checkpoints. Exemplos de ativação/remoção nas páginas não foram executados.

Pontos decisivos: DCO não é formato flexível; Advantage não é aprovação universal de variantes; `adgroup_id` no evento de fadiga é o anúncio; a tabela de bidding tem aviso de objetivos deprecados. Receita GAM medida no painel não equivale a evento de valor recebido pela Meta.

Faltam os guias detalhados de bid-strategy, Advantage Get Started, webhooks overview e ad-recommendations. Não há inbox remoto nem execução de recomendações implementados nesta rodada.

## Verificação e limites

108 testes focais de backend e 45 de interface passaram. Build passou com avisos existentes de tamanho de bundle/dependências. TypeScript permanece com erros fora do domínio alterado, contagem registrada no relatório final. O teste antigo da demo ainda esperava as oito etapas anteriores; foi atualizado para a jornada atual preservando a contraprova de criação bloqueada.

Testes de interface são jsdom; não são QA visual autenticado. Não foi exercitada aprovação ou geração em banco oficial. Nenhum token lido, nenhum push/deploy, nenhuma chamada Meta, geração paga ou migration oficial.

Memória: P11-T05 e cap_meta_ads continuam partial. A atualização do grafo é feita pelo gerador canônico, nunca editando o snapshot.
