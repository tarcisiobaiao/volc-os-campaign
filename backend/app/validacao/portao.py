"""O portão `(engajamento, dado_unico)` com chamada própria.

## Por que ele saiu do formulário

É a decisão de maior consequência do motor — ela zera o índice do tema — e é a
única com evidência imune ao viés de seleção que contamina o resto da base: 9
temas, R$ 138.814, acima da mediana dos vencedores, prejuízo líquido.

E era tomada como item 2 de um formulário de dez eixos e 648 linhas.

A correção não é auto-consistência de N amostras: isso triplica custo e
latência para comprar estabilidade sem comprar acerto. É dar ao portão a
própria chamada — pergunta binária, teste operacional na frente, nada mais
competindo por atenção.

## O que este módulo NÃO faz

Não classifica `engajamento`. O portão responde `dispara: true|false`; o NÍVEL
do eixo (`diagnostico`, `condicional`, `sequencial`, `comparativo`,
`dado_unico`) continua saindo do classificador. Quando o portão dispara, o
nível é `dado_unico` por definição e o classificador é sobreposto — nesse e só
nesse eixo.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional, Sequence

from app.config import Settings
from app.llm import get_engine
from app.llm.json_defensivo import extract_json

log = logging.getLogger("pautador.validacao.portao")

PROMPT = (pathlib.Path(__file__).resolve().parents[1]
          / "motor_pautas" / "prompts" / "portao_engajamento.md")


def carregar_prompt() -> str:
    return PROMPT.read_text(encoding="utf-8")


def entrada(temas: Sequence[Dict[str, str]]) -> str:
    return json.dumps({"temas": list(temas)}, ensure_ascii=False, indent=1)


async def perguntar(temas: Sequence[Dict[str, str]], *, settings: Settings,
                    engine: Optional[str] = None,
                    model: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """`{id: {"dispara": bool, "resposta_literal": str, ...}}`.

    Um tema que não voltar na resposta fica FORA do dicionário — ausência não
    vira `False`. Portão que não foi perguntado é diferente de portão que não
    disparou, e tratar os dois igual é o erro que `PORTOES_EXIGEM_MEDICAO`
    existe para impedir do outro lado.
    """
    if not temas:
        return {}
    motor = get_engine(settings, engine, model)
    cliente = getattr(motor, "client", None)
    if cliente is None:
        log.warning("engine sem cliente de texto — portão não perguntado")
        return {}

    bruto = await cliente.complete(carregar_prompt(), entrada(temas))
    dados = extract_json(bruto)

    fora: Dict[str, Dict[str, Any]] = {}
    for item in (dados.get("temas") or []):
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or "")
        dispara = item.get("dispara")
        if not ident or not isinstance(dispara, bool):
            # `"true"` entre aspas é verdadeiro em Python — um portão marcado
            # assim mataria o tema por erro de tipo. Sem booleano, sem veredito.
            log.info("portão sem booleano para %s: %r", ident, dispara)
            continue
        fora[ident] = {
            "dispara": dispara,
            "consulta_dominante": item.get("consulta_dominante") or "",
            "resposta_literal": item.get("resposta_literal") or "",
            "decisao_que_sobra": item.get("decisao_que_sobra") or "",
            "porque": item.get("porque") or "",
            "apelacao": item.get("apelacao") or {},
            "fonte": f"{getattr(motor, 'name', '?')}:{getattr(motor, 'model', '?')}",
        }
    return fora


def temas_de(cards: Sequence[Any]) -> List[Dict[str, str]]:
    return [{"id": f"opp{c.opportunity_id}", "termo": c.termo,
             "pais": c.country_code or "??",
             "descricao": getattr(c, "descricao", "") or ""}
            for c in cards]


# ── as duas passadas, e a régua assimétrica ────────────────────────────────

PORTAO = "portao"
LIMITROFE = "limitrofe"
SEM_PORTAO = "sem_portao"

# ⚠️ DÍVIDA DE GOVERNANÇA, DECLARADA EM VEZ DE SILENCIOSA.
#
# `DECISOES.md` fecha com a regra de retomada: "só promover a portão com
# replicação FORA dos nove temas originais". Este portão já retira o tema da
# fila, e a replicação não aconteceu. Uma auditoria externa pegou.
#
# A proteção operacional fica — os 9 temas consumiram R$ 138.814 e o mecanismo
# é plausível. O que muda é a honestidade: a promoção vai marcada como
# PENDENTE, viaja na evidência de todo card, e aparece no veredito da tela.
# Dívida declarada se paga; dívida silenciosa vira folclore.
#
# Como quitar: replicação em entidades novas, exposição inicial comum, medindo
# P(ao menos uma impressão viewable | clique) e RPC/CPC, controlando página,
# país e layout. Enquanto `False`, todo veredito diz isso.
PROMOCAO_REPLICADA = False
NOTA_DE_REPLICACAO = (
    "evidência forte (9 temas, R$ 138.814, acima da mediana dos vencedores) "
    "e NÃO replicada fora deles. Os nove são o mesmo arquétipo: consulta de "
    "registro pessoal. Generalizar para toda resposta curta é um salto."
)


async def avaliar(temas: Sequence[Dict[str, str]], *, settings: Settings,
                  engine: Optional[str] = None, model: Optional[str] = None,
                  passadas: int = 2) -> Dict[str, Dict[str, Any]]:
    """Duas passadas para DETECTAR DESACORDO — não para votar.

    ## A diferença, e ela é estrutural

    Maioria de N amostras compra estabilidade sem comprar acerto: se o modelo
    oscila 60/40, a maioria devolve o lado de 60% com cara de certeza. Isto aqui
    não agrega — **mede**. Quando as duas passadas discordam, o resultado não é
    um voto vencedor: é a informação de que o caso é limítrofe.

    ## A régua é assimétrica de propósito

        2/2 dispara  ->  portao      o tema não sustenta funil
        1/2 dispara  ->  limitrofe   revisão humana
        0/2 dispara  ->  sem_portao

    Qualquer disparo isolado rebaixa. Os dois erros não custam igual: deixar
    passar um tema `dado_unico` é o que queimou R$ 138.814 em 9 temas; matar um
    tema bom por engano custa um tema. A régua erra para o lado do humano olhar.

    Duas passadas não separam perfeitamente — num caso 60/40 elas concordam por
    acaso boa parte do tempo. A assimetria compensa isso sem custo adicional.

    ## `limitrofe` NÃO é escotilha

    A escotilha que foi removida do classificador (o S4) **resgatava** o tema:
    subia o nível e devolvia o card para a fila. O limítrofe tira o card da fila
    exatamente como o portão tira. Ele não afrouxa a consequência — só recusa a
    fingir certeza que a medição não tem.

    Custo: uma passada extra por LOTE (~25s), não por card.
    """
    rodadas: List[Dict[str, Dict[str, Any]]] = []
    for _ in range(max(1, passadas)):
        rodadas.append(await perguntar(temas, settings=settings,
                                       engine=engine, model=model))

    fora: Dict[str, Dict[str, Any]] = {}
    for tema in temas:
        ident = str(tema.get("id"))
        respostas = [r[ident] for r in rodadas if ident in r]
        if not respostas:
            # Portão não perguntado é diferente de portão que não disparou.
            fora[ident] = {"veredito": None, "motivo": "portao_nao_respondido",
                           "passadas": []}
            continue

        votos = [bool(r["dispara"]) for r in respostas]
        if all(votos):
            veredito = PORTAO
        elif any(votos):
            veredito = LIMITROFE
        else:
            veredito = SEM_PORTAO

        # A evidência do disparo, quando houve; senão a da primeira passada.
        base = next((r for r, v in zip(respostas, votos) if v), respostas[0])
        fora[ident] = {
            "veredito": veredito,
            "passadas": votos,
            "n_passadas": len(votos),
            "n_disparos": sum(votos),
            "consulta_dominante": base.get("consulta_dominante", ""),
            "resposta_literal": base.get("resposta_literal", ""),
            "decisao_que_sobra": base.get("decisao_que_sobra", ""),
            "porque": base.get("porque", ""),
            # O que a OUTRA passada disse, quando discordou — é a razão de o
            # card ir para revisão humana, e ela tem de estar visível.
            "divergencia": ([r.get("decisao_que_sobra", "") for r, v in
                             zip(respostas, votos) if not v][:1] or [""])[0]
            if veredito == LIMITROFE else "",
            "fonte": base.get("fonte", ""),
            "promocao_replicada": PROMOCAO_REPLICADA,
            "nota_de_replicacao": (NOTA_DE_REPLICACAO
                                   if veredito == PORTAO and not PROMOCAO_REPLICADA
                                   else ""),
        }
    return fora
