# Handoff — plano de controle de publicação orgânica v1

**Data:** 02/09/2026
**Branch:** `sprint/organic-publication-control-plane-v1`
**Base:** `origin/volc-os-v2` = `382c5d4c67fc521d5e6739f8e76d1c36a96fdb53` (conferida)
**HEAD:** `ea43c0329f02d96b26515c34f139c2587da44bbe`
**Worktree:** `/private/tmp/volc-organic-publication-control-plane-v1`
**Árvore:** limpa · **Commits:** 4 locais, **nenhum push, nenhum merge**

**Veredito:** `LOCAL_OPERATIONAL_SPINE_ACCEPTED`.
**Não** `PRODUCTION_READY` — nenhuma página real, nenhuma instância Postiz e
nenhuma publicação real foram exercitadas.

---

## 1. O que foi entregue

| camada | onde | tamanho |
|---|---|---|
| schema governado | `supabase/migrations/v14_01_publicacao_organica.sql` + `v14_99` rollback | 2.068 + 160 linhas |
| ciclo de prova SQL | `scripts/provar-ciclo-v14_01.sh` | aplicar → operar → reverter → reaplicar |
| domínio, porta, aplicação, infra, rotas | `backend/app/publicacao_organica/` | 6 arquivos |
| adaptadores | `backend/app/publicacao_organica/adaptadores/{postiz,fake}.py` | real + hermético |
| testes de backend | `backend/tests/{apoio_,test_}publicacao_organica*` | **128** |
| tela operacional | `src/features/publicacao-organica/` | **112** testes |
| pacote Postiz | `deploy/postiz/` + `scripts/validar_postiz_pacote.py` | compose, runbook, licença, validador com autoteste |
| fechamento | `docs/closure/organic-publication-control-plane-v1/` | este pacote |

O fluxo que passou a existir:

```
peça aprovada (criativo_aprovacao)
  → destino orgânico (cofre_ativo + publicacao_organica_destino)
  → publicacao_organica_job  [snapshot IMUTÁVEL, chave derivada, digest no banco]
  → liberar → reivindicar (lease + fencing)
  → UMA chamada à porta, a partir do snapshot
  → concluir (transição atômica + recibo imutável)
  → reconciliar (observações sucessivas, append-only)
  → a tela, com o tom decidido no servidor
```

## 2. Antes e depois

| pergunta | antes (base) | depois |
|---|---|---|
| existe destino orgânico como entidade? | não — só `project_wordpress`, **um site por projeto** | sim, N canais, ligados ao Cofre |
| quem cria a intenção de publicar? | ninguém: `disparar` gerava **e** publicava (`publicar=True` literal) | `POST /jobs` cria a intenção; **nada sai** até `/despachar` |
| quem aprova? | o painel do WordPress, sem recibo | `criativo_aprovacao`, exigida por gatilho de banco |
| ownership | inexistente (`grep owner_id` vazio no pacote inteiro) | fail-closed no banco: peça, destino e job do mesmo dono |
| idempotência | `SELECT` antes de `INSERT`, sem constraint | chave derivada + digest no banco + UNIQUE + índice parcial |
| agendamento | inexistente (zero `publish_at`, zero IANA) | modo, horário local, timezone, instante UTC derivado no banco |
| concorrência | `os.kill(pid, 0)` | lease + fencing, com corrida real entre dois processos provada |
| recibo | jsonb **mutável**, sobrescrito em 3 caminhos | tabela append-only, com histórico de observações |
| "API respondeu" = "publicado"? | colapsados | 3 estados distintos; `reconciliado` exige referência, URL **e** instante |
| Postiz | 78 menções, **zero** em código | porta + adaptador reais, contra a API oficial |

## 3. As premissas, verificadas

