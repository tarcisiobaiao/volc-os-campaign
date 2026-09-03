# Contratos — broker AdsPower e plano de controle de prova visual

**Data:** 02/09/2026 · **Branch:** `sprint/hermes-adspower-visual-proof-control-plane-v1`
**Base:** `origin/volc-os-v2 @ 382c5d4c67fc521d5e6739f8e76d1c36a96fdb53`

## Convenção de nomes

As **classes** usam os nomes canônicos da missão, em inglês
(`BrowserProfileReference`, `AdsPowerBrokerRequest`, …), para que o documento e
o código sejam greppáveis pelo mesmo termo. Os **campos** seguem o português do
resto do repositório (`ativo_id`, `chave_idempotencia`, `nome_logico`), porque é
com o Cofre que eles conversam e uma tradução no meio do fluxo é onde os erros
de mapeamento nascem.

Todos vivem em `backend/app/visual_proof/dominio.py`, que é `stdlib`-only.

---

## 1. `BrowserProfileReference`

O perfil como o VOLC o conhece.

| Campo | Tipo | Nota |
|---|---|---|
| `ativo_id` | `str` | ativo do Cofre, tipo `browser_profile` |
| `perfil_logico` | `str` | `^[A-Z][A-Z0-9_]{1,63}$` — ex.: `PERFIL_PILOTO_01` |
| `owner_sub` | `str` | dono; comparado com o dono do pedido |
| `provider` | `str` | um dos cinco de `cofre.PROVIDERS` |
| `credencial_nome_logico` | `str` | ex.: `ADSPOWER_API_KEY` |

**O que NÃO existe nesta classe, e por quê:**

- **`user_id`** — o identificador que a Local API aceita para abrir o perfil.
  Quem o tem e alcança a porta 50325 abre o navegador com a sessão já
  autenticada da página. Ele não é "segredo" no sentido de senha, e é
  exatamente por isso que costuma vazar: entra em log, em recibo, em issue. A
  tradução `PERFIL_PILOTO_01 → user_id` mora só na allowlist do broker, no host
  isolado (`PerfilAutorizado.user_id`).
- **`localizador`** — a classe nem aceita o argumento; passá-lo levanta
  `TypeError`. O broker resolve o endereço pela própria allowlist.

## 2. `AdsPowerBrokerRequest`

`pedido_id`, `chave_idempotencia`, `operacao`, `perfil`, `owner_sub`,
`ativo_id`, `timeout_s`, `url_alvo?`, `dominio_esperado?`, `viewport?`,
`timezone?`.

**Allowlist de operação** (`OPERACOES_DO_BROKER`) — quatro, e não existe
"executar comando":

    estado_do_perfil · abrir_perfil · capturar_superficie · fechar_perfil

`impressao()` é o SHA-256 do JSON canônico **sem `pedido_id`**: ele muda a cada
retry, e incluí-lo faria toda repetição parecer um pedido novo — o defeito que a
chave de idempotência existe para evitar.

## 3. `AdsPowerBrokerReceipt`

`recibo_id`, `pedido_id`, `chave_idempotencia`, `operacao`, `perfil_logico`,
`owner_sub`, `ativo_id`, `estado`, `motivo_codigo`, `motivo`, `iniciado_em`,
`concluido_em`, `duracao_ms`, `adspower_code?`, `url_final?`, `status_http?`,
`redirecionamentos[]`, `artefato?`, `console_resumo`, `rede_resumo`.

`estado ∈ {executado, recusado, falhou, replay}`.

`para_dicionario()` sanitiza: `motivo` passa por `sanitizar_texto`, `url_final`
e cada redirecionamento por `sanitizar_url_para_recibo` (mantém esquema, host e
caminho; **redige os valores da query, preserva as chaves** — `?token=` conta
uma história que `?` apaga).

## 4. `VisualProofJob`

Campos exigidos pela missão, todos presentes em `para_dicionario()`:

`job_id`, `owner_sub`, `ativo_id`, `perfil`, `url_esperada`, `url_final`,
`dominio_esperado`, `viewport`, `timezone`, `classe_de_agente`, `criado_em`,
`timeout_s`, `tentativas`, `chave_idempotencia`, `conteudo_sha256_esperado`,
`artefato`, `console_resumo`, `rede_resumo`, `redirecionamentos`, `checagens`,
`recibo_id`, `veredito`, `justificativas`, `revisao_humana`, `estado`,
`historico`.

**`classe_de_agente`, nunca `user_agent`.** `desktop-chromium` diz ao revisor o
que ele precisa para julgar o enquadramento; uma impressão digital de navegador
diria a um terceiro como reconhecer o perfil em outro lugar. Há teste que falha
se a string `fingerprint` aparecer na projeção.

