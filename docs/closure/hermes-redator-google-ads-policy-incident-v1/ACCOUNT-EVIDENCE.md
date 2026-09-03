# ACCOUNT EVIDENCE — leitura read-only sanitizada

Capturado em: 2026-09-03T00:53:00Z (passo anterior do Hermes)
Relido e analisado em: 2026-09-03 (esta sessão — **sem nova leitura de conta**)

Identificadores crus não são versionados. Este arquivo e
`account-evidence-sanitized.json` guardam apenas pseudônimos, sinalizadores de
presença e URLs finais públicas.

- Mutação no Google Ads tentada: **não**
- Criação de conta tentada: **não**
- Apelação enviada: **não**
- Nova leitura de conta nesta sessão: **não** (ver §4)

---

## 1 · O que a leitura devolveu

| | |
|---|---|
| API disponível | `True` |
| Contas acessíveis | 13 |
| Contas com permissão de leitura | 3 — `CUST_006`, `CUST_010`, `CUST_013` |
| Contas com `USER_PERMISSION_DENIED` | 9 |
| Anúncios de Busca com `creditoup.com.br` ou `/r/` | 14 |

### Estado por conta legível

| pseudônimo | `customer.status` | observação |
|---|---|---|
| `CUST_006` | `ENABLED` | nenhum anúncio correspondente |
| `CUST_010` | `ENABLED` | 9 anúncios correspondentes; campanhas `PAUSED`/`REMOVED` |
| **`CUST_013`** | **`SUSPENDED`** | 5 anúncios correspondentes, todos para `creditoup.com.br/r/*` |
| `CUST_005` | — | consulta devolveu `CUSTOMER_NOT_ENABLED_OR_DEACTIVATED` |

## 2 · As duas leituras que mais importam

1. **A suspensão é de CONTA, não de anúncio.** `CUST_013` está `SUSPENDED`
   enquanto **todos os seus anúncios** estão `APPROVED`/`REVIEWED`. Isso
   **refuta** a tese de que o texto dos anúncios foi reprovado: o gatilho está no
   nível da conta ou do destino, não da criação.

2. **`CUST_013` é a conta que anunciava `/r/fgts-saque-aniversario/`** — a URL
   preservada em `evidence-public/`.

### Status de política, no nível do anúncio

| `approval_status` / `review_status` | anúncios |
|---|---:|
| `APPROVED` / `REVIEWED` | 11 |
| `APPROVED_LIMITED` / `REVIEWED` | 2 |
| `UNKNOWN` / `REVIEW_IN_PROGRESS` | 1 |

Os dois `APPROVED_LIMITED` apontam para
`portalmundomais.com/r/nova-carteira-identidade-nacional-2026` — documento de
identidade nacional, categoria coberta pela política *Government documents and
services*. **É o único sinal literal de restrição de política que a API
entrega**, e vale registrar como tal: ele diz que aquela categoria já estava
limitada, não que ela causou a suspensão.

## 3 · A classificação literal da suspensão NÃO foi obtida

`customer.status` diz `SUSPENDED`; ele **não** carrega o motivo. A política
citada vive na **notificação in-account e no e-mail** enviados ao anunciante —
a documentação do Google é explícita: *"The email notification will identify all
policies the advertiser has been suspended for violating."*
(`support.google.com/google-ads/answer/9841640`, consultado em 2026-09-03).

> **Pedido de evidência ao operador.** Para fechar a causa é preciso:
>
> 1. o texto literal da notificação in-account e do e-mail, com a(s) política(s)
>    nomeada(s);
> 2. a data da suspensão;
> 3. o histórico de avisos anteriores da conta;
> 4. o estado da verificação de anunciante.
>
> **Não inferir a causa a partir do destino.** `ROOT-CAUSE-ANALYSIS.md` conclui
> `HYPOTHESIS_PARTIALLY_SUPPORTED` justamente por essa lacuna.

## 4 · Higiene da leitura de conta

A tentativa read-only anterior produziu **stderr verboso do cliente do Google
Ads no console do operador**, apesar de não haver mutação. Os artefatos do
repositório foram reduzidos imediatamente a campos de classificação e não
guardam ID de cliente nem de requisição.

**Condição para qualquer leitura futura:** suprimir completamente o logging de
requisição/stderr do cliente antes de executar, e persistir apenas saída
sanitizada e pseudonimizada.

**Nesta sessão nenhuma leitura de conta foi executada.** Toda a análise acima é
releitura do JSON sanitizado já versionado.
