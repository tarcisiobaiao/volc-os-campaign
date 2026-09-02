# Checkpoint de autorização — persistir a espinha orgânica no Supabase oficial

**Missão:** `hermes-asset-vault-organic-access-v1`
**Branch:** `sprint/hermes-asset-vault-organic-access-v1` · **base:** `c8ca862`
**Data:** 02/09/2026
**Estado:** **nada foi executado.** Este documento pede UMA autorização; ele não
é o registro de uma execução.

---

## Resultado em uma frase

O código que faltava para a espinha `1Password → referência → Cofre → ativo →
perfil AdsPower → broker → página → prontidão` existe e está local; o que falta
para ela sair do papel são **dados reais que ninguém digitou ainda** e **uma
autorização** para escrever no Supabase oficial. Este pedido cobre as duas
coisas — e nenhuma delas publica nada.

---

## ⚠️ O bloqueio que vem ANTES da autorização

**Não existe um único dado real da Página.** Nem ID, nem URL, nem Business
Portfolio, nem o nome verdadeiro. A única evidência continua sendo a declaração
do dono de 26/08/2026, e a única linha do repositório que fala dela
(`src/features/asset-vault/fixtures.ts:11-44`) traz `external: {}`.

Esta missão **procurou** e não encontrou fonte autorizada de leitura: não há
credencial Meta configurada nesta máquina, não há AdsPower instalado, não há
1Password (nem app, nem CLI `op`, nem MCP) — e nenhum deles poderia ser aberto
sem sair do envelope autorizado.

Por isso, **autorizar a escrita hoje não a torna executável.** A ordem é:

1. o operador preenche a ficha (lista mínima em [`CAMPOS-QUE-FALTAM.md`](CAMPOS-QUE-FALTAM.md));
2. esta autorização é concedida;
3. os payloads são gerados pelo script existente e aplicados;
4. o readback prova o que entrou.

Autorizar antes do passo 1 é legítimo — só não desbloqueia nada sozinho.

---

## 1. Página selecionada (sanitizada)

| Campo | Valor | Procedência |
|---|---|---|
| `ativo_id` | `asset:facebook-page:monetized-acquired` | constante do onboarding (`scripts/onboarding_pagina_facebook.py:214`) |
| `kind` / `cluster` | `facebook_page` / `social_presence` | catálogo v13_01 |
| `plataforma` | `Meta` | constante do onboarding |
| `display_id` | `•••-•••-NNNN` (4 últimos dígitos) | **a preencher** — o ID inteiro nunca entra em payload nenhum |
| `nome` | **a preencher** | a fixture traz só o rótulo provisório "Página monetizada adquirida" |
| `url_publica` | **opcional, a preencher** | forma `profile.php?id=<número>` é recusada: carrega o ID inteiro |
| `localizacao_rotulo` | `Business Portfolio Meta · <nome do portfólio>` | **a preencher** |
| `dono_nome` / `dono_custodia` | **a preencher** / `declared` \| `verified` | o Cofre não aceita ativo sem dono nomeado |

**Nada acima foi inventado.** Os campos marcados "a preencher" estão em
`PREENCHER` no modelo versionado, e o script recusa a ficha inteira enquanto
sobrar um — um payload com `"nome": "PREENCHER"` passa em toda CHECK de
comprimento do banco e cria um ativo real chamado PREENCHER.

## 2. Perfil AdsPower (sanitizado)

| Campo | Valor | Procedência |
|---|---|---|
| `ativo_id` | `asset:browser-profile:<slug>` | slug escolhido pelo operador |
| `kind` / `cluster` | `browser_profile` / `automation` | catálogo v13_01 |
| `display_id` | o `user_id` do cliente AdsPower, **inteiro** | intencional: P03-T07 exige ID visível, e o número é inútil sem a chave da Local API — que nunca entra no Cofre |
| `localizacao_rotulo` | `Proxy · <rótulo não sensível>` | nunca host, porta, usuário ou senha |

**Bloco opcional.** Se não houver perfil dedicado, `perfil_adspower` e
`credencial_perfil` viram `null`, e o onboarding emite **quatro** operações em
vez de seis — sem inventar perfil nenhum.

## 3. Provider, tipo de referência e hash

| | |
|---|---|
| Provider | `1password` |
| Forma aceita | `op://…` — forma 1Password com segmentos mascarados, espaços em `%20`, **sem query string** |
| Por que sem query string | `?attribute=otp` aponta para o TOTP, e segundo fator está fora do Cofre **inclusive por referência** |
| Nomes lógicos previstos | `FACEBOOK_PAGE_ACESSO` (ou equivalente) e `ADSPOWER_API_KEY` |
| Hash da referência | **não calculável hoje** — não existe referência real |

