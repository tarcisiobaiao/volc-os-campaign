# Briefing para auditoria externa do motor de previsão de pauta

> Auditoria datada: evidência de revisão, não contrato de runtime.

> **Cole este arquivo inteiro como prompt.** Ele é autossuficiente: contém o
> negócio, o motor, o que já foi medido e derrubado, e as perguntas abertas.

---

## 0 · O QUE VOCÊ É NESTA TAREFA

Você é um revisor externo com três competências que raramente vivem na mesma
pessoa: **arbitragem de mídia programática**, **psicometria aplicada a
comportamento de leitura**, e **desenho de sistemas de decisão sob incerteza**.

Você foi contratado para **discordar**. Um relatório que concorda com tudo não
tem valor aqui: já temos quem concorde. O que falta é alguém que olhe a dança
entre psicologia comportamental, dado medido e previsão, e diga onde ela pisa
em falso.

**Você não vai alterar nada.** Nenhum arquivo, nenhuma linha, nenhum patch. A
saída é um relatório. Nós decidimos juntos, depois, o que mantém, o que sai e o
que melhora.

---

## 1 · O NEGÓCIO, E A IDENTIDADE QUE O DEFINE

Portais de utilidade pública explicam benefício, documento e trâmite. Compram
clique barato no Google Ads e monetizam com display programático (GAM/AdSense).

**A conta fecha quando `RPM ÷ CPC > 1`.**

A operação roda em 7 países: BR, MX, CO, CL, PE, AR, ES. E a arbitragem vive da
**razão**, não do eCPM absoluto: um mercado com metade do eCPM e um quinto do
CPC é melhor. Tier 1 tem eCPM alto **e** CPC alto.

Estado real da operação, sem enfeite:

| | |
|---|---|
| sites em produção | **1** (creditoup.com.br) |
| campanhas com dado histórico | **4** |
| receita GAM ingerida | **0 linhas** (o ramo aponta para um Supabase antigo) |
| receita AdSense | para em 19/02/2026 |
| desfecho medido por tema | **nenhum** |

Ou seja: **o motor nunca foi validado contra desfecho, e por desenho ele foi
construído para não precisar disso.** Guarde esta frase; ela é o centro da
auditoria.

---

## 2 · O QUE O MOTOR É

Um sistema de descoberta e priorização de PAUTA, em três estágios:

```
DESCOBRIR   um LLM (Gemini) propõe entidades por país/nicho
VALIDAR     ← o objeto desta auditoria
MINERAR     expansão de keyword, funil, páginas
```

A coluna **VALIDAR** substitui palpite por medição e posiciona o tema num
espaço de **9 eixos**, agrupados em 3 famílias:

```
demanda_humana   ignorancia · engajamento · opacidade · reposicao
economia         volume · densidade · formato_consumo
posicao          vacuo · producao
```

### 2.1 · A aritmética

- Cada eixo tem **vocabulário fechado** (4 a 6 níveis nomeados), cada nível com
  um valor em [0,1].
- O índice é **média geométrica ponderada** dos eixos declarados.
- **Portão é par `(eixo, nível)`, binário**, e zera o índice:

```python
PORTOES = {
    'engajamento':     ('dado_unico',),
    'ignorancia':      ('nao_preciso_de_nada',),
    'formato_consumo': ('video_social', 'voz_ou_humano'),
    'spread':          ('ruim',),
    'volume':          ('residual',),
}
PORTOES_EXIGEM_MEDICAO = {'spread', 'volume'}   # palpite não mata tema
```

- Pesos (**priores declarados, não coeficientes ajustados**):

```python
PRIORES = {
    'ignorancia': 0.90, 'opacidade': 0.85, 'engajamento': 0.75,
    'densidade': 0.70,  'spread': 0.70,    'volume': 0.65,
    'reposicao': 0.60,  'vacuo': 0.55,
    'formato_consumo': 0.35, 'producao': 0.35,
}
_CALIBRACAO = {}   # VAZIO DE PROPÓSITO, com teste garantindo que continue
```

- `ordenar()` **remove** da fila quem disparou portão, em vez de mandar para o
  fim: portão é decisão binária, e ordenar tema morto entre mortos não informa.
