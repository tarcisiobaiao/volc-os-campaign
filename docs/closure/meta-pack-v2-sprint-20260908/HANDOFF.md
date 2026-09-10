# Pack → mídia → anúncios por conjunto: sprint local

Data: 2026-09-08. Estado: `LOCAL_PARTIAL`.
Branch existente: `execution/volc-os-operacao-80-20`.
Base observada: `be4483b19f62d638909ca22ee523ec92816e1d14`.
Sem novo branch, worktree, commit, push ou substituição do rebranding.
Alterações anteriores de outros trabalhos foram preservadas.

## Implementado

- O pack confirmado no conjunto mostra as imagens finais, revisão humana,
  inspeção de política e ato separado de envio à conta.
- `POST /api/trafego/meta/ativos/revisar` retorna evidência sobre os bytes finais.
  `/registrar` exige os hashes conferidos, reavalia todas as peças antes do
  primeiro upload e não aceita aprovação da estratégia como aprovação da imagem.
- Reuso consulta aprovações existentes. Master arquivado, versão/finalidade/dono
  divergente, revogação e hash diferente bloqueiam envio.
- O retorno `master_ref → asset_ref` monta anúncios no conjunto explicitamente
  selecionado e importa a copy como sugestão, nunca como aprovação automática.
  Recibos parciais/ambíguos não montam um lote aparentemente completo.
- Reaplicar o mesmo recibo não duplica os anúncios locais. Outro conjunto recebe
  outro anúncio; o original não é movido. Placeholder inicial intocado é
  substituído; texto editado pelo operador é preservado.
- Conclusão assíncrona usa o rascunho atual e confere seleção/versão/conta.
- `/criacao/aprovar` aceita V1/V2. O banco deriva o manifesto financeiro do
  snapshot, preservando ABO/CBO, DAILY/LIFETIME, valores, datas e lances.
  Lifetime nunca é apresentado como orçamento diário.
- Executor confere cada anúncio contra seu conjunto resolvido, orçamento em
  ambos os níveis, promoted_object, janela de atribuição, datas e público.
  Continua criando exclusivamente PAUSED, com ledger e reconciliação.

## Evidências

- Integrador: 148 testes backend passaram em seis arquivos (readback,
  paused_birth, approval_budget, criacao_pausada_rotas, revisao_de_midia,
  registro_de_midia).
- Frontend: 39 testes passaram em quatro arquivos (materializar-pack,
  preparar-pack, vinculos, rascunho-v2), incluindo segundo clique obrigatório,
  demo sem chamadas, detector ausente e reuso sem aprovação duplicada.
- Executor de schema: cinco testes PostgreSQL descartável passaram:
  apply/reapply, quatro combinações de orçamento, RPC roundtrip, 31 passos,
  `adset:key`, fencing, snapshot imutável e recusa de authenticated.
- TypeScript do projeto app: 76 erros globais preexistentes; nenhum nos arquivos
  deste sprint na verificação. Build Vite passou.
- Suíte ampliada de componentes Meta: 131 passaram / 1 falhou. O teste
  `meta-sem-formula-legada` exige o rótulo de retorno dentro da página que
  delega a renderização a `MetaCampaignReadView`. Essa delegação já está no
  HEAD, os dois arquivos não foram alterados neste sprint e o rótulo existe
  no componente filho. Não foi mascarado como suíte global verde.
- Smoke HTTP local: frontend 8080 = 200; capacidades do backend 8010 = 401 sem
  sessão. Isso não é QA visual autenticado nem validação de criação real.

## Gemini e revisão

Consultas por API ao modelo exato `gemini-3.8-flash`, `thinkingLevel=MEDIUM`,
`google_search` habilitado. Metadados: lifecycle 8 pesquisas/40 grounding chunks;
optimization 17 pesquisas/41 chunks; ambas terminaram STOP.
Somente perguntas públicas sobre documentação Meta foram enviadas. Código
privado, imagens de clientes e credenciais não foram enviados ao revisor.
As respostas são insumos, não autoridade: números de subcódigos e escalas de
ROAS ambíguas não foram incorporados. Revisão local independente encontrou
aprovação repetida, callback obsoleto e placeholder inicial; os três corrigidos.

## Migration preparada, não aplicada oficialmente

Arquivo: `supabase/migrations/20260908234824_meta_v2_approval_budget_manifest.sql`

SHA256: `ec81aaf6e3aab4476973d0146593f389a293a2d8653a11bd6d2b97e7f6c33f0a`.

Somente destino operacional permitido: `https://database.agenciavolc.com.br`.
Antes de aplicar: conferir catálogo/dependências, revisar o delta e confirmar
autorização do arquivo exato. Depois: reler funções, constraints e grants,
conferir Python×SQL e prova transacional sem resíduos. Não fazer rollback que
torne aprovações V2 existentes irrecuperáveis.

## Pendências reais

1. **Inspeção de imagem não configurada:** não há detector registrado de
   `texto_na_imagem` nem `marca_visual`. Tesseract tampouco está instalado.
   Aprovação humana não deve se passar por inspeção automatizada. Configurar
   adaptador real e provar fotos/textos/marcas antes de habilitar upload.
2. **Migration V2 oficial pendente:** ausência é reportada como
   `META_CREATE_SCHEMA_REQUIRED`; teste descartável não prova banco oficial.
3. **Persistência parcial do rascunho:** seleção pack/conjunto é durável;
   anúncios montados e edições de copy ainda vivem no estado React. Recarregar
   perde a montagem; a aprovação final é o snapshot durável do plano. Não
   declarar autosave completo. Registro de mídia usa ledger idempotente por
   conta/hash, separado desse estado local.
4. **Canário pendente:** nenhuma nova geração paga, upload, validate_only ou
   criação Meta foi executada neste sprint. Precisamos de conta, Page, peças,
   plano/hash, orçamento e confirmação nominal do nascimento PAUSED.
5. **QA autenticado pendente:** não houve inspeção visual em browser nesta
   janela. Testes DOM e build não substituem o teste do operador.
6. Gestão real de pausar/duplicar, vídeo, Flexible e transferência de dark post
   não foram completadas por este sprint. Pack não transfere comentários ou
   curtidas de post existente.

Roadmap: P11-T02/P11-T05 continuam partial. Nós: cap_meta_ads e
cap_bancada_criativa. Não promover a produção sem as provas acima.
