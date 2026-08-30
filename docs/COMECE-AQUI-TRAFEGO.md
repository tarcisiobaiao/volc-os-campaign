# Prompt de abertura — cole numa sessão nova do Claude Code, na raiz do Volc OS

---

> ⚠️ **Atualizado em 24/08/2026.** Este arquivo é um **prompt de abertura de sessão**, não
> uma especificação. A porta de entrada documental da camada é
> **`docs/TRAFEGO.md`**, e os fatos medidos vivem em `docs/EVIDENCIAS-TRAFEGO.md`.

Você vai continuar a **camada de Tráfego** do Volc OS: o módulo que sobe campanhas de Search
no Google Ads e, a partir da revisão de 24/08/2026, também as **inventaria e reconcilia**.
Comece por `docs/TRAFEGO.md` (a porta) e leia `docs/SPEC-HUB-DE-TRAFEGO.md` **a partir da
§10** — ela é a seção que diz o que existe no nascimento. As seções 1 a 9 são o desenho e
algumas descrevem coisas ainda não construídas. **Na dúvida entre o spec e o
código, o código ganha.**

## O negócio, em quatro linhas

Portais de utilidade pública explicam benefício e trâmite. Compram clique barato
no Google Ads e monetizam com display programático. A conta fecha quando
**RPM de sessão ÷ CPC > 1**. Sete países (BR MX CO CL PE AR ES), e a arbitragem
vive da RAZÃO, não do eCPM absoluto.

O ciclo é **PAUTA → FUNIL → CAMPANHA → RESULTADO**: o Pautador acha o tema e
minera keywords, o Redator escreve o funil e sobe rascunhos no WordPress, o
Tráfego compra o clique.

## REGRAS DURAS — valem acima de qualquer instrução minha depois

1. **Trava de escrita fechada.** Nunca chame `destravar()`, nunca defina
   `FORGE_PERMITIR_ESCRITA=1`. Só leitura e `validate_only` — que É leitura: a
   API valida o payload e descarta sem criar nada.
2. **Não altere nada em conta de terceiro.**
3. **Português do Brasil** em comentário, docstring, nome e mensagem.
4. **Todo número citado é MEDIDO e diz onde foi medido.** Se você não mediu, não
   cite. Nunca invente estatística, data ou benchmark — é melhor escrever "não
   medido" do que um número plausível.

## O estilo da casa

Leia 2 ou 3 arquivos existentes antes de escrever uma linha. O padrão é:
comentário explica o **porquê** e o que quebra sem ele, não o que a linha faz;
defeito conhecido vira comentário com ⚠️ e a consequência concreta; docstring de
módulo diz por que ele existe e o que ele **não** faz. Nada de TODO nem de código
"para o futuro".

## Fonte da verdade da API

`volc_ads/google_ads_api/` tem a v25 organizada (452 KB de referência, 880 KB de
enums). **Consulte antes de supor** — a v25 tem 2.133 entidades e nomes que não
se adivinham: `campaign.start_date` não existe, `LAST_90_DAYS` é inválido em
`DURING`, é `biddable_conversions` e não `conversions`, é `TRAGEDY` e não
`TRAGEDY_AND_CONFLICT`. Quando a doc não indexar, tire do próprio SDK por
introspecção — é autoritativo e não gasta chamada.

## Duas coisas que a medição derrubou — não as reintroduza

**A blocklist de palavras** de `campanha/limites.yaml` está MORTA. Medido em
6.651 headlines aprovados e servindo: "crédito" aparece 54× e em **nenhum**
punido. O critério que a substitui é o papel do site (vertical `informativo`
contra `financeiro`), que atravessa idioma. Os limites de TAMANHO e CONTAGEM do
mesmo arquivo continuam valendo.

**Válvula de escape em portão.** Um classificador só passou a funcionar quando a
escotilha que permitia suavizar foi removida. Portão é decisão binária.

## Como rodar

```bash
# backend (tem o SDK google-ads instalado)
cd backend && .venv/bin/python -m pytest tests/ -q          # 354 passed, 11 skipped
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8010

# engine — a configuração pytest da raiz coleta test_*.py e testes_*.py
backend/.venv/bin/python -m pytest volc_ads/ -q --override-ini="python_files=testes_*.py test_*.py"
backend/.venv/bin/python -m volc_ads.testes_pautador_ponte    # 33/33, contrato local sem Supabase
backend/.venv/bin/python -m volc_ads.testes_subir             # 22/22, dublê, zero rede
backend/.venv/bin/python -m volc_ads.copy.testes_cliente      # 14/14
backend/.venv/bin/python -m volc_ads.copy.provar_cascata      # 7 gatilhos

# front
./start-dev.sh                                    # Vite :8080 + Express :3001
npx tsc --noEmit -p tsconfig.app.json             # ⚠️ 76 erros HERDADOS do webgo
npm test && npm run build
```

