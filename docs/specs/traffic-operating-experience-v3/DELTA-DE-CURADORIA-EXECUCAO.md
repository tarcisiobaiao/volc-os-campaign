# Delta factual para curadoria — execução da Bancada Guiada

**Branch:** `execution/volc-os-operacao-80-20` · **Base:** `0aa090e`
**Data:** 03/09/2026

> ⚠️ Este é um **delta proposto**, não uma reconciliação aplicada. Conforme o
> protocolo do `CLAUDE.md`, uma lane de execução não promove tarefa no
> `ROADMAP-VIVO.json` nem escreve em `curadoria-operacional.json`, e trabalho que
> só existe numa branch não pode marcar a fonte compartilhada como concluído. O
> integrador central decide, depois da inspeção humana em `localhost:8080`.

---

## 1. Capacidades entregues

| # | Capacidade | Evidência |
|---|---|---|
| C1 | A projeção do cockpit emite `bloqueado`, `bloqueios[]` e `lido_em` | `backend/app/trafego/projecao.py` · `src/types/trafego.ts` |
| C2 | Régua única de severidade, com `limitacao` barrando | `volc_ads/pautador_ponte.py` importa `SEVERIDADE_BARRA` de `campanha/conteudo.py` |
| C3 | Ausência viaja como `null` de ponta a ponta (CPC, volume, agregados, triagem) | `projecao.py`, `pautador_ponte.py`, `types/trafego.ts`, `__tests__/ausencia-nao-e-zero.test.tsx` |
| C4 | **O ato de aprovar o conjunto pago passa a existir** | `GET`/`POST /api/pautador/opportunities/{id}/conjunto-pago[/aprovar]` · `backend/tests/test_conjunto_pago_aprovacao.py` |
| C5 | Bancada Guiada de seis paradas com estado na URL | `src/pages/trafego/NovaCampanhaPage.tsx` · `bancada/**` |
| C6 | Rascunho do operador sobrevive ao F5 dentro da aba | `bancada/useRascunho.ts` |
| C7 | Recibo persistente na página, retornável por `#recibo` | `recibos/ReciboDaBancada.tsx` |
| C8 | Antessala multicanal única, lendo o veredito do servidor | `HubDeTrafegoPage.tsx` monta `PainelDeCanais` na aba `criar` |
| C9 | Motivo humano nasce vazio e trava de reentrância no `/subir` | `components/trafego/Lancamento.tsx` |

---

## 2. Defeitos fechados, com a medição que os nomeia

| Defeito | Onde estava | Consequência medida |
|---|---|---|
| **A0 — o conjunto pago nunca era aprovado** | `paid_eligibility.py:1166` sem chamador de produção; `funnel_factory.py:391` persiste sem `approved_set_sha256` | `portao_conjunto_pago.py:158` recusava, `/provar` e `/subir` devolviam 409 `CONJUNTO_PAGO_NAO_APROVADO`. **A campanha Search não nascia pelo caminho normal.** |
| Veredito calculado e descartado | `pautador_ponte.py:266-272` tinha as `@property`; `projecao.py:157` não as copiava | Cada tela refiltrava severidade no navegador. Duas réguas: o engine barrava só `bloqueio`, a tela barrava tudo que não fosse `informacao`/`atencao`. |
| `limitacao` significava o oposto nos dois lados | `PortaoDePolitica.tsx:159` dizia que a campanha sobe; `conteudo.py:56` a punha entre as que barram | FULLY_LIMITED deixou 57 anúncios sem veicular em 39 contas. |
| CPC ausente virava `R$ 0,00` | `projecao.py:45` — `float(getattr(c,"valor",0) or 0)` | Um clique não medido aparecia como de graça, no módulo cujo docstring diz "Nenhum CPC sai sem procedência". |
| Positivas iam no corpo do pedido | `NovaCampanhaPage.tsx:367-381,413` | `somente_negativas_do_corpo` recusa com `CRITERIO_POSITIVO_DO_CORPO_RECUSADO`. Escondido porque `criterios_do_cluster` roda antes e o 409 visível era outro. |
| Motivo humano pré-preenchido pela máquina | `Lancamento.tsx:99` | Passava folgado pelo gate de 10 caracteres; o recibo gravava a frase do robô. |
| Trava de duplo clique apenas emergente | `Lancamento.tsx:173-185` | `/subir` CRIA CAMPANHA; dois cliques no mesmo frame não tinham garantia de re-render entre eles. |
| Recibo morria ao fechar o modal | `Lancamento.tsx:93` + `NovaCampanhaPage.tsx:789` | Perdia `request_id`, `recibo_id`, `item_id` — o conjunto exato de que se precisa quando o desfecho é indeterminado. |
| Simetria falsa de canal | `jornada.ts:644` liberava por `sabe_criar`, sem consultar o canário | Display saía com botão primário "Começar campanha" enquanto o servidor recusa com `fora_da_janela_do_canario`. |
| Abas sublinhadas | `HubDeTrafegoPage.tsx:109-115,572` | `design.md` §Surfaces proíbe: era a terceira gramática de aba do produto. |

---

## 3. Lacunas que PERMANECEM abertas

