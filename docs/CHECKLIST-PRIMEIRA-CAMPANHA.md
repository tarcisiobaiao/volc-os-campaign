# Checklist — colocar a primeira campanha no ar

> Feito para imprimir. Medido no card **74 · Maquininha de Cartão** (run 7)
> em 19/08/2026, com a prova rodando contra a conta real.
>
> **O front não é o gargalo.** O cockpit já monta, prova e sobe. O que falta
> são duas coisas, e só uma delas é código.

---

## Onde você está agora

```
prova de voo do card 74  ·  13 erros  →  2 erros
                            ▲             ▲
                    11 falsos positivos   o que sobrou é real
                    de marca (corrigido)
```

| | |
|---|---|
| LP publicada | ✅ `creditoup.com.br/r/maquininha-de-cartao-menor-taxa/` |
| conta vinculada | ✅ `8017851692` · BRL · fuso São Paulo |
| meta de conversão detectada | ✅ `adViewInterstitial` |
| copy escrita | ✅ 15 headlines · 4 descriptions · 4 sitelinks · 4 callouts |
| keywords | ✅ 10 em 3 grupos |
| engine em CPC manual | ✅ provado no payload (`manual_cpc`, eCPC desligado) |
| **habilitação financeira** | ❌ **bloqueia** |
| **1 description com 91 chars** | ❌ bloqueia (limite 90) |

---

## ETAPA 1 · A habilitação — comece por aqui, é a mais lenta

☐ **Decidir a vertical do portal.**

O engine classificou como `financeiro@BR` e exige
`verificacao_servicos_financeiros`. A pergunta é factual:

> **O Crédito Up *presta* serviço financeiro, ou apenas *explica* como
> funciona?**

A própria copy escreve *"Este portal apenas explica as regras da…"*. Se o
portal só compara taxas e não intermedia contratação, a vertical correta é
`informativo` — e aí **não há portão**.

| se você marcar | consequência |
|---|---|
| `informativo` | sobe hoje, sem verificação. **Risco:** se o Google entender que maquininha = serviço financeiro, o anúncio é reprovado depois da veiculação começar |
| `financeiro` | precisa da verificação antes. **Custo:** dias a semanas, é processo do Google |

☐ **Se escolher `financeiro`:** iniciar a verificação em
`Google Ads → Ferramentas → Configuração → Verificação do anunciante →
Serviços financeiros`. É **por país** — verificar no Brasil não habilita
México. Verificação feita no MCC pode propagar para as contas gerenciadas.

☐ **Se escolher `informativo`:** trocar a vertical no cockpit e seguir para a
etapa 2. Nenhum código muda.

> ⚠️ Esta é a **única** etapa que pode levar semanas. Todas as outras somam
> menos de um dia.

---

## ETAPA 2 · Cortar um caractere

☐ Abrir a copy do card 74 e encurtar **uma** description:

```
Taxa Minizinha NFC 2: 0,58%. Taxa Ton: 0,57%. Fontes: pagseguro.uol.com.br/, www…
                                                            ↑ 91 caracteres, limite 90
```

Sugestão: cortar a segunda fonte ou abreviar `pagseguro.uol.com.br/` →
`pagseguro.uol.com.br`. Um caractere resolve.

☐ Rodar a prova de novo e confirmar que sobrou **zero** erro:

```bash
curl -s -X POST -H "X-API-Key: $VITE_PAUTADOR_API_KEY" \
  -H "Content-Type: application/json" --data @pedido.json \
  http://localhost:8010/api/trafego/provar | jq '.preparo.aprovado, .preparo.selo'
```

**Aceite:** `aprovado: true` e um **selo** com impressão sha256.
A prova roda `validate_only` contra a conta real e **não cria nada** —
repita à vontade.

---

## ETAPA 3 · Subir

☐ **Conferir que a campanha nasce como a doutrina manda** — na Mesa de Lance:

```
● CPC manual  ·  R$ 0,38        (o lance é seu; sob automático o Google ignora)
  orçamento    R$ 30,00 / dia
  match type   PHRASE            (decorre da estratégia, não se escolhe)
  graduação    30 conversões → Maximizar conversões, broad liberado
```

☐ **Abrir a trava de escrita.** São dois fatores, de propósito:

```bash
# 1. no ambiente
export FORGE_PERMITIR_ESCRITA=1
# 2. no código: chamar destravar() com um motivo de 10+ caracteres
```

☐ **Subir.** O `/subir` roda o `validate_only` de novo por dentro antes de
escrever — o selo é do payload, não da sessão.

☐ **Fechar a trava imediatamente depois.**

☐ **Guardar o recibo.** Ele sai em `volc_ads/dados/recibos/`.
**⚠️ Hoje ele NÃO vai para o banco** — a campanha nasce invisível para o nosso
sistema (ver "o que fica devendo").

---

## ETAPA 4 · Ativar

☐ A campanha nasce **`PAUSED`**, sempre. Isso é trava, não bug.

☐ Ativar é gesto humano, no Google Ads ou no front. **É aqui que o dinheiro
começa a sair** — é o único ato irreversível de todo o processo.

☐ Nas primeiras 48h, olhar direto no Google Ads:
- o anúncio foi **aprovado** ou reprovado por política?
- o CPC real está perto de R$ 0,38 ou muito acima?
- há impressão? Se zero, o lance está baixo demais para o leilão.

---

## O que fica devendo — e por que dá para viver com isso agora

| dívida | por que espera |
|---|---|
| a campanha não é gravada em `campaigns` | para 1–3 campanhas você olha no Google Ads. Vira problema quando forem 20 |
| sem `funnel_run_id` persistido | idem — a junta funil→campanha fecha no F4 do PRD |
| sem upload de conversão offline | **em CPC manual não faz falta**: quem decide o lance é você, não o modelo. Vira obrigatório na graduação |
| sem ingestão de custo própria | o Google Ads mostra o gasto. A ingestão é para escala |
| 3 ad groups em vez de 1 | contraria a doutrina (P7), mas não impede subir. Vale colapsar antes da segunda campanha |

**O ponto:** o PRD do Fable põe a criação no F4, depois de F0–F3. Aquelas fases
constroem *saber o que aconteceu* e *gerenciar em escala* — não *criar*. Para as
primeiras campanhas, você pode operar olhando o Google Ads direto.

---

## Antes de escalar (não trava a primeira, trava a décima)

☐ **Desligar o webhook aberto** `1cb2069d…` — está na internet sem
autenticação e a URL está no bundle público do front. Um POST fixa tCPA
arbitrário na conta real.

☐ **Desativar os 6 formulários públicos** da Factory v3 (endpoints abertos
contra conta real).

☐ **Girar** o developer token do Google Ads, o Application Password do
WordPress e a chave do exchangerate-api.

☐ **Persistir a campanha no banco** no `/subir` — a menor peça do F4, e a que
tira você de voar cego.

---

## Resumo de uma linha

> **Decida a vertical, corte um caractere, destrave e suba.**
> Tudo o mais é escala.
