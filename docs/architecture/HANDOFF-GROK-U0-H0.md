# Contrato para o Grok — U0 + H0

**Data:** 26/08/2026 · **De:** Claude (backend/domínio/contrato)
**Vale contra:** `VERSAO_INVENTARIO = 2`

Só o que você precisa para conectar. O detalhe está no
[handoff completo](./HANDOFF-CLAUDE-U0-H0.md).

---

## 1. Endpoint H0

```
GET /api/trafego/campanhas/{volc_campaign_id}
```

Cliente pronto: **`pautadorApi.campanhaCanonica(volcCampaignId)`**.

| resposta | quando |
|---|---|
| `200` | a campanha existe |
| `404` | id interno inexistente · **`campaign_id` externo** · id fora do formato |
| `401` / `403` | sem credencial ou sem papel |
| `503` | snapshot indisponível |

⚠️ **Não passe `campaign_id` do Google.** O id externo é único *dentro de uma
conta*, não no VOLC O.S. — a identidade externa virou uma trinca
`(plataforma, conta, id)`. Uma rota que adivinhasse as outras duas pontas
abriria a campanha de outro cliente com a URL certa na barra de endereço. Ela dá
404 e nem tenta.

Zero Google Ads no render · zero mutação · **não passa pela listagem paginada**
(há teste provando que a listagem não é tocada).

## 2. Payload do detalhe — `CampanhaCanonica`

```jsonc
{
  "versao": 2,
  "campanha": { /* CampanhaNoInventario — a MESMA projeção da lista */ },
  "identidade": {
    "volc_campaign_id": "gads-8017851692-241",
    "campaign_lineage_id": null,
    "plataforma": "GOOGLE_ADS",
    "conta_externa": "8017851692",   // null = ainda não se sabe a conta
    "id_externo": "241"
  },
  "conta": {
    "customer_id": "8017851692",
    "frescor": "recente",            // é ele que carimba os números
    "tentativa_resultado": "ok"
  },
  "manifesto": { /* ManifestoDeCanal */ }   // null quando o canal não tem
}
```

**`manifesto: null`** acontece com `VIDEO` e `SHOPPING`: eles aparecem no
inventário e o Hub não os opera. `null` diz isso. Um manifesto vazio diria "não
pode nada", que é outra afirmação — e a tela renderizaria capacidades zeradas
como se fossem medidas.

**Derive as ações do manifesto**, nunca da lista de canais. Quatro canais não são
quatro botões de "criar": existe **um** construtor. `manifesto.sabe_criar` e
`manifesto.indisponibilidades[0]` são a frase que explica a recusa.

## 3. Payload da reconciliação

`GET /api/trafego/quadro` → cada item de `prontos[]` ganha `reconciliacao`.

```jsonc
"reconciliacao": {
  "estado": "correspondencia_provavel",
  "candidatas": [ {
    "volc_campaign_id": "gads-…",
    "externa": { "customer_id": "…", "campaign_id": "…" },
    "nome": "…", "estado_externo": "ENABLED", "canal": "SEARCH",
    "historico": false, "vinculo_id": null,
    "sinais": [ { "regra": "url_no_nome_declarado",
                  "forca": "medio",
                  "evidencia": { "url": "…", "lida_de": "nome_da_campanha" } } ]
  } ],
  "sinais_ausentes": [ { "regra": "linhagem_declarada",
                         "motivo": "…",
                         "impede_prova": false } ],
  "acao_permitida": "confirmar_vinculo",
  "exige_confirmacao_humana": true,
  "pode_montar": false,
  "pode_relancar": false
}
```

### As três regras que a tela precisa obedecer

**1 · `reconciliacao: null` BLOQUEIA a montagem.** Ela vem nula quando a prova
não pôde ser feita, e `campanhas_lancadas` vem `null` junto. **Não faça
`?? 0`** — isso transforma "não apurei" em "não há", e "não há" é o convite
verde. É o defeito que esta rodada inteira fecha.

**2 · `sem_campanha` só libera sem ressalva quando a prova foi completa.** Com
`exige_confirmacao_humana: true`, a montagem continua liberada — quase todo funil
novo começa em rascunho, e bloquear ali bloquearia trabalho legítimo — mas a tela
**avisa em vez de convidar**. O motivo está em `sinais_ausentes` com
`impede_prova: true`.

**3 · Nenhuma correspondência por nome isolado libera ação.** A regra
`url_no_nome_declarado` é `medio` e nunca fecha vínculo sozinha; a confirmação
humana é sempre obrigatória (ADR-09).

### Comportamento com os dados reais

| funil | estado | `pode_montar` | `exige_confirmacao` |
|---|---|---|---|
| FGTS (run 9) | `correspondencia_provavel` | **false** | true |
| Maquininha (run 7) | `correspondencia_provavel` | **false** | true |
| rascunho (run 6) | `sem_campanha` | true | **true** |
| inédito | `sem_campanha` | true | false |

A FGTS tem **3 candidatas, 1 no ar**. Histórico removido **não gera conflito** —
o que disputa o leilão é o que está no ar, e a história de relançamento é
legítima (aconteceu cinco vezes com motivo declarado).

### Ações permitidas

| `acao_permitida` | `pode_montar` | `pode_relancar` |
|---|---|---|
| `abrir_o_que_existe` | false | false |
| `confirmar_vinculo` | false | false |
| `abrir_revisao` | false | false |
| `relancar_declarado` | false | **true** |
| `montar` | **true** | false |

