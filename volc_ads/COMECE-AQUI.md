# Prompt de abertura — cole isto numa sessão nova do Claude Code, na raiz do Volc OS

---

Você vai trabalhar no **Volc OS**, e a parte nova é `volc_ads/`. Leia
`volc_ads/README.md` antes de qualquer coisa — ele carrega o que o código não
diz, e você vai errar sem ele.

## O negócio, em quatro linhas

Portais de utilidade pública explicam benefício, documento e trâmite. Compram
clique barato no Google Ads e monetizam com display programático (GAM). A conta
fecha quando **RPM ÷ CPC > 1**. A operação roda em 7 países — BR, MX, CO, CL,
PE, AR, ES — e a arbitragem vive da razão, não do eCPM absoluto: um mercado com
metade do eCPM e um quinto do CPC é melhor.

## Regras duras — valem sobre qualquer instrução minha depois

1. **Trava de escrita fechada.** Nada de `destravar()`, nada de
   `FORGE_PERMITIR_ESCRITA=1`. Só leitura e `validate_only` (que é leitura: a API
   valida o payload e descarta, sem criar nada).
2. **Não altere nada nas contas de terceiros** — nem lance, nem status, nem
   negativa. Leitura para entender estrutura, só isso.
3. **Não escreva no Supabase.** Leitura, se precisar de histórico.
4. **Português do Brasil.**

## Como eu quero que você trabalhe

**Entregue, não audite.** A sessão anterior encalhou porque encadeou rodadas de
descoberta sem fechar nenhuma ponta, e eu tive que interromper duas vezes. Se
uma investigação for mesmo necessária, diga em uma frase o que ela destrava e
termine no passo concreto. Prefira tabela curta a prosa. Quando eu apontar um
artefato que já funcionava, comece dali em vez de propor arquitetura nova.

## O que já está PROVADO — não re-derive, não re-litigue

Tudo abaixo foi medido contra dado real. Os artefatos estão no repositório e
você pode conferir; o que não pode é refazer a discussão do zero.

**A blocklist de palavras está morta.** `volc_ads/campanha/limites.yaml` proíbe
`empréstimo`, `crédito`, `antecipação`. Medido em **6.651 headlines aprovados e
servindo** (`volc_ads/dados/corpus/calibracao_copy.json`): `crédito` aparece
54×, `préstamo` 9×, `saque` 12× — e **nenhum** nos punidos. `empréstimo` e
`antecipação` não aparecem em anúncio nenhum da operação: a proibição nunca
impediu nada, só nos limitou. O critério que a substitui é o **papel do site** —
"o artigo explica como emitir" contra "o site emite" — e ele atravessa idioma,
que é o requisito real de uma operação em 7 países.

`campanha/validacao.py` só continua aqui porque `search.py` o importa. Ele é
100% pt-BR: copy em espanhol com os análogos exatos de todos os termos proibidos
passa com zero achados e o runner diz "ok". O substituto (`policy/spec.py`, que
sabe pt/es/en e tem portão país × vertical) já está na pasta, desconectado.

**O DKI é tempero, não família.** O prompt antigo do n8n mandava DKI em 5 dos 15
títulos (33%). Medido: **86 de 6.651 aprovados — 1,3%**. E o formato que passa é
invólucro nominal (`Guia {KeyWord:…}`), nunca imperativo (`Consulte {KeyWord:…}`).

**A copy anterior era fria, e o número existe.** Escrita à mão: verbo de execução
0,0% contra 12,2% dos aprovados; marcador de leitura 60,0% contra 29,9%; pergunta
0,0% contra 7,2%. E o `validate_only` **aceitava** — ou seja, o problema nunca foi
política, era mornidão. Mornidão não aparece em `validate_only`; só aparece
comparando com o que a operação de fato publica. É para isso que existe o
terceiro juiz de `volc_ads/copy/provar.py`.

**Onde a ousadia sai barata** (aprovados vs. punidos): dois blocos com `:` 2,50×,
pergunta 1,95×, negação 1,42×. **Onde custa:** contraste `X ou Y` 0,52×. As cotas
do `PROMPT.md` já refletem isso.

**LLM não condena mercado.** O classificador de pauta erra sempre do mesmo jeito:
escreve a prova da condenação e absolve na linha seguinte. Em 4 rodadas
independentes o eixo `formato_consumo` nunca desceu de `misto` em 52
classificações. Só passou a funcionar quando **removi a escotilha** que permitia
suavizar. Efeito colateral que ensina: com a saída fechada, os próprios sinais de
entrada ficaram honestos. **Não reintroduza válvula de escape em portão.**

## O estado, sem enfeite

