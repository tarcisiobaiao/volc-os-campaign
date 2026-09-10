# Meta — varinha de copy e nomenclatura

Implementação no worktree operacional `execution/volc-os-operacao-80-20`.
Frontend8080/API8010 responderam200. Webgo e motor de imagens não alterados.

## Operação

1. Em Destino/Criativos/Revisão, abrir **Nomes organizados automaticamente**.
2. Informar assunto/site e conferir tags; selecionar conta, reservar e preencher.
   O rascunho é salvo antes de conferir a versão e consultar a Meta.
3. No anúncio flexível, **Sugerir copies com IA** abre briefing/quantidade.
   **Gerar sugestões** faz a chamada; acrescentar/substituir exige outra ação.
4. Aguardar o indicador de montagem salva e revisar antes de qualquer publicação.

`LP_R` significa rota WordPress `/r/`. O alias do site é editável, não inferimos
que um domínio equivale ao nome interno `TECHNEWS_BR`. Configurações realmente
presentes geram tags de mídia, plataforma, idade, orçamento e conversão. Gênero
ou Feed não são fabricados se ausentes do contrato. Nomes são editáveis e não
mudam IDs, UTMs, orçamento, targeting ou aprovação vigente do plano.

## Contratos

- POST `/api/trafego/meta/drafts/{draft_ref}/naming-reservation`:
  `expected_version`. Resposta: `campaign_number`, `account_ref`, `draft_ref`,
  `history_complete`, `history_count`. Reserva não incrementa versão do draft;
  o frontend salva a intenção `naming` pelo autosave existente com CAS.
- POST `/api/trafego/meta/drafts/{draft_ref}/copy-suggestions`:
  `expected_version`, `adset_key`, `count`1..5, `brief`até2000.
  Resposta: arrays `primary_text`, `headline`, `description`, `model`,
  `context_sha256`. Dono/conjunto/versão conferidos antes e depois do modelo.
- Sugestões não incluem tokens, contas, IDs, públicos ou imagens. URL sem
  userinfo/query/fragment é contexto textual, nunca acessada. Refino criativo
  respeita fatos fornecidos; sem promessa de CTR ou resultado comercial.

## Banco oficial

Migration `20260910081646_meta_campaign_naming_reservations.sql` aplicada em
`https://database.agenciavolc.com.br` após ensaio DDL×2 + fixtures revertidos.
SHA256: `66e2fdfdef371335180e8434ebfcb98383675c32ed74a71f837e334786f28145`.

Script `scripts/provar-meta-naming.mjs --apply` com fixtures novamente revertidas
confirmou: salvar/reler naming, preservar flexibleTexts/post, reset de aprovação,
bootstrap35→36, retry36, outro dono na mesma conta37, CAS, conta divergente,
história incompleta, naming inválido, archive sem reciclar e grants privados.
Nenhuma campanha ou rascunho real foi modificado. Nenhuma escrita Meta.

Rollback: primeiro coordenar o código e exportar reservas/intenção. Não apagar
reservas, não rebaixar a RPC enquanto rascunhos contiverem naming. A migration
amplia a definição instalada por transformação guardada, preservando seu corpo.

## Provas

- 103 testes backend (naming/copy/draft/flexible) passaram.
- 65 frontend (15 novos + contratos/editor/retomada) passaram.
- Build de produção aprovado; TypeScript sem erros nos arquivos da entrega,
  mas permanece dívida global preexistente. `git diff --check` limpo.
- Chrome:375/1440 claro/escuro, teclado e preview antes de aplicar, sem overflow
  nem erroJS. Módulos reais em fixture, sem sessão do operador. Capturas:
  `/private/tmp/meta-copy-naming-{375,1440}-{light,dark}.png`.
- Canário real: uma chamada textual com briefing sintético de estudo, respondeu
  `gemini-3.8-flash`, JSON validado (um texto, título e descrição). Sem dados da
  campanha e sem imagens. Isso prova integração, não desempenho da copy.
- Achado corrigido: proposta de conta anterior ficava aplicável; agora contexto
  inclui conta/Página/receita/conjunto, brief e quantidade no navegador. Também
  impede resposta atrasada de nomenclatura atingir a nova conta.

## Pendências honestas

P11-T18 `partial`: falta validar o fluxo autenticado na conta do operador com
seu histórico real, retomada ponta a ponta e aprovação de qualidade das copies.
Os 24 testes SQL descartáveis, incluindo duas conexões concorrentes, não
iniciaram por SHMMNI no macOS; não são apresentados como executados. O lock e
unicidade estão implementados, mas a prova oficial acima foi sequencial.
Não houve nova campanha Meta, rebranding ou alteração no Webgo.

Decisão: `docs/architecture/ADR-META-NOMENCLATURA-E-COPY.md`.
