# Meta: jornada automática e leitura pós-criação

Estado: parcial, alterações locais. Nenhuma criação, upload, ativação ou migration realizada nesta rodada.

## Entregue

- Portfólios empresariais cadastrados carregam da integração autenticada. A BM selecionada carrega suas contas automaticamente; trocar de BM limpa a conta anterior antes de receber a nova lista. Nenhum token é entregue ao componente.
- Consulta do anunciante automática, mantendo confirmação dos responsáveis e seleção quando há mais de uma identidade. Demo não consulta identidades reais.
- Revisão dispara compilação e validate-only automaticamente quando o rascunho está completo, com debounce, descarte de respostas obsoletas e tentativa limitada por fase/plano. Aprovação e criação permanecem atos humanos separados. Falha possui retry explícito.
- Países: seleção múltipla com busca, nomes pt-BR, bandeiras e exclusão recíproca. O contrato continua ISO2.
- Públicos personalizados e semelhantes existentes carregam automaticamente por conta. CSV não é um público semelhante: exige público de origem e operação própria de criação, ainda não implementada internamente.
- Enquadramento especial passa a ser uma pergunta simples. Não se presume ausência de categoria especial.

## Incidente confirmado por leitura

O último recibo parcial parou após criar o conjunto, antes dos criativos. A Meta normalizou um início passado para o horário exato de criação e acrescentou VOLUNTARY_VERIFICATION ao enquadramento solicitado. O executor recusava ambas as leituras. Agora aceita estritamente essa normalização temporal comprovada e esse marcador adicional, preservando beneficiário/pagador e categorias pedidas. Também reconhece CAMPAIGN_PAUSED/ADSET_PAUSED herdados, sem aceitar configured_status diferente de PAUSED. A releitura dos objetos existentes passou; não foi executada retomada.

## Evidência

- Backend: 144 testes focais passaram (readback V2, nascimento pausado, rotas, lote estático, contrato).
- Frontend: 51 testes passaram (24 de BM, anunciante, países e catálogo; 27 de nascimento, incluindo aprovação, duplo clique e respostas obsoletas na preparação automática).
- Build Vite aprovado; typecheck não apontou erros nos componentes alterados, mas o projeto tem erros herdados.
- Health de 8080, 3001 e 8010 respondeu; autoridade Supabase verificada.
- Suite adicional de recuperação: 11 passaram / 1 falhou na expectativa antiga de META_SHOP_REDIRECT_CLEARED versus opt-out explícito do compilador, fora da alteração deste sprint.

## Pendências e aceite

Faltam QA visual autenticado, nova criação completa PAUSED e fluxo interno de CSV/criação de semelhantes. A suíte de nascimento foi adaptada à sequência automática; as demais suites antigas da jornada não foram integralmente executadas nesta rodada. Não declarar produção integralmente validada.

Para testar: abrir /trafego/meta/nova sem modo=demo. Confirmar BM, conta, responsáveis, enquadramento e anúncios. Verificar recibo com campanha, conjuntos, criativos e anúncios; não repetir criação às cegas diante de recibo parcial.

Referência de contrato: SDK oficial Meta, https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/campaign.py (consulta 2026-09-09). O suporte específico continua sujeito à validação da conta e versão usadas pelo backend.
