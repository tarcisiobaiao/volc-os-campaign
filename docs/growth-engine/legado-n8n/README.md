# Legado n8n — o conhecimento operacional de mídia paga, inventariado

> Agente G · missão **Google Growth Engine do VOLC OS** · 26/08/2026
> Ownership de escrita: `docs/growth-engine/legado-n8n/` — nada além disso.

## O que esta pasta responde

O VOLC OS vai ganhar um motor de autogestão de campanhas. Antes de escrever a
primeira regra, é preciso saber **o que a casa já sabia** — porque isso está
preso dentro de 32.570 linhas de JavaScript e Python que moram em JSONs do n8n,
sem teste, sem git e sem como rodar local.

Esta pasta separa três coisas que estavam misturadas:

1. **o que vale absorver** — regras compradas com dado real, que faltam ao VOLC OS;
2. **o que é universal demais para reimplementar como está** — as regras do tipo
   *"CPA acima de X pausa"*, *"aumente sempre 20%"*, *"sem conversão em um dia
   significa campanha ruim"*, que a missão proíbe reproduzir;
3. **onde o legado e o VOLC OS já disputam o mesmo número** — o achado mais
   importante, em `conflitos.md`.

| Arquivo | O que é |
|---|---|
| `README.md` | este sumário |
| `fichas.md` | **48 fichas**, agrupadas por tema, com destino canônico para cada regra |
| `regras-canonicas.json` | **19 políticas propostas**, legíveis por máquina, no formato que o motor de autogestão vai consumir |
| `conflitos.md` | **11 pontos de autoridade paralela** e o que fazer com cada um |
| `MANIFESTO-PROPRIEDADE.json` | identidade, SHA-256, classificação e sucessor dos nove workflows resgatados em 28/08/2026 |

## Complemento de 28/08/2026

O núcleo sanitizado passou de 30 para **33 workflows** com a inclusão read-only de
GTM/scroll do funil, congruência de CTA e RSA Darwin. O recorte original de 48
fichas e 19 políticas continua válido como análise da primeira leva; não foi
silenciosamente recontado. A segunda ingestão está documentada em
`docs/architecture/RESGATE-INTELIGENCIA-N8N-ORAKUL-PREDITIVO.md` e no manifesto.

O export sanitizado continua privado e ignorado pelo Git. Sanitização é uma rede
de segurança, não autorização para publicar JSONs: Code nodes podem conter
configuração ou segredo em texto livre que um filtro por nome de campo não
reconheça.

## Como isto foi feito, e o que não foi feito

**Fonte primária:** `inventario-n8n/` — uma extração read-only da instância de
produção do n8n feita em **19/08/2026** pela API, já sanitizada, e que **está no
`.gitignore` e nunca deve ser versionada**. Grande parte da leitura pesada já
estava feita ali; este trabalho não a refez.

**O que eu acrescentei:** reconferi contra os JSONs no disco, em 26/08/2026, todo
literal que entrou nas fichas e no JSON canônico — as constantes `CONFIG` dos dois
motores NEXUS, o objeto `THRESHOLDS` do robô de search terms, a contagem de nós de
mutate por endpoint e por flow, o destino de cada escrita (hospedado × self-hosted)
e o estado `ativo` de cada `.meta.json`. Onde a minha medição **divergiu** dos
documentos do inventário, o texto diz isso — o caso mais relevante está na seção
de segredos de `conflitos.md`.

**Portões que permaneceram fechados:** nenhum workflow n8n foi ativado, editado,
disparado ou importado; nenhuma chamada à API do n8n; nenhuma chamada ao Google
Ads; nenhum segredo, token, webhook ou URL com chave embutida foi transcrito.
Leitura de JSON em disco, apenas.

---

## O tamanho da coisa

| | |
|---|---:|
| workflows no núcleo do inventário atual | **33** |
| deles, **tocam operação de mídia paga** | **17** |
| dos 17, **escrevem em algum lugar** | **14** |
| dos 17, escrevem **no Google Ads** | **5** |
| dos 17, escrevem **em banco** | **12** |
| dos 17, **ativos declarados no n8n** | **10** |
| ativos declarados **que escrevem no Google Ads** | **3** |
| regras inventariadas (fichas) | **48** |
| delas, **universais demais para reimplementar como estão** | **10** |
| políticas propostas em `regras-canonicas.json` | **19** |
| pontos de **autoridade paralela** | **11** |