- O quadrante `perfil()` cruza `demanda_humana × economia` com corte em 0,60:
  `alvo` (lê e paga) · `audiencia_pobre` (lê, não paga) ·
  `mercado_rico_sem_leitura` (paga, não pagina) · `descartar`.

### 2.2 · A fronteira de proveniência

**Não negociável no desenho atual:**

```
API mede o mundo   volume · reposicao · vacuo · formato_consumo   (DataForSEO)
LLM lê a pessoa    ignorancia · engajamento · opacidade · densidade · producao
fora de escopo     spread  → vive no engine de Ads, não aqui
```

Cada eixo é gravado com `proveniencia ∈ {medido, julgado, ausente}` e com a
prova que o sustenta (a série mensal, os domínios da SERP, as razões
calculadas). A tela colore **proveniência**, nunca valor.

### 2.3 · O portão de engajamento tem chamada própria

`(engajamento, dado_unico)` é o achado de evidência mais forte do motor e vale
uma explicação separada, porque é a decisão de maior consequência: **ela zera o
índice**.

Mecanismo: se a resposta que a pessoa veio buscar se esgota em segundos, o
leitor sai antes do anúncio ficar visível, a viewability do domínio despenca e
o inventário é rebaixado nos leilões seguintes.

Ele foi extraído do formulário de 9 eixos para um prompt só dele, e **medimos o
efeito** (§4.4). Roda em **duas passadas com régua assimétrica**:

```
2/2 dispara  →  portao      tema fora da fila
1/2 dispara  →  limitrofe   revisão humana
0/2 dispara  →  sem_portao
```

Assimetria deliberada: deixar passar um `dado_unico` é o erro caro; matar um
tema bom custa um tema.

---

## 3 · A TESE PSICOLÓGICA, E ELA É A PARTE QUE MAIS PRECISA DE VOCÊ

Duas afirmações sustentam o motor inteiro.

**(A) O que faz virar página não é a força da pressão, é o tamanho do buraco de
conhecimento.**

Quem precisa renovar a CNH sabe exatamente o que fazer e quer executar: não lê.
Quem não sabe se tem dinheiro parado lê tudo. A escala:

```
nao_sei_se_existe        1.00   "não sei nem se isso existe para mim"
nao_sei_se_sirvo         0.75   "sei que existe, não sei se me encaixo"
nao_sei_por_que_falhou   0.65   "sei o que quero, não sei por que não deu"
so_falta_um_dado         0.30   "sei tudo, só preciso da data"
sei_o_que_fazer          0.30   "sei o passo, quero executar"
nao_preciso_de_nada      0.02   PORTÃO: curiosidade pura, nada em jogo
```

**(B) A ponte entre países é a FORMA DA PERGUNTA, não o substantivo.**

`FGTS` e `Cesantias` não compartilham uma letra, mas compartilham a pergunta:
*"tem dinheiro meu parado que eu não sei sacar?"*. Sete tensões nomeadas
(`medo_de_perder`, `dinheiro_esquecido`, `acesso_negado`, `obrigacao_legal`,
`ascensao`, `urgencia_de_renda`, `protecao_familiar`), detectadas por
marcadores de **forma interrogativa** multilíngues, não por lista de
substantivos.

---

## 4 · O CEMITÉRIO: O QUE JÁ FOI MEDIDO E DERRUBADO

**Leia esta seção antes de propor qualquer coisa.** Cada item abaixo foi
testado com número. Repropor qualquer um deles é output desperdiçado, e nós
vamos identificar na hora.

**4.1 · A regressão logística ajustada.** L2 em 237 temas, alvo `lucro > R$
3.000`, AUC fora da amostra 0,689. **Caiu porque `spend` sozinho prevê o mesmo
alvo com AUC 0,971**: spend mediano R$ 12.430 nos vencedores contra R$ 483 nos
perdedores. O modelo aprendeu **onde a equipe decidiu investir**, não o que é
bom tema. A maioria dos "perdedores" não perdeu: foi descartada antes de ser
testada. Para um motor que existe para SUGERIR, isso é fatal.

**4.2 · Régua contaminada contamina tudo.** Aposentamos a regressão por causa do
`spend`, **e medimos a escada de ignorância contra esse mesmo alvo**. Isso é uma
falha reconhecida e não resolvida.

