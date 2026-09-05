# Gates — meta-governed-create-paused-path-v1

Rodados na worktree `/private/tmp/volc-os-operacao-80-20`, branch
`execution/volc-os-operacao-80-20`, base `37258f1c`.

**Nenhum gate falou com a Meta, com o Supabase oficial ou com a rede de
produção.** Todo HTTP dos testes é um transporte falso injetado no lugar de
`httpx.AsyncClient`; todo Postgres é um cluster que nasce e morre dentro do
script.

---

## Resultado

| # | Gate | Comando | Resultado |
|---|------|---------|-----------|
| 1 | Testes focais da criação | `PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests/test_meta_criacao_pausada_rotas.py -q -p no:randomly` | **40 passaram** |
| 2 | Suíte Meta do backend | `PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests -k "meta or Meta" -q -p no:randomly` | **223 passaram** (era 183; **+40**) |
| 3 | Suíte backend inteira | `./scripts/gates-backend.sh` | 3888 passaram, 88 skipped, **as mesmas 5 falhas pré-existentes**, ver Ressalvas |
| 4 | Testes de UI Meta | `npx vitest run src/pages/trafego/__tests__/meta-criacao-bancada.test.tsx src/pages/trafego/__tests__/meta-criacao-nascimento.test.tsx src/pages/trafego/__tests__/meta-operacao-demo.test.tsx src/components/trafego/meta/__tests__/meta-read-preview.test.tsx src/pages/__tests__/meta-campaign-insights.test.tsx` | **34 passaram** (era 21; **+13**) |
| 5 | TypeScript | `npx tsc -p tsconfig.app.json --noEmit` | **77 erros — os mesmos 77 do HEAD**; **0 nos cinco arquivos tocados**, medido arquivo a arquivo |
| 6 | Build Vite | `npm run build` | ✓ built in 6.78s |
| 7 | Ciclo da migration candidata | `bash scripts/provar-ciclo-meta-create-paused.sh` | ✓ aplicar → **usar** → reverter → reaplicar, em PostgreSQL 15 descartável |
| 8 | Whitespace | `git diff --check` | limpo |
| 9 | Scanner de segredos | `python3 scripts/verificar_segredos.py` | nenhum padrão forte encontrado |
| 10 | Frescor do grafo | `python3 scripts/atualizar_grafo_volc_os.py` e `--check` | reconstruído e verificado ao final desta lane |

---

## O que o gate 7 passou a provar

O ciclo já cobria aplicar → usar → reverter → reaplicar. Esta missão acrescentou,
no mesmo script:

- **11 RPCs com `GRANT EXECUTE` ao `service_role`**, contadas. Uma função nova sem
  o par `REVOKE`/`GRANT` só falharia em produção, na primeira chamada — o pior
  lugar para descobrir.
- **O recibo de validação como condição da aprovação, campo a campo**: recibo
  inexistente, plano divergente, conta divergente, ator divergente, manifesto
  divergente, confirmação PAUSED ausente, expiração de duas horas, recibo com
  objeto criado, cobertura desconhecida, e reuso do mesmo recibo. Dez recusas,
  cada uma pelo código próprio.
- **Reconciliação**: `fail_step` continua recusando um passo AMBÍGUO (o que
  impede fechar um recibo sem prova); `resolve_absent` é o único caminho de
  AMBIGUOUS para FALHO e recusa um passo já fechado; `close_step` fecha
  AMBIGUOUS como CRIADO quando a presença foi provada.
- **Concorrência real** entre duas conexões, agora com **um recibo de validação
  por sessão** — senão o que barraria a segunda seria o `UNIQUE(validation_id)`
  e a prova do lock consultivo deixaria de existir.
- **Autorização**: papel de navegador não aprova **e não grava recibo de
  validação**.

---

## A rodada corretiva

Codex (`codex-cli 0.151.0`, reasoning **high**, sandbox **read-only**) revisou
`37258f1c..1ad7b8a` e devolveu **oito achados**, com veredito REPROVADO. Cada um
foi verificado no código antes de qualquer ação:

- **sete eram reais**, incluindo dois caminhos concretos de duplicação de
  campanha, e foram fechados com teste próprio para o cenário;
- **um foi rejeitado** — o revisor apontou que o `AdCreative` nasce `ACTIVE`, o
  que contraria a receita aprovada, que declara literalmente "Creative não é
  veiculável";
- **de um deles o achado foi aceito e o remédio recusado**: fechar o recibo
  depois do read-back perderia o id numa queda entre o `POST` e o `INSERT`. A
  ordem ficou; o que entrou foi o registro durável da divergência.

A adjudicação completa, com o relatório na íntegra, está em
`REVISAO-ADVERSARIAL-CODEX.md`. Os gates desta página foram rodados **depois**
da rodada corretiva.

O que a correção acrescentou aos gates:

| Prova nova | Onde |
|---|---|
| a mesma campanha não nasce por duas aprovações | `provar-ciclo`, bloco `$duplicacao$` |
| passo idêntico em voo/ambíguo bloqueia outra aprovação | idem |
| ausência não fecha com o despachante possivelmente em voo | `provar-ciclo`, bloco `$tempo$` |
| janela de reconciliação abaixo do piso é recusada | idem |
| divergência de read-back fica gravada e aparece no recibo | idem, e no backend |
| 5xx da Meta depois do POST responde 502, não 422 | backend |
| objeto anterior ao despacho não é adotado | backend |
| criativo nunca é fechado por leitura | backend |
| recibo inventado/de outra pessoa para antes do Keychain | backend |

## As duas mutações que mediram os testes

Um teste que passa não prova que morde. Duas mutações foram aplicadas
deliberadamente e revertidas:

| Mutação | Efeito esperado | Efeito medido |
|---|---|---|
| Ambiguidade tratada como recusa da Meta (502 → 422) | testes de ambiguidade e reconciliação ficam vermelhos | **6 testes falharam** |
| Read-back passa a aceitar `ACTIVE` em `configured_status` | o teste do recibo verde falso fica vermelho | **passou** ⚠️ |

A segunda mutação **não foi detectada na primeira tentativa**, e a causa é
instrutiva: o cenário de divergência marcava `configured_status` **e**
`effective_status` como `ACTIVE`, então o teste ficava vermelho pela guarda
errada, e a asserção `"status" in mensagem` casava com `"effective_status"`.

O cenário foi estreitado para divergir **só** `configured_status`, e a asserção
passou a exigir `"no campo status"` **e** negar `"no campo effective_status"`.
Com isso a mutação passou a ser detectada. O mesmo método confirmou a trava
síncrona de duplo clique: removido o `if (emVoo.current) return`, o teste
`bloqueia o duplo clique dentro do mesmo tique do evento` fica vermelho.

---

## Ressalvas honestas

### As 5 falhas do gate 3 são pré-existentes

Medidas, não presumidas.

| Teste | Diagnóstico |
|---|---|
| `test_meta_real_read_model.py::test_sql_e_rollback_de_insights_sao_coerentes` | **passa da raiz do repositório.** `gates-backend.sh` faz `cd backend`, e o teste usa caminho relativo. Defeito do modo de invocação, já registrado no `GATES.md` da lane anterior. |
| `test_google_inteligencia_persistente.py::test_a_consulta_de_conta_nao_precisa_de_migration` | idem: passa da raiz. |
| `test_canario_pedido_aprovado.py::test_4_identidade_do_pedido_bate_com_o_dossie` | **falha idêntica em `37258f1c`**, medido numa cópia limpa via `git archive`. |
| `test_canario_pedido_aprovado.py::test_6b_carimbo_de_outra_execucao_invalida_o_selo` | idem. |
| `test_trafego.py::test_provar_sem_copy_reprova_e_diz_por_que` | **falha idêntica em `37258f1c`** com o mesmo `.env`: 409 `N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`. Nada a ver com Meta. |

Nenhuma delas toca o caminho `create_paused`. Zero falhas introduzidas.

### O ratchet do TypeScript está vermelho antes desta missão

`scripts/gate_tsc_ratchet.py` guarda baseline **76**; HEAD produz **77**. Medido
na lane anterior e inalterado por esta. O baseline **não foi mexido**: alterá-lo
esconderia a dívida em vez de declará-la. Os cinco arquivos tocados produzem
**zero** erros, verificado arquivo a arquivo.

### `npm test` inteiro continua com vermelhos herdados

16 testes em 6 arquivos, todos em `src/components/trafego/inventario/**` e
`src/features/work-road/**` — nenhum tocado por esta missão, e todos já
registrados como herdados na lane anterior.

### Nenhuma chamada real à Meta, em nenhum gate

E, diferente da lane anterior, **nenhuma fora deles também**: esta missão não
tinha autorização para `validate_only` real nem para criação, e não fez nenhum
dos dois.

### Sem inspeção visual no navegador

A extensão do Chrome não foi conectada. A tela é exercitada por 13 testes novos
em jsdom que renderizam a página inteira. Ninguém olhou os pixels.

### Um teste de UI foi corrigido, não adaptado

`meta-operacao-demo.test.tsx` afirmava a copy *"criar de verdade é outro ato, e
ele não existe nesta rota"*. A frase deixou de ser verdadeira quando a rota
nasceu — o que fecha o ato agora é a autorização do servidor, não a ausência de
rota. A asserção passou a exigir *"Criação PAUSED ainda fechada neste servidor"*
mais *"Ativar continua sendo outro ato"*, e o teste continua provando o padrão
fechado (sem servidor que responda `capacidades`, a bancada fica fechada).

Pelo mesmo motivo, `test_router_nao_monta_create_approve_ou_enable` foi
**renomeado e reescrito**: ele varria só `trafego_meta_validacao.router` e teria
continuado verde afirmando algo falso. A varredura do app inteiro vive agora em
`test_nenhuma_rota_de_ativacao_existe_no_app_inteiro`.