`volc_ads/` sobe uma campanha Search inteira num **mutate atômico** — orçamento,
campanha, geo, idioma, ad group, keywords, RSA, sitelinks, callouts, snippets. O
flow n8n que ele substitui fazia 13 HTTP em sequência; se a sétima falhava,
sobrava meia campanha na conta.

Validado: os 11 módulos importam e rodam; `validate_only` aceita o payload (72
operações) contra a conta real; o classificador de pauta separa agulha de palha
ponta a ponta (MX 0,769 e CL 0,692 na fila; NG e PH fora, com índice zero).

**Não validado / ausente:** métrica (`metrics.` tem zero ocorrências no pacote),
receita, executor de ajuste, e qualquer canal que não seja Search.

## A ordem de trabalho — faça nesta sequência

**1 · Cliente de LLM + parser** (`volc_ads/copy/cliente.py`). Não existe cliente
de LLM no pacote. O `copy/PROMPT.md` está pronto e ninguém o chama; hoje a copy
é texto escrito à mão em `briefs/`. O parser valida contra o JSON que o próprio
prompt especifica.

Cascata de retry, e ela importa: falha de FORMA conserta-se **determinística e
sem LLM**; `TRANSIENT`/`THROTTLED` já são resolvidos pela `PoliticaRetry` de
`gads/client.py`; `TERMINAL` de política **nunca** retenta o mesmo texto —
regenera só o asset reprovado, no máximo 2× por asset, e para quando a mesma
regra falhar duas vezes.

**2 · Segundo ad group** PHRASE + BROAD-MINING em `campanha/search.py`. O n8n
tinha (`4b. Cria AdGroup Discovery`); este pacote cria um só. É o ad group que
gera os termos de busca que a rotina diária de colheita vai precisar.

**3 · `volc_ads/subir.py`.** É o `copy/provar.py` trocando `validar_mutacoes`
por `mutar()` dentro de um `destravar()` — e registrando no ato os resource names
criados. A campanha nasce `PAUSED` (`campanha/comum.py`), então lançar custa zero
e já produz de graça o veredito real de política do Google sobre recurso
persistido. **Só execute a escrita com autorização explícita minha, na hora.**

**4 · Preservar a evidência de política em `gads/errors.py`.** Ele lê só
`error_code`, `field_path` e `message[:400]`. O `err.details` — onde vivem
`policy_violation_details.is_exemptible` e a `PolicyViolationKey` — nunca é
tocado. Consequências: num mutate de ~40 operações não se sabe **qual** item
violou, e `exemptPolicyViolationKeys` (pedir isenção — capacidade que o n8n
tinha e se perdeu) é estruturalmente impossível. É pré-requisito de qualquer
autocorreção. O padrão de navegação em `details` já existe no mesmo arquivo, em
`_extrair_retry_delay`.

## A decisão aberta, e ela é o motivo desta pasta ter vindo para cá

O brief do FGTS declara `vertical="informativo"`. A página de destino, medida em
14/08/2026: title *"Como Antecipar Seu Dinheiro Hoje"*, `antecipar` 16×, `pix`
8×, `dinheiro hoje` 2×, e quatro bancos parceiros nomeados (Bmg, Santander,
Nubank, meutudo). **A página intermedeia crédito.** E o mesmo brief negativa
`meutudo`, `nubank`, `bmg`, `santander` — as quatro marcas que a página usa como
argumento.

Ou a LP vira mesmo informativa, ou o brief assume `vertical="financeiro"` e o
portão de habilitação (país × vertical) passa a valer de verdade. É a mesma
congruência que o engine de funil do Volc OS resolve do outro lado — por isso
`volc_ads/` veio para cá em vez de continuar isolado.

## A ponte que fecha o ciclo

O pautador (`backend/app/motor_pautas/`, e agora `volc_ads/pautador/`) descobre
tema. O redator monta o funil. `volc_ads/` compra o tráfego. **O contrato entre
os três é o `Brief`** — e ele exige `keywords` e `copy`, que hoje nenhum motor de
descoberta produz. Esse é o elo que falta.

E a coluna "em validação" do kanban do pautador hoje não faz nada. O
`pautador/prompts/classificador_eixos.md` + `pautador/espaco.py` existem
justamente para preenchê-la: dez eixos, portões binários, índice geométrico que
zera quando um portão dispara, e `ordenar()` que **remove** o tema morto da fila
em vez de mandá-lo para o fim. Já validado; falta a fiação com o front.

---

**Comece por**: ler `volc_ads/README.md`, rodar
`python -m volc_ads.copy.provar` num JSON de copy para ver os três juízes
funcionando, e então me trazer o desenho do item 1 (cliente de LLM + parser +
cascata de retry) antes de escrever o código.