Quando existir, o digest sai por `broker.dominio.forma_da_referencia`:
`sha256(localizador)[:16]`, mais a FORMA (esquema, nº de segmentos, presença de
seção). Cofre, item e campo **não** entram no recibo. Digest de *localizador*
não é digest de segredo: ele correlaciona execuções e não abre caminho para
adivinhar valor nenhum — é a mesma disciplina de `tools/onepassword-smoke`.

## 4. As RPCs exatas, na ordem de dependência

Todas são `POST /rest/v1/rpc/<função>` no Supabase oficial
(`https://database.agenciavolc.com.br`), executadas pelo papel `service_role`,
que é o único com `EXECUTE` nelas.

| # | Função governada | O que cria | Chave de idempotência |
|---|---|---|---|
| 1 | `public.cofre_cadastrar_ativo(jsonb, text, uuid, text, text)` | a Página | derivada do payload |
| 2 | `public.cofre_cadastrar_ativo(...)` | o perfil AdsPower *(só se houver)* | derivada do payload |
| 3 | `public.cofre_relacionar(jsonb, text, uuid, text)` | `authenticates_through` da Página → perfil | derivada do payload |
| 4 | `public.cofre_referenciar_credencial(jsonb, text, uuid, text)` | referência de acesso da Página | derivada do payload |
| 5 | `public.cofre_referenciar_credencial(...)` | referência de acesso do perfil *(só se houver)* | derivada do payload |
| 6 | `public.cofre_registrar_verificacao(jsonb, text, uuid, text)` | o primeiro recibo de prova | derivada do payload |

**Não existe caminho de escrita direta em tabela**, e não por convenção: a
v13_01 revoga `ALL` de `service_role` nas nove tabelas `cofre_*`. Um `POST
/rest/v1/cofre_ativo` responde 403 — e essa é a intenção.

Gerar os payloads (não faz rede, não escreve no banco, não fala com a Meta nem
com o AdsPower):

```bash
python3 scripts/onboarding_pagina_facebook.py --ficha ~/ficha-pagina.json          # JSON
python3 scripts/onboarding_pagina_facebook.py --ficha ~/ficha-pagina.json --sql    # SELECT public.cofre_*(...)
```

## 5. Payloads sem segredo — a forma

`localizador` é o **único** campo do sistema inteiro que aceita uma secret
reference, e ele entra por **uma** porta (`cofre_referenciar_credencial`) e não
sai por nenhuma: nenhuma função de leitura o projeta, nem para `service_role`.

```jsonc
// 1 — ativo (o mesmo shape para a Página e para o perfil)
{ "ativo_id": "...", "kind": "...", "cluster": "...", "nome": "...",
  "plataforma": "...", "estado": "...", "criticidade": "...", "resumo": "...",
  "dono_nome": "...", "dono_custodia": "...", "display_id": "•••-•••-NNNN",
  "localizacao_rotulo": "Business Portfolio Meta · ...",
  "capacidades": ["..."], "tags": ["..."], "proxima_acao": "..." }

// 3 — relação
{ "origem_id": "asset:facebook-page:monetized-acquired",
  "tipo": "authenticates_through",
  "destino_id": "asset:browser-profile:<slug>",
  "destino_rotulo": "...", "estado": "declared" }

// 4/5 — referência de credencial  ← o ÚNICO payload que carrega um op://
{ "ativo_id": "...", "provider": "1password", "nome_logico": "FACEBOOK_PAGE_ACESSO",
  "localizador": "op://…", "finalidade": "...",
  "owner_nome": "...", "estado": "referenced", "valido_ate": null }

// 6 — verificação
{ "ativo_id": "...", "alvo": "ativo", "resultado": "unverified|partial|verified|...",
  "metodo": "...", "procedencia": "owner_declaration|live_observation|...",
  "evidencia": "...", "observado_em": "2026-09-02T14:35:00-03:00" }
```

Nenhum outro payload pode conter `localizador`: a varredura de chave sensível
roda no documento inteiro, e `localizador` está na lista de chaves proibidas
justamente para não poder viajar dentro de outro documento.

## 6. Chave de idempotência

Derivada do **conteúdo** do ato (`chave_de_idempotencia(sufixo, payload)` no
onboarding), nunca sorteada e nunca do relógio. Semântica do banco: mesma chave
+ mesma entrada devolve o recibo (`idempotente: true`, HTTP 200); mesma chave +
entrada diferente **falha**. Um retry que gera chave nova publica duas vezes.

## 7. Linhas que serão criadas

| Tabela | Linhas | Observação |
|---|---|---|
| `cofre_ativo` | 1 ou 2 | Página, e o perfil quando houver |
| `cofre_relacao` | 0 ou 1 | só quando houver perfil |
| `cofre_credencial_referencia` | 1 ou 2 | provider, nome lógico, localizador, owner, finalidade |
| `cofre_verificacao` | 1 | o primeiro recibo de prova |
| `cofre_revisao` / trilha | 1 por operação | append-only, com autor e motivo |

