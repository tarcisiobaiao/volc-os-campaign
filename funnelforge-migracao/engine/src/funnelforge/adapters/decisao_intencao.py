"""JEV consultivo: demanda real -> sinais emocionais tipados para o arquiteto.

O adaptador não escreve copy, não inventa avatar demográfico e nunca bloqueia
uma página. Uma chamada em lote classifica as perguntas que já vieram de PAA,
termos ou autocomplete. Sem credencial, timeout ou contrato válido, o motor
continua com a heurística estreita e registra o fallback.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx

FORMATOS = ("secao", "faq", "ferramenta", "avaliar")
FAMILIAS = (
    "oportunidade",
    "incerteza",
    "medo_de_perder",
    "desejo_de_controle",
    "prevencao_de_erro",
    "necessidade_de_acao",
    "ambigua",
)
ENTREGAS = (
    "explicacao",
    "criterios",
    "calendario",
    "calculo",
    "comparacao",
    "passo_a_passo",
    "localizacao",
    "correcao",
    "confirmacao",
    "alerta",
)
MOMENTOS = ("reconhecimento", "qualificacao", "decisao", "preparacao", "acao", "confirmacao")
NIVEIS = ("ausente ou irrelevante", "baixo", "moderado", "alto", "muito alto")


class ProviderDeDecisao(Protocol):
    def classificar(self, perguntas: list[str], *, contexto: dict | None = None) -> dict: ...


def _formato_heuristico(texto: str) -> str:
    from funnelforge.domain.dossie import texto_normal

    t = texto_normal(texto)
    return (
        "ferramenta"
        if any(x in t for x in ("calcular", "calculo", "simular", "quanto"))
        else "faq"
        if t.startswith(("qual o telefone", "qual o horario", "onde ligar"))
        else "secao"
        if t.startswith(("o que e", "qual a diferenca"))
        else "avaliar"
    )


def _familia_heuristica(texto: str) -> str:
    """Fallback pequeno. Não tenta substituir o classificador por regex."""
    from funnelforge.domain.dossie import texto_normal

    t = texto_normal(texto)
    if any(x in t for x in ("prazo", "quando", "data", "perder", "ainda da tempo")):
        return "medo_de_perder"
    if any(x in t for x in ("erro", "evitar", "golpe", "documento", "nao consigo")):
        return "prevencao_de_erro"
    if any(x in t for x in ("como fazer", "como pedir", "como sacar", "onde ir", "inscricao")):
        return "necessidade_de_acao"
    if any(x in t for x in ("quanto", "calcular", "acompanhar", "consultar", "controlar")):
        return "desejo_de_controle"
    if any(
        x in t for x in ("ganhar", "receber", "gratis", "gratuito", "beneficio", "oportunidade")
    ):
        return "oportunidade"
    if any(x in t for x in ("quem", "qual", "sera", "posso", "tenho direito")):
        return "incerteza"
    return "ambigua"


_DIRECAO = {
    "oportunidade": (
        "nomeie o ganho informacional ou a possibilidade concreta que a próxima resposta esclarece"
    ),
    "incerteza": "prometa reduzir uma dúvida específica e diga exatamente o que será esclarecido",
    "medo_de_perder": "mostre o que conferir para não perder prazo, direito ou próximo passo real",
    "desejo_de_controle": (
        "devolva controle com cálculo, comparação, acompanhamento ou critério verificável"
    ),
    "prevencao_de_erro": (
        "mostre o erro evitável, o sinal de alerta ou o preparo que reduz retrabalho"
    ),
    "necessidade_de_acao": (
        "conduza ao próximo passo executável, com verbo concreto e resultado informacional"
    ),
    "ambigua": "nomeie a próxima resposta concreta sem fabricar urgência ou personalização",
}

_LIMITES = {
    "oportunidade": "não transforme possibilidade em promessa de ganho ou aprovação",
    "incerteza": "não simule consulta, saldo, elegibilidade ou resultado pessoal",
    "medo_de_perder": "não invente prazo, escassez, contagem regressiva ou última chance",
    "desejo_de_controle": "não prometa dados individuais que a página não possui",
    "prevencao_de_erro": "não use medo genérico; cite apenas risco sustentado pelo conteúdo",
    "necessidade_de_acao": "não diga que o site executa a ação quando ele apenas orienta",
    "ambigua": "não force emoção sem sinal observado na demanda",
}


def _nota(answer: dict, campo: str = "score") -> float:
    try:
        valor = float(answer.get(campo, 0.0))
    except (TypeError, ValueError):
        return 0.0
    teto = 1.0 if campo == "confidence" else 4.0
    return round(max(0.0, min(teto, valor)) * (100 / teto), 1)


def _probabilidades(answer: dict) -> dict[str, float]:
    probs = answer.get("probabilities") or {}
    if not isinstance(probs, dict):
        return {}
    fora = {}
    for chave, valor in probs.items():
        if chave not in FAMILIAS:
            continue
        try:
            fora[chave] = round(max(0.0, min(1.0, float(valor))) * 100, 1)
        except (TypeError, ValueError):
            continue
    return fora


def _sinal_fallback(pergunta: str, duvida_id: str = "") -> dict:
    familia = _familia_heuristica(pergunta)
    return {
        "pergunta": pergunta,
        "duvida_id": duvida_id,
        "familia": familia,
        "correspondencia": {familia: 100.0},
        "confianca": 0.0,
        "intensidade": 0.0,
        "autorrelevancia": 0.0,
        "potencial_continuacao": 0.0,
        "urgencia_de_acao": 0.0,
        "entrega": "explicacao",
        "momento": "reconhecimento",
        "formato": _formato_heuristico(pergunta),
        "direcao_cta": _DIRECAO[familia],
        "limite_cta": _LIMITES[familia],
    }


def _correlacoes(sinais: list[dict]) -> list[dict]:
    ordem = {m: i for i, m in enumerate(MOMENTOS)}
    fora = []
    for i, a in enumerate(sinais):
        for j, b in enumerate(sinais[i + 1 :], i + 1):
            mesma_familia = a["familia"] == b["familia"] and a["familia"] != "ambigua"
            mesma_entrega = a["entrega"] == b["entrega"]
            distancia = abs(ordem.get(a["momento"], 0) - ordem.get(b["momento"], 0))
            adjacentes = distancia == 1
            nota = (
                (45 if mesma_familia else 0)
                + (25 if mesma_entrega else 0)
                + (20 if adjacentes else 0)
            )
            if a["potencial_continuacao"] >= 60 and b["potencial_continuacao"] >= 60:
                nota += 10
            if nota < 45:
                continue
            if mesma_familia and mesma_entrega and distancia == 0:
                relacao, motivo = (
                    "possivel_redundancia",
                    "mesma família, entrega e momento; conferir se são a mesma dúvida",
                )
            elif adjacentes:
                relacao, motivo = (
                    "progressao",
                    "momentos adjacentes da jornada com tensão compatível",
                )
            else:
                relacao, motivo = (
                    "complementar",
                    "mesma tensão com entregas ou momentos diferentes",
                )
            fora.append(
                {
                    "origem": i,
                    "destino": j,
                    "origem_duvida_id": a.get("duvida_id", ""),
                    "destino_duvida_id": b.get("duvida_id", ""),
                    "nota": float(min(nota, 100)),
                    "relacao": relacao,
                    "motivo": motivo,
                }
            )
    return sorted(fora, key=lambda x: (-x["nota"], x["origem"], x["destino"]))


def _perfil(
    sinais: list[dict],
    *,
    provider: str,
    pedido: str = "",
    servido: str = "",
    estado: str = "presente",
) -> dict:
    distribuicao = {f: 0.0 for f in FAMILIAS}
    for sinal in sinais:
        probs = sinal.get("correspondencia") or {sinal["familia"]: 100.0}
        for familia in FAMILIAS:
            distribuicao[familia] += float(probs.get(familia, 0.0))
    if sinais:
        distribuicao = {f: round(v / len(sinais), 1) for f, v in distribuicao.items()}
    dominante = max(distribuicao, key=distribuicao.get) if sinais else "ambigua"

    def forca(sinal):
        return (
            0.30 * sinal["intensidade"]
            + 0.25 * sinal["autorrelevancia"]
            + 0.30 * sinal["potencial_continuacao"]
            + 0.15 * sinal["urgencia_de_acao"]
        )

    climax = max(range(len(sinais)), key=lambda i: forca(sinais[i])) if sinais else None
    climax_duvida_id = sinais[climax].get("duvida_id") if climax is not None else None
    entrega = sinais[climax]["entrega"] if climax is not None else "explicacao"
    resumo = (
        f"Leitor movido principalmente por {dominante.replace('_', ' ')}, "
        f"que busca {entrega.replace('_', ' ')} antes de avançar."
        if sinais
        else "Demanda insuficiente para formar avatar comportamental."
    )
    return {
        "schema_version": 1,
        "estado": estado,
        "provider": provider,
        "modelo_pedido": pedido,
        "modelo_servido": servido,
        "familia_dominante": dominante,
        "distribuicao": distribuicao,
        "resumo": resumo,
        "sinais": sinais,
        "correlacoes": _correlacoes(sinais),
        "climax_pergunta": climax,
        "climax_duvida_id": climax_duvida_id,
        "hipotese": "Leitura comportamental consultiva; precisa ser calibrada com dados reais.",
    }


class HeuristicaDeIntencao:
    def classificar(self, perguntas: list[str], *, contexto: dict | None = None) -> dict:
        ids = (contexto or {}).get("duvida_ids") or []
        sinais = [
            _sinal_fallback(q, ids[i] if i < len(ids) else "") for i, q in enumerate(perguntas)
        ]
        return {
            "formatos": [s["formato"] for s in sinais],
            "provider": "deterministico",
            "requested_model": "",
            "served_model": "",
            "fallback": False,
            "perfil_emocional": _perfil(sinais, provider="deterministico", estado="fallback"),
        }


class JevDeIntencao:
    def __init__(
        self, *, enabled=False, key=None, model="jev-latest", timeout=10.0, transport=None
    ):
        self.enabled = enabled
        self.key = key or os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
        self.model, self.timeout, self.transport = model, timeout, transport
        self.chamadas = 0

    @staticmethod
    def _questions(perguntas: list[str]) -> dict:
        questions: dict[str, dict[str, Any]] = {}
        for i, _ in enumerate(perguntas):
            alvo = f"`perguntas[{i}].texto`"
            questions[f"formato_{i}"] = {
                "type": "choice",
                "instructions": (
                    f"Qual formato melhor entrega a resposta de {alvo}? Não decida se vira página."
                ),
                "criteria": {f: f for f in FORMATOS},
            }
            questions[f"familia_{i}"] = {
                "type": "choice",
                "instructions": (
                    "Qual tensão comportamental é mais visível na linguagem de "
                    f"{alvo}? Use ambigua se não houver sinal claro."
                ),
                "criteria": {
                    "oportunidade": "busca por ganho, acesso, benefício ou possibilidade",
                    "incerteza": "não sabe se, quem, qual ou como algo se aplica",
                    "medo_de_perder": "receio de perder prazo, dinheiro, direito ou ocasião",
                    "desejo_de_controle": (
                        "quer calcular, acompanhar, comparar ou dominar a situação"
                    ),
                    "prevencao_de_erro": (
                        "quer evitar fraude, rejeição, retrabalho ou decisão errada"
                    ),
                    "necessidade_de_acao": "quer executar um próximo passo concreto agora",
                    "ambigua": "o texto não permite distinguir com segurança",
                },
            }
            for nome, instrucao in {
                "intensidade": "Quão forte é a tensão emocional explicitamente observável",
                "autorrelevancia": (
                    "Quanto a pergunta indica consequência pessoal para quem pergunta"
                ),
                "continuacao": (
                    "Quanto a resposta tende a abrir uma próxima dúvida útil e relacionada"
                ),
                "acao": "Quanto a pessoa parece precisar executar um próximo passo concreto",
            }.items():
                questions[f"{nome}_{i}"] = {
                    "type": "score",
                    "instructions": (
                        f"{instrucao} em {alvo}. Julgue a linguagem, não invente demografia."
                    ),
                    "criteria": list(NIVEIS),
                }
            questions[f"entrega_{i}"] = {
                "type": "choice",
                "instructions": f"Qual entrega editorial responde melhor a {alvo}?",
                "criteria": {e: e.replace("_", " ") for e in ENTREGAS},
            }
            questions[f"momento_{i}"] = {
                "type": "choice",
                "instructions": f"Em qual momento de decisão {alvo} aparece?",
                "criteria": {m: m for m in MOMENTOS},
            }
        return questions

    def classificar(self, perguntas: list[str], *, contexto: dict | None = None) -> dict:
        fallback = HeuristicaDeIntencao().classificar(perguntas, contexto=contexto)
        if not self.enabled or not self.key:
            return {**fallback, "motivo": "desligado" if not self.enabled else "sem_credencial"}
        state = {
            "tema": (contexto or {}).get("tema", ""),
            "pais": (contexto or {}).get("pais", ""),
            "idioma": (contexto or {}).get("idioma", ""),
            "perguntas": [
                {
                    "indice": i,
                    "duvida_id": ((contexto or {}).get("duvida_ids") or [])[i]
                    if i < len((contexto or {}).get("duvida_ids") or [])
                    else "",
                    "texto": q,
                }
                for i, q in enumerate(perguntas)
            ],
        }
        payload = {"model": self.model, "state": state, "questions": self._questions(perguntas)}
        # Um funil real combina PAA, termos e dores e costuma chegar a 15–20
        # sinais. O teto antigo de 30 kB desligava o JEV exatamente nesses runs,
        # embora a requisição continue pequena para o endpoint (dezenas de KB,
        # não MB). Mantemos UMA chamada e um teto rígido, apenas dimensionado
        # para o lote real medido; acima dele o fail-soft continua intacto.
        if self.chamadas or len(json.dumps(payload, ensure_ascii=False)) > 60000 or not perguntas:
            return {**fallback, "fallback": True, "motivo": "orcamento"}
        self.chamadas += 1
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as cliente:
                resp = cliente.post(
                    "https://api.typesafe.ai/v1/systemone",
                    json=payload,
                    headers={"Authorization": "Bearer " + self.key},
                )
                resp.raise_for_status()
                dados = resp.json()
            answers, servido = dados["answers"], str(dados.get("model") or "")
            if not servido:
                raise ValueError("modelo_ausente")
            sinais = []
            for i, pergunta in enumerate(perguntas):
                familia_a = answers[f"familia_{i}"]
                familia, formato = familia_a["choice"], answers[f"formato_{i}"]["choice"]
                entrega, momento = (
                    answers[f"entrega_{i}"]["choice"],
                    answers[f"momento_{i}"]["choice"],
                )
                if (
                    familia not in FAMILIAS
                    or formato not in FORMATOS
                    or entrega not in ENTREGAS
                    or momento not in MOMENTOS
                ):
                    raise ValueError("contrato")
                sinais.append(
                    {
                        "pergunta": pergunta,
                        "duvida_id": state["perguntas"][i]["duvida_id"],
                        "familia": familia,
                        "correspondencia": _probabilidades(familia_a),
                        "confianca": _nota(familia_a, "confidence"),
                        "intensidade": _nota(answers[f"intensidade_{i}"]),
                        "autorrelevancia": _nota(answers[f"autorrelevancia_{i}"]),
                        "potencial_continuacao": _nota(answers[f"continuacao_{i}"]),
                        "urgencia_de_acao": _nota(answers[f"acao_{i}"]),
                        "entrega": entrega,
                        "momento": momento,
                        "formato": formato,
                        "direcao_cta": _DIRECAO[familia],
                        "limite_cta": _LIMITES[familia],
                    }
                )
            perfil = _perfil(
                sinais,
                provider="typesafe_jev",
                pedido=self.model,
                servido=servido,
                estado="presente",
            )
            return {
                "formatos": [s["formato"] for s in sinais],
                "provider": "typesafe_jev",
                "requested_model": self.model,
                "served_model": servido,
                "fallback": False,
                "usage": dados.get("usage"),
                "custo_usd": (dados.get("usage") or {}).get("cost_usd"),
                "perfil_emocional": perfil,
            }
        except Exception as exc:
            perfil = fallback["perfil_emocional"]
            perfil["provider"] = "deterministico_fallback"
            return {
                **fallback,
                "fallback": True,
                "requested_model": self.model,
                "served_model": "",
                "motivo": type(exc).__name__,
                "perfil_emocional": perfil,
            }