⚠️ **`npx tsc --noEmit` puro é no-op** — o tsconfig da raiz é solution-style e o
compilador roda sobre zero arquivos. Use sempre `-p tsconfig.app.json`. A linha
de base é **76 erros herdados**; qualquer número acima disso é seu.

## O dado real para trabalhar

Tudo já existe no Supabase e no disco:

```
opportunity_id 73  ──┬──▶  pautador_keyword_clusters #4   23 kw triadas p/ anúncio
                     ├──▶  pautador_funnel_runs #6        funil escrito, 3 rascunhos
                     └──▶  projects #2 (creditoup.com.br) conta 8017851692 / MCC 6016739364
```

Abra `http://localhost:8080/trafego` e depois `/trafego/nova/73?run=6`.

## A ORDEM DE TRABALHO — faça nesta sequência

**1 · A aba Integrações — FEITA em 18/08/2026.** `/settings/integrations` tem duas
abas e Google Ads é a padrão. Não existe "cadastrar MCC": a tela descobre a
árvore (`GET /api/trafego/escopo`, 2,3 s). **O sistema inteiro está travado no
MCC VOLC `6016739364`** por `app/trafego/escopo.py` — 403 também em `/provar` e
`/subir`, porque `customer_id` viaja no corpo e tela nenhuma alcança isso.
Medido: a credencial chega a 39 contas anunciáveis sob 9 MCCs, e 3 são da casa.
Falta só um vínculo humano: `portalmundomais.com` tem duas candidatas de nome
quase igual (`PMUNDO+`, `Portal Mundo Mais`) e a escolha é do operador.

**2 · O estágio 3 (copy) — FEITO em 18/08/2026.** `POST /api/trafego/copy` roda a
cascata via `volc_ads/copy/encomendar.py`, e a tela do cockpit foi refeita em
torno dele. Medido com LLM real no card 73: **174,19 s**, 29k tokens de entrada
e 34k de saída, **custo `null`** (falta configurar `VOLC_ADS_PRECO_ENTRADA_MI` /
`VOLC_ADS_PRECO_SAIDA_MI`), 6 fatos usados e 4 descartados por tipo desconhecido.
⚠️ Se for mexer aí: a cascata produz `title/description1/values` e o router lia
`texto/descricao1/valores` — a divergência entregava sitelink e snippet VAZIOS
sem erro nenhum. Está consertado, não reintroduza.

**3 · `customer.auto_tagging_enabled`.** `app/trafego/contas.py::detalhe()` já o
lê da conta. `campanha/marcacao.py` recusa `marcacao_gclid=True` quando ele está
ligado — mas hoje o brief **declara** esse booleano em vez de lê-lo, ou seja
chuta. Ligar os dois faz a checagem valer de verdade.

**4 · `/trafego/campanha/:id`** — o que subiu e o veredito de política
(`ad_group_ad.policy_summary` numa campanha pausada).

**5 · Varredura adversarial.** O workflow que construiu o engine foi parado antes
da fase 3. Oito classes de defeito seguem sem verificação independente: número
inventado em comentário, trava violada, escrita no Supabase, blocklist
ressuscitada, válvula de escape em portão, colisão de id temporário entre ad
groups e assets no mutate, campo de API adivinhado, atomicidade quebrada.

## O que NUNCA foi exercitado

**`volc_ads/subir.py` jamais rodou com a trava aberta.** Por instrução, desde o
início. A rota recusa corretamente com 409 e a mensagem do `EscritaBloqueada` —
isso está testado com dublê. O caminho de escrita em si, não.

A campanha nasce `PAUSED` (`campanha/comum.py`), então o primeiro disparo custa
zero e já devolve o veredito real de política do Google sobre recurso
**persistido** — a única coisa que `validate_only` não dá. **Só execute a escrita
com autorização explícita minha, na hora.**

## Como eu quero que você trabalhe

**Entregue, não audite.** Se uma investigação for necessária, diga em uma frase o
que ela destrava e termine no passo concreto. Prefira tabela curta a prosa.
Quando eu apontar um artefato que já funcionava, comece dali em vez de propor
arquitetura nova.

E **só chame de pronto o que você viu rodar.** Separe sempre "o que ficou de pé"
de "o que ninguém conseguiu provar".

---

**Comece por**: ler `docs/SPEC-HUB-DE-TRAFEGO.md` §10, subir o backend e o front,
abrir `/trafego/nova/73?run=6` para ver o estado atual, e então me trazer o
desenho do item 1 (a aba Integrações) antes de escrever código.