| premissa | veredito | evidência |
|---|---|---|
| Postiz é o control plane oficial e **não** está implantado | **confirmada** | `grep -rn "POSTIZ"` = 0; system:postiz `todo` |
| MultiPost é fallback, sem código | **confirmada** | 37 menções, todas doc/roadmap |
| AdsPower é QA visual, sem implementação | **confirmada** | 172 menções, nenhuma chama a Local API |
| Postiz não recebe `service_role` | **confirmada**, e virou controle | contenção por AST no adaptador |
| gerar ≠ aprovar ≠ publicar | **parcial** na base | aprovar existia e funcionava; a perna que faltava era a entrega. Agora separada |
| publicação exige destino+owner+aprovação+recibo | **parcial** na base | destino era fail-closed; owner **não existia**; aprovação era terceirizada ao painel; recibo era mutável |
| não existe `PublicationJob` canônico | **confirmada** | 7 menções, todas em prosa |
| nenhuma peça real percorreu publicação orgânica | **confirmada** | zero permalinks sociais no repositório |
| o fluxo WordPress não pode ser estendido | **confirmada** | 8 dimensões estruturais em `CONTRACTS.md` §1.1 |

⚠️ **O grafo está stale e é de outra linhagem.** `UPDATE_STATUS.json` declara
`built_at_commit=a539dbd7` com árvore suja; `merge-base --is-ancestor` contra a
base é falso e 282 commits os separam. Usei código, roadmap e curadoria como
autoridade, nessa ordem. Detalhes em `CURATION-HANDOFF.json`.

## 4. Capacidade PROVADA localmente

- ciclo SQL completo em Postgres descartável, com **contraprovas A–O**;
- **corrida real** entre dois processos: exatamente um vencedor, fencing=1;
- E2E hermético cobrindo os **14 degraus** da missão, sobre a v14_01 real,
  o `RepositorioSupabase` real, o `rotas.py` real e o `AdaptadorPostiz` real —
  só a rede é substituída;
- timezone: conversão independente do TZ do servidor, horário inexistente,
  **horário ambíguo**, offset fracionário (+05:45), passado, ausente;
- `now` bloqueado sem consentimento humano específico, em **três** camadas;
- a tela nunca pinta de verde estado incerto, desconhecido, ou um backend que
  se contradiz — **provado por mutação**;
- nenhum segredo versionado, por dois detectores independentes.

## 5. Capacidade NÃO provada — dita, não escondida

1. **Nenhum ato externo.** Sem instância, sem página, sem publicação.
2. **PG 16, não 15.8.** Docker indisponível; o modo `--local` imprime a divergência.
3. **Um destino no cenário.** "Falha de um destino não contamina outro" (aceite
   de P12-T09) **não** foi exercitado.
4. **Sem mídia.** A v1 envia texto; `upload`/`upload-from-url` não exercitados.
5. **Sem promoção rascunho→agendamento.** `PUT /posts/{id}/status` existe na API
   e não foi implementada — promover mudaria o `modo`, que é parte do snapshot.
6. **DNS rebinding não fechado por completo.** Revalidação por chamada reduz a
   janela; só pinagem de IP a fecharia.

## 6. Bloqueadores reais

**Nenhum bloqueador de código.** Os três bloqueadores são externos e estão no
`AUTORIZACAO-EXTERNA.md`: não há instância Postiz (P12-T08), não há credencial, e
não há destino real conectado (P12-T02). **O primeiro elo que falta não é o
adapter — é o destino.**

## 7. Dívida não bloqueante (registrada em `CURATION-HANDOFF.json`)

- **D1** `criativo_entrega` vazia e sem chamador: existem duas tabelas de entrega.
  Decisão do dono do Estúdio Criativo — a fronteira desta missão proibia tocá-la.
- **D2** `publicacao.py:1606` lê a tabela errada (ramo morto).
- **D3** `publicacao.py:990` grava `'error'` contra um CHECK que só aceita `'failed'`.
- **D4** `publisher_quality/fetch.py` é a única guarda de SSRF do repositório e
  não tem chamador de produção.
