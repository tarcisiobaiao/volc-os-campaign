"""Parser defensivo de saída de LLM — cópia única, dois consumidores.

Extraído de `app/llm/base.py` sem uma alteração de comportamento. Vive aqui,
e não lá, porque passou a ter dois consumidores: o motor de pautas (via
`app.llm.base`, que o re-exporta) e `volc_ads/copy/` (via `volc_ads.ponte`).

O princípio é o mesmo que matou o fork de `motor_pautas`: duas cópias de um
artefato validado divergem, três divergem mais rápido. Este arquivo é a cópia.

Só stdlib. Nada de `app.*` — é o que o torna importável dos dois lados.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

def repair_json_delimiters(s: str) -> str:
    """Conserta deslizes de FECHAMENTO do modelo, respeitando literais de string.

    Motivação real: numa descoberta de 20 entidades (~66k chars, finishReason
    STOP), o Gemini emitiu um `]` a mais antes de fechar o objeto raiz —

        }
      ]
      ]     <- este
    }

    e a geração inteira (~19k tokens) era descartada, caindo no mock. Em 2 de 3
    chamadas do mesmo cenário.

    Duas correções, ambas conservadoras:
      - fechamento que não casa com o que está aberto (ou sem nada aberto) é
        DESCARTADO — é o `]`/`}` sobrando;
      - o que sobrou aberto no fim é FECHADO — cobre truncamento por MAX_TOKENS,
        entregando as entidades completas em vez de nenhuma (a parcial é barrada
        depois pela validação item a item).

    Nunca é chamado sobre JSON válido: só entra depois que o parse normal falha.
    """
    out: List[str] = []
    stack: List[str] = []
    in_string = False
    escaped = False

    for ch in s:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            continue
        if ch in "{[":
            stack.append(ch)
            out.append(ch)
            continue
        if ch in "}]":
            if not stack:
                continue  # fecha sem ter aberto
            if ch != ("}" if stack[-1] == "{" else "]"):
                continue  # fecha o tipo errado: é o delimitador sobrando
            stack.pop()
            out.append(ch)
            continue
        out.append(ch)

    if in_string:  # truncou no meio de um valor
        out.append('"')
    while stack:  # truncou com containers abertos
        out.append("}" if stack.pop() == "{" else "]")
    return "".join(out)


def extract_json(text: Any) -> Dict[str, Any]:
    """
    Robustly extract a JSON object from a model response.

    Ports the n8n "RESULT PROCESSOR" defensive parsing: accept a dict as-is,
    strip ```json fences, then fall back to a greedy {...} regex slice — e, por
    último, a um reparo de delimitadores (ver `repair_json_delimiters`).
    """
    if isinstance(text, dict):
        return text
    s = (text or "").strip()
    if not s:
        raise ValueError("Empty model output")

    # strip code fences
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)

    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        pass

    match = re.search(r"\{.*\}", s, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            pass

    # último recurso: reparar delimitadores. Uma geração cara não pode ser
    # perdida por um colchete a mais.
    for candidate in (s, match.group(0) if match else None):
        if not candidate:
            continue
        try:
            repaired = json.loads(repair_json_delimiters(candidate))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(repaired, dict):
            return repaired

    raise ValueError("Could not parse JSON object from model output")
