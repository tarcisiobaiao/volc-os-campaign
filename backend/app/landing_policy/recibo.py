"""O RECIBO do portão — o que ficou provado, e contra o quê.

Um veredito sem recibo é uma opinião com data. O recibo existe para que, seis
semanas depois, dê para responder três perguntas sem reabrir o caso:

  * **qual página** foi avaliada — URL e hash do conteúdo, não "a LP do FGTS";
  * **contra qual política** — a versão é o hash da matriz de fontes, então
    ninguém edita a regra e mantém o recibo antigo parecendo válido;
  * **com que evidência** — o hash de cada inventário (links, formulários,
    alegações…), que prova QUAL inventário foi avaliado sem arrastar 170 KB de
    HTML para dentro do artefato.

`paid_destination_ready` só é `true` quando não sobrou bloqueio nem
desconhecido. É a única afirmação forte do arquivo, e ela é estreita de
propósito — ver `portao.Avaliacao.paid_destination_ready`.
"""
from __future__ import annotations

import json
from typing import Any

from app.landing_policy.contrato import (
    CARIMBO_DETERMINISTICO,
    SCHEMA_VERSION,
    carregar_fontes,
    fonte_do_codigo,
    impressao,
    versao_da_fonte,
)
from app.landing_policy.portao import Avaliacao


def emitir(
    avaliacao: Avaliacao,
    *,
    hash_do_conteudo: str,
    carimbo: str = CARIMBO_DETERMINISTICO,
    fontes: dict[str, Any] | None = None,
    referencias_de_evidencia: list[str] | None = None,
) -> dict[str, Any]:
    """Monta o recibo de UMA passagem pelo portão.

    `carimbo` tem default determinístico de propósito: recibo emitido sobre
    artefato local precisa poder ser comparado byte a byte entre duas execuções.
    Quem avalia uma página AO VIVO passa o instante real da observação — ali a
    hora é evidência, não ruído.
    """
    fontes = fontes if fontes is not None else carregar_fontes()

    inventarios = {
        v.nome: {
            "status": v.status,
            "itens": len(v.inventario),
            "sha256": v.hash_inventario(),
            **({"detalhe": v.detalhe} if v.detalhe else {}),
        }
        for v in sorted(avaliacao.verificacoes, key=lambda v: v.nome)
    }

    def _achados(lista: list[Any]) -> list[dict[str, Any]]:
        saida = []
        for achado in lista:
            item = achado.para_json()
            fonte = fonte_do_codigo(achado.codigo, fontes)
            if fonte:
                item["policy"] = {
                    "policy": fonte.get("policy"),
                    "url": fonte.get("url"),
                    "consulted_at": fonte.get("consulted_at"),
                }
            saida.append(item)
        return saida

    return {
        "schema": "LandingPolicyGateReceipt",
        "schema_version": SCHEMA_VERSION,
        "gate_point": avaliacao.ponto.value,
        "role": avaliacao.papel.value,
        "url": avaliacao.url,
        "content_sha256": hash_do_conteudo,
        "observed_at": carimbo,
        "policy_source_version": versao_da_fonte(fontes),
        "policy_sources_consulted": sorted(
            {
                (r.get("url") or "")
                for r in (fontes.get("rules") or {}).values()
                if r.get("url")
            }
        ),
        "verdict": avaliacao.veredito.value,
        "paid_destination_ready": avaliacao.paid_destination_ready,
        "not_ready_reasons": avaliacao.motivos,
        "inventory_hashes": inventarios,
        "identity_result": inventarios.get("identity", {}).get("status"),
        "security_result": inventarios.get("destination_security_signals", {}).get("status"),
        "blockers": _achados(avaliacao.bloqueios),
        "risks": _achados(avaliacao.riscos),
        "observations": _achados(avaliacao.observacoes),
        "unknowns": avaliacao.desconhecidos,
        "evidence_refs": sorted(referencias_de_evidencia or []),
        # A prova de contenção viaja NO recibo, não numa frase de relatório: um
        # recibo é a única coisa que sobrevive a esta sessão.
        "external_mutation": {
            "google_ads_mutate": False,
            "wordpress_write": False,
            "appeal_submitted": False,
            "deploy": False,
        },
    }


def json_deterministico(recibo: dict[str, Any]) -> str:
    return json.dumps(recibo, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def impressao_do_recibo(recibo: dict[str, Any]) -> str:
    """Hash do recibo inteiro — o que se cita num handoff sem colar o recibo."""
    return impressao(recibo)
