# Diagnóstico factual da baixa qualidade visual — geração real de 09/09/2026

Não é hipótese. As quatro imagens abaixo existem no disco, as linhas existem no
Supabase oficial, e o prompt foi **reconstruído e conferido por sha256** contra
`criativo_master.prompt_sha256`. Os quatro hashes batem.

## As quatro peças reais inspecionadas

| job | slot | arquivo | modo | prompt_sha256 (banco = recalculado) |
|---|---|---|---|---|
| `7b5423f3` (A) | 9x16 | `9x16_ce06e66d…png` | `sem_foto` | `75ea04fc…d058` ✔ |
| `7b5423f3` (A) | 4x5  | `4x5_5c539f50…png`  | `sem_foto` | `57d9f07f…5486` ✔ |
| `bd1761d9` (B) | 9x16 | `9x16_d5f744ed…png` | `sem_foto` | `1bbaa7d7…a9af` ✔ |
| `bd1761d9` (B) | 4x5  | `4x5_7969a532…png`  | `sem_foto` | `6c45faf2…9e63d` ✔ |

Motor: `openai:gpt-image-2`, `qualidade=medium`, `modelo_servido=NULL` nas quatro.

## O prompt exato que saiu para o provider (job A, 9x16)

```
Fundo claro, cartão centralizado simulando formulário simples de checagem, ícones de conferência em linhas finas, sem promessa de concessão garantida.
Texto na arte: VEJA SE VOCÊ SE ENQUADRA · Novo calendário divulgado para o Gás do Povo. · Verificar regras
OUTCOME_TRAFFIC
Público: Público querendo saber se se enquadra no Gás do Povo.

Formato de saída: 864x1536 px, entrega final 1080x1920 px.
Componha para este enquadramento especificamente, não para um quadrado recortado. Preencha o canvas inteiro, sem bordas vazias e sem tarjas. Reserve uma área limpa e contínua para texto, adequada a esta proporção.
Sem texto, sem letras, sem logotipo e sem marca d'água na imagem.
formato: Vertical
modo_de_composicao: sem_foto
```

## D1 — O prompt pede o texto e proíbe o texto, no mesmo corpo

`services/creative_engine/motores/openai_imagem.py:560-565` (e o gêmeo em
`gemini_imagem.py:340`) escolhem a frase final por `modo_de_composicao`:

```python
inspiracao = pedido.contexto.get("modo_de_composicao") == "referencia_visual"
texto = (
    "Use apenas o texto na arte aprovado no briefing, …"  if inspiracao else
    "Sem texto, sem letras, sem logotipo e sem marca d'água na imagem.\n"
)
```

`sem_foto` é o caminho **default** do Estúdio, e cai no `else`. Resultado: a
linha `Texto na arte: …` chega ao modelo e, oito linhas depois, uma ordem
imperativa manda não escrever nada. A proibição vem por último.

**Efeito medido, não suposto:**
- Job A obedeceu a proibição: as duas peças saíram com **zero texto** — barras
  cinzas de placeholder onde a headline deveria estar e um **botão de CTA vazio**.
- Job B desobedeceu em parte: entregou headline e complemento, e **descartou o
  CTA** ("Saiba mais"), deixando de novo um botão com seta e sem palavra.

Duas execuções do mesmo caminho, dois resultados diferentes: é o comportamento
esperado de um modelo diante de instruções contraditórias, não de um bug
determinístico. Por isso o defeito não aparecia de forma reproduzível.

## D2 — Enum operacional da Meta vaza para dentro da direção de arte

`OUTCOME_TRAFFIC` ocupa uma linha inteira do prompt, sozinha, como se fosse
instrução visual. Vem de `criativo_briefing.objetivo` e é concatenado cru em
`backend/app/criativo/execucao.py:1073-1080` (`_insumo_do_briefing`).

O adaptador já tem um detector de metadado operacional
(`studio/adaptador.py:230`, `contem_metadado_operacional`) — mas ele só protege o
**texto da arte**, nunca o campo `objetivo`.

## D3 — Os três campos internos são achatados e perdem hierarquia

`studio/adaptador.py:45-53` junta headline, complemento e CTA com `" · "`:

```python
partes = [peca.headline_interna, peca.complemento_interno, peca.cta_visual]
return " · ".join(...)
```

O modelo recebe três frases irmãs e nenhuma informação de que a primeira é
headline e a terceira é botão. Não há como ele acertar hierarquia tipográfica —
e, no job B, ele simplesmente descartou a terceira.

## D4 — A "spec" é uma string, não um contrato

`studio/adaptador.py:297` colapsa tudo em um campo de texto:

```python
"mensagem": f"{primeiro.direcao_visual}\nTexto na arte: {primeiro.texto_na_arte}",
```

Não viajam: hierarquia tipográfica, composição e posição dos elementos, margens
e áreas de proteção por formato, espaço reservado ao texto, paleta e contraste,
direção fotográfica, elementos proibidos, procedência. `criativo_briefing.fatos`
estava `[]` nas quatro peças: nenhum fato sustentou a mensagem.

## D5 — Duplicação de rótulo

`Público: Público querendo saber se se enquadra no Gás do Povo.` — o prefixo é
adicionado por `_insumo_do_briefing` sobre um valor que já começa com "Público".

## D6 — O prompt efetivo não é recuperável

`execucao.py:646` grava `insumo_sanitizado: None` por decisão explícita; só o
sha256 sobrevive. Foi possível reconstruir o prompt aqui **porque o código foi
lido linha a linha** — o produto não oferece esse caminho ao operador.
`criativo_job.prompt_sha256` está NULL mesmo quando o master tem o hash.

## D7 — Risco de política, não só de estética

Job B saiu em azul-e-amarelo institucional imitando a identidade de um programa
federal ("Gás do Povo"). Nada no briefing pediu isso e nada no caminho impede.
`Não invente vínculo oficial` é regra do produto e hoje não tem gate.

## O que este diagnóstico NÃO afirma

- Não afirma que corrigir D1 sozinho entrega peça boa. D3 e D4 continuariam
  impedindo hierarquia e composição confiáveis.
- Não afirma que medida escrita no prompt vira pixel exato. Não vira.
- `modelo_servido` é NULL nas quatro: o provider não devolveu o campo, então não
  há prova de qual modelo serviu — só de qual foi pedido.
