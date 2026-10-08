"""JEV consultivo: demanda real -> sinais emocionais tipados para o arquiteto.

O adaptador não escreve copy, não inventa avatar demográfico e nunca bloqueia
uma página. Uma chamada em lote classifica as perguntas que já vieram de PAA,
termos ou autocomplete. Sem credencial, timeout ou contrato válido, o motor
continua com a heurística estreita e registra o fallback.
"""

from __future__ import annotations

import json
import os
import time
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
INTENCOES = (
    "elegibilidade",
    "prazo",
    "valor",
    "procedimento",
    "status_pessoal",
    "problema",
    "comparacao",
    "acesso_oficial",
    "outra",
)

_EMOCOES: dict[str, str] = {
    "oportunidade": "access to a concrete benefit, gain or useful possibility",
    "incerteza": "uncertainty about whether, who, which rule or how something applies",
    "medo_de_perder": "fear of missing a real deadline, payment, right or opportunity",
    "desejo_de_controle": "desire to calculate, verify, compare, track or regain control",
    "prevencao_de_erro": "desire to avoid fraud, rejection, rework or a wrong decision",
    "necessidade_de_acao": "need to execute a concrete next step now",
}


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


def _noul(answer: dict) -> float:
    """Noul é P(sim), não intensidade nem booleano já decidido."""
    try:
        valor = float(answer["noul"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("noul_invalido") from exc
    if not 0.0 <= valor <= 1.0:
        raise ValueError("noul_fora_da_faixa")
    return round(valor * 100, 1)


def _custo_estimado(usage: dict | None) -> float | None:
    """Estimativa separada do faturado: Jev 1.13 = US$42/B input, output grátis."""
    try:
        tokens = int((usage or {}).get("input_tokens") or 0)
    except (TypeError, ValueError):
        return None
    return round(tokens * 42 / 1_000_000_000, 9) if tokens else None


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
        "ganho_informacional": 0.0,
        "sinal_observavel": 0.0,
        "sensibilidade_temporal": 0.0,
        "consulta_pessoal": 0.0,
        "canal_oficial_necessario": 0.0,
        "respondavel_editorialmente": 0.0,
        "proximo_passo_concreto": 0.0,
        "intencao": "outra",
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
        "schema_version": 2 if provider == "typesafe_jev" else 1,
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
        self, *, enabled=False, key=None, model="jev-1.13.0", timeout=10.0, transport=None
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
            # Emoções coexistem. Seis Nouls preservam essa realidade; um Choice
            # exclusivo obrigava incerteza, controle e ação a competirem.
            for familia, descricao in _EMOCOES.items():
                questions[f"emocao_{familia}_{i}"] = {
                    "type": "noul",
                    "instructions": (
                        f"Does {alvo} express {descricao}? Judge observed language and measured "
                        "context only; do not invent demographics or personal circumstances."
                    ),
                }
            for nome, instrucao in {
                "sinal_observavel": "Does the query contain a clear behavioral need rather than an ambiguous topic mention?",
                "sensibilidade_temporal": "Is the query meaningfully time-sensitive in the measured context?",
                "consulta_pessoal": "Does fully resolving the query require the reader's personal status or account data?",
                "canal_oficial": "Does the final action require an official service, tool or channel?",
                "respondavel_editorialmente": "Can editorial content answer the query substantially before any official action?",
                "proximo_passo": "Does a concrete next action remain after the query is fully answered?",
            }.items():
                questions[f"{nome}_{i}"] = {
                    "type": "noul",
                    "instructions": f"{instrucao} Evaluate {alvo} against the supplied state.",
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
                "ganho_informacional": "Quanto uma resposta completa acrescenta informação nova e útil",
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
            questions[f"intencao_{i}"] = {
                "type": "choice",
                "instructions": f"Which single reader job best describes {alvo}?",
                "criteria": {x: x.replace("_", " ") for x in INTENCOES},
            }
        return questions

    def classificar(self, perguntas: list[str], *, contexto: dict | None = None) -> dict:
        fallback = HeuristicaDeIntencao().classificar(perguntas, contexto=contexto)
        if not self.enabled or not self.key:
            return {**fallback, "motivo": "desligado" if not self.enabled else "sem_credencial"}
        state = {
            "fase": "pre_arquitetura",
            "tema": (contexto or {}).get("tema", ""),
            "pais": (contexto or {}).get("pais", ""),
            "idioma": (contexto or {}).get("idioma", ""),
            "contexto_medido": (contexto or {}).get("contexto_medido") or {},
            "perguntas": [
                {
                    "indice": i,
                    "duvida_id": ((contexto or {}).get("duvida_ids") or [])[i]
                    if i < len((contexto or {}).get("duvida_ids") or [])
                    else "",
                    "texto": q,
                    "prioridade": (((contexto or {}).get("duvidas") or [{}] * len(perguntas))[i]
                                   if i < len((contexto or {}).get("duvidas") or []) else {}).get("prioridade", 0),
                    "evidencia_demanda": (((contexto or {}).get("duvidas") or [{}] * len(perguntas))[i]
                                          if i < len((contexto or {}).get("duvidas") or []) else {}).get("evidencia_demanda", []),
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
        if self.chamadas or len(json.dumps(payload, ensure_ascii=False)) > 180000 or not perguntas:
            return {**fallback, "fallback": True, "motivo": "orcamento"}
        self.chamadas += 1
        try:
            inicio = time.perf_counter()
            with httpx.Client(timeout=self.timeout, transport=self.transport) as cliente:
                resp = cliente.post(
                    "https://api.typesafe.ai/v1/systemone",
                    json=payload,
                    headers={"Authorization": "Bearer " + self.key},
                )
                resp.raise_for_status()
                dados = resp.json()
            latencia_ms = round((time.perf_counter() - inicio) * 1000)
            answers, servido = dados["answers"], str(dados.get("model") or "")
            if not servido:
                raise ValueError("modelo_ausente")
            sinais = []
            for i, pergunta in enumerate(perguntas):
                correspondencia = {
                    familia: _noul(answers[f"emocao_{familia}_{i}"])
                    for familia in _EMOCOES
                }
                sinal_observavel = _noul(answers[f"sinal_observavel_{i}"])
                familia_candidata = max(correspondencia, key=correspondencia.get)
                familia = (
                    familia_candidata
                    if sinal_observavel >= 60 and correspondencia[familia_candidata] >= 60
                    else "ambigua"
                )
                formato = answers[f"formato_{i}"]["choice"]
                entrega, momento = (
                    answers[f"entrega_{i}"]["choice"],
                    answers[f"momento_{i}"]["choice"],
                )
                intencao = answers[f"intencao_{i}"]["choice"]
                if (
                    familia not in FAMILIAS
                    or formato not in FORMATOS
                    or entrega not in ENTREGAS
                    or momento not in MOMENTOS
                    or intencao not in INTENCOES
                ):
                    raise ValueError("contrato")
                sinais.append(
                    {
                        "pergunta": pergunta,
                        "duvida_id": state["perguntas"][i]["duvida_id"],
                        "familia": familia,
                        "correspondencia": correspondencia,
                        # Noul não tem confidence separado. Esta é a distância
                        # da decisão de "há sinal observável" ao ponto 50/50.
                        "confianca": round(abs(sinal_observavel - 50) * 2, 1),
                        "intensidade": _nota(answers[f"intensidade_{i}"]),
                        "autorrelevancia": _nota(answers[f"autorrelevancia_{i}"]),
                        "potencial_continuacao": _nota(answers[f"continuacao_{i}"]),
                        "urgencia_de_acao": _nota(answers[f"acao_{i}"]),
                        "ganho_informacional": _nota(answers[f"ganho_informacional_{i}"]),
                        "sinal_observavel": sinal_observavel,
                        "sensibilidade_temporal": _noul(answers[f"sensibilidade_temporal_{i}"]),
                        "consulta_pessoal": _noul(answers[f"consulta_pessoal_{i}"]),
                        "canal_oficial_necessario": _noul(answers[f"canal_oficial_{i}"]),
                        "respondavel_editorialmente": _noul(answers[f"respondavel_editorialmente_{i}"]),
                        "proximo_passo_concreto": _noul(answers[f"proximo_passo_{i}"]),
                        "intencao": intencao,
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
                "custo_estimado_usd": _custo_estimado(dados.get("usage")),
                "latencia_ms": latencia_ms,
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

    @staticmethod
    def _estado_da_jornada(plan: Any, contexto: dict | None = None) -> dict:
        paginas = []
        por_slug = {p.slug: p for p in plan.pages}
        arestas = []
        for pagina in plan.pages:
            jornada = pagina.jornada
            editorial = pagina.editorial
            paginas.append({
                "pagina": pagina.page_number,
                "slug": pagina.slug,
                "h1": pagina.h1_title,
                "pergunta": jornada.pergunta_principal if jornada else "",
                "resposta_imediata": jornada.resposta_imediata if jornada else "",
                "tensao_residual": jornada.tensao_residual if jornada else "",
                "informacao_nova": jornada.valor.informacao_nova if jornada and jornada.valor else "",
                "entregas": list(jornada.valor.entregas) if jornada and jornada.valor else [],
            })
            for link in editorial.links if editorial else []:
                destino = por_slug.get(link.target)
                if destino is None:
                    continue
                dj = destino.jornada
                arestas.append({
                    "indice": len(arestas),
                    "origem_pagina": pagina.page_number,
                    "origem_slug": pagina.slug,
                    "origem_pergunta": jornada.pergunta_principal if jornada else "",
                    "origem_resposta": jornada.resposta_imediata if jornada else "",
                    "origem_tensao_residual": jornada.tensao_residual if jornada else "",
                    "cta": link.cta or destino.editorial.cta_label if destino.editorial else link.cta,
                    "motivo": link.reason,
                    "destino_pagina": destino.page_number,
                    "destino_slug": destino.slug,
                    "destino_pergunta": dj.pergunta_principal if dj else "",
                    "destino_entrega": destino.editorial.useful_delivery if destino.editorial else "",
                    "destino_informacao_nova": dj.valor.informacao_nova if dj and dj.valor else "",
                })
        return {
            "fase": "pos_arquitetura",
            "tema": (contexto or {}).get("tema", ""),
            "pais": (contexto or {}).get("pais", ""),
            "idioma": (contexto or {}).get("idioma", ""),
            "contexto_medido": (contexto or {}).get("contexto_medido") or {},
            "paginas": paginas,
            "arestas": arestas,
        }

    @staticmethod
    def _questions_jornada(arestas: list[dict]) -> dict:
        questions: dict[str, dict[str, Any]] = {}
        for i, _ in enumerate(arestas):
            alvo = f"`arestas[{i}]`"
            for nome, instrucao in {
                "resposta_origem": "Does the source page fully answer its own question before asking for this click?",
                "destino_entrega": "Does the destination deliver exactly what this CTA promises?",
                "valor_novo": "Does the destination add distinct useful value instead of repeating the source?",
                "cta_generico": "Is the CTA generic or understandable only with surrounding context?",
                "resultado_pessoal": "Does the CTA imply a personal result, approval or account data the editorial site cannot know?",
            }.items():
                questions[f"{nome}_{i}"] = {
                    "type": "noul",
                    "instructions": f"{instrucao} Evaluate {alvo} only.",
                }
            for nome, instrucao in {
                "motivacao": "How compelling is the CTA after the source has delivered its answer?",
                "congruencia": "How precisely does the CTA match the destination's question and delivery?",
            }.items():
                questions[f"{nome}_{i}"] = {
                    "type": "score",
                    "instructions": f"{instrucao} Evaluate {alvo} only.",
                    "criteria": list(NIVEIS),
                }
        return questions

    def verificar_jornada(self, plan: Any, *, contexto: dict | None = None) -> dict:
        """Segunda chamada, dependente do esqueleto: lint semântico, nunca rewrite."""
        estado = self._estado_da_jornada(plan, contexto)
        if not estado["arestas"]:
            return {"provider": "typesafe_jev", "fallback": False, "arestas": [],
                    "resumo": {"usar": 0, "revisar": 0, "recusar": 0},
                    "motivo": "sem_arestas"}
        if not self.enabled or not self.key:
            return {"provider": "deterministico_fallback", "fallback": True,
                    "arestas": [], "resumo": {"usar": 0, "revisar": 0, "recusar": 0},
                    "motivo": "desligado" if not self.enabled else "sem_credencial"}
        payload = {"model": self.model, "state": estado,
                   "questions": self._questions_jornada(estado["arestas"])}
        if self.chamadas or len(json.dumps(payload, ensure_ascii=False)) > 180000:
            return {"provider": "deterministico_fallback", "fallback": True,
                    "arestas": [], "resumo": {"usar": 0, "revisar": 0, "recusar": 0},
                    "motivo": "orcamento"}
        self.chamadas += 1
        try:
            inicio = time.perf_counter()
            with httpx.Client(timeout=self.timeout, transport=self.transport) as cliente:
                resp = cliente.post(
                    "https://api.typesafe.ai/v1/systemone", json=payload,
                    headers={"Authorization": "Bearer " + self.key})
                resp.raise_for_status()
                dados = resp.json()
            latencia_ms = round((time.perf_counter() - inicio) * 1000)
            answers = dados["answers"]
            servido = str(dados.get("model") or "")
            if not servido:
                raise ValueError("modelo_ausente")
            saidas = []
            contagem = {"usar": 0, "revisar": 0, "recusar": 0}
            for i, aresta in enumerate(estado["arestas"]):
                valores = {
                    "resposta_origem": _noul(answers[f"resposta_origem_{i}"]),
                    "destino_entrega": _noul(answers[f"destino_entrega_{i}"]),
                    "valor_novo": _noul(answers[f"valor_novo_{i}"]),
                    "cta_generico": _noul(answers[f"cta_generico_{i}"]),
                    "resultado_pessoal": _noul(answers[f"resultado_pessoal_{i}"]),
                    "motivacao": _nota(answers[f"motivacao_{i}"]),
                    "congruencia": _nota(answers[f"congruencia_{i}"]),
                }
                problemas = []
                # Noul perto de 50 é inconclusivo, não um "não" moderado. Só
                # extremos governam código nesta camada consultiva; o meio fica
                # como telemetria para calibração, sem criar fila humana.
                if valores["destino_entrega"] <= 20:
                    problemas.append("cta_destino_incongruente")
                if valores["valor_novo"] <= 20:
                    problemas.append("destino_redundante")
                if valores["resultado_pessoal"] > 85:
                    problemas.append("promessa_de_resultado_pessoal")
                decisao = "recusar" if problemas else "usar"
                if decisao == "usar" and (
                    valores["resposta_origem"] <= 20
                    or valores["cta_generico"] >= 80
                    or valores["motivacao"] < 50
                    or valores["congruencia"] < 50
                ):
                    decisao = "revisar"
                contagem[decisao] += 1
                saidas.append({**aresta, **valores, "decisao": decisao,
                               "problemas": problemas})
            usage = dados.get("usage") or {}
            return {
                "schema_version": 1,
                "provider": "typesafe_jev",
                "requested_model": self.model,
                "served_model": servido,
                "fallback": False,
                "usage": usage,
                "custo_usd": usage.get("cost_usd"),
                "custo_estimado_usd": _custo_estimado(usage),
                "latencia_ms": latencia_ms,
                "arestas": saidas,
                "resumo": contagem,
            }
        except Exception as exc:
            return {"provider": "deterministico_fallback", "fallback": True,
                    "requested_model": self.model, "served_model": "", "arestas": [],
                    "resumo": {"usar": 0, "revisar": 0, "recusar": 0},
                    "motivo": type(exc).__name__}