Os 13 flows fora do recorte são as 10 camadas de receita (GAM, AdSense, JoinAds),
os 2 de pauta editorial e 1 de dashboard de receita. Eles só aparecem aqui quando
alimentam uma decisão de mídia — e aí registro só a interface.

**Distribuição dos destinos canônicos** entre as 48 fichas:

| Destino | Fichas |
|---|---:|
| ① política versionada do domínio | 26 |
| ② job que chama o backend canônico | 6 |
| ③ absorvido — já existe no VOLC OS | 6 |
| ④ descartar | 4 |
| ⑤ decidir depois | 6 |

---

## As 5 regras que mais valem a pena absorver

Critério: **defensável** (não é uma régua universal disfarçada de política),
**ausente** do VOLC OS hoje, e **barata** de implementar em relação ao dano que
evita. Todas as cinco vêm do `orakul-vos-auto-adjust` — o único motor do legado
com execução comprovada — e todas as cinco já estão em `regras-canonicas.json`.

### 1. Modo de validação por idade da campanha — `modo_de_validacao_por_idade`
`EXPLORATION` (< 7 dias) · `CALIBRATION` (7–13) · `PRODUCTION` (≥ 14), com teto de
corte e histerese diferentes por modo, e otimização desligada em EXPLORATION.
**É a defesa mais importante do legado inteiro**: impede que o otimizador mate uma
campanha antes de o algoritmo do Google convergir. Ficha C01.

### 2. Piso de verba e teto de perda — `piso_de_verba_e_teto_de_perda`
`floor = max(budget × 0.30, min(10, budget))`; perda máxima do dia `budget × 0.30`
e de 3 dias `budget × 3 × 0.60`, relaxados para `0.45`/`0.75` em campanha provada.
**Perda controlada com piso de aprendizado é a essência da arbitragem** — apostar
sem quebrar, e sem zerar o sinal que já foi comprado. Ficha C06.

### 3. Histerese em dias consecutivos — `histerese_de_dias_consecutivos`
Dois dias ruins para cortar, três a cinco para pausar, dois dias bons para
escalar — com contadores separados para subir e para descer. **Elimina a maior
parte do ruído diário sem precisar de teste estatístico**, e é a mais barata de
implementar das cinco. Ficha C05.

### 4. Evento externo pelo desacoplamento compra × venda — `evento_externo_desacoplamento`
eCPM cai mais de 20% **e** o CPC não se move mais de 15% ⇒ o problema é do lado
venda, não do leilão. Efeito: relaxa a tolerância, adia a pausa, segura a mão.
**É exatamente o diagnóstico que um operador humano faria**, e é barato.
Correção obrigatória de escopo: deve ser um serviço avaliado **uma vez por dia
sobre o portfólio**, não recalculado por campanha. Ficha D02.

### 5. O lance ancorado no RPC medido — `lance_ancorado_no_rpc`
`cpc_alvo = rpc_3d × Π(multiplicadores)` e `tCPA = cpc_alvo / max(cvr, 0.01)`.
**Amarrar o lance ao que o clique rendeu, e não a uma meta de CPA escolhida por
alguém, é literalmente a definição de arbitragem.** Vai com o teto **derivado**
(`tCPA_max = RPC ÷ k`, com `k` medido — foi 0,677 / 0,676 / 0,805 nas três
campanhas da casa) em vez das constantes herdadas, porque depois de **17/08/2026**
o tCPA deixou de ser teto e virou gasto autorizado. Ficha C02.

**Menção obrigatória — a forma em que as cinco se encaixam.** O
`orakul-predictive-integrado-v1` tem o desenho conceitualmente mais limpo do
legado: **o motor propõe, o árbitro veta**, com vetos independentes
(comportamental, temporal, preditivo) e um `motivos[]` textual que dá
auditabilidade sem esforço. A geração seguinte removeu o árbitro e ficou pior.
Junto com ele vai a fila de ações do BEAST, que separa `executavel_base` (mérito)
de `executavel` (permissão temporal) — é o que permite dizer ao operador **por que**
uma ação não rodou. Fichas C10 e C11.

