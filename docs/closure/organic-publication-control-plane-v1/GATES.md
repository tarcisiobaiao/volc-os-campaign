# Gates — plano de controle de publicação orgânica v1

**Data:** 02/09/2026 · **Branch:** `sprint/organic-publication-control-plane-v1`
**Base:** `382c5d4c67fc521d5e6739f8e76d1c36a96fdb53` · **HEAD:** ver `HANDOFF.md`

Máquina: macOS 24.6.0, Python 3.14.6, PostgreSQL 16.11 (Homebrew), Node/vitest 4.1.10.
**Docker indisponível nesta máquina** — o ciclo SQL rodou em modo `--local`, que
imprime a divergência de major em vez de escondê-la (produção é PG 15.8).

---

## Como rodar tudo

```bash
cd /private/tmp/volc-organic-publication-control-plane-v1
PY=/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/backend/.venv/bin/python

# 1. ciclo SQL completo: aplicar -> operar -> reverter -> reaplicar
./scripts/provar-ciclo-v14_01.sh --local

# 2. testes focais de backend (128)
cd backend && VOLC_EXIGIR_POSTGRES=1 PYTHONPATH=.. $PY -m pytest \
  tests/test_publicacao_organica_*.py -q -p no:randomly

# 3. suíte ampla de backend
cd backend && PYTHONPATH=.. $PY -m pytest tests/ -q -p no:randomly

# 4. testes focais de frontend (112) — exige node_modules
ln -sfn /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/node_modules node_modules
./node_modules/.bin/vitest run src/features/publicacao-organica

# 5. TypeScript (ratchet oficial) e build
$PY scripts/gate_tsc_ratchet.py
./node_modules/.bin/vite build

# 6. pacote Postiz — offline, nada sobe
$PY scripts/validar_postiz_pacote.py --pacote deploy/postiz
$PY scripts/validar_postiz_pacote.py --autoteste

# 7. segredos e higiene
python3 scripts/verificar_segredos.py
git diff --check
```

---

## Resultados medidos

| # | gate | baseline (`382c5d4`) | branch | veredito |
|---|---|---|---|---|
| 1 | ciclo SQL v14_01 | n/a (não existia) | aplicar → operar → reverter → reaplicar, **completo** | ✅ |
| 2 | backend focal | n/a | **128 passed** | ✅ |
| 3 | backend amplo | 2600 passed / 87 skipped / **0 failed** | 2728 passed / 87 skipped / **0 failed** | ✅ +128, zero regressão |
| 4 | frontend focal | n/a | **112 passed** (3 arquivos) | ✅ |
| 5 | frontend amplo | 1134 passed / **2 failed** (7 arquivos) | 1248 passed / **2 failed** (7 arquivos) | ✅ mesmas falhas |
| 6 | `tsc --noEmit -p tsconfig.app.json` | 117 linhas / ratchet **76** | 117 linhas / ratchet **76** | ✅ saída **byte a byte idêntica** |
| 7 | `vite build` | — | exit 0 | ✅ |
| 8 | validador do pacote Postiz | n/a | **APROVADO** com 3 avisos | ✅ |
| 9 | autoteste do validador | n/a | **18 mutações reprovadas** pelo rótulo esperado | ✅ |
| 10 | `verificar_segredos.py` | limpo | **limpo** | ✅ |
| 11 | `git diff --check` | limpo | limpo | ✅ |

### As 7 falhas de frontend são pré-existentes, e isso foi medido

Rodei a suíte ampla nas duas árvores e comparei a lista de arquivos que falham.
`diff` **vazio**. Todas param em `Error: Missing Supabase environment variables`
(`src/lib/supabase.ts:7`), em `src/components/trafego/**` e
`src/components/settings/meta-capi/**`. Nenhuma toca esta missão.

### O ratchet de TypeScript

`scripts/gate_tsc_ratchet.py` conta **76** nas duas árvores, contra o baseline
de 76 gravado na linha 32 do script. E a saída bruta de `tsc` é idêntica linha a
linha entre base e branch — os arquivos desta missão contribuem **zero** erros.

---

## As contraprovas, uma a uma

Cada uma foi escrita **vermelha primeiro** ou reproduzida contra o código antes
do conserto. Onde uma contraprova não se aplica, está dito por quê — nenhuma foi
marcada verde por vacuidade.

