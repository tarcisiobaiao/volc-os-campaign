# Preflight — o primeiro lançamento Search com ledger

*Conta-laboratório Portal Mundo Mais `547-809-6539` · MCC `601-673-9364`*

⚠️ **Nada aqui foi executado.** Nenhuma chamada real ao Google Ads — nem `validate_only` —
saiu nesta sessão. Toda prova rodou contra dublês herméticos e um Postgres descartável.

## 1. O que já está fechado por construção, e não depende de você lembrar

| Trava | Onde vive | O que ela impede |
|---|---|---|
| Conta única | `canario.exigir` (`canario.py:118`) | qualquer conta que não seja a 547-809-6539 |
| Canal único | idem | qualquer canal que não seja SEARCH |
| Teto de verba/CPC | idem | R$ 20/dia e R$ 1,00 de CPC, mesmo pausada |
| Criação pausada obrigatória | idem + `comum.py` | ativação não existe neste fluxo |
| Crédito Up intocável | `escopo.conta_da_casa` | conta financeira fora do caminho |
| Selo do plano | `subir()` 409 | payload que mudou depois da prova |
| Aprovação vinculada | constraint `trafego_item_aprovacao_vinculada_ao_plano` | autorização reaproveitada para outro payload |
| Recibo antes da rede | `trafego_ledger_despachar` | mutate sem rastro local |
| Um voo por item | gatilho `trafego_recibo_um_voo_por_item` | segunda chamada com a primeira em trânsito |
| Ledger ausente | `subir()` 503 | campanha criada sem recibo |

## 2. Pré-condições que EXIGEM você

| # | Condição | Como conferir |
|---|---|---|
| P1 | v10_01 + v10_03 aplicadas | `PREFLIGHT-SUPABASE-OFICIAL.md` §5 |
| P2 | **D4** — grants/RLS fechados e credenciais rotacionadas | `OPEN-DECISIONS.md` D4; smoke anônimo provando zero escrita |
| P3 | **D10** — webhook n8n `apply-bidding` desativado ou autenticado | ele muta lances fora da porta única |
| P4 | Trava de escrita de dois fatores | `destravar()` no código **e** `FORGE_PERMITIR_ESCRITA=1` no ambiente |
| P5 | Backend com `SUPABASE_URL`/`SERVICE_ROLE_KEY` | senão `/subir` responde 503 e nada sai |
| P6 | Operador presente na tela | a confirmação de criação pausada é um clique humano |
| P7 | **Ninguém usa o CLI de escrita** | `python -m volc_ads.subir --subir` (`volc_ads/subir.py:1310`) chama o executor direto, **sem ledger, sem política do canário e sem recibo**. A trava de dois fatores continua valendo, mas com ela aberta esse caminho cria campanha sem rastro local. Ver `RELATORIO-DE-ENTREGA.md` §7 |

## 3. A sequência autorizável, ato por ato

1. **`POST /api/trafego/provar`** — `validate_only`. Não cria nada em desfecho nenhum;
   pode ser repetido à vontade. *Autorização separada, porque toca a conta real.*
2. **Ler o plano na tela.** Grupos, keywords, negativas, RSA, verba, CPC e a URL final.
   A impressão que aparece aí é a que vai ser aprovada.
3. **`POST /api/trafego/subir`** — o único ato que muta. Nesta ordem, verificável:
   `abrir` → leitura de idempotência → `despachar` (recibo `em_voo` commitado) →
   **mutate** → `fechar`.
4. **Conferir o recibo na tela**: desfecho, id na conta, estado do item, número do recibo.
5. **Conferir o veredito de política** com o id externo.

**A ativação não existe em nenhum destes atos** e não é alcançável por esta rota.

## 4. Como saber, DEPOIS, o que de fato aconteceu

```sql
-- o que ficou em aberto (esperado: 0 linhas num lançamento bem-sucedido)
SELECT r.recibo_id, r.item_id, r.idempotency_key, r.tentativa, r.desfecho,
       now() - r.enviado_em AS ha
  FROM public.trafego_recibo r
 WHERE r.desfecho IN ('em_voo','sem_resposta') ORDER BY r.enviado_em;

-- a campanha, ponta a ponta
SELECT i.estado, i.id_externo, i.id_externo_lido_em, i.volc_campaign_id,
       i.aprovado_por, i.aprovado_em, i.tentativas
  FROM public.trafego_lote_item i WHERE i.id_externo IS NOT NULL;
```

## 5. Se a resposta não vier

**NÃO REENVIE.** O sistema já está construído para isso, e a tela diz isso — mas vale
escrito:

1. o recibo fica `em_voo` ou `sem_resposta`, e o item vira `indeterminado`;
2. `/subir` responde 504 com `reenvio_permitido: false` e o `recibo_id`;
3. a próxima ação é **verificar na conta** e chamar `trafego_ledger_reconciliar`, que
   fecha **o mesmo recibo**;
4. o banco recusa qualquer nova tentativa enquanto houver recibo sem desfecho — a recusa
   é estrutural, não uma convenção.

⚠️ **Uma consequência que você precisa aceitar antes:** depois de um `sem_resposta`, esse
plano **não volta a ser enviável** por esta rota, nem após a verificação. É *fail-closed*
deliberado, herdado da camada 3 da v10_01. Se a verificação provar que a campanha **não**
foi criada e você quiser relançar, isso hoje exige uma decisão sua (mudar o plano gera
chave nova; afrouxar a guarda é mudança de contrato). Está registrado em
`ROLLBACK-…md` §3 como item aberto.

## 6. O que continua proibido depois deste lançamento

Ativar a campanha · tocar a Crédito Up · qualquer outra conta · qualquer outro canal ·
segundo lançamento sem reconciliar o primeiro.