## 8. Readback esperado

Somente leitura, pelas RPCs governadas:

| Chamada | Deve responder |
|---|---|
| `cofre_listar_ativos(null,…)` | a Página em `social_presence`; o perfil em `automation` |
| `cofre_detalhar_ativo('asset:facebook-page:monetized-acquired')` | identidade, dono, `display_id` mascarado, relação `authenticates_through`, **zero** `localizador` |
| `cofre_postura_credencial(<ativo>)` | provider, nome lógico, finalidade, estado, frescor — e **nenhum** endereço |
| `GET /api/cofre/ativos/{id}/handoff` | `pronto_para_handoff` e `bloqueios` coerentes |
| `GET /api/cofre/ativos/{id}/prontidao` | as oito perguntas + bloqueios; `perfil_disponivel` = `desconhecido` (esta API não sonda) |

**Critério de recusa:** se `op://` aparecer em QUALQUER resposta de leitura, a
persistência é revertida e o defeito é tratado antes de qualquer nova escrita.

## 9. Rollback lógico

Não existe `DELETE` concedido a ninguém em nenhuma tabela `cofre_*`. Desfazer é
**marcar**, e a trilha permanece:

| Para desfazer | Chamada | Efeito |
|---|---|---|
| a Página / o perfil | `public.cofre_aposentar_ativo(ativo_id, motivo, chave, autor…)` | `aposentado_em` + motivo; sai das listagens padrão |
| a relação | `public.cofre_desfazer_relacao(relacao_id, motivo, chave, autor…)` | `desfeito_em` + motivo |
| a referência | `cofre_referenciar_credencial` com `estado: "retired"` | a referência deixa de ser a corrente |
| a verificação | — | **append-only por projeto**; um recibo errado é corrigido por um recibo novo, não apagado |

O rollback de SCHEMA (`supabase/migrations/v13_99_cofre_de_ativos_rollback.sql`)
**não** faz parte deste pedido: v13_01 e v13_02 já estão aplicadas e em uso.

## 10. Operações AdsPower planejadas

Somente leitura, e somente pelo broker desta missão
(`backend/app/asset_vault/broker/`), em loopback, com Bearer injetado por
`op run`:

| Ação | Método e caminho | Muta? |
|---|---|---|
| `status` | `GET /status` | não |
| `inventario_perfis` | `GET /api/v1/user/list` | não |
| `inventario_grupos` | `GET /api/v1/group/list` | não |
| `estado_do_perfil` | `GET /api/v1/browser/active` | não |

**Recusadas por nome, com estado `blocked/exige_checkpoint`:** `abrir_perfil`
(`browser/start`), `fechar_perfil`, `criar_perfil`, `atualizar_perfil`,
`apagar_perfil`, `criar_grupo`. Abrir navegador exige um **segundo** checkpoint,
que este documento **não** pede.

⚠️ **Procedência dos caminhos:** documentação pública da Local API citada no ADR
de 28/08/2026. Eles **não** foram exercitados contra um cliente AdsPower real —
não há AdsPower nesta máquina. Se a versão do cliente mudar um caminho, a falha
é um 404 sanitizado, e não um efeito inesperado: toda ação publicada é
não-mutante por construção, e o transporte recusa qualquer ação com `muta=True`
mesmo que ela apareça no catálogo.

---

## O que está sendo pedido

**Uma** autorização, cobrindo quatro atos:

1. **persistir** Página, perfil AdsPower e referências de credencial no Supabase
   oficial, pelas seis RPCs governadas acima;
2. **relacionar** os ativos (`authenticates_through`);
3. **resolver efemeramente** a referência `op://` — apenas em memória, dentro do
   processo do broker, sob `op run`, no host isolado;
4. **consultar o AdsPower em somente leitura**, pelas quatro ações acima.

## O que NÃO está sendo pedido, e não acontecerá

- ❌ nenhuma publicação, agendamento, rascunho ou envio de mídia;
- ❌ nenhuma alteração de Página, administrador ou monetização;
- ❌ nenhuma abertura de perfil ou de navegador AdsPower;
- ❌ nenhuma migration nova, nenhum deploy, nenhum merge;
- ❌ nenhum valor de segredo lido, medido, hasheado ou derivado;
- ❌ nenhuma escrita direta em tabela (o banco a recusa de qualquer forma).

**Confirmação explícita:** este checkpoint **não** publica conteúdo. A
publicação continua sendo um ato separado, com aprovação própria, e depende de
`P12-T09` — que não existe. É por isso que `prontidao` responde
`peca_roteavel: nao` para toda página do Cofre hoje.
