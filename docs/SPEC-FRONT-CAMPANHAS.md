# SPEC — o front de campanhas do VOLC O.S.

> Estado: **v1 em execução**. Escrito em 18/08/2026, depois de medir o banco,
> os flows legados e o engine. Todo número aqui é medido e diz onde.

## 0. O problema, numa frase

O sistema sabe criar campanha, mas **nasce com a estratégia errada** — e a
gestão herda o erro do nascimento. Um front bonito em cima disso só deixa o
erro mais rápido.

## 1. A doutrina (decidida, não inventada)

Estas quatro decisões vieram de operar, foram conferidas contra a documentação
do Google e contra a mecânica da API. Elas mandam no desenho.

| decisão | por quê | fonte |
|---|---|---|
| **Campanha = rei.** Um termo, uma campanha. | Hierarquia do projeto; não se divide um termo em duas campanhas | decisão do operador, 18/08/2026 |
| **Um conjunto.** Não N por sub-intenção, não 2 por match type. | Orçamento é da campanha (`campaignBudgets/{id}`), lance é do grupo (`adGroup.cpcBidMicros`). Dividir só fragmenta o aprendizado do RSA sem separar verba | medido no flow legado; [Google: consolidar em grupos temáticos](https://support.google.com/google-ads/answer/14752782) |
| **Nasce em CPC manual, phrase.** | Broad sem Smart Bidding não tem sinal que filtre a consulta | [Google: broad match pede Smart Bidding](https://support.google.com/google-ads/answer/10195720) |
| **Gradua em 30 conversões** → Maximizar conversões, e **só então** broad. | `TCPA_GRADUATION_CONVS: 30`, lance = CPA real do dia anterior, verba = `max(2× atual, R$30)` | `GOOGLE ADS - New Campaigns Validation`, nó `Code1` |

**O corolário que amarra tudo:** a graduação não é só um evento de lance. É o
evento de estrutura. Match type, estratégia e teto mudam juntos, no mesmo
gatilho. Broad é a recompensa da graduação, não a condição inicial.

### ⚠️ 17/08/2026 — o Smart Bidding mudou, e a graduação ficou mais cara

Desde 17/08/2026, campanhas **limitadas por orçamento** com estratégia **baseada
em meta** (CPA alvo, ROAS alvo) passaram a **convergir para a meta** em vez de
frequentemente entregar abaixo dela. Arbitragem é limitada por orçamento por
definição — nunca sairemos da população atingida.

O que isso faz com esta doutrina:

- **O nascimento em `MANUAL_CPC` não é atingido** — lance manual não é
  estratégia baseada em meta. A decisão da linha 3 desta tabela nos protege por
  consequência, não por previsão: ela foi tomada por causa de broad match, um
  dia antes.
- **A graduação passa a ser o ponto de risco.** Meta folgada virou autorização
  de gasto. Projetado sobre CPA medido em fevereiro: uma campanha que entregava
  R$ 0,099 graduada com o teto da casa (R$ 0,35) convergiria para **3,5× o
  custo por conversão**.
- **Subir o alvo inverteu de significado** — era "permita gastar se precisar",
  virou "gaste".

Análise completa, com a derivação do teto de tCPA a partir do RPC e os números
medidos: **[SMART-BIDDING-2026-08-17.md](SMART-BIDDING-2026-08-17.md)**.

## 2. A arquitetura do front: canal → papel → estrutura

Hoje é só Search. Mas PMax, Display e Geração de Demanda vêm, e o front não
pode ser reescrito a cada um. Então o cockpit é **paramétrico por canal**:

```
CANAL          o que o operador escolhe        o que decorre
─────────────  ──────────────────────────────  ─────────────────────────
SEARCH         keywords + copy + lance         1 ad group, phrase, CPC manual
PMAX           asset group + sinais de público  listing filters, sem keyword
DISPLAY        segmentação + criativo           placements, exclusões
DEMAND GEN     público + criativo (vídeo/img)   asset group, formatos
```

Cada canal declara um **perfil**: que estágios o cockpit mostra, que campos o
pedido carrega, e que provas o `validate_only` roda. O front lê o perfil; ele
não tem `if canal === 'PMAX'` espalhado.

> Só o perfil `SEARCH` está implementado. Os outros três existem como forma no
> tipo, sem tela — deliberadamente, para que a primeira implementação de PMax
> não precise mexer no que já funciona.

## 3. O que o cockpit já tem (medido no código, 18/08/2026)

`/trafego/nova/:opportunityId` — [NovaCampanhaPage.tsx](../src/pages/trafego/NovaCampanhaPage.tsx), 674 linhas:

1. **Origem** — pauta, funil, URL final, vertical
2. **Keywords** — cluster minerado, seleção, volume
3. **Copy** — geração pela cascata, persistida em `pautador_trafego_copy`
4. **Conta** — vínculo e escopo de MCC ([escopo.py](../backend/app/trafego/escopo.py))
5. **Ignição** — [Lancamento.tsx](../src/components/trafego/Lancamento.tsx): a escada
   `prova → escrita → recibo`, com `POST /provar` rodando `validate_only`
   contra a conta real

O alicerce é bom e é raro: `/provar` emite um **Selo**, e `subir()` recusa
payload sem selo. A prova é estrutural, não opcional.

## 4. O que falta — e é o objeto desta v1

**A Mesa de Lance.** O estágio que não existe, e sem ele a campanha nasce
errada:

| hoje | precisa ser |
|---|---|
| `maximize_conversions` fixo no engine | **CPC manual** escolhido no nascimento |
| sem graduação | **regra de graduação declarada** no lançamento |
| campo `conversao` morto (ninguém lê) | **meta de conversão real** (`selective_optimization`) |
| `match_type: 'PHRASE'` cravado no front | decorre do papel, e muda na graduação |

O painel também precisa parar de mentir. Hoje [PainelDoLancamento.tsx:126](../src/components/trafego/PainelDoLancamento.tsx#L126)
avisa, corretamente, que *"o cockpit não escolhe a meta"*. Depois desta v1 ele
escolhe — e o aviso sai.

## 5. Anatomia da Mesa de Lance

Uma escolha, não uma lista de configurações. O operador escolhe **como a
campanha nasce**; estrutura, match type e teto decorrem.

```
┌─ COMO ESTA CAMPANHA NASCE ─────────────────────────────────┐
│                                                             │
│  ● CPC MANUAL              ○ MAXIMIZAR CONVERSÕES           │
│    você controla o clique     o Google controla o leilão    │
│    phrase · 1 conjunto        exige histórico de conversão  │
│                                                             │
│  LANCE          ORÇAMENTO/DIA      META DE CONVERSÃO        │
│  R$ 0,38        R$ 30,00           adviewinterstitial       │
│                                    PURCHASE · muitas/clique │
│                                                             │
│  ── GRADUAÇÃO ────────────────────────────────────────────  │
│  em 30 conversões: → Maximizar conversões                   │
│                    → lance = CPA real do dia anterior       │
│                    → verba = max(2×, R$ 30)                 │
│                    → broad liberado                         │
│  registrada agora; quem executa é o motor de gestão         │
└─────────────────────────────────────────────────────────────┘
```

Três regras de tela:

- **A graduação aparece no nascimento.** Não é configuração futura: é contrato
  que a campanha carrega desde o dia zero, e é o que o motor de gestão vai ler.
- **Nada é inventado.** Se a conta não expõe a meta de conversão, o campo diz
  *"não medido"* — nunca um valor plausível.
- **O que a escolha causa fica visível.** Escolher CPC manual mostra que o
  match type virou phrase. O operador nunca descobre depois.

## 6. Contrato — o que muda no pedido

`ProvarEntrada` ([trafego.py](../backend/app/routers/trafego.py)) ganha campos
**opcionais com padrão**, para não quebrar quem já chama:

```python
canal: str = "SEARCH"                    # SEARCH | PMAX | DISPLAY | DEMAND_GEN
estrategia_lance: str = "MANUAL_CPC"     # MANUAL_CPC | MAXIMIZE_CONVERSIONS
graduacao_em_conversoes: int = 30        # 0 desliga
meta_conversao_id: Optional[str] = None  # -> selective_optimization
```

`conversao: str` fica, **marcado como morto**, até virar
`campaign.selective_optimization.conversion_actions`. O payload exato está
medido no flow `Google Ads Search - Clickup`:

```
ConversionAction  category PURCHASE · type UPLOAD_CLICKS
                  countingType MANY_PER_CLICK · primaryForGoal true
  → CustomConversionGoal
    → conversionGoalCampaignConfig  goalConfigLevel CAMPAIGN
```

## 7. Depois desta v1, nesta ordem

1. **`campaign_funnel_urls` preenchido no `/subir`.** Hoje o operador digita as
   URLs do funil à mão no `FunnelUrlsEditor` — e o Redator já as conhece, porque
   as publicou. Preencher liga `campaign_funnel_urls.url` →
   `fact_page_daily.path`, dando comportamento por página por campanha. É o elo
   mais barato do sistema inteiro.
2. **`funnel_run_id` no `campaigns`.** Coluna existe; medido em 18/08/2026:
   **0 de 3 campanhas preenchidas**. Uma linha no `/subir`.
3. **O sensor contar anúncio visto.** `fact_funnel_daily.avg_ads_per_session`
   está **0,00 em todas as linhas** — o meio da equação de arbitragem
   (`RPC = páginas/sessão × anúncios/página × eCPM/1000`) está cego.
4. **`Proposta` como tipo no backend** — o substantivo comum. Hoje o Árbitro
   fala `tipo_acao`, a `OrientacaoBox` fala markdown e a `OtimizacaoBox` fala
   outro JSON. Sem um substantivo, as telas não compõem.
5. **A fila** em `/trafego`: de "o que posso anunciar" para "o que o sistema
   quer fazer hoje", agrupado por reversibilidade — defesa executa, ajuste
   enfileira, mudança de rota exige a escada.

## 8. O que este spec NÃO faz

- Não mexe em campanha de terceiro. O portão de MCC da casa continua fechado.
- Não abre a trava de escrita. `validate_only` é leitura; criar exige
  autorização explícita, na hora.
- Não implementa PMax, Display nem Geração de Demanda. Só deixa o lugar deles.