1. **`strictNullChecks` está desligado** (`tsconfig.app.json` `"strict": false`).
   O contrato `number | null` tem valor documental e **zero enforcement do
   compilador**: `.toFixed()` sobre `null` compila limpo e explode em runtime.
   O único gate é `__tests__/ausencia-nao-e-zero.test.tsx`.
2. **Ausência-como-zero a montante, fora do escopo desta lane**, encontrada e
   não tocada: `agents/mining/merger.py:62-67,72,98,176`,
   `gold_extractor.py:30,105,120,157,160`, `orchestrator.py:369-370,431-432`.
3. **Baseline vermelho herdado:** `backend/tests/test_trafego.py::test_provar_sem_copy_reprova_e_diz_por_que`
   segue em 409 `N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`. Não é regressão: o
   cluster #4 da oportunidade 73 não tem `conjunto_pago` em funil nenhum. O
   conserto é minerar aquele card pelo motor Python.
4. **`volc_ads` não está no gate oficial** (`scripts/gates-backend.sh:151` roda
   só `tests/`): 743 testes do engine fora de qualquer gate automatizado.
5. **Race de escrita na aprovação:** `factory_output` é read-modify-write por
   requisição; duas aprovações concorrentes no mesmo cluster são
   last-writer-wins. `hash_conferido` cobre mudança da seleção, não concorrência.
6. **Nenhuma inspeção visual autenticada foi feita.** A extensão de browser não
   estava conectada nesta sessão. Todo juízo visual aqui é de código, não de
   pixel — vale "projetado para o contrato", nunca "conforme medido".
7. **`EstudioLigado`, `EstudioMulticanal` e `canal/jornada.ts`** deixaram de ser
   montados e **não foram apagados**: são candidatos com evidência, e dois testes
   de segurança varrem os arquivos. Removê-los é outro lote.

---

## 4. Estado sugerido (proposta, não aplicada)

| Tarefa/nó | Estado sugerido | Por quê |
|---|---|---|
| Aprovação do conjunto pago (A0) | `partial` | Rota existe e tem contraprovas com dublê; **não foi exercida contra o Supabase real**. |
| Verdade operacional da projeção | `partial` | Emitida e consumida; falta inspeção humana. |
| Bancada Guiada Search | `partial` | Fluxo completo em teste; falta operar com oportunidade real na tela. |
| Recibo persistente | `partial` | Implementado e coberto; reconciliação exige admin e não foi exercida. |
| Antessala multicanal | `partial` | Fonte única (servidor) e aba consolidada; CTA por canal depende do painel. |
| Ausência não é zero | `partial` | Ponta a ponta no caminho da Bancada; a montante (mining) segue aberto. |

**Nenhuma tarefa deve ir para `done` antes da inspeção do proprietário.**

---

## 5. Pente-fino de contrato multicanal — 04/09/2026

Delta proposto para **P04-T05**, **P04-T07** e **P04-T09**, sem promoção de
estado nesta branch:

- Display: a Bancada passou a editar o contrato efetivo do builder — nome da
  empresa, títulos, título longo, descrições, imagens por papel, vídeos por
  resource name, orçamento e tCPA opcional. A ponte HTTP agora transporta tCPA
  e remonta `assets_display` também no caminho `/subir`.
- Demand Gen: channel controls, `upgraded_targeting`, lista explícita de
  audiences, cobertura de mídia, copy e orçamento alimentam um
  `PedidoDeProvaDemandGen` discriminado. Intenções textuais, exclusões,
  carrossel, vídeo responsivo e produto seguem nomeados como não operados.
- Performance Max: asset group, brand guidelines, audience signals, search
  themes, negativas, cobertura por papel, bidding e alvo econômico ficaram
  editáveis no rascunho. Final URL expansion continua travada em OFF. Não há
  CTA de prova/criação porque a ponte HTTP e o executor PMax ainda não existem.
- Display não ganhou seletores falsos de audience/placement/brand safety: o
  próprio builder declara essas superfícies como não operadas e inventário
  aberto. A interface agora diz isso literalmente.
- Assets vivem apenas na montagem da página; metadados do formulário ficam no
  `sessionStorage`, mas bytes precisam ser reanexados após F5. Nenhuma peça ou
  id de conta é inventado.
- Nesta execução, a CTA multicanal apenas confere a completude e a montagem do
  contrato local. `validate_only` real permanece um ato externo separado, não
  autorizado por este pente-fino.
- Bloqueante descoberto e **não afrouxado**: `/provar` ainda atravessa o portão
  do conjunto pago antes de bifurcar por canal. Isso é coerente com Search,
  mas cria um requisito de keywords para Demand Gen que o próprio adaptador
  declara irrelevante. A correção precisa de autorização separada porque muda
  a alcançabilidade do `validate_only` real; até lá, o botão faz somente a
  conferência local e não promete que a prova remota está liberada.

Evidência mínima: build Vite verde; 43 testes focais frontend verdes; 104
testes dos builders Display/Demand Gen/multicanal verdes; 98 testes das pontes
HTTP e nascimento verdes; `git diff --check` limpo. Nenhuma chamada Google Ads,
Supabase, n8n ou WordPress ocorreu.