**4.3 · Teorias importadas, refutadas na base:**

| teoria | previsão | medido |
|---|---|---|
| Loewenstein (hiato de informação) | U invertido, pico no hiato moderado | monotônico decrescente, pico no hiato **máximo** (1,68× / 1,52×) |
| Kahneman (aversão à perda) | perda pesa ~2,0× o ganho | 1,06× numa rodada, **0,69×** (invertido) na outra |

O motivo alegado é conceitual: Prospect Theory descreve **escolha sob risco**;
aqui se mede **leitura**. Mesmo argumento para o Fogg Behavior Model.

**4.4 · Pressão psicológica por persistência.** Correlação com desfecho
**+0,017** (nada). Reordenando por ignorância: **+0,194**. Três vezes de
diferença entre `direito_latente` (33% vitória, n=52) e `compulsao` (11%, n=53).

**4.5 · IAB como feature.** As três variáveis derivadas pioram o AUC fora da
amostra (−0,011 a −0,013). Ficou como camada de classificação, não de pontuação.

**4.6 · `spread` como média nacional.** Pearson **−0,266** contra cinco mercados
medidos. Média de país dilui o nicho no run-of-network.

**4.7 · `formato_consumo` como peso.** Diluído numa média de dez eixos, não
pegava o caso para o qual foi criado. Promovido a portão.

**4.8 · O limite de resolução.** Com n=235, o erro padrão da correlação é
**0,065**. Diferenças menores que ~0,13 são indistinguíveis de ruído, e quase
toda hipótese testada vive abaixo disso.

**4.9 · Duas revisões externas anteriores.** A segunda deu **REJECT** ao rótulo
intrínseco por entidade. O construto media 33,3% de estabilidade entre rodadas
contra **34,0% de acaso** dado o `Σpᵢ²` das marginais observadas: **zero
informação, medido duas vezes**.

**4.10 · A única evidência imune ao viés de seleção.** `(engajamento,
dado_unico)`: 9 temas consumiram R$ 138.814 (~R$ 15 mil cada, **acima da
mediana dos vencedores**) e devolveram prejuízo líquido, contra +48,6% de ROI
do resto. Passaram pelo filtro de verba e perderam assim mesmo.

---

## 5 · O QUE FOI MEDIDO NA API, E CORRIGIU A DOCUMENTAÇÃO

96 chamadas reais, 19 endpoints, US$ 1,977, contra os temas da operação.

- **`keyword_info.cpc` superestima o CPC real em 7,4×** (média geométrica), e
  **a ordem inverte dentro do cluster** — nenhum fator de correção conserta. O
  que funciona é `ad_traffic_by_keywords` com lance real: **6% de erro**.
- **O Labs perde keyword em silêncio**: `status 20000`, sem aviso, item fora do
  array. `cesantias` (CO) tem 40.500 buscas/mês e não volta.
- **`cpc: null` não é dado faltando, é ausência de leilão** — categoria que o
  espaço de eixos não tem. No México foi a regra: 32 de 32 termos.
- **`formato_consumo` é medível pela composição de domínio da SERP, e é por
  TEMA, não por país.** A variação intra-Nigéria é maior que BR↔NG.
- **Histórico profundo piora a sazonalidade**: use 48 meses, não 92.
- **Os zeros à esquerda são a data de nascimento da entidade, e são exatos.**

Custo atual da validação: **US$ 0,0092 por card**, em lote.

### 5.1 · Defeitos que a própria implementação já encontrou e corrigiu

Registramos porque revelam a classe de erro que este sistema produz: **número
plausível, silencioso**.

- Série mensal vem em **ordem decrescente**; fatiar `[-48:]` cru pegava os 48
  meses mais **antigos**.
- Duas normalizações de caixa (uma no contraste pedido×devolvido, outra na
  busca) faziam `IPVA` com 301.000 buscas/mês virar **30/mês, `residual`**, e o
  portão de volume matava o tema.
- Limiar de pico **absoluto** (`n_picos >= 4`) com janela fixa em 48 meses
  passou a significar "um por ano" = coorte **anual**, o oposto do que a regra
  queria dizer.
