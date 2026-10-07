"""PACOTE DE POLÍTICAS DO REVISOR (reforma editorial, etapa B5).

## Por que existe

O revisor contextual pode BLOQUEAR uma página — e só pode fazer isso com uma
regra de plataforma que exista de verdade. Sem uma lista fechada, o modelo
"lembra" regras (a proibição de primeira pessoa, a de "grátis", a de pergunta
em título) que a Frente A mostrou não existirem nas páginas oficiais.

## De onde vem

É GERADO do livro-razão da Frente A (`frente-a-politicas/ledger.json`), nunca
escrito à mão, por `scripts/gerar_pacote_revisor.py`:

- entra só o que é A (exigência explícita da plataforma: `o_que_exige`) ou B
  (interpretação contextual de risco: `o_que_apenas_sugere_risco`, e crença
  "não escrita" classificada B), das superfícies `search_ads`, `landing_page` e
  `monetizacao_publisher`;
- C (preferência interna) vira NOTA: o revisor pode citá-la como nota, nunca
  como bloqueio;
- D (obsoleta ou sem fundamento) não entra;
- cada entrada leva id, classe, texto curto, url, `consultado_em` e `aplica_a`.

## Dono e validade

O arquivo declara `dono` e `valido_ate` (refresh em 30 dias). Vencido, o
revisor continua rodando e apontando, mas não aprova sozinho: a página vai para
decisão humana até alguém regenerar o pacote com a política consultada de novo
(ver `pipeline/revisao.py`).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

VERSAO = "pacote-revisor-v1"
SUPERFICIES: tuple[str, ...] = ("search_ads", "landing_page", "monetizacao_publisher")
REFRESH_DIAS = 30
LIMITE_DO_TEXTO = 280
CAMINHO_DO_PACOTE = Path(__file__).with_name("pacote_revisor.json")

# O que é REGRA DE PÁGINA (o que o revisor do funil julga): tudo que se aplica
# à landing page ou à monetização do publisher, mais as famílias de
# Misrepresentation/abuso/marca de `search_ads`, que valem para a promessa e o
# destino. Formato de anúncio (limite de título, pontuação, snippet) é regra da
# copy Search, não de página: fica no arquivo e fora do prompt do revisor.
_PREFIXOS_DE_PAGINA_EM_SEARCH = ("ADS-MIS-", "ADS-ORB-", "ADS-ABU-", "ADS-TM-")


# O ledger da Frente A escreveu parte dos itens JÁ APLICADOS ao caso que ela
# auditou ("não sugerir vínculo com o Senac"). O pacote vai ao revisor de
# QUALQUER nicho: esses itens são marcados e o prompt os mostra como exemplo,
# junto da regra geral — sem reintroduzir o caso Senac como regra genérica.
_CASO_ESPECIFICO_RE = re.compile(r"senac|cr[eé]dito\s*up|\bcnc\b|\bpsg\b", re.IGNORECASE)


def _curto(texto: str, limite: int = LIMITE_DO_TEXTO) -> str:
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _aplica_a(entrada: dict) -> list[str]:
    principal = entrada.get("superficie")
    secundarias = [s for s in (entrada.get("superficies_secundarias") or []) if s]
    ordem = [principal, *secundarias] if principal else list(secundarias)
    vistos: list[str] = []
    for s in ordem:
        if s and s not in vistos:
            vistos.append(s)
    return vistos


def _pertinente(entrada: dict) -> bool:
    """Superfície principal no escopo, ou (fora da API) secundária no escopo."""
    principal = entrada.get("superficie")
    if principal in SUPERFICIES:
        return True
    if principal == "api":
        return False
    return bool(set(entrada.get("superficies_secundarias") or []) & set(SUPERFICIES))


def _url(entrada: dict) -> str:
    return str(entrada.get("url_final") or entrada.get("url") or "").strip()


def _classe_da_crenca(texto: str | None) -> str:
    """'B (risco), não A' -> B; 'C (conservadora; base B)' -> C; 'D ...' -> D."""
    bruto = (texto or "").strip().upper()
    return bruto[:1] if bruto[:1] in {"A", "B", "C", "D"} else ""


def _marca_de_caso(texto: str, geral: str) -> dict:
    if _CASO_ESPECIFICO_RE.search(texto or ""):
        return {"caso_especifico": True, "regra_geral": geral}
    return {}


def gerar_pacote(ledger: list[dict], *, gerado_em: date, dono: str,
                 fonte: dict[str, str]) -> dict[str, Any]:
    """O pacote a partir das entradas do ledger. Puro e determinístico."""
    regras: list[dict] = []
    notas: list[dict] = []
    excluidos: dict[str, list[str]] = {"classe_d": [], "fora_de_superficie": [],
                                       "sem_classe": []}
    for entrada in ledger:
        eid = str(entrada.get("id") or "").strip()
        tipo = entrada.get("tipo")
        if not eid or tipo not in ("regra", "nao_escrito"):
            continue
        if not _pertinente(entrada):
            excluidos["fora_de_superficie"].append(eid)
            continue
        base = {"regra": eid, "url": _url(entrada),
                "consultado_em": str(entrada.get("consultado_em") or ""),
                "aplica_a": _aplica_a(entrada),
                "titulo": _curto(entrada.get("titulo") or "", 120)}
        geral = _curto(entrada.get("regra_resumo") or entrada.get("titulo") or "", 200)
        if tipo == "regra":
            itens = [("A", t) for t in entrada.get("o_que_exige") or []]
            itens += [("B", t) for t in entrada.get("o_que_apenas_sugere_risco") or []]
            contagem = {"A": 0, "B": 0}
            for classe, texto in itens:
                contagem[classe] += 1
                regras.append({"id": f"{eid}#{classe}{contagem[classe]}", "classe": classe,
                               "texto": _curto(texto), **base,
                               **_marca_de_caso(texto, geral)})
            continue
        classe = _classe_da_crenca(entrada.get("classe_da_crenca"))
        texto = _curto(entrada.get("regra_resumo") or entrada.get("titulo") or "")
        if classe == "B":
            regras.append({"id": f"{eid}#B1", "classe": "B", "texto": texto, **base,
                           **_marca_de_caso(texto, _curto(entrada.get("titulo") or "", 200))})
        elif classe == "C":
            notas.append({"id": eid, "classe": "C", "texto": texto, **base})
        elif classe == "D":
            excluidos["classe_d"].append(eid)
        else:
            excluidos["sem_classe"].append(eid)
    return {
        "versao": VERSAO,
        "gerado_em": gerado_em.isoformat(),
        "valido_ate": (gerado_em + timedelta(days=REFRESH_DIAS)).isoformat(),
        "refresh_dias": REFRESH_DIAS,
        "dono": dono,
        "fonte": dict(fonte),
        "superficies": list(SUPERFICIES),
        "regra_de_classes": ("A e B podem sustentar bloqueio (com id e url); C é nota "
                             "e nunca bloqueia; D não entra."),
        "regras": regras,
        "notas_c": notas,
        "excluidos": excluidos,
    }


@dataclass
class PacoteDoRevisor:
    versao: str
    dono: str
    gerado_em: date
    valido_ate: date
    vencido: bool
    regras: list[dict] = field(default_factory=list)
    notas_c: list[dict] = field(default_factory=list)
    fonte: dict = field(default_factory=dict)

    def ids_bloqueantes(self) -> set[str]:
        return {r["id"] for r in self.regras if r.get("classe") in ("A", "B")}

    def ids_de_nota(self) -> set[str]:
        return {n["id"] for n in self.notas_c}

    def resumo(self) -> dict:
        return {"versao": self.versao, "dono": self.dono,
                "gerado_em": self.gerado_em.isoformat(),
                "valido_ate": self.valido_ate.isoformat(), "vencido": self.vencido}


def carregar_pacote(caminho: Path | None = None, *, hoje: date | None = None) -> PacoteDoRevisor:
    """Lê o pacote versionado. `vencido` compara `valido_ate` com hoje."""
    dados = json.loads((caminho or CAMINHO_DO_PACOTE).read_text(encoding="utf-8"))
    hoje = hoje or date.today()
    valido_ate = date.fromisoformat(dados["valido_ate"])
    return PacoteDoRevisor(
        versao=dados.get("versao", VERSAO), dono=str(dados.get("dono") or ""),
        gerado_em=date.fromisoformat(dados["gerado_em"]), valido_ate=valido_ate,
        vencido=hoje > valido_ate, regras=list(dados.get("regras") or []),
        notas_c=list(dados.get("notas_c") or []), fonte=dict(dados.get("fonte") or {}),
    )


def _de_pagina(regra: dict) -> bool:
    if set(regra.get("aplica_a") or []) & {"landing_page", "monetizacao_publisher"}:
        return True
    return str(regra.get("regra") or "").startswith(_PREFIXOS_DE_PAGINA_EM_SEARCH)


def pacote_para_o_revisor(pacote: PacoteDoRevisor) -> dict:
    """O recorte que vai ao prompt do revisor de PÁGINA: regras A/B de página e
    as notas C (que só podem virar nota)."""
    return {
        "resumo": pacote.resumo(),
        "regras": [r for r in pacote.regras if _de_pagina(r)],
        "notas_c": list(pacote.notas_c),
    }
