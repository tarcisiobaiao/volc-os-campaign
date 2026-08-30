# A mudança do Smart Bidding de 17/08/2026 — e o que ela faz com a arbitragem

> Escrito em 19/08/2026. Fonte oficial:
> [Alterações nas estratégias de lances com metas](https://support.google.com/google-ads/answer/17061251?hl=pt).
> Todo número desta página foi medido em `daily_campaign_metrics` na conta da
> casa, e diz a janela.

## 1. O que mudou, na letra do Google

Vigora desde **17/08/2026**. Atinge campanhas **limitadas por orçamento** que
usam **estratégia baseada em meta** (CPA alvo, ROAS alvo).

> *"campanhas limitadas por orçamento que usam uma estratégia de lances baseada
> em meta terão desempenho mais consistente com base na meta de lance, mesmo se
> você fizer ajustes de orçamento"*

E o exemplo que o próprio Google dá é a coisa toda:

> *"se uma campanha tem meta de CPA de 10 € mas atinge 5 € de CPA, a campanha
> vai se aproximar de 10 € de CPA real"*

**Antes**, uma campanha travada no orçamento frequentemente entregava melhor do
que a meta — a meta era um teto que sobrava. **Agora** ela converge para a meta.
O que era folga virou custo.

Canais atingidos: Search, Shopping, Performance Max, Demand Gen, Display
(parcial), Hotéis (parcial), Viagens. **Não atinge** campanhas de app, alcance
de vídeo e visualização de vídeo.

## 2. Por que isto é sobre nós, e não sobre "algumas campanhas"

Arbitragem de display é **limitada por orçamento por definição**. O teto de verba
não é uma limitação que a gente pretende remover quando puder — é o controle de
risco. Nunca sairemos da população atingida.

Ou seja: a exceção que o Google cita ("se suas campanhas não têm restrição de
gastos, provavelmente não serão afetadas") **não vale para este negócio**.

## 3. O número que decide tudo: conversões por clique

A identidade que liga as duas pernas da arbitragem:

```
k    = conversões ÷ cliques
CPA  = CPC ÷ k
```

Medido na conta, janela **12/02 a 19/02/2026**, `daily_campaign_metrics`:

| campanha | cliques | conversões | **k** | CPC | CPA real |
|---|---:|---:|---:|---:|---:|
| 23518009650 | 6.032 | 4.084,5 | **0,677** | R$ 0,067 | R$ 0,099 |
| 23518661646 | 2.104 | 1.423,0 | **0,676** | R$ 0,056 | R$ 0,083 |
| 23524108985 | 622 | 501,0 | **0,805** | R$ 0,198 | R$ 0,246 |

A identidade fecha: `0,067 ÷ 0,677 = 0,099`. ✅

⚠️ **`k` é menor que 1**, apesar de `countingType: MANY_PER_CLICK`. Ou seja: nem
todo clique gera uma visualização de anúncio contada. Isso contraria a intuição
de que "várias views por sessão" produziria k > 1 — e é medido, não suposto.

## 4. O dano concreto, com os números da casa

O teto de tCPA da casa é **R$ 0,35** (`MAX_TCPA_BRL`, medido no flow
`GOOGLE ADS - New Campaigns Validation`, nó `Code1`). Aplicando a mudança às
campanhas reais medidas acima:

| campanha | CPA que ela entregava | se graduar com tCPA R$ 0,35 | efeito |
|---|---:|---:|---|
| 23518009650 | R$ 0,099 | → converge para R$ 0,35 | **×3,5 no custo por conversão** |
| 23518661646 | R$ 0,083 | → converge para R$ 0,35 | **×4,2** |
| 23524108985 | R$ 0,246 | → converge para R$ 0,35 | **+42%** |

Antes de 17/08 isso era teoria: o algoritmo entregava R$ 0,099 e ignorava a
folga até R$ 0,35. Depois de 17/08, a folga é uma autorização de gasto.

**Traduzido para a equação da arbitragem:** `SPREAD = RPC − CPC`, e
`CPC = CPA × k`. Triplicar o CPA triplica o CPC e come o spread inteiro.

## 5. O que isto muda no nosso engine

### 5.1 O nascimento está do lado certo — por sorte da doutrina

Desde 18/08 a campanha nasce em **`MANUAL_CPC`**
([SPEC-FRONT-CAMPANHAS.md §1](SPEC-FRONT-CAMPANHAS.md)). Lance manual **não é
estratégia baseada em meta** — não é atingido.

Sejamos honestos sobre a causalidade: essa decisão foi tomada por causa de
broad match e sinal de leilão, um dia antes desta mudança aparecer no radar.
Ela nos protege por consequência, não por previsão.

### 5.2 A graduação é onde a mudança morde

A regra medida no legado (`Code1`): ao atingir 30 conversões, troca para
`MAXIMIZE_CONVERSIONS` com **`newValue = m.spend / m.convs`** — o CPA real do
dia anterior — e **dobra o orçamento**.

Sob o regime novo isso vira duas coisas ao mesmo tempo:

- **A boa notícia:** definir a meta = CPA observado é exatamente o
  comportamento correto agora. Não há folga a perder, porque não há folga.
- **A má notícia:** dobrar o orçamento junto reduz a restrição, e qualquer meta
  acima do CPA observado passa a ser gasto autorizado, não teto de segurança.

### 5.3 A escalada de lance inverteu de significado

O ORAKUL e o validador legado sobem o alvo em **+15%** quando a campanha perde
impressão por rank (`BID_INCREMENT_STEP: 0.15`, com `IS_RANK_THRESHOLD: 0.25`).

| | antes de 17/08 | a partir de 17/08 |
|---|---|---|
| subir o tCPA | *"permita gastar mais SE precisar"* | *"gaste mais"* |
| baixar o tCPA | efeito incerto (já entregava abaixo) | efeito direto e confiável |

**Subir a meta deixou de ser barato.** O gatilho hoje é perda de impressão por
rank — um sinal de leilão, não de economia. Sob o regime novo, subir a meta sem
provar que o RPC comporta é comprar volume com margem.

### 5.4 Existe uma bifurcação real na graduação

- **`MAXIMIZE_CONVERSIONS` sem alvo** — não é estratégia baseada em meta.
  **Não é atingida.** Gasta o orçamento buscando volume.
- **`MAXIMIZE_CONVERSIONS` com `target_cpa_micros`** — é baseada em meta.
  **É atingida.** Converge para o alvo declarado.

No nosso engine ([`campanha/comum.py`](../volc_ads/campanha/comum.py)) isso já é
literal: `if brief.tcpa: ... target_cpa_micros = micros(tcpa) else: 0`. Zero
significa sem alvo. **A escolha entre as duas passou a ser uma decisão de
regime, não um detalhe de preenchimento.**

## 6. O teto de tCPA que a arbitragem permite — derivado, não arbitrado

Da identidade da §3 e de `SPREAD > 0`:

```
SPREAD > 0  ⟺  RPC > CPC  ⟺  RPC > CPA × k  ⟺  CPA < RPC ÷ k
```

Com o `k ≈ 0,70` medido: **tCPA máximo ≈ RPC × 1,43**.

Isso dá um teto **calculado a partir da receita medida**, e não herdado de um
número que alguém escolheu uma vez. É a forma certa de definir a meta no regime
novo, porque a meta agora É o gasto.

### Uma inconsistência que a derivação revelou

Os dois tetos da casa não conversam entre si:

- `MAX_CPC_BRL = 0,50` → com k = 0,70, corresponde a CPA de **R$ 0,714**
- `MAX_TCPA_BRL = 0,35` → com k = 0,70, corresponde a CPC de **R$ 0,245**

O teto de tCPA é **menos da metade** do teto de CPC, medido no mesmo k. Pode ser
deliberado — exigir economia melhor sob automação do que sob controle manual —
ou pode ser resíduo. **Não sei qual, e não vou supor.** Mas depois de 17/08 a
diferença deixou de ser acadêmica: o tCPA agora é gasto efetivo.

## 7. O que fazer, na ordem

1. **Não graduar com meta folgada.** Se o CPA observado é R$ 0,099, a meta na
   graduação é R$ 0,099 — não o teto da casa. O ORAKUL já faz isso; o que não
   pode é alguém "arredondar para cima por segurança", que agora é o contrário
   de segurança.
2. **A Mesa de Lance precisa dizer isto** na linha da graduação. Hoje ela
   promete *"lance = CPA real do dia anterior"* sem explicar que, desde 17/08,
   esse número é o que será gasto e não um limite.
3. **O teto de tCPA deve virar função do RPC**, não constante — `RPC ÷ k`, com
   ambos medidos. Depende de a receita voltar a fluir (`joinads_metrics` está
   vazia; ver [SPEC-FRONT-CAMPANHAS.md §7](SPEC-FRONT-CAMPANHAS.md)).
4. **Reler a regra de escalada de lance do ORAKUL** antes de portá-la para o
   backend. `+15% por perda de rank` foi calibrado num regime que acabou.
5. **Considerar graduar para MaxConv SEM alvo** enquanto não houver RPC medido
   para calcular o teto. Sem alvo não há convergência para alvo — o risco vira
   o orçamento, que já é controlado.

## 8. O que este documento NÃO afirma

- Não medi o efeito depois de 17/08: a operação está reiniciando e
  `daily_campaign_metrics` termina em 25/06/2026. Os números da §4 são
  **projeções da regra declarada pelo Google** sobre CPA medido em fevereiro,
  não observação.
- Não sei se a inconsistência da §6 é intencional.
- A Ferramenta de Ajuste de Metas que o Google cita (disponível desde
  06/07/2026) não foi aberta nem avaliada.