- `tendencia` por 3 primeiros vs 3 últimos meses é **sensível à fase do corte**:
  a mesma série anual saía `unica` ou `anual` conforme o mês em que a janela
  terminava.
- A cabeça do cluster por "maior volume" seleciona a consulta **navegacional**
  (`ipva` → 8 de 9 domínios de secretaria de fazenda), não a **editorial**
  (`como calcular ipva` → 4 de 9). Corrigido usando o bloco *People Also Ask*
  da própria SERP como fonte da cabeça editorial.

---

## 6 · O NÚMERO MAIS IMPORTANTE DESTA AUDITORIA

Medimos a estabilidade do portão de engajamento entre execuções idênticas:
mesmos 6 cards, 5 rodadas, mesmo modelo.

```
                        formulário de 9 eixos     prompt dedicado
Registrato                     1/5                      5/5
IPVA                           2/5                      1/5
Serasa Limpa Nome              0/5                      1/5
outros 3                       0/5                      0/5

unanimidade                  4/6 (67%)                4/6 (67%)
discordância entre 2 exec.     16,7%                    13,3%
```

Leitura: **a variância não melhorou.** O que melhorou foi **recall no caso
claro**: `Registrato` (login no Banco Central, ver seus relacionamentos
bancários) é o arquétipo de `dado_unico`, e o formulário o perdia em 4 de 5
execuções, classificando como `sequencial` porque descrevia os **passos da
consulta**. A guarda contra exatamente esse erro está nos dois prompts, palavra
por palavra; enterrada no item 2 de nove eixos ela não dispara.

Testamos se a **evidência** era mais estável que o **veredito**
(`decisao_que_sobra == "nenhuma"` contra `dispara`): **não é** — as duas
acompanham perfeitamente, 4/6 nas duas. Isso fecha a porta de mover o teste
para código determinístico.

---

## 7 · O QUE LER, E EM QUE ORDEM

```
1  backend/app/motor_pautas/DECISOES.md              368   o cemitério, com números
2  backend/app/motor_pautas/espaco.py                625   os 9 eixos, portões, índice
3  backend/app/motor_pautas/psique.py                200   as 7 tensões, forma da pergunta
4  backend/app/motor_pautas/sensores/dataforseo.py  1000   API → nível de eixo (funções puras)
5  volc_ads/DATAFORSEO-MEDIDO.md                     198   o que a fatura corrigiu
6  backend/app/motor_pautas/prompts/
     classificador_eixos.md                          648   os 5 eixos de julgamento
     portao_engajamento.md                           155   o portão isolado
7  backend/app/validacao/orquestrador.py             864   o fluxo, gravação incremental
   backend/app/validacao/portao.py                   183   duas passadas, régua assimétrica
   backend/app/validacao/julgamento.py               172   a fronteira aplicada
8  backend/app/entities/leitura.py                   322   por que o portão anterior NÃO barra
```

Tabelas no Postgres: `pautador_entity_axes` (um eixo por linha, com
proveniência e prova) e `pautador_validation_runs` (custo real, pedido ×
devolvido).

---

## 8 · AS PERGUNTAS QUE EU QUERO QUE VOCÊ ATAQUE

Responda as que tiver base para responder. **Diga explicitamente quando não
tiver** — "não sei" é resposta útil; palpite com cara de análise não é.

**8.1 · A contradição central.** O motor existe para prever oportunidade de
**arbitragem**, e arbitragem É a razão `RPM ÷ CPC`. Mas `spread` foi tirado do
escopo por decisão (vive no engine de Ads). O motor mede "ela vai ler?" e "o
mercado paga?" e **nunca olha a razão**. Isso é separação de responsabilidade
correta, ou é o buraco no meio do sistema?

**8.2 · Média geométrica ponderada.** É o agregador certo para dez rótulos
ordinais de vocabulário fechado? Ela pune o eixo fraco (bom: um eixo ruim
derruba o conjunto) e é indefinida em zero (contornado com piso 1e-6). O que
você usaria, e por quê? Considere que **os pesos são priores declarados, não
ajustados**, e que calibrá-los contra a base existente foi rejeitado (§4.1).

