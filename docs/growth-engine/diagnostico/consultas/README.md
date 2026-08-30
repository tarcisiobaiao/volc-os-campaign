# Como reproduzir este diagnóstico

Tudo aqui é **somente leitura**. Nenhum arquivo desta pasta é capaz de alterar uma
conta: `rodar.py` só chama `search_stream`, não importa `mutar` nem `destravar`, e
recusa qualquer GAQL que não comece em `SELECT`.

## Rodar

```bash
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign

PYTHONPATH="$PWD:$PWD/backend" backend/.venv/bin/python \
  docs/growth-engine/diagnostico/consultas/rodar.py \
  --saida docs/growth-engine/diagnostico/evidencia.json
```

Uma consulta só, para comparar contra a linha de base depois de uma mudança:

```bash
PYTHONPATH="$PWD:$PWD/backend" backend/.venv/bin/python \
  docs/growth-engine/diagnostico/consultas/rodar.py \
  --apenas metricas_desde_o_lancamento keywords --saida -
```

Opções: `--conta` (padrão `8017851692`), `--janela` (padrão `LAST_30_DAYS`),
`--apenas <nomes>`, `--saida` (`-` para stdout).

## Garantias

| garantia | onde é imposta |
|---|---|
| só `SELECT`, sem `;` | `_exigir_select()`, antes de qualquer rede |
| só a árvore do MCC da casa | `app.trafego.escopo.exigir_escopo()`, antes de qualquer rede |
| toda chamada sob `login_customer_id=6016739364` | `rodar()` passa `mid` a `cliente()` |
| nenhuma escrita possível | o módulo não importa `mutar` nem `modo.destravar` |
| trava de escrita registrada no resultado | `_meta.modo_de_escrita` grava `modo.estado()` |
| nenhum segredo em disco | credenciais ficam no `~/google-ads.yaml` que o SDK carrega; nada é lido ou impresso daqui |

A falha de uma consulta **não derruba as outras**: cada uma roda no seu `try` e,
se falhar, entra no JSON como `{"ok": false, "erro": "<mensagem literal da API>"}`.
"Não consegui ler" e "não existe" são fatos opostos, e a saída os mantém separados.

## Formato da saída

```jsonc
{
  "_meta": {
    "lido_em_utc": "...",           // carimbo da leitura
    "customer_id": "8017851692",
    "login_customer_id": "6016739364",
    "versao_api": "v25",
    "janela_das_metricas": "LAST_30_DAYS",
    "modo_de_escrita": { "escrita_permitida": false, ... },
    "somente_leitura": true
  },
  "consultas": {
    "<nome>": {
      "gaql": "SELECT ...",         // a query literal que produziu as linhas
      "por_que": "...",             // a pergunta que ela responde
      "lido_em_utc": "...",         // carimbo por consulta
      "ok": true, "n": 5, "linhas": [ ... ]
    }
  }
}
```

## Armadilhas medidas na v25 — em 26/08/2026

Todas descobertas rodando contra a conta real; a correção já está no `rodar.py`.

| sintoma | causa | correção |
|---|---|---|
| `Unrecognized fields: 'campaign.start_date', 'campaign.end_date'` | renomeados na v25 | usar **`campaign.start_date_time` / `end_date_time`** |
| `Cannot select ... 'search_budget_lost_impression_share' ... 'KEYWORD_VIEW'` | métrica incompatível com o recurso | só existe em `campaign`; em `keyword_view` e `ad_group` não |
| `Cannot select ... 'conversions' ... 'CONVERSION_ACTION'` | idem | usar `metrics.all_conversions` |
| `Unrecognized fields: 'recommendation.campaign_budget_recommendation.*'` | subcampos não selecionáveis | selecionar só `recommendation.type/campaign/dismissed/campaign_budget` |
| `GoogleAdsFieldService` recusa `WHERE name LIKE '...'` | sintaxe não suportada | inspecionar o **proto local** do SDK (`Campaign.pb(...).DESCRIPTOR.fields`) — offline e confiável |

## ⚠️ A armadilha que produz conclusão errada sem produzir erro

**O `criterion_id` de uma keyword é COMPARTILHADO entre campanhas.** As cinco
campanhas desta conta são irmãs criadas do mesmo brief e repetem os mesmos
`criterion_id`. Juntar `keywords` com `keywords_estimativas` ou
`keywords_metricas` **apenas por `criterion_id`** mistura campanha viva com
removida — e o resultado sai plausível, sem erro nenhum.

Foi exatamente o que aconteceu na primeira passagem deste diagnóstico: as
estimativas da Maquininha viva apareceram atribuídas à removida, e as duas vivas
pareceram não ter estimativa alguma.

**A chave correta é `(ad_group.id, ad_group_criterion.criterion_id)`** — e é por
isso que a consulta `keywords_estimativas` seleciona `campaign.id` e `ad_group.id`
mesmo sem "precisar" deles para a estimativa.

## Notas de interpretação

- **`LAST_30_DAYS` não inclui hoje.** Por isso existem as consultas
  `metricas_hoje` (`DURING TODAY`) e `metricas_desde_o_lancamento`, esta última
  com datas explícitas (`BETWEEN '2026-08-19' AND '2026-08-26'`) em vez de apelido.
- **`0,0999` e `0,9001`** são os valores-limite que a API usa para reportar
  "< 10%" e "> 90%" de parcela de impressões. Não são medidas exatas.
- **Ausência não é zero.** Um campo que não aparece na linha **não foi devolvido**.
  `search_budget_lost_impression_share: 0.0` (devolvido, igual a zero) e um campo
  ausente são fatos diferentes, e o diagnóstico depende dessa distinção.
- **`change_event` cobre no máximo 14 dias** e exige `LIMIT`. Fora dessa janela não
  há forense disponível pela API.
