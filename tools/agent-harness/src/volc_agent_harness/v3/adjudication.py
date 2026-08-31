"""Adjudicação entre revisores.

Em rodadas anteriores o Gemini aprovou por checklist candidatos que o Sol
reprovou com contraprova executável — no P14 v4 e no P17 a2. A regra abaixo
existe para que essa divergência nunca dependa de quem lê o relatório primeiro.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Iterable, Sequence


class Forca(IntEnum):
    """Precedência da evidência. Maior vence."""

    CHECKLIST = 1
    REVISAO_SEM_EXECUCAO = 2
    EVIDENCIA_FILE_LINE = 3
    TESTE_DE_PROPRIEDADE = 4
    CONTRAPROVA_EXECUTAVEL = 5


@dataclass(frozen=True)
class Parecer:
    reviewer: str
    provider: str
    veredito: str          # accept | changes_requested | blocked
    forca: Forca
    resumo: str = ""
    reproducao: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "provider": self.provider,
            "veredito": self.veredito,
            "forca": self.forca.name,
            "forca_valor": int(self.forca),
            "resumo": self.resumo,
            "reproducao": self.reproducao,
        }


def adjudicar(pareceres: Sequence[Parecer]) -> dict[str, Any]:
    """Uma aprovação por checklist não vence contraprova executável."""

    if not pareceres:
        return {"veredito": "BLOQUEADO", "motivo": "nenhum parecer", "pareceres": []}

    contrarios = [p for p in pareceres if p.veredito != "accept"]
    favoraveis = [p for p in pareceres if p.veredito == "accept"]

    if not contrarios:
        return {
            "veredito": "ACEITAR",
            "motivo": "todos os revisores aceitaram",
            "forca_decisiva": max(p.forca for p in favoraveis).name,
            "pareceres": [p.as_dict() for p in pareceres],
        }

    mais_forte_contra = max(contrarios, key=lambda p: p.forca)
    mais_forte_a_favor = max(favoraveis, key=lambda p: p.forca) if favoraveis else None

    # Empate ou vitória do contrário: prevalece a recusa. Aceitar exige que a
    # aprovação seja ESTRITAMENTE mais forte que a objeção.
    if mais_forte_a_favor is not None and mais_forte_a_favor.forca > mais_forte_contra.forca:
        veredito = "ACEITAR"
        motivo = (
            f"aprovação de {mais_forte_a_favor.reviewer} ({mais_forte_a_favor.forca.name}) "
            f"supera a objeção de {mais_forte_contra.reviewer} ({mais_forte_contra.forca.name})"
        )
    else:
        veredito = "BLOQUEADO" if mais_forte_contra.veredito == "blocked" else "CORRIGIR"
        motivo = (
            f"{mais_forte_contra.reviewer} ({mais_forte_contra.forca.name}) prevalece"
            + (
                f" sobre {mais_forte_a_favor.reviewer} ({mais_forte_a_favor.forca.name})"
                if mais_forte_a_favor is not None else ""
            )
        )

    return {
        "veredito": veredito,
        "motivo": motivo,
        "forca_decisiva": mais_forte_contra.forca.name,
        "exige_contraprova_antes_de_corrigir": mais_forte_contra.forca < Forca.CONTRAPROVA_EXECUTAVEL,
        "reproducao": mais_forte_contra.reproducao,
        "pareceres": [p.as_dict() for p in pareceres],
    }
