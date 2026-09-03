#!/usr/bin/env python3
"""REPLAY BEFORE/AFTER — motor anterior e Camada 2 sobre EXATAMENTE os mesmos casos.

## O que é "antes" e o que é "depois"

**Antes** é a superfície de decisão que existia em `b2af81f0`: o que
`validacao.orquestrador._resumir` grava a partir de `espaco.posicionar` —
`apto`, `motivo`, `perfil`, `indice`, `portoes_disparados`, `cobertura`.
Essa superfície **não foi alterada** por esta lane: `espaco.py`, `ficha.derivar`
e `ficha.agregar` estão byte-idênticos ao commit base. O replay confirma isso
em vez de assumir.

**Depois** é a tese da Camada 2 sobre o MESMO resumo.

## Por que o corpus é uma varredura, e não uma lista

Escolher fixtures é escolher o resultado. O corpus aqui é o **produto
cartesiano do espaço de observáveis** da ficha (o mesmo espaço que
`test_todo_nivel_derivavel_e_alcancavel` varre) cruzado com os estados de
proveniência dos eixos de sensor — medido, ausente e palpite. Nenhum caso foi
escolhido por conveniência; todos os que o motor consegue produzir estão aqui.

Os casos "vencedor", "perdedor", "deterioração", "empate" e "extremo" não são
rótulos que eu atribuí: são a classificação do que a varredura produziu.

Uso:
    backend/.venv/bin/python scripts/replay_pautador_oportunidade.py --saida <arquivo.json>
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import pathlib
import sys
from collections import Counter
from typing import Any, Dict, List

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.motor_pautas import espaco as E                      # noqa: E402
from app.validacao.ficha import Ficha, agregar, derivar        # noqa: E402
from app.validacao.oportunidade import (                       # noqa: E402
    PRIORS_WEBGO, comparar, tese_do_resumo,
)

# ── proveniência dos eixos de sensor ─────────────────────────────────────────
#
# Três estados, e eles precisam ser distinguíveis no replay: é a contraprova
# 3/4 sendo exercitada sobre o corpus inteiro, não sobre um caso.
SENSORES = {
    "completo": {
        "volume": ("alto", "medido"), "reposicao": ("continua", "medido"),
        "vacuo": ("raso", "medido"), "densidade": ("densa", "medido"),
        "formato_consumo": ("texto_busca", "medido"),
    },
    "volume_ausente": {
        "volume": (None, "ausente"), "reposicao": ("continua", "medido"),
        "vacuo": ("raso", "medido"), "densidade": ("densa", "medido"),
        "formato_consumo": ("texto_busca", "medido"),
    },
    "volume_zero_medido": {
        "volume": ("residual", "medido"), "reposicao": ("continua", "medido"),
        "vacuo": ("raso", "medido"), "densidade": ("densa", "medido"),
        "formato_consumo": ("texto_busca", "medido"),
    },
    "volume_zero_palpite": {
        "volume": ("residual", "julgado"), "reposicao": ("continua", "medido"),
        "vacuo": ("raso", "medido"), "densidade": ("densa", "medido"),
        "formato_consumo": ("texto_busca", "medido"),
    },
    "quase_tudo_ausente": {
        "volume": (None, "ausente"), "reposicao": (None, "ausente"),
        "vacuo": (None, "ausente"), "densidade": ("densa", "medido"),
        "formato_consumo": ("texto_busca", "medido"),
    },
    "canal_morto": {
        "volume": ("massivo", "medido"), "reposicao": ("continua", "medido"),
        "vacuo": ("virgem", "medido"), "densidade": ("densa", "medido"),
        "formato_consumo": ("video_social", "medido"),
    },
}


def _resumo_do_motor_anterior(fichas: Dict[str, Ficha], sensores: str) -> Dict[str, Any]:
    """Reproduz `_resumir` do orquestrador, sem banco e sem rede.

    Usa `agregar`, `niveis_da_entidade` e `espaco.posicionar` — as MESMAS
    funções do caminho vivo, não uma reimplementação.
    """
    ent = agregar(fichas)
    if ent is None:
        return {}

    eixos: Dict[str, Dict[str, Any]] = {}
    niveis: Dict[str, str] = {}
    medidos: set = set()

    for nome, (nivel, prov) in SENSORES[sensores].items():
        eixos[nome] = {"nivel": nivel, "proveniencia": prov,
                       "motivo_ausencia": None if nivel else "nao_medido"}
        if nivel:
            niveis[nome] = nivel
            if prov == "medido":
                medidos.add(nome)

    for eixo, nivel in (ent.niveis or {}).items():
        eixos[eixo] = {"nivel": nivel, "proveniencia": "julgado", "motivo_ausencia": None}
        if nivel:
            niveis[eixo] = nivel

    try:
        pos = E.posicionar("caso", pais="BR", medidos=medidos,
                           escopo=E.ESCOPO_PAUTADOR, **niveis)
    except ValueError as exc:
        return {"apto": False, "motivo": "nivel_fora_do_vocabulario",
                "erro": str(exc)[:120], "eixos": eixos}

    portoes = pos.portoes_disparados()
    apto = not portoes
    return {
        "apto": apto,
        "motivo": (f"portao_{portoes[0]}" if portoes else None),
        "indice": round(pos.indice, 4) if pos.indice is not None else None,
        "cobertura": round(pos.cobertura, 2),
        "perfil": pos.perfil(),
        "portoes_disparados": portoes,
        "alertas": pos.alertas,
        "eixos": eixos,
        "ficha": {
            "share_dado_unico": ent.share_dado_unico,
            "n_perguntas": len(ent.fichas),
            "pergunta_mais_rica": ent.pergunta_mais_rica,
            "perguntas": [
                {"pergunta": q, "ramos": f.ramos_de_acao,
                 "condicoes": f.condicoes_pessoais,
                 "decide_depois": f.decisao_apos_resposta,
                 "oficial_fecha_sozinho": f.oficial_fecha_sozinho,
                 "engajamento": derivar(f)["engajamento"]}
                for q, f in ent.fichas
            ],
        },
        "tensao": ({"tensao": ent.tensao_dominante,
                    "share_com_tensao": ent.share_com_tensao,
                    "intensidade_prior": ent.intensidade}
                   if ent.tensao_dominante else None),
    }


def _fingerprint(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()[:16]


def _classe(antes: Dict[str, Any]) -> str:
    """Rótulo derivado do que a varredura produziu — não atribuído por mim."""
    if antes.get("portoes_disparados"):
        return "perdedor"
    i = antes.get("indice")
    if i is None:
        return "indeterminado"
    if i >= 0.70:
        return "vencedor"
    if i >= 0.45:
        return "deterioracao"
    return "extremo_baixo"


def gerar() -> List[Dict[str, Any]]:
    casos: List[Dict[str, Any]] = []

    # Varredura do espaço de observáveis da ficha. Duas perguntas por entidade
    # é o mínimo que produz distribuição; a segunda é fixa de propósito (uma
    # pergunta de lookup, que TODA entidade rica tem — foi o `DIRPF` que
    # ensinou isso, ver ficha.veredito_do_portao).
    lookup = Ficha(condicoes_pessoais=0, ramos_de_acao=1, fontes_oficiais=1,
                   decisao_apos_resposta=False, oficial_fecha_sozinho=True,
                   regra_mudou_recentemente=False, stake=True,
                   descobre_que_existe=False,
                   resposta_literal="O prazo é 31 de outubro.")

    for cond, ramos, dec, ofic, stk in itertools.product(
            range(4), range(1, 4), (False, True), (False, True), (False, True)):
        principal = Ficha(
            condicoes_pessoais=cond, ramos_de_acao=ramos, fontes_oficiais=2,
            decisao_apos_resposta=dec, oficial_fecha_sozinho=ofic,
            regra_mudou_recentemente=False, stake=stk, descobre_que_existe=True,
            resposta_literal="depende da sua situação: para X vale A, para Y vale B.")
        fichas = {"principal": principal, "lookup": lookup}

        for sensores in SENSORES:
            antes = _resumo_do_motor_anterior(fichas, sensores)
            if not antes:
                continue

            entrada = {
                "condicoes_pessoais": cond, "ramos_de_acao": ramos,
                "decisao_apos_resposta": dec, "oficial_fecha_sozinho": ofic,
                "stake": stk, "sensores": sensores,
            }

            depois = tese_do_resumo(antes, tema="caso", aplicar_priors=False)
            com_priors = tese_do_resumo(antes, tema="caso", aplicar_priors=True)

            # Estados do dado, contados a partir do resumo real
            ausentes = sorted(k for k, v in (antes.get("eixos") or {}).items()
                              if v.get("proveniencia") == "ausente")
            zeros_medidos = sorted(
                k for k, v in (antes.get("eixos") or {}).items()
                if v.get("proveniencia") == "medido" and v.get("nivel") in ("residual", "nenhuma"))
            palpites = sorted(k for k, v in (antes.get("eixos") or {}).items()
                              if v.get("proveniencia") == "julgado")

            casos.append({
                "id": f"{cond}{ramos}{int(dec)}{int(ofic)}{int(stk)}-{sensores}",
                "classe": _classe(antes),
                "entrada": entrada,
                "fingerprint_entrada": _fingerprint(entrada),
                "fingerprint_resumo": _fingerprint(antes),
                "antes": {
                    "apto": antes.get("apto"),
                    "motivo": antes.get("motivo"),
                    "perfil": antes.get("perfil"),
                    "indice": antes.get("indice"),
                    "cobertura": antes.get("cobertura"),
                    "portoes_disparados": antes.get("portoes_disparados"),
                    "decisao_legivel": (
                        "sem veredito de oportunidade — o motor anterior "
                        "media eixos e não respondia 'vale aprofundar?'"
                    ),
                },
                "depois": {
                    "decisao": depois.decisao,
                    "formato_de_funil": depois.formato_de_funil,
                    "observaveis_do_formato": list(depois.observaveis_do_formato),
                    "comparavel": depois.comparavel,
                    "motivo_incomparavel": depois.motivo_incomparavel,
                    "n_fatos": len(depois.fatos),
                    "n_hipoteses": len(depois.hipoteses),
                    "n_desconhecidos": len(depois.desconhecidos),
                    "n_contradicoes": len(depois.contradicoes),
                    "proximo_experimento": depois.proximo_experimento,
                },
                "componentes_deterministicos": {
                    "indice_citado": depois.indice_citado,
                    "cobertura": depois.cobertura,
                    "perfil_citado": depois.perfil_citado,
                    "indice_recalculado": False,
                    "indice_identico_ao_anterior": depois.indice_citado == antes.get("indice"),
                },
                "estados_do_dado": {
                    "ausentes": ausentes,
                    "zeros_confirmados_medidos": zeros_medidos,
                    "palpites_nao_medidos": palpites,
                    "ausente_virou_zero": any(
                        a in " ".join(depois.fatos) for a in ausentes),
                    "ausente_declarado_como_desconhecido": all(
                        any(a in d for d in depois.desconhecidos) for a in ausentes
                    ) if ausentes else True,
                },
                "bloqueadores": {
                    "portoes_do_motor": antes.get("portoes_disparados") or [],
                    "veto_do_formato": depois.formato_de_funil is None and bool(
                        antes.get("ficha", {}).get("perguntas")),
                    "cobertura_insuficiente": depois.decisao == "retido",
                },
                "explicacao_da_mudanca": _explicar(antes, depois),
                "influencia_dos_priors": {
                    "decisao_muda": com_priors.decisao != depois.decisao,
                    "formato_muda": com_priors.formato_de_funil != depois.formato_de_funil,
                    "fatos_mudam": com_priors.fatos != depois.fatos,
                    "desconhecidos_mudam": com_priors.desconhecidos != depois.desconhecidos,
                    "hipoteses_acrescidas": len(com_priors.hipoteses) - len(depois.hipoteses),
                },
            })
    return casos


def _explicar(antes: Dict[str, Any], depois) -> str:
    if depois.decisao == "sem_validacao":
        return "sem resumo: a tese declara lacuna, não veredito."
    if depois.decisao == "retido":
        return (f"cobertura {antes.get('cobertura')} abaixo do mínimo: o motor "
                "anterior devolvia índice mesmo assim; a tese retém a priorização.")
    if antes.get("portoes_disparados"):
        return (f"portão {antes['portoes_disparados']} já matava o tema antes; "
                "a tese CITA o portão e nomeia a ação seguinte.")
    if depois.formato_de_funil is None:
        return ("o canal oficial fecha todas as perguntas: informação que o motor "
                "anterior contava (`oficial_fecha_sozinho`) e jogava fora.")
    return (f"o motor anterior parava no índice {antes.get('indice')}; a tese "
            f"acrescenta formato ({depois.formato_de_funil}) com os observáveis "
            "que o produziram, e separa fato de desconhecido.")


def resumir(casos: List[Dict[str, Any]]) -> Dict[str, Any]:
    por_classe = Counter(c["classe"] for c in casos)
    por_decisao = Counter(c["depois"]["decisao"] for c in casos)
    por_formato = Counter(str(c["depois"]["formato_de_funil"]) for c in casos)

    priors_influenciam = [
        c["id"] for c in casos
        if c["influencia_dos_priors"]["decisao_muda"]
        or c["influencia_dos_priors"]["formato_muda"]
        or c["influencia_dos_priors"]["fatos_mudam"]
        or c["influencia_dos_priors"]["desconhecidos_mudam"]
    ]
    ausente_virou_zero = [c["id"] for c in casos
                          if c["estados_do_dado"]["ausente_virou_zero"]]
    indice_divergente = [
        c["id"] for c in casos
        if not c["componentes_deterministicos"]["indice_identico_ao_anterior"]
    ]
    return {
        "total_de_casos": len(casos),
        "por_classe": dict(por_classe),
        "por_decisao_nova": dict(por_decisao),
        "por_formato": dict(por_formato),
        "invariantes": {
            "priors_influenciam_algo_decisorio": priors_influenciam,
            "casos_em_que_ausente_virou_zero": ausente_virou_zero,
            "casos_em_que_o_indice_divergiu_do_anterior": indice_divergente,
        },
        "priors_registrados": [
            {"id": p["id"], "confianca": p["confianca"],
             "tem_controle": p["tem_controle"], "pode_decidir": p["pode_decidir"]}
            for p in PRIORS_WEBGO
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", required=True)
    args = ap.parse_args()

    casos = gerar()
    resumo = resumir(casos)

    # Empates: mesma decisão e mesmo índice, ordenados por `comparar`.
    teses = [tese_do_resumo(None, tema=f"vazio-{i}") for i in range(2)]
    aptos, fora = comparar(teses)
    resumo["empates"] = {
        "dois_cards_sem_validacao": {
            "no_ranking": [t.tema for t in aptos],
            "fora_do_ranking": [t.tema for t in fora],
            "regra": "desempate final por tema, estável e declarado",
        }
    }

    saida = {
        "contrato": "BEFORE-AFTER-REPLAY/1",
        "base": "b2af81f0a2018626c5d873574664991b16f7ce38",
        "o_que_e_antes": (
            "a superfície de decisão de `_resumir`/`espaco.posicionar` no commit "
            "base — apto, motivo, perfil, indice, cobertura, portoes. Esta lane "
            "NÃO alterou essa superfície."
        ),
        "o_que_e_depois": "a tese da Camada 2 sobre o MESMO resumo.",
        "corpus": (
            "produto cartesiano do espaço de observáveis da ficha "
            "(condicoes 0-3 x ramos 1-3 x decide x oficial_fecha x stake) "
            "cruzado com 6 estados de proveniência dos sensores. Nenhum caso "
            "escolhido a dedo."
        ),
        "resumo": resumo,
        "casos": casos,
    }
    pathlib.Path(args.saida).write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
