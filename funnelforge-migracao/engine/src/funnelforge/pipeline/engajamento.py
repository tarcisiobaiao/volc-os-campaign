"""O vocabulário do eixo `engajamento` — e a ponte entre as DUAS escalas.

⚠️ A ESCALA DO MOTOR DE PAUTAS COLAPSOU DE CINCO NÍVEIS PARA DOIS.

Em `backend/app/motor_pautas/espaco.py` o eixo `engajamento` hoje é binário —
`sustenta` e `dado_unico` — porque os cinco níveis nunca discriminaram: o nível
dominante trocou de `diagnostico` (62,5%) para `condicional` (76,2%) só mudando
a amostra, e "sempre existe um nível para carimbar quase tudo". Os cinco antigos
sobrevivem lá só como `ENGAJAMENTO_LEGADO`, para LER linha já gravada.

O funnelforge, porém, não precisa do NÍVEL: precisa da FORMA DA PERGUNTA. É ela
que escolhe a ferramenta (`ENGAJAMENTO_PARA_ARQUETIPO`) e os blocos nativos
(`VISUAL_BLOCKS_BY_ENGAGEMENT`). `sustenta` não carrega forma — ele diz apenas
"ramifica, condiciona ou deixa decisão: há o que ler". Por isso a ponte é
assimétrica DE PROPÓSITO:

    dado_unico   -> dado_unico   (o único rótulo que separou limpo: 1,00 em
                                  "consultar CPF" contra 0,00 em "aposentadoria
                                  por invalidez")
    sustenta     -> REFINADO por inferência semântica sobre H1/objetivo/
                    estrutura da própria página (`steps.infer_engajamento`),
                    NUNCA para `dado_unico` — isso contradiria a declaração
    as 5 formas  -> elas mesmas (card antigo continua legível)

LER é permitido nas duas escalas. ESCREVER forma continua sendo as cinco.
"""
from __future__ import annotations

import unicodedata

# As cinco FORMAS DE PERGUNTA — o vocabulário que o funnelforge sabe traduzir
# em ferramenta e em bloco nativo.
FORMAS_DE_PERGUNTA: frozenset[str] = frozenset({
    "condicional", "sequencial", "comparativo", "diagnostico", "dado_unico",
})

# A escala BINÁRIA nova do motor de pautas. `dado_unico` pertence às duas (é
# nível E forma); `sustenta` é SÓ nível — não existe bloco nem widget "de
# sustenta", e é por isso que ele precisa ser refinado antes de virar decisão.
NIVEIS_BINARIOS: frozenset[str] = frozenset({"sustenta", "dado_unico"})

# Tudo que pode CHEGAR (do card do Pautador, do briefing ou do declarador) sem
# ser tratado como lixo.
VOCABULARIO_ACEITO: frozenset[str] = FORMAS_DE_PERGUNTA | NIVEIS_BINARIOS


def canon_engajamento(valor: object) -> str:
    """Dobra acento, hífen e espaço num rótulo canônico (`Dado Único` ->
    `dado_unico`, `diagnóstico` -> `diagnostico`). Mesma regra do
    `entities/leitura._canon` do VOLC O.S., pelo mesmo motivo: o vocabulário é
    fechado, mas a GRAFIA de quem escreve não é, e descartar `dado único` como
    "fora do vocabulário" apagaria justamente o rótulo que manda NÃO construir
    widget. Devolve "" quando não é string ou está vazio.

    O que NÃO existe aqui é aproximação semântica: rótulo que não cai
    exatamente num nível continua sendo rótulo desconhecido, nunca o "mais
    parecido".
    """
    if not isinstance(valor, str):
        return ""
    t = unicodedata.normalize("NFD", valor.strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return "_".join(t.replace("-", " ").split())