---

## As 10 regras universais demais para reimplementar como estão

Nenhuma destas pode entrar no motor com os números do legado. Cada ficha traz o
que faltaria para torná-la defensável.

| Ficha | Regra | Por que é universal demais |
|---|---|---|
| **E03** | `CPA > R$ 5,00` mata a keyword mesmo convertendo | O caso-livro de *"CPA acima de X pausa"*. O teto correto **não é um número, é uma função**: `CPA < RPC ÷ k`. E os CPAs reais medidos ficam **20 a 50 vezes abaixo** de R$ 5,00 — o teto provavelmente nunca disparou e ninguém percebeu. |
| **C07** | Gastou R$ 15 e receita zero ⇒ pausa | *"Sem conversão em um dia significa campanha ruim"*, agravado por artefato de medição: às 18:30 o dia parcial entra com custo completo e receita não aterrissada. A condição fica verdadeira **por atraso de dado**. |
| **A03** | CTR > 3% ⇒ subir lance +25% | *"CPC baixo é sempre o problema"*. Passo fixo, sem olhar spread nem distância até o alvo — e CTR alto com RPC baixo é motivo para **baixar** o lance. |
| **A07** | Perdeu por verba ⇒ +25%; perdeu por rank ⇒ +15% | O **diagnóstico é bom**, o remédio é *"aumente sempre 20%"*. E depois de 17/08 subir a meta deixou de ser barato. |
| **A05** | Zero impressão ⇒ lance fixo R$ 0,15 | Número mágico sobrescrevendo a decisão anterior. Zero impressão tem cinco causas e **quatro não melhoram com lance maior**. → **descartada**. |
| **A04** | 100 impressões e CTR ≤ 1% ⇒ relevância crítica | **100 impressões não decidem CTR**: com CTR real de 1%, zero cliques é resultado comum de campanha saudável. |
| **A02** | Utilização < 30% ou < 500 impressões ⇒ inércia | Absolutos, sem referência a canal, vertical, geo ou tamanho de verba. Uma campanha de R$ 10/dia e uma de R$ 500/dia recebem a mesma régua. |
| **E02** | Vampiro (3 cliques), fantasma (100 imps), lixo (50 imps) | **Três amostras que não sustentam a decisão.** Com a CVR da casa, 3 cliques sem conversão é resultado esperado de keyword boa. |
| **E04** | Promover com 5 cliques e 2 conversões | Promover ruído. Erro **barato e reversível**, ao contrário do da E03 — mas continua sendo amostra escolhida, não derivada. |
| **D01** | Anomalia por z-score \|z\| > 2,0 (ou 2,5) | Z-score sobre **7 pontos**: o desvio amostral é instável e a própria observação anômala entra no cálculo da base, mascarando-se. E os dois limiares divergem no mesmo sistema. |

O padrão que atravessa as dez: **o diagnóstico costuma estar certo e o remédio
costuma ser uma constante**. O que falta em quase todas é a mesma lista — janela
mínima, atraso de conversão declarado, amostra derivada da taxa observada em vez
de escolhida, teto calculado em vez de herdado, cooldown lido de atuação real e
condição de rollback.

---

## Os 11 pontos de autoridade paralela

Detalhe completo em `conflitos.md`. Em uma linha cada, por gravidade:

🔴 **1.** O **webhook de bidding** (`atuacao-apply-bidding-webhook-v2`) está
**ativo**, sem autenticação, sem limite de valor — e a URL está **hardcoded no
bundle do front**, em `src/components/campaign/BiddingActionBox.tsx:123`,
verificado hoje neste branch. É uma escrita não autenticada, feita de fora, direto
na conta de mídia.
🔴 **2.** **Seis formulários públicos** da Factory v3 criam campanha na conta de
mídia (73 nós de mutate). Mitigação real: tudo nasce `PAUSED`.
🟠 **3.** Arrastar um card no **ClickUp** sobe uma campanha (18 mutates). Está
quebrado no segundo passo — e a correção é de duas linhas.
🟠 **4.** A tabela **`campaigns` tem dois donos** (a RPC do legado e
`backend/app/routers/trafego.py:1507`), e um trigger **apaga a procedência**:
`status_source = 'volc_os'` é inalcançável por construção.
🟠 **5.** **Split-brain de banco**: 271 endpoints no Supabase hospedado contra 30
no self-hosted que o produto lê. É a prioridade 2 da curadoria.
🟠 **6.** **Force update sem autenticação** dispara 99 nós e centenas de chamadas
à Google Ads API — negação de serviço da medição.
🟡 **7.** A **orientação diária** é gravada dentro da tabela de fato, com
`orientacao_gerado_em DEFAULT now()` — 92 linhas carimbadas contra 12 com decisão.
🟡 **8.** **Dois sistemas** decidem quem enxerga qual campanha (o vínculo por
`change_event` e o `volc_role_of()` do Hub).
🟡 **9.** O **BEAST** está inativo, mas é o único com execução comprovada — 10
mutações — e reativar é um clique.
🟡 **10.** O **robô de search terms** está inativo; era o único que escrevia
sozinho no Google Ads, e a saída dele era um e-mail.
🟡 **11.** **Onze MCCs e contas** nos 17 flows, e a conta desta missão
(`8017851692`) **não aparece em nenhum deles**.

---

## Perguntas que continuam abertas

Estas não são lacunas do inventário — são coisas que **não são respondíveis com o
acesso disponível**, e que mudariam decisões desta missão.

1. **Por que a linha de decisão inteira foi desligada em 19/02/2026?** As 10
   mutações foram bem-sucedidas e o workflow foi editado às 23:47 do mesmo dia.
   *Falta:* o histórico de execuções do n8n (`execution_entity`).
2. **Quem chama o webhook de bidding hoje?** Ele está **ativo**, e o único chamador
   que o inventário encontra é o ramo manual de um workflow inativo — mais o botão
   do dashboard. Se algo externo posta nele, existe um caminho de mutação de lance
   vivo e não governado. *Falta:* o log de requisições do n8n.
3. **Qual dos dois Supabase é a produção?** *Falta:* credencial de leitura do
   projeto hospedado para comparar `count(*)` e `max(date)` dos dois lados.
4. **O piso de ROAS para aumento é 1,70 ou 1,00?** As duas gerações do mesmo motor
   respondem diferente e nenhuma decisão está registrada. *Falta:* decisão do dono
   do domínio — está como `null` no JSON canônico.
5. **A inconsistência dos tetos é deliberada?** `MAX_CPC_BRL 0,50` com `k ≈ 0,70`
   equivale a CPA de R$ 0,714 — o **dobro** do `MAX_TCPA_BRL 0,35`. *Falta:*
   decisão registrada.
6. **Qual é o atraso real da receita de GAM/AdSense?** É o número que falta para
   `dia_parcial_nao_decide` e `zumbi_gasto_sem_receita` ficarem seguras. Hoje é
   `null` em todo o JSON canônico, e **não foi inventado**. *Falta:* a ingestão de
   receita voltar a fluir para poder medir.
7. **O ad group de mineração BROAD a 70% do lance entra no perfil de canal
   SEARCH?** É decisão de custo de aprendizado, e é do dono do domínio. Ficha B02.

---

## Como usar isto na próxima onda

- **Agente C** (engine multicanal): `regras-canonicas.json` é o contrato de
  entrada do motor de autogestão. Nenhuma regra ali está ativa, e nenhuma pode ser
  implementada com os literais de `valores_do_legado` — eles são **evidência de
  intenção**, não valores adotados. As fichas B01, B03 e B04 apontam o que já está
  absorvido em `volc_ads/`, para não reescrever.
- **Agente E** (Supabase e linhagem): os pontos 4, 5 e 7 de `conflitos.md` são
  requisitos de schema — três tabelas em vez de uma, procedência que o trigger não
  apague, e carimbo de decisão que não venha de `DEFAULT now()`.
- **Agente F** (frontend): o ponto 1 de `conflitos.md` está no código que você
  toca — `BiddingActionBox.tsx:123`.
- **Agente H** (auditoria adversarial): a seção "Perguntas que continuam abertas"
  é o inventário honesto do que eu **não** consegui provar.
