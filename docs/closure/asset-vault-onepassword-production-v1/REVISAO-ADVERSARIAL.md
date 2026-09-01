# Revisão adversarial e de contrato — o que foi refutado, e o que fiz

**Data:** 01/09/2026 · **Base:** `36bec04` · **Revisado em:** `4c213de`–`664272f`

## Quem revisou, e o que aconteceu com quem não pôde

| Revisor | Papel | Estado |
|---|---|---|
| **Codex** (`codex-cli 0.151.0`) | adversarial focal — tentar REFUTAR oito afirmações de segurança | executou; 7 de 8 refutadas com reprodução |
| **Gemini** (`0.57.0`) | contrato, completude e documentação factual | **indisponível**: `Please set an Auth method … GEMINI_API_KEY` |
| **Claude fresco** (subagente sem contexto) | substituto do Gemini | executou; rodou todos os gates e conferiu documento contra código |

A indisponibilidade do Gemini está registrada aqui em vez de silenciada: o CLI
existe (`/Users/mac/.npm-global/bin/gemini`) e não tem credencial configurada
nesta máquina. A missão previa exatamente isso — indisponibilidade de revisor
não bloqueia implementação comprovada, e é substituída por revisão Claude
fresca, que foi o que aconteceu.

## As oito afirmações que o Codex atacou

| # | Afirmação | Veredito | O que fiz |
|---|---|---|---|
| A1 | Nenhum caminho da API devolve o `localizador` | **REFUTADA** (ALTO) | corrigido |
| A2 | Uma senha bruta não cabe na coluna `localizador` | **REFUTADA** (ALTO) | afirmação corrigida na documentação |
| A3 | A recusa nunca ecoa o valor recusado | **REFUTADA** (CRÍTICO) | corrigido (parte 2); parte 1 documentada como limite |
| A4 | Escrita só por função governada | **NÃO REFUTADA** | — |
| A5 | Idempotência: chave repetida com outra entrada falha | **REFUTADA** (ALTO) | corrigido (duas causas) |
| A6 | Falha de banco não vira lista vazia | **REFUTADA** (MÉDIO) | corrigido |
| A7 | Ausência é NULL, não-verificado não é verificado | **REFUTADA** (ALTO) | corrigido |
| A8 | As três fontes concordam | **REFUTADA** (MÉDIO) | corrigido |

### A1 — a proteção cobria os campos errados

**Reprodução do revisor:** cadastrar um ativo com
`"plataforma": "op://Vault/Item/password"`. A referência voltava por
`cofre_listar_ativos`, `cofre_detalhar_ativo`, `cofre_postura_credencial` **e**
pelo snapshot da trilha.

**Causa.** `cofre_ativo_prosa_limpa` cobria quatro colunas — `resumo`,
`proxima_acao`, `display_id`, `localizacao_rotulo` — e deixava `nome`,
`plataforma`, `dono_nome`, `projeto`, `vertical` de fora; e `owner_nome` na
tabela de referências. Eu tinha protegido os campos que **imaginei** que alguém
usaria para prosa, e não os que o schema **publica**. A pergunta certa não era
"onde alguém escreveria um token?" e sim "qual coluna sai numa resposta?".

**Correção.** `v13_01` seção 11: a CHECK cobre todas as colunas de texto de
`cofre_ativo`, `cofre_credencial_referencia`, `cofre_relacao`,
`cofre_verificacao`, `cofre_ativo_revisao` e `cofre_engine_perfil`. O mesmo em
`rotas.py`, campo a campo.

**Prova.** Quatro provas no ciclo SQL (`op://` em `plataforma`, `nome`,
`dono_nome`, `owner_nome`) e nove testes parametrizados em
`test_A1_referencia_op_nao_entra_por_NENHUM_campo_publicado`.

### A2 — a afirmação estava forte demais

**Reprodução:** `op://Vault/Item/password` passa nas cinco gramáticas — e pode
ser, literalmente, a senha que alguém escolheu.

O revisor está certo e o achado é sobre **linguagem**, não sobre código:
sintaxe não alcança semântica. A gramática prova que o texto **tem forma de
endereço**, não que **é** um endereço. Corrigi a afirmação na migration, no
contrato de produto e onde mais ela aparecia. O que a forma entrega continua
real e continua limitado: recusa o que não tem forma de referência — que é o
caso de praticamente toda senha, token e chave que existem por aí.

