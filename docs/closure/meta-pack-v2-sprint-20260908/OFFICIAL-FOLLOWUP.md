# Sprint autorizado: persistência oficial e inspeção local

Data: 08/09/2026. Branch `execution/volc-os-operacao-80-20`.
Estado: **PARTIAL**. Mesma árvore operacional; rebranding e alterações anteriores preservados. Sem commit/push, nova branch ou worktree.

Atualização posterior: autorização explícita de pixels recebida e detector Gemini
Meta integrado/testado. A ausência de `marca_visual` descrita abaixo é histórica;
estado atual e limites em [GEMINI-BRAND-INSPECTION.md](GEMINI-BRAND-INSPECTION.md).

## Supabase oficial — aplicado e provado

Destino único: `https://database.agenciavolc.com.br`. Autoridade conferida pelo script do projeto; DNS e SSH conferidos contra o runbook de infraestrutura. PostgreSQL 15.8 no container `supabase-db`.

Backup protegido, somente schema, criado no servidor antes da primeira alteração: `/root/meta-v2-schema-20260908-Pp7j8R/schema.sql`. SHA256 `b1bf2294424c3894a0e7d8586f5e93bb62d5247a99fa9eaab3d178e3990f886e`. Não exportado para o repositório. Restauração global não é automática; preservar novas escritas em qualquer recuperação.

| Migration em `supabase/migrations` | SHA256 | Resultado |
| --- | --- | --- |
| `20260908234824_meta_v2_approval_budget_manifest.sql` | `ec81aaf6e3aab4476973d0146593f389a293a2d8653a11bd6d2b97e7f6c33f0a` | COMMIT |
| `20260909000758_meta_campaign_draft_persistence.sql` | `5e709189a997a304ff68c6a2eb634481279d434956dca4b7e02cba5a9e919cb0` | COMMIT |

Aplicação por arquivos exatos, `psql -X -v ON_ERROR_STOP=1`, cada migration com transação própria. Nenhuma fila global de migrations executada. PostgREST notificado após cada aplicação.

Provas no banco oficial, com fixtures sintéticas e ROLLBACK:

- Aprovação e recibo V2 preservam manifesto nas quatro combinações ABO/CBO × diário/total. Nenhum despacho à Meta, nenhum passo artificial fechado como campanha real. Marcador: `V2_OFFICIAL_ABO_CBO_DAILY_LIFETIME_ROUNDTRIP_ROLLED_BACK_OK`.
- Rascunho: salvar, reler, editar, recusar versão obsoleta, isolar proprietário e negar RPC a `authenticated`. Marcador: `META_DRAFT_OFFICIAL_SMOKE_ROLLED_BACK_OK`.
- As fixtures não permaneceram no banco. A tabela de aprovação estava vazia antes da janela.

## Montagem recuperável

Novo endpoint autenticado guarda o Draft completo: conjuntos, anúncios, textos, orçamento, público, mensuração e origem dos packs. CAS impede sobrescrita silenciosa entre abas. A UI distingue recuperando, salvando, salvo, erro e conflito; edição aguarda hidratação. A aprovação exige salvar antes. Demo não grava o Draft no banco.

A releitura dos ativos não pode apagar público/conversão nem substituir uma peça ao restaurar a mesma conta. Apenas troca efetiva de conta limpa referências incompatíveis e declarações da peça. O backend continua revalidando a elegibilidade atual; preservar referência não prova que o ativo continua disponível.

A ficha do canário deixou de chamar o método inexistente `buscar_validacao`: agora consulta o recibo pelo hash exato e ator autenticado, com janela de 1.800 segundos. Recibos futuros/vencidos ou incompatíveis são recusados. SELECT já era permitido pelo schema; nenhuma migration adicional. Consulta real read-only ao banco oficial com hash/ator sintéticos inexistentes concluiu normalmente. Não herda autorização de criação nem reutiliza `validation_id` consumido.

JSONB reordena chaves: o hook compara fingerprints canônicos. Salvar sem alteração não bloqueia autosaves posteriores. Declarações de direitos/categoria e autorização de lançamento não são herdadas do Draft; precisam de confirmação após retomar. Detalhes do contrato: `../meta-creative-reuse-v1/CAMPAIGN-DRAFT-PERSISTENCE.md`.

## Inspeção de imagens — capacidade real, limite explícito

Apple Vision OCR implementado no Mac, com leitura real de uma imagem sintética contendo `TESTE OCR 2026`. Nenhum pixel enviado pela rede; nenhum custo. Configuração local ignorada pelo git: `CRIATIVO_POLICY_LOCAL_OCR_ENABLED=true`. Backend reiniciado em 8010, health `ok`, nenhum router/rotina ausente; frontend 8080 HTTP 200.

O OCR declara apenas `texto_na_imagem`, nunca `marca_visual`. Um logo sem texto não é reconhecido por OCR. O código executa a leitura fora do event loop, valida MIME/tamanho e identifica o detector como não determinístico.

**Reconhecimento visual de marcas permanece ausente.** O auto-review recusou a implementação que enviaria pixels privados ao Gemini sem autorização específica desse payload. A recusa foi respeitada: nenhum adapter externo, chave ou envio de imagem ao Gemini foi feito nesta rodada. Para concluir, obter autorização explícita para enviar imagens finais à API Google/Gemini para essa inspeção, com modelo/custo/limites declarados, ou instalar detector local real. Não cadastrar detector vazio e não converter ausência de inspeção em aprovação. OCR macOS não equivale a detector disponível no futuro servidor Linux/Webgo.

## Verificações

- Backend integrado: 65 passed, 1 skipped (OCR real opt-in nessa execução). O OCR real foi executado separadamente: 4 passed com `VOLC_TEST_APPLE_OCR=1`, incluindo reconhecimento on-device. Nenhuma falha focal.
- PostgreSQL descartável incluído nessa bateria: 5 provas V2 e 4 de Draft.
- Consulta da prova por hash: 9 testes novos passaram, além da leitura oficial sem escrita.
- Frontend: 45 testes de página/pack + 6 do hook de persistência passaram.
- Chrome headless: seis capturas 375/768/1440 × claro/escuro, teclado, isolamento dos anúncios por conjunto, autosave e reload. Componentes reais, APIs simuladas e rede externa bloqueada. **Não é QA autenticado com ativos de cliente.** Runner local `/private/tmp/qa-meta-ads-stage.mjs`; capturas `/private/tmp/meta-ads-stage-<largura>-<tema>.png`.
- Build passou em 12,61 s. TSC mantém 76 erros globais, nenhum nos arquivos novos de Draft ou `MetaCriacaoPage`; não é gate global verde.
- Scanner sem padrões fortes de segredo e `git diff --check` limpo.

## Próxima prova

Concluir detector `marca_visual` com autoridade de envio apropriada; então revisar e registrar uma imagem real do pack, fixar em cada anúncio e executar um canário PAUSED com conta, conteúdo e orçamento explicitamente conferidos. Nenhuma criação/ativação Meta, geração paga, mutation n8n/Google Ads ou deploy foi realizada nesta rodada.

Memória: P11-T02 e P11-T05 permanecem `partial`; nós `cap_meta_ads` e `cap_bancada_criativa` recebem estas provas. O grafo deve ser reconstruído após integrar o handoff, sem promover prontidão de produção por teste local.
