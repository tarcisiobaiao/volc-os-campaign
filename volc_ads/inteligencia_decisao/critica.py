"""Porta opcional para crítica/explicação sem autoridade decisória.

Nenhuma implementação de rede é fornecida nesta missão. A porta recebe somente
campos allowlisted e devolve comentário estruturado separado do veredito.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


CAMPOS_PERMITIDOS = (
    "scenario_id",
    "veredito",
    "health_gate",
    "fatores",
    "politicas",
    "conflitos",
    "evidencias",
)
RESPOSTA_PERMITIDA = ("resumo", "questoes", "campos_considerados")
LIMITE_CONTEXTO_BYTES = 48_000
LIMITE_RESUMO = 4_000
LIMITE_QUESTOES = 20
LIMITE_QUESTAO = 1_000
LIMITE_RESPOSTA_BYTES = 32_000


class PortaCritica(Protocol):
    def analisar(self, contexto: Mapping[str, Any]) -> Mapping[str, Any]: ...


class CriticoDeterministico:
    """Fake hermético: mesma entrada, mesma resposta, zero chave e zero rede."""

    def analisar(self, contexto: Mapping[str, Any]) -> Mapping[str, Any]:
        conflitos = contexto.get("conflitos") or []
        return {
            "resumo": (
                "A cadeia causal está coerente com os bloqueios declarados."
                if not conflitos
                else "A decisão respeita os conflitos e mantém a ação bloqueada."
            ),
            "questoes": [
                "A procedência e o frescor acompanham cada fator?",
                "Há algum dado ausente tratado como zero?",
            ],
            "campos_considerados": sorted(contexto),
        }


def executar_critica(porta: PortaCritica | None, contexto: Mapping[str, Any]) -> dict[str, Any]:
    """Filtra entrada e saída; a crítica não recebe nem devolve campos de poder."""

    if porta is None:
        return {
            "estado": "nao_configurada",
            "autoridade": "explicador_sem_poder_decisorio",
            "resposta": None,
        }
    filtrado = {chave: contexto.get(chave) for chave in CAMPOS_PERMITIDOS}
    import json

    if len(json.dumps(filtrado, ensure_ascii=False, default=str).encode("utf-8")) > LIMITE_CONTEXTO_BYTES:
        return {"estado": "indisponivel", "autoridade": "explicador_sem_poder_decisorio", "resposta": None}
    try:
        bruto = porta.analisar(filtrado)
    except Exception:  # a crítica opcional nunca derruba o kernel determinístico
        return {"estado": "indisponivel", "autoridade": "explicador_sem_poder_decisorio", "resposta": None}
    if not isinstance(bruto, Mapping) or set(bruto) != set(RESPOSTA_PERMITIDA):
        return {
            "estado": "resposta_rejeitada",
            "autoridade": "explicador_sem_poder_decisorio",
            "resposta": None,
        }
    resumo = bruto.get("resumo")
    questoes = bruto.get("questoes")
    campos = bruto.get("campos_considerados")
    if not isinstance(resumo, str) or len(resumo) > LIMITE_RESUMO or not isinstance(questoes, Sequence) or isinstance(questoes, str):
        return {
            "estado": "resposta_rejeitada",
            "autoridade": "explicador_sem_poder_decisorio",
            "resposta": None,
        }
    if not isinstance(campos, Sequence) or isinstance(campos, str):
        return {
            "estado": "resposta_rejeitada",
            "autoridade": "explicador_sem_poder_decisorio",
            "resposta": None,
        }
    if any(str(c) not in CAMPOS_PERMITIDOS for c in campos):
        return {
            "estado": "resposta_rejeitada",
            "autoridade": "explicador_sem_poder_decisorio",
            "resposta": None,
        }
    if len(questoes) > LIMITE_QUESTOES or any(len(str(q)) > LIMITE_QUESTAO for q in questoes):
        return {"estado": "resposta_rejeitada", "autoridade": "explicador_sem_poder_decisorio", "resposta": None}
    if len(json.dumps(bruto, ensure_ascii=False, default=str).encode("utf-8")) > LIMITE_RESPOSTA_BYTES:
        return {"estado": "resposta_rejeitada", "autoridade": "explicador_sem_poder_decisorio", "resposta": None}
    return {
        "estado": "explicada",
        "autoridade": "explicador_sem_poder_decisorio",
        "resposta": {
            "resumo": resumo,
            "questoes": [str(q) for q in questoes],
            "campos_considerados": [str(c) for c in campos],
        },
    }
