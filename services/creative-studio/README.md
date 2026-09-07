# Creative Studio: base Aprova para integração VOLC

Estado: **SANITIZED_REFERENCE_IMPORTED / RUNTIME_NOT_INTEGRATED**.

A cópia está em `upstream/`. Ela preserva componentes, fluxo de geração, providers,
eventos SSE, tratamento de erros, testes e configuração de build do Aprova Ad Studio.
Não é um serviço já operante, não está montada em 8080 e não constitui aprovação de segurança.

## O que mudou na cópia

- `src/pages/Login.tsx`: removida credencial fixa e autenticação local.
- `src/App.tsx`: substituído por tela de referência sem montar ações legadas.
- `backend/app/main.py`: importação bloqueada antes de carregar configuração/providers.
- `package.json`: scripts bloqueados para impedir execução acidental.
- Credenciais, .env, runtime_config.json, .git, node_modules, dist, caches,
  script de boot legado, lock binário Bun e imagens/logos do cliente não foram importados.
- Onze arquivos ausentes no working tree foram recuperados do HEAD do projeto fonte
  somente nesta cópia; consultar IMPORT-MANIFEST.json.
- Componentes ainda contêm referências visuais Aprova e pressupostos legados. São
  material de portabilidade, não autoridade de produto. Remover os pressupostos na
  extração para o host VOLC, não restaurar o login/configuração antigos.

Não executar `start-dev.sh` da origem, não remover o bloqueio para subir a API antiga,
não importar esse `app` Python no processo VOLC e não apontar o browser ao backend legado.

## Contrato e execução

Leia:
- `docs/specs/creative-studio-aprova-integration-v1/SPEC.json`
- `docs/specs/creative-studio-aprova-integration-v1/EXECUTION-GUIDE.md`
- `docs/specs/creative-studio-aprova-integration-v1/EXECUTOR-PROMPT.md`

A fronteira a construir é estratégia aprovada → pedidos de imagem → assets privados.
O assistente Meta existente é a autoridade estratégica. O parque criativo existente
é dono de jobs/storage/recibos. Esta pasta identifica o pacote e preserva sua origem;
o contrato permite extração futura como serviço sem criar um segundo sistema agora.

Nada nesta importação modifica o produto fonte, cria campanha, gera imagem, publica
workflow, instala dependências ou aplica migration. O projeto fonte continua só leitura.