### A3 — a recusa vazava em dois lugares

1. **CHECK direto ainda ecoa.** `DETAIL: Failing row contains (…)` é
   comportamento do servidor e nenhuma constraint o evita. É por isso que o
   caminho governado valida **antes** do INSERT e o backend nunca repassa
   `details`. Documentado como limite explícito, não corrigido — não há
   correção possível nessa camada.
2. **A mensagem de conflito de idempotência ecoava a CHAVE.** A gramática da
   chave (`[A-Za-z0-9._:-]{8,120}`) aceita uma senha inteira, e o filtro do
   backend tratava qualquer frase com "chave de idempotencia" como segura.
   **Corrigido:** a mensagem não repete mais a chave — quem chamou já sabe qual
   mandou. O filtro agora só reconhece a frase nova. Prova no ciclo SQL e em
   `test_A3_a_frase_de_conflito_de_idempotencia_nao_carrega_mais_a_chave`.

### A5 — dois caminhos para duplicar efeito

1. **O hash ignorava `p_motivo`, `p_autor_sub` e `p_autor_email`.** A mesma
   chave com o mesmo payload e **outro autor** devolvia o recibo guardado como
   `idempotente: true`, e a trilha registrava só o primeiro autor. Corrigido:
   `cofre_entrada_hash` ganhou `p_extra`, e todas as sete chamadas passam autor
   e motivo.
2. **A janela de 60s da chave do frontend.** Com `Date.now()` em 59999 e 60000
   a mesma ação produzia duas chaves, e o mesmo payload entrava duas vezes.
   Era o caso **mais provável**, porque o retry humano acontece depois de alguns
   segundos. Corrigido: `chaveDoAto` é função pura do conteúdo, sem relógio.

### A6 — `[None]` virava `[]`

`_lista` terminava em `[i for i in bruto if isinstance(i, dict)]`, e a rota
respondia `200 {"engines": []}` sobre um banco que respondeu errado. É o mesmo
defeito que `_objeto` já evitava, escrito de novo uma função abaixo. Corrigido:
elemento estranho é indisponibilidade.

### A7 — append-only sem desempate não é ordem

Duas verificações com o mesmo `observado_em` saíam em ordem indefinida, e a tela
preenche o instante com precisão de **minuto**. Uma correção `unverified`
registrada depois de um `verified` no mesmo minuto podia continuar sendo
projetada como `verified` — a correção existia na trilha e não aparecia no card.
Corrigido: `ORDER BY observado_em DESC, verificacao_id DESC`.

### A8 — o contrato público recusava um fato válido do banco

`contract.ts` aceitava quatro estados de verificação; o schema e o backend
gravavam seis. `failed` e `blocked` não cabiam no retrato. Corrigido, e a
concordância virou teste que lê a migration.

## O que a revisão de contrato encontrou

Além da completude (A–G), ela encontrou **19 defeitos de documentação** — nove
deles números que envelheceram enquanto a branch andava ("75 provas" quando
eram 92, "47 testes" quando eram 67, um HEAD anterior).

Três consertos estruturais saíram daí:

1. **`scripts/medir-gates-cofre.sh`** — os números passam a ser gerados, não
   digitados. `GATES.md` é a fonte corrente.
2. **DEGRAU 2b no ciclo SQL** — a "prova ponta-a-ponta" dos engines tinha
   acontecido à mão, num cluster que já não existia. Agora o importador roda
   contra o schema recém-aplicado, dentro do harness.
3. **Tabela de mutantes do smoke** — passou a dizer que foi feita à mão e não é
   reproduzível, em vez de parecer prova corrente.

Também: um teste citado que não existia (`test_cofre_dominio.py`), "27 tipos"
numa migration que cria 28, seis referências de seção erradas no SQL, a
justificativa do piso PG15 que morreu junto com a view removida, e uma
"imprecisão" acusada que na verdade estava correta.

## Uma correção que a revisão fez em mim, e não no código

O pacote de fechamento acusava o commit `beeb9e7` de dizer "Doze rotas sob
/api/cofre" imprecisamente. A revisão mediu: `git show
beeb9e7:backend/app/asset_vault/rotas.py | grep -c '^@router'` = **12**. A
afirmação estava certa naquele commit; a décima terceira nasceu depois. Acusar
de erro uma afirmação verdadeira é o mesmo defeito de número desatualizado, com
o sinal trocado.