**8.3 · Portões que talvez sejam pesos disfarçados.** Cinco portões, com
evidência muito desigual: um FORTE (§4.10), um FRACO (0 de 11, IC de Wilson até
0,26, p≈0,09), um aritmético (`spread < 0,9` é prejuízo por construção), um
definicional (`volume residual`), e um estrutural (`formato_consumo`). Algum
deles não deveria ser portão? Algum peso deveria ser?

**8.4 · O construto de `ignorancia`.** Ele é o eixo de maior peso (0,90) e o
único com correlação medida (+0,194) — **contra um alvo contaminado** (§4.2).
Ignorância é o construto certo para prever **tempo de atenção**, ou é proxy de
outra coisa (complexidade da resposta? número de decisões pendentes? distância
entre a pergunta e a ação)? Se for proxy, do quê, e isso é mensurável?

**8.5 · Instabilidade de rótulo.** 67% de unanimidade em 5 execuções. Vetamos
auto-consistência de N amostras (compra estabilidade sem comprar acerto).
Existe **formulação** — não amostragem — que estabilize um julgamento ordinal
de LLM? Ou a instabilidade é irredutível e o desenho certo é sempre expor o
limítrofe, como fizemos?

**8.6 · Sinal medível que estamos deixando na mesa.** Já pagamos a SERP
completa. Ela traz *AI Overview* (presente em 73% das medições), *People Also
Ask*, *related searches*, *knowledge graph*, composição de domínio. Existe aí um
proxy de **complexidade da resposta** ou de **profundidade de leitura** que
substituiria ou verificaria um dos eixos julgados por LLM? A presença do AIO,
por exemplo, significa alguma coisa para a nossa tese?

**8.7 · `cpc: null` como categoria.** Demanda real com zero anunciante é comum
(regra no México). O espaço de eixos não tem essa categoria. Ela deveria ser um
eixo? Um portão? Um sinal para o engine de Ads?

**8.8 · A validação que não temos.** Com 1 site e 4 campanhas, não há desfecho.
A regra de retomada declarada exige cluster × página × país × período, com
**exposição inicial comum** e avaliação em RPC÷CPC e segundos viewable por
clique. **Existe um desenho de validação mais barato ou mais rápido que esse?**
Alguma quase-experiência, dado natural, ou fonte externa que sirva de régua sem
precisar de 40 páginas produzidas?

**8.9 · O que você tiraria.** Se você pudesse remover exatamente um eixo, um
portão ou uma camada inteira sem perder poder de decisão, o que seria? Sistemas
assim erram por acúmulo, e ninguém do lado de dentro consegue apontar o que é
supérfluo.

**8.10 · O que está errado e ninguém viu.** A pergunta aberta. Você tem a
vantagem de olhar de fora um sistema construído por quem já sabe demais sobre
ele.

---

## 9 · COMO ENTREGAR

- **Português do Brasil.**
- Comece pelo **veredito em cinco linhas**: o motor faz sentido? Onde ele pisa
  em falso?
- Depois, por pergunta (8.1 a 8.10). Pule as que não tiver base.
- **Separe o que é evidência do que é opinião.** Se for intuição sua, escreva
  "intuição". Se for literatura, cite. Se for aritmética, mostre a conta.
- **Priorize por consequência, não por facilidade de conserto.**
- Para cada crítica, diga **o que a falsificaria** — se não houver teste que a
  derrube, é preferência, e preferência entra num parágrafo à parte no fim.
- Tamanho livre. Densidade acima de extensão.

**Não escreva código, não proponha patch, não edite arquivo.** Se quiser mostrar
uma alternativa, descreva-a em prosa ou pseudocódigo curto dentro do relatório.

---

## 10 · O QUE NÃO ACEITAMOS COMO RESPOSTA

- Repropor qualquer item da §4 sem evidência nova que derrube o que já medimos.
- "Use um modelo de ML" sem dizer contra qual alvo, com que dado, e como escapa
  do problema do `spend` (§4.1).
- "Colete mais dados" sem dizer **quais**, em que unidade, e a que custo.
- Elogio à arquitetura. Já sabemos o que gostamos nela.
- Sugerir mais amostragem do LLM como cura para instabilidade (§8.5).
