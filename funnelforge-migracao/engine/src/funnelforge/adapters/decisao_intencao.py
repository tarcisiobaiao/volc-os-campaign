"""Experimento consultivo TypeSafe. Nunca decide fatos nem bloqueia páginas."""
from __future__ import annotations

import json
import os
from typing import Protocol

import httpx

FORMATOS = ("secao", "faq", "ferramenta", "avaliar")


class ProviderDeDecisao(Protocol):
    def classificar(self, perguntas: list[str]) -> dict: ...


class HeuristicaDeIntencao:
    def classificar(self, perguntas: list[str]) -> dict:
        from funnelforge.domain.dossie import texto_normal
        resultados = []
        for q in perguntas:
            texto = texto_normal(q)
            formato = ("ferramenta" if any(t in texto for t in ("calcular", "calculo", "simular"))
                       else "faq" if texto.startswith(("qual o telefone", "qual o horario"))
                       else "secao" if texto.startswith(("o que e", "qual a diferenca"))
                       else "avaliar")
            resultados.append(formato)
        return {"formatos": resultados, "provider": "deterministico",
                "requested_model": "", "served_model": "", "fallback": False}


class JevDeIntencao:
    def __init__(self, *, enabled=False, key=None, model="jev-latest", timeout=3.0,
                 transport=None):
        self.enabled, self.key = enabled, key or os.environ.get("TYPESAFE_API_KEY")
        self.model, self.timeout, self.transport = model, timeout, transport
        self.chamadas = 0

    def classificar(self, perguntas: list[str]) -> dict:
        fallback = HeuristicaDeIntencao().classificar(perguntas)
        if not self.enabled or not self.key:
            return {**fallback, "motivo": "desligado" if not self.enabled else "sem_credencial"}
        # Até UMA chamada por instância. 20k caracteres impõem teto conservador
        # muito inferior a US$ .05 no preço publicado; sem retry.
        payload = {"model": self.model, "state": perguntas, "questions": {
            f"q{i}": {"type": "choice", "instructions": f"Sugira formato para pergunta {i}. "
                       "Nenhuma pergunta justifica sozinha criar uma página.",
                       "criteria": {f: f for f in FORMATOS}} for i in range(len(perguntas))}}
        if self.chamadas or len(json.dumps(payload)) > 20000 or not perguntas:
            return {**fallback, "fallback": True, "motivo": "orcamento"}
        self.chamadas += 1
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as cliente:
                resp = cliente.post("https://api.typesafe.ai/v1/systemone", json=payload,
                                    headers={"Authorization": "Bearer " + self.key})
                resp.raise_for_status()
                dados = resp.json()
            formatos = [dados["answers"][f"q{i}"]["choice"] for i in range(len(perguntas))]
            if not dados.get("model") or any(f not in FORMATOS for f in formatos):
                raise ValueError("contrato")
            return {"formatos": formatos, "provider": "typesafe_experimental",
                    "requested_model": self.model, "served_model": dados["model"],
                    "fallback": False, "usage": dados.get("usage"), "custo_usd": None}
        except Exception as exc:
            return {**fallback, "fallback": True, "requested_model": self.model,
                    "served_model": "", "motivo": type(exc).__name__}