- **D5** divergência factual sobre o `/health` do Postiz (§2.2 de POSTIZ-OPERATIONS).

## 8. Revisão adversarial

**Codex `gpt-5.6-sol`** — a primeira tentativa foi recusada por política de
conteúdo do provedor (registrado uma vez); reformulada como revisão de qualidade,
rodou e achou **4 defeitos reais**, todos consertados **com contraprova**:

1. **Buraco negro do lease.** `reivindicar` só aceita `pronto` e todo claim move
   para `em_voo` — logo a condição de lease vencido era **código morto**, e um
   despachante que morresse deixava o job preso com reivindicar, reconciliar e
   cancelar todos recusando. Consertado com `expirar_lease` → `indeterminado`
   (e **não** redespacho, que duplicaria o post) + `presos()`.
2. **Horário ambíguo** aceito em silêncio no recuo do DST.
3. **Exception safety**: dois caminhos deixavam o job preso em `em_voo`.
4. **Egresso**: redirect não declarado e destino validado só na construção.

**Verificação interna** (4 agentes, build + revisão adversarial + rodada corretiva
+ verificação independente) achou 2 bloqueantes no validador do pacote — ele era
derrotado por **YAML válido** e lia um arquivo enquanto o Compose **mescla**
overrides — e, em duas verificações independentes, a mesma lacuna na tela: a
escada de veto não acoplava estado a tom.

**Gemini 3.7 Flash** confirmou 17 de 18 itens do contrato Postiz. O único
refutado (`/health`) **não se sustentou** contra a fonte primária, e a decisão
conservadora foi mantida com a divergência registrada.

## 9. Gates

Detalhe em `GATES.md`. Resumo:

| gate | baseline | branch |
|---|---|---|
| backend amplo | 2600 / 87 skip / **0 fail** | 2723 / 87 skip / **0 fail** |
| frontend amplo | 1134 / **2 fail** (7 arquivos) | 1248 / **2 fail** (**os mesmos** 7) |
| `tsc` | 117 linhas, ratchet 76 | **saída byte a byte idêntica** |
| build | — | exit 0 |
| ciclo SQL | n/a | completo |
| validador Postiz | n/a | APROVADO + **18 mutações** mordidas |
| segredos | limpo | limpo |

## 10. Confirmação de zero ação externa

Nenhum deploy, merge, push, publicação, conexão de página, escrita no Supabase
oficial, AdsPower, Meta write, Google Ads ou n8n. A tabela item a item, com como
conferir cada uma, está em `AUTORIZACAO-EXTERNA.md`.

Leituras externas: documentação pública do Postiz, `LICENSE` e releases do
GitHub, e o compose público. Read-only, sem credencial.

## 11. Arquivos deste pacote

| arquivo | o que responde |
|---|---|
| `HANDOFF.md` | este — o mapa |
| `CONTRACTS.md` | por que não estendemos o existente; o domínio canônico; estados; idempotência; timezone; fronteira de segredo |
| `GATES.md` | os comandos, os números medidos, e as contraprovas A–O uma a uma |
| `POSTIZ-OPERATIONS.md` | o contrato externo com fonte, as 4 ausências, a divergência de rate limit, os limites de segurança abertos |
| `AUTORIZACAO-EXTERNA.md` | o que não aconteceu, e o pedido único em blocos A–E |
| `CURATION-HANDOFF.json` | proposta para roadmap e curadoria; 5 contradições/dívidas; frescor do grafo |

## 12. Para quem pegar isto a seguir

Leia nesta ordem: `CONTRACTS.md` §1 (por que o desenho é este),
`AUTORIZACAO-EXTERNA.md` (o que falta e em que ordem), `GATES.md` (como rodar).

E antes de mudar qualquer coisa no schema, rode
`./scripts/provar-ciclo-v14_01.sh --local`. Ele pegou duas decisões erradas
minhas antes de qualquer humano ver — o índice que impedia a segunda
reconciliação, e a máquina de estados sem as arestas do mundo real.