Clientes prontos: `pautadorApi.confirmarVinculo({…})` e
`pautadorApi.desfazerVinculo(id, motivo)`.

⚠️ **Não mande `confirmado_por` no corpo** — o servidor tira do token e ignora o
corpo. Há teste provando.

Códigos que a tela precisa tratar: **409** = já existe vínculo vivo (desfaça o
atual antes) · **404** = campanha ou vínculo inexistente · **403** = papel
revogado.

## 4. Ordem — **a fonte de verdade é o servidor**

`customer_id` → `ordem_operacional` → `volc_campaign_id`.

| degrau | o quê |
|---|---|
| 0 | pede atenção |
| 1 | ligada |
| 2 | pausada |
| 3 | demais estados presentes |
| 4 | histórico |

### ⚠️ `ordenarCampanhas()` precisa sair

`src/components/trafego/hub/ordenarCampanhas.ts`, chamado em
`GrupoDeConta.tsx:254`, reordena **só a página já carregada**. Ele foi correto
enquanto o contrato não tinha ordem; agora tem, e as duas discordam:

- **a partir da página 2** a ordem local é uma ordem *dentro de uma fatia* de uma
  ordem global. O operador vê "atenção primeiro" em cada página e nenhuma
  ordem entre elas;
- os **pesos são outros**: você usa `atenção+ENABLED=0`, `ENABLED=1`,
  `atenção=2`, `PAUSED=3`; o servidor usa atenção como eixo **primário** — uma
  pausada que a conta não confirma sobe na frente de uma ligada que está bem,
  porque a primeira é divergência aberta e a segunda não é nada;
- o desempate é `nome` no cliente e `volc_campaign_id` no servidor. Nome é
  editável no painel do Google; a ordem mudaria sozinha.

**Remova a chamada e o arquivo.** A ordem do servidor já chega pronta.

O `ADAPTACAO.md:17` também precisa perder a linha "sem parâmetro de ordem".

## 5. Ausência e falha — o vocabulário

| campo | `null` significa |
|---|---|
| `reconciliacao` | **a prova falhou** — não "não há campanha" |
| `campanhas_lancadas` | idem. Nunca trate como `0` |
| `manifesto` | o canal não é operado pelo Hub |
| `conta_externa` | ainda não se sabe em que conta a campanha vive |
| `entrega.*` | não foi medido — diferente de `0`, que é zero medido |
| `url_final` | não colhida ainda, ou o anúncio não tem destino |

`sinais.forca` tem **três** degraus: `forte` (observado, com carimbo próprio) ·
`medio` (declarado por nós, pode estar velho) · **`historica`** (observado, **sem**
carimbo próprio — sustenta e não fecha).

`url_final_da_conta` viaja hoje como **`historica`**, não `forte`: o gatilho
preserva a URL entre varreduras e o espelho não distingue "lida agora" de
"preservada". Volta a `forte` quando existir `url_final_lida_em`.

## 6. Filtros que mudaram

| parâmetro | mudança |
|---|---|
| **`incluir_historico`** | **novo**, default `false`. Filtrar por `estado_externo=REMOVED` ou `presenca=removida` **liga o histórico sozinho** — sua `adaptacao.ts` continua funcionando |
| `frescor` | **passou a filtrar de verdade.** Era aceito e ignorado; agora recorta por frescor da conta |
| `totais` | `campanhas` **saiu**. Entraram `operacionais`, `historicas` e `geral`. O rótulo da aba usa `operacionais`; `geral` **não** é o universo — com `busca=FGTS`, `geral` é quantas de FGTS existem contando história |
| `Canal` | seis valores (`VIDEO` e `SHOPPING` entraram — a API os emite). `CanalComManifesto` são os quatro que o Hub opera |
| cursor | **v1 é recusado com mensagem.** Carrega três chaves agora |

## 7. O que muda no seu lado

| arquivo | o quê |
|---|---|
| `hub/ordenarCampanhas.ts` | **remover** — e a chamada em `GrupoDeConta.tsx:254` |
| `hub/ADAPTACAO.md:17` | tirar "sem parâmetro de ordem" |
| `preparar/estados.ts:29` | ler `c.reconciliacao.estado`; tratar `null` como "não foi possível provar", **nunca** como `sem_campanha`. O `?? 0` sai |
| `pages/trafego/CampanhaCanonPage.tsx` | ligar em `pautadorApi.campanhaCanonica()` |
| `inventario/formato.tsx` | ✅ já corrigido por você |

⚠️ **`src/components/trafego/inventario/formato 2.tsx`** — cópia de Drive/Finder
não rastreada, zero imports, e é o **único** erro de tipo acima do baseline de
76. Junto com `EstadosDoInventario 2.tsx`, `Selos 2.tsx` e `useInventario 2.ts`.
Não removi: fora do meu escopo.

## 8. Estado dos gates

backend **716 · 3 falhas herdadas** (ambiente sem `google-ads`) ·
frontend **556/556** · tipos **77 = 76 baseline + 1** (`formato 2.tsx`) ·
build verde · zero token privilegiado no bundle.

**A U0.1 só funciona em produção depois da v9_03 e da v9_04.** As duas estão
prontas, com rollback executável e ciclo provado — e não aplicadas. Enquanto
isso, o filtro `historico` e a ordenação por degrau respondem erro do PostgREST
contra o banco oficial.