## 5. `VisualProofArtifact`

`referencia` (`vpartifact://<perfil_logico>/<recibo_id>/captura.png`), `sha256`,
`bytes`, `mime`, `criado_em`.

**Os bytes nunca entram em JSON.** Um screenshot de 1366×768 passa de 300 KB;
em base64 dentro do recibo, do Roadmap ou do grafo, cada prova visual viraria um
arquivo que ninguém revisa, versiona ou apaga — e um deles já basta para
carregar dado pessoal de quem aparecer na tela. A referência também não é
caminho de disco: um caminho absoluto carrega o usuário do host (precedente do
`canonical_path` dos manifestos de engine, que trazia o e-mail do operador).

## 6. `VisualProofVerdict`

`resultado`, `justificativas[]`, `checagens[]`.

| Conjunto | Valores |
|---|---|
| `VEREDITOS_AUTOMATICOS` | `eligible_for_human_review`, `needs_correction`, `indeterminate` |
| `VEREDITOS_DO_JOB` | os três acima **+ `approved`** |

**`approved` está fora do conjunto automático, e a ausência é o contrato.**
`avaliar_captura` nunca o devolve; o único caminho é `VisualProofJob.aprovar()`
com revisor nomeado, e chamá-lo sem revisor levanta `TransicaoInvalida`.

## 7. Estados do job

    requested → authorized → running → captured → approved
                                     ↘ needs_correction
                                     ↘ indeterminate
    (qualquer não-terminal) → failed | cancelled | expired

Terminais: `approved`, `needs_correction`, `indeterminate`, `failed`,
`cancelled`, `expired` — **nada sai deles**. Um job aprovado que volta a
`running` é um recibo que deixou de valer sem ninguém revogá-lo.

`eligible_for_human_review` **não é estado do job**: ele para em `captured`,
esperando gente. Colapsar os dois faria a fila de revisão sumir da tela.

## 8. Rota nova — `GET /api/cofre/ativos/{ativo_id}/prontidao-visual`

ADMIN, sessão do Supabase. **Leitura composta**: não cria job, não chama o
broker, não abre navegador.

Devolve `pagina`, `referencia_de_credencial`, `perfil_de_navegador`, `broker`,
`qa_visual`, `pronto_para_receber_peca`, `pronto_para_publicar`,
`pronto_para_qa`, `bloqueios[]`, `proxima_acao`.

**As três prontidões não são uma.** `receber_peca` pergunta sobre o ativo
(existe, não aposentado); `publicar` exige referência verificada e perfil
relacionado; `qa` acrescenta o broker configurado. Um "pronto" único mandaria a
fábrica criativa produzir para uma página que ninguém consegue abrir.

**`qa_visual.estado` tem seis valores** — `nao_persistido`, `nao_executado`,
`em_execucao`, `indeterminado`, `corrigir`, `aprovado`. Hoje a API responde
`nao_persistido`, porque não existe tabela de `VisualProofJob`. Dizer
`nao_executado` seria mais otimista que a verdade.

## 9. Contrato HTTP do broker

Duas rotas, e só:

    POST /v1/operacoes   → AdsPowerBrokerReceipt (HTTP 200 mesmo em recusa)
    GET  /v1/saude       → retrato do preflight, sem segredo, sem `user_id`, sem localizador e sem caminho absoluto de artefatos

`Authorization: Bearer <token do broker>`, comparado com `hmac.compare_digest`.

**200 mesmo em recusa** porque o estado do RECIBO é a resposta: um 403 sem
corpo faria o chamador perder o motivo. O corpo de entrada é lido cru e validado
à mão, pelo mesmo motivo documentado em `asset_vault/rotas.py` — um validador
que ecoa o valor recusado publica, na resposta de erro, exatamente o que a
recusa existia para impedir.

`perfil.localizador` e `user_id` no corpo são **recusados com 400**: aceitá-los
transformaria o broker na porta do cofre.

## 10. Fronteira entre os dois domínios

`visual_proof` **não importa** `asset_vault` — provado por AST em
`test_visual_proof_fronteira_cofre.py`. As gramáticas duplicadas (nome lógico,
chave de idempotência) são provadas equivalentes sobre um corpus compartilhado,
no mesmo padrão com que `test_cofre_ativos.py` compara `dominio.py` com o SQL.

No sentido inverso, `asset_vault/rotas.py` importa **no topo** apenas
`LeitorDeProvaVisual` (porta) e `montar_prontidao` (função pura). Os adaptadores
concretos entram dentro das fábricas de dependência — o mesmo padrão que
`obter_casos` já usava para `SupabaseService`.
