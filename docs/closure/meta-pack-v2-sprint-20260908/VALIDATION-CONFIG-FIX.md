# Correção de validação e configuração — 08/09/2026

Estado: **LOCAL_FIX_VERIFIED / LIVE_ENABLEMENT_PENDING**. P11-T02 e P11-T05 continuam partial.

## Correções

- Uma pendência de mensuração não acusa mais a URL válida como inválida. Pixel/dataset, evento ausente e seleção ambígua têm mensagens próprias por conjunto.
- `pendenciasDaVariacao` é a fonte única da completude e dos motivos por anúncio: imagem, conjunto, nomes, copy, CTA e confirmações de uso. Reabrir um rascunho não restaura autorização de publicação.
- Conferir/validar mostra andamento e resultado, com região viva identificada. O foco vai para o feedback ao iniciar a ação; editar posteriormente não rouba o foco. Alterar o plano invalida o resultado e explica que é preciso conferir novamente.
- Corrigida a afirmação obsoleta de que o contrato V2 não possui criação. A criação continua exigindo aprovação, validação e capacidades reais.
- Flags de criação, ledger, validate_only e allowlists agora usam leitura centralizada de Settings/arquivos locais. Ambiente explícito, inclusive vazio/0, prevalece. Validar não autoriza criar; upload e prova de destino continuam por conta. Ambos os ledgers e as rotas V1/V2 usam a mesma fonte.

## Provas

- Backend: 153 testes passaram (configuração, rotas de criação pausada, registro de mídia e validação V1/V2). Arquivos temporários sintéticos provam carregamento/recarregamento, revogação e ausência de liberação implícita entre contas.
- Frontend: 71 testes passaram em três arquivos. Testes antigos que procuravam o seletor de lote retirado da jornada foram adaptados à adição/remoção por conjunto, preservando as verificações de identidade e não perda dos anúncios.
- Build Vite passou. TypeScript global segue com erros fora dos arquivos alterados nesta correção; não é gate verde global.
- Chrome real, APIs isoladas com fixtures: seis capturas (375/768/1440, claro/escuro), teclado, isolamento de conjunto e persistência/reload da fixture, sem overflow nem erros de página. Não constitui QA autenticado no banco oficial.
- Frontend 8080 e health do backend 8010: HTTP 200. Uvicorn recarregou o worker após as alterações.
- Autoridade Supabase conferida pelo verificador do repositório: self-hosted oficial. Nenhuma migration ou gravação no banco nesta correção.

## Limites e próximo ato

A tentativa de gravar as permissões no backend/.env foi recusada pela proteção de execução por habilitar criação no processo inteiro, sem escopo de conta para essa flag. A recusa foi respeitada: **nenhuma dessas flags foi gravada**, e a configuração atual continua validate_only=false, ledger=false, processo de criação=false, zero contas de upload e zero contas com prova de destino. A correção do leitor está implementada; a liberação operacional não está.

É necessária autorização explícita para uma configuração limitada à conta do teste (a capacidade atual de criação é global, portanto seu escopo também precisa ser resolvido). Não aceitar um valor de configuração como prova de elegibilidade externa. A prova de destino website/Shop desta conta não foi estabelecida neste trabalho.

O operador ainda precisa escolher o pixel/dataset associado ao evento, usar a URL final real, revisar data de início e confirmar direitos/identidade das imagens. Não selecionamos valores por conta própria. Depois: conferir → validar → aprovar o hash exato → criar pausada → conferir recibo e read-back. Nenhuma campanha, geração paga, upload ou chamada Meta foi disparada nesta correção.

## Integração e reversão

Mesma branch e worktree operacional; mudanças preexistentes preservadas. Sem commit/push. Não reverter o arquivo inteiro: ele contém trabalho anterior. Para revogar permissões após futura autorização, valores explícitos vazios/0 continuam fechando as portas; alterações em arquivos de configuração exigem reinício. Memória reconciliada nos nós cap_meta_ads e cap_bancada_criativa; grafo reconstruído pelo script canônico.