| # | contraprova | onde é provada | como |
|---|---|---|---|
| **A** | publicação sem aprovação | ciclo SQL (A1/A2/A3) + E2E | decisão `rejeitado` → 23514; aprovação `revogada` → 23514; finalidade de classe não-orgânica → 23514 |
| **B** | owner A publicando ativo de B | ciclo SQL (B1/B2/B3) + E2E | peça alheia → 42501; destino alheio → 42501; detalhar job alheio → **NULL** (mesma resposta de "não existe", de propósito) |
| **C** | destino ausente ou divergente | ciclo SQL (C1/C2) + E2E | destino inexistente → 23503; destino sem adapter apto → 23514, com o motivo |
| **D** | retry duplicando publicação | ciclo SQL (D0/D2/D3/D4) + E2E | 3 chamadas → 1 job; segundo sucesso de despacho → 23505 pelo índice parcial; `rascunho_externo → pronto` recusado; redespachar → 409 **sem tocar a porta** |
| **E** | mesma chave, payload diferente | ciclo SQL (E) + E2E | 23505, **e a chave não aparece na mensagem** (a gramática dela aceita uma senha) |
| **F** | dois consumidores concorrentes | ciclo SQL (F, F2, **F-real**) | sequencial: o 2º recebe `reivindicado:false`. **Real: dois processos `psql` com barreira por relógio do banco → exatamente 1 vencedor, fencing=1, tentativas=1.** Fencing velho → 40001 |
| **G** | timeout virando sucesso | porta (5 injeções) + ciclo SQL + E2E | timeout/erro-de-rede/500-após-gravar/corpo-ilegível/200-sem-postId → todos `DesfechoIncerto` → `indeterminado`, **e nenhum recibo inventado** |
| **H** | erro externo vazando token | porta + E2E + ciclo SQL | 400 que ecoa `{"Authorization": "<token>"}` → token ausente da resposta, do job e do banco. `prosa_limpa` recusa a linha; chave sensível no recibo → 23001 |
| **I** | ativo alterado depois da aprovação | ciclo SQL (I1–I4) + E2E | aprovação da v1 não cobre a peça v2 → 23514; snapshot imutável mesmo por `UPDATE` direto como superusuário → 23001; snapshot preso à versão **e** ao `content_hash` aprovados |
| **J** | `now` sem consentimento | ciclo SQL (J1/J2) + domínio + E2E | ausente → 23514; `false` explícito → 23514; recusado no domínio **antes** de qualquer ida ao banco; com consentimento, o ator e o instante ficam registrados |
| **K** | schedule com timezone errado | ciclo SQL (K1–K7) + domínio + E2E | zona inexistente; passado; horário que **não existe** (salto do DST); sem horário; **conversão independente do TZ do servidor** (mesmo instante em UTC e em Pacific/Kiritimati); **horário ambíguo** (fim do DST) recusado, com controle provando que horário normal passa; offset fracionário (+05:45) correto |
| **L** | recibo sem referência externa | ciclo SQL (G/L) + E2E | sucesso sem referência → 23514 ("resposta vazia não é recibo"); `PUBLISHED` sem URL nem instante → 23514 |
| **M** | frontend verde para estado parcial | 112 testes de frontend | varredura dos 11 estados no DOM e na unidade; backend contraditório (`incerto`+`sucesso`, e `estado`×`tom`) não ganha verde; estado desconhecido não ganha verde; **provado por mutação: removendo o veto, 11 testes caem** |
| **N** | Postiz com acesso ao Supabase | contenção por AST + ciclo SQL | o adaptador não pode **referenciar** `service_role`, `SupabaseService`, `get_settings`, `Settings` (verificado na árvore sintática, não no texto); `service_role` não lê nem escreve nas 5 tabelas; `anon` não lê recibo; a função interna de idempotência não é chamável de fora |
| **O** | segredo versionado | scanner oficial + detector próprio | ambos limpos. O detector tem **contraprova de mordida**, e os valores sintéticos são montados por concatenação — um literal reprovaria o scanner da casa, e a saída seria enfraquecer o scanner para acomodar o teste |

### Contraprovas que exigiriam o que não existe

| o que | por que não foi provada | o que a fecharia |
|---|---|---|
| "falha de um destino não contamina outro" (aceite de P12-T09) | o cenário tem **um** destino apto. Montar dois destinos aptos herméticos provaria o isolamento do nosso lado, mas não o do control plane | dois destinos reais, ou um segundo canal no fake |
| adapter em **sandbox** | nenhuma instância Postiz foi implantada | P12-T08 + autorização |
| backup/restore do Postiz **provados** | exigem instância e dados | P12-T08 + autorização |

---

## O que os gates NÃO provam

1. **Nada externo aconteceu.** Todo tráfego HTTP desta suíte passou por
   `httpx.MockTransport`. Nenhum container subiu, nenhuma página real foi tocada,
   nenhuma migration foi aplicada no Supabase oficial.
2. **O ciclo SQL rodou em PostgreSQL 16**, não 15.8 como produção. O modo
   `--local` imprime a divergência. Com Docker disponível, `./scripts/provar-ciclo-v14_01.sh`
   sem flag usa `postgres:15`.
3. **A suíte não prova que a pilha do Postiz sobe.** O validador é offline e
   confere o *pacote*, não a execução — e ele diz isso na própria saída.
4. **34 erros aparecem em `test_criativo_deposito_contrato.py` quando
   `VOLC_EXIGIR_POSTGRES=1` está ligado.** São pré-existentes e não desta missão:
   aquele arquivo usa `conftest_postgres.py`, que exige o driver `psycopg` —
   ausente nos quatro venvs desta máquina. Sem a variável, viram skips visíveis.
   ⚠️ O E2E desta missão **não** tem essa dependência (fala por `psql`), então ele
   roda nos dois modos: 30 passed com e sem a variável.
