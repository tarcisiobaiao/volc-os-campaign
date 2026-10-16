# Pré-registro — Swarm Lab (worker E, Fase 5)

Escrito em 2026-10-16T00:08-0300, **antes** de rodar os grids de resultado.
O sha256 deste arquivo é gravado no manifesto de cada JSON de resultado; os scripts
`scripts/swarm_*.py` recusam rodar se ele não existir. Qualquer mudança posterior
neste texto muda o hash e fica visível.

Natureza: **simulação sintética com seed**. Nenhuma célula é campanha real; nada
aqui é "validado".

## Divulgação do piloto (antes deste pré-registro)

Para depurar o código rodei um piloto de 40 seeds (seeds 0..39) em 4 configurações
(base D=3; ideal sem saturação/D=0/ruído baixo; vencedoras lentas D=3 e D=6). O
piloto informou só correções de definição feitas antes deste texto: (a) "top-k
verdadeiro" passou a considerar apenas células com contribuição positiva; (b) o ASHA
passou a escolher a produção como as n_final melhores do último rung entre
`n_topo = n_final·eta` concluídas (antes promovia as primeiras a terminar).
Os grids oficiais usam seeds **disjuntas** do piloto: `seed = 1_000_000 + i`, i = 0..199.

## Pergunta

"ASHA/SH supera random, equal e greedy sem aumentar falsos vencedores ou drawdown?"

## Critério de decisão (por cenário e por candidato)

Candidatos: `sh_parcial`, `sh_madura`, `asha_parcial`, `asha_madura`.
Baselines simples: `equal`, `random_sh` (cronograma do SH com promoção aleatória),
`greedy_parcial`, `greedy_madura`. **Melhor baseline** = o de menor regret médio no
cenário (escolhido depois de rodar, o que favorece o baseline — é conservador para SH/ASHA).

O candidato **supera** no cenário se, e somente se, as três condições valem:

1. **Regret**: o IC95 de Monte Carlo do regret médio do candidato fica inteiro
   abaixo do IC95 do melhor baseline (ICs não se cruzam: limite superior do
   candidato < limite inferior do baseline). IC normal, n = 200 seeds.
2. **Falsos vencedores** (métrica primária): média de `frac_orcamento_perdedoras_final`
   do candidato ≤ limite superior do IC95 do melhor baseline.
   (`frac_orcamento_perdedoras_final` = fração do orçamento dos 5 últimos ciclos
   alocada em células com contribuição verdadeira ≤ 0. É comparável entre todas as
   políticas, inclusive `equal`, que não "promove".) A taxa de falso vencedor por
   célula promovida (promovida com contribuição ≤ 0 ou fora do top-k verdadeiro) é
   reportada como secundária e não entra no critério.
3. **Drawdown**: média do drawdown máximo do lucro acumulado realizado (receita
   madura − gasto) do candidato ≤ limite superior do IC95 do melhor baseline.

A diferença pareada por seed (candidato − melhor baseline) também é reportada,
mas **não** substitui a regra 1.

## Regra do veredito global (grid principal de 12 cenários)

- `não`: nenhum candidato supera em nenhum cenário.
- `sim em simulação (todas as condições testadas)`: algum candidato supera em todos os 12.
- `depende de Y`: supera em alguns e não em outros; reporto a lista X de cenários em
  que supera e o(s) fator(es) Y que separam os casos. Resultado negativo é preservado.

Multiplicidade: 12 cenários × 4 candidatos = 48 comparações. A regra de ICs que não
se cruzam é muito mais estrita que p < 0,05 por comparação, mas não há correção
formal; um "supera" isolado em um único cenário deve ser lido como frágil.

## Hipóteses secundárias pré-registradas

- H1 (contraprova de risco): com maturação heterogênea em que as vencedoras maturam
  devagar (`vencedoras_lentas`) e atraso D ≥ 3, `sh_parcial` poda incorretamente mais
  células do top-k verdadeiro que `sh_madura` (diferença pareada com IC95 > 0).
- H2: com maturação **uniforme** entre células, decidir por receita parcial não piora a
  ordenação do SH (o fator de maturação é igual para todas as vivas, que gastaram nos
  mesmos ciclos); logo `sh_parcial` tem regret ≤ `sh_madura` (que paga a espera).
- H3: ASHA é mais sensível que SH ao atraso parcial, porque células comparadas no
  mesmo rung chegaram a ele em ciclos e idades diferentes.
- H4: com saturação (capacidade de escala), o valor observado em gasto baixo
  (rung 0) correlaciona pior com o valor na escala de produção do que com v —
  a premissa de "baixa fidelidade informativa" do ASHA enfraquece.

## Grids (fixos)

Parâmetros comuns: K=16 células, T=30 ciclos, orçamento R$960/ciclo (micros int),
mínimo R$10 por célula ativa, CPC R$2, top_k=4. Políticas: n_final/n_top=4, degraus
SH/ASHA (60, 180) cliques, eta=2, ASHA 8 slots, greedy janela 3 e passo λ=0,3, Thompson
top-4 (extensão, fora do veredito). `madura` usa `atraso_assumido` = D verdadeiro do cenário.

**Grid principal (200 seeds cada)**: base (D=3, maturação uniforme, valor/evento R$8,
estacionário, sem interferência, saturação padrão); sem_atraso (D=0); atraso_6;
vencedoras_lentas_D3; vencedoras_lentas_D6; maturacao_por_canal_D3; ruido_baixo
(R$2/evento); ruido_alto (R$30/evento); nao_estacionario (troca da vencedora em T/2);
interferencia (rho=0,5); ideal_sem_saturacao (cap ×100, D=0, R$2/evento);
adverso (D=6, vencedoras lentas, troca em T/2, rho=0,5, R$30/evento).

**Grid de parâmetros de SH/ASHA (200 seeds)** em base, vencedoras_lentas_D3 e
ideal_sem_saturacao: eta ∈ {2, 3} × primeiro degrau ∈ {20, 60, 150} cliques (segundo =
3× o primeiro) × decisão ∈ {parcial, madura}; mais unidade = gasto (R$120/R$360) para
eta=2; mais n_final ∈ {1, 2, 4} (greedy/Thompson com n_top igual).

**Grid de sensibilidade (200 seeds)**: D ∈ {0, 1, 3, 6} × maturação ∈ {uniforme,
vencedoras_lentas} × valor/evento ∈ {R$2, R$8, R$30} × não estacionariedade ∈ {não, sim}
(48 cenários), políticas equal, random_sh, greedy_p/m, sh_p/m, asha_p/m.

**Diagnóstico do mapeamento ASHA**: correlação de Spearman entre o ROI observado no
rung 0 (parcial e madura) e (i) v verdadeiro, (ii) valor por R$ na escala de produção;
viés parcial/madura por classe de maturação.
