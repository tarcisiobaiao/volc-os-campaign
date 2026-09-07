# Missão: Assistente Criativo VOLC com experiência Aprova

Você é o executor principal Claude Opus. Implemente uma jornada utilizável, não outra
rodada genérica de arquitetura. Reaproveite o produto Aprova importado e conecte-o
ao assistente Meta e ao parque criativo do VOLC. Não construa outro sistema de login,
outra autoridade de estratégia, outra biblioteca isolada ou outra porta de frontend.

## Worktree e fontes

Trabalhe SOMENTE em:
 /private/tmp/volc-os-operacao-80-20

Branch:
 execution/volc-os-operacao-80-20

Base de preparação:
 53d57746f8ba00461dd1b0d6056a695c89b34c86

Cópia local sanitizada:
 /private/tmp/volc-os-operacao-80-20/services/creative-studio/upstream

Documentos obrigatórios:
 /private/tmp/volc-os-operacao-80-20/services/creative-studio/README.md
 /private/tmp/volc-os-operacao-80-20/services/creative-studio/IMPORT-MANIFEST.json
 /private/tmp/volc-os-operacao-80-20/docs/specs/creative-studio-aprova-integration-v1/SPEC.json
 /private/tmp/volc-os-operacao-80-20/docs/specs/creative-studio-aprova-integration-v1/EXECUTION-GUIDE.md

O original do cliente é SOMENTE LEITURA. Não precisa acessá-lo: use a cópia.
Não criar branch ou worktree; não tocar checkout principal. Preservar a importação
e os docs locais mesmo se ainda não commitados. Confirmar ancestralidade e writers.

## Autoridade técnica

Leia AGENTS.md, PRODUCT.md, design.md. Use skills disponíveis de UI e Supabase.
Consulte grafo e código; snapshot não comprova produção. Leia o SPEC inteiro e siga
S01–S07, CP0–CP4. Consulte specs anteriores apenas onde o novo contrato remete.

Fontes runtime:
 backend/app/criativo/agente/
 backend/app/routers/criativos_agente.py
 backend/app/criativo/execucao.py
 backend/app/criativo/persistencia.py
 services/creative_engine/
 src/pages/trafego/HubDeTrafegoPage.tsx
 src/pages/pautador-pro/PautadorProPage.tsx
 src/lib/criativosApi.ts
 src/lib/pautadorApi.ts
 supabase/migrations/v11_05_criativo_agente_meta.sql

## Entrega

1. No Hub rede=meta, Assistente Criativo abaixo de Nova Campanha Meta.
2. Rota protegida /trafego/meta/assistente-criativo e detalhe por projectRef.
3. Fluxo Aprova: formato/briefing → acompanhamento → estratégia/refinamento →
   aprovação → geração → galeria/zoom/download individual e ZIP → retomada.
4. Estratégia exclusivamente do AgenteCriativoMeta: fatos, grupos, copy compartilhada,
   peça e etapa mental preservados. O planejador antigo de concurso não decide.
5. Imagem via contrato/adaptador canônico; N peças × formatos explícito, limitações
   antes de qualquer efeito, origem/hash/owner/approval mantidos até asset_ref.
6. Persistência segura do assistente e integração mínima com jobs/master/storage.
   Corrigir listagem, retomada, refinamento com saída anterior, refs duplicadas,
   congelamento estável e permissões que permitam fabricar aprovações.
7. Front com design VOLC, sem identidade Aprova, mock silencioso, hero decorativo,
   loader inventado, crop universal4:5, ação exclusiva por hover ou botão sem função.
8. Contrato portável: host fornece identidade/repositório/mídia; nada depende do
   caminho privado do cliente. Pasta importada é referência, não app a expor.

O upstream tem bloqueios intencionais de App/main/scripts. Não simplesmente remova
para abrir endpoints antigos. Extraia/reuse código com o transporte autenticado VOLC.

## Permissões e checkpoints

Autorizado: implementação LOCAL desta frente, testes herméticos, SQL candidato,
documentação e commits lineares escopados. Não repetir arquitetura inteira.

A v11_05 oficial foi solicitada pelo operador. Antes de qualquer aplicação, execute
CP3: catálogo SQL, manifesto exato de scripts/hashes, dependências mínimas, backup/
rollback, teste descartável. Caso sejam necessárias outras migrations, storage ou
escritas reais não delimitadas, solicite aprovação do delta e siga o restante local.

Não autorizado por este prompt: push, deploy, Meta/Google Ads read/validate/mutate,
criação/ativação de campanha, n8n, WordPress, Postiz, migração ampla, acesso ao cliente
original, alteração de credenciais ou geração paga automática. Prova real de modelo
requer aprovação explícita de quantidade/modelo/custo; sem ela, entregue local pronto.

Mantenha localhost:8080. Não encerre processos de outros projetos. Antes de reiniciar,
verifique autoridade Supabase, cwd/PID/portas; preserve sessão sem pedir senha.
Não rode o start-dev.sh do Aprova.

## Forma de execução

Um writer; checkpoints curtos com resultado visível. Testes proporcionais aos riscos,
uma rodada corretiva focal, sem dezenas de revisores ou reformulação interminável.
Não criar um relatório de “feito” se falta botão, campo, persistência ou preview.
No final: SHA, arquivos, testes medidos, screenshots/URLs, status por etapa, migrations
aplicadas versus somente candidatas, lacunas e próximo ato. Atualize memória uma vez.
Sem push. Não confundir cópia local, fluxo local, banco oficial e geração real.
