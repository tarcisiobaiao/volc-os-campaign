"""Operações de gestão SEM delta — o espelho em Python da v17_03.

`supabase/migrations/v17_03_gestao_operacoes_sem_delta.sql` deixa a regra
declarar, por operação, o que ela autoriza sem tamanho numérico
(`trafego_regra_otimizacao.operacoes_sem_delta`) e com que teto próprio; o
gatilho `trafego_proposta_respeita_regra` só aceita proposta sem delta quando a
regra lista a operação e a proposta cabe no teto
(`trafego_proposta_sem_delta_defeito`).

Este módulo repete a MESMA conferência antes da primeira escrita, pela mesma
razão de `casos_de_uso.conferir_contra_regra`: a recusa vira mensagem com
`codigo` estável antes de virar linha órfã (evidência e diagnóstico gravados
para uma proposta que o banco recusaria). O banco continua sendo a trava; isto
é só a tradução antecipada. Divergir do SQL é defeito — os testes leem o
vocabulário do arquivo da migration para pegar a deriva.

⚠️ Regra sem a coluna (v17_03 não aplicada, ou regra antiga) = `{}` = nenhuma
operação sem delta: a trava 4a da v10_02 vale como sempre.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional

#: As 13 operações sem delta e a classe de cada uma — o CASE de
#: `trafego_operacao_sem_delta_classe()`. Monetárias (`orcamento.diario`,
#: `lance.alvo`) ficam FORA de propósito: continuam exigindo delta e limite.
CLASSES: Dict[str, str] = {
    "status": "status",
    "lance.estrategia": "estrategia",
    "ajuste.dispositivo": "ajuste",
    "ajuste.horario": "ajuste",
    "negativa.keyword": "segmentacao",
    "exclusao.placement": "segmentacao",
    "exclusao.ip": "segmentacao",
    "programacao.anuncios": "segmentacao",
    "lista.criar": "estrutura",
    "lista.adicionar": "estrutura",
    "lista.anexar": "estrutura",
    "recomendacao.aplicar": "recomendacao",
    "recomendacao.dispensar": "recomendacao",
}

MONETARIAS = ("orcamento.diario", "lance.alvo")

#: `trafego_recomendacao_monetaria()`: recomendação que mexe em verba, alvo,
#: estratégia, ou é tarifa. Por padrão, para pegar tipo novo sem migration.
_REC_MONETARIA = re.compile(r"(BUDGET|TARGET_CPA|TARGET_ROAS|MAXIMIZE_|ENHANCED_CPC|_FEE$|OPERATING_C)")

#: Onde está a lista que se conta, por operação (como `Acao.valor_proposto()` a escreve).
_CAMPO_DOS_ITENS = {
    "negativa.keyword": "adicionar", "lista.criar": "itens", "lista.adicionar": "adicionar",
    "lista.anexar": "anexar", "exclusao.placement": "excluir", "exclusao.ip": "excluir_ips",
}


def recomendacao_monetaria(tipo: Optional[str]) -> bool:
    return bool(_REC_MONETARIA.search(tipo or ""))


def classe(operacao: str) -> Optional[str]:
    return CLASSES.get(operacao)


def declaradas(regra: Mapping[str, Any]) -> Dict[str, Any]:
    """`operacoes_sem_delta` da regra; ausente/nula = nenhuma (v10_02 pura)."""
    cfg = regra.get("operacoes_sem_delta")
    return dict(cfg) if isinstance(cfg, Mapping) else {}


def _numero(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def defeito(cfg: Any, operacao: str, alvo_nivel: Optional[str],
            atual: Any, proposto: Any) -> Optional[str]:
    """Por que a proposta sem delta passa do teto declarado. `None` = cabe.

    Tradução linha a linha de `trafego_proposta_sem_delta_defeito()`. Toda
    leitura ausente RECUSA — "não consegui contar" não é "zero itens".
    """
    if not isinstance(cfg, Mapping):
        return f"a regra não declara {operacao} entre as operações sem delta"
    if not isinstance(proposto, Mapping):
        return "valor_proposto ausente"
    atual = atual if isinstance(atual, Mapping) else {}

    if operacao == "status":
        valor = proposto.get("status")
        if valor is None:
            return "valor_proposto.status ausente"
        if valor == "REMOVED":
            return "REMOVED não é gestão: é terminal, não tem reverso e tem funil próprio"
        if valor not in (cfg.get("status_permitidos") or ()):
            return f"status {valor} fora de status_permitidos {cfg.get('status_permitidos')}"
        if "niveis" in cfg and alvo_nivel not in (cfg.get("niveis") or ()):
            return f"nível {alvo_nivel or '(nenhum)'} fora de níveis {cfg.get('niveis')}"

    elif operacao == "lance.estrategia":
        valor = proposto.get("estrategia")
        if valor is None:
            return "valor_proposto.estrategia ausente"
        if valor not in (cfg.get("estrategias") or ()):
            return f"estratégia {valor} fora de estrategias {cfg.get('estrategias')}"
        if "teto_micros" in cfg:
            for campo in ("tcpa_micros", "teto_cpc_micros"):
                if campo in proposto:
                    n = _numero(proposto[campo])
                    if n is None:
                        return f"{campo} não é número"
                    if n > float(cfg["teto_micros"]):
                        return f"{campo} = {proposto[campo]} passa do teto_micros {cfg['teto_micros']}"

    elif operacao in ("ajuste.dispositivo", "ajuste.horario"):
        m = _numero(proposto.get("modificador"))
        if m is None:
            return "valor_proposto.modificador ausente ou não numérico"
        lo, hi = float(cfg["modificador_min"]), float(cfg["modificador_max"])
        if m < lo or m > hi:
            return f"modificador {proposto.get('modificador')} fora de [{cfg['modificador_min']}, {cfg['modificador_max']}]"

    elif operacao in _CAMPO_DOS_ITENS or operacao == "programacao.anuncios":
        if operacao == "programacao.anuncios":
            criar, remover = proposto.get("criar"), proposto.get("remover")
            if not isinstance(criar, list) or not isinstance(remover, list):
                return "valor_proposto sem as listas criar/remover: sem contagem não há teto"
            n = len(criar) + len(remover)
        else:
            campo = _CAMPO_DOS_ITENS[operacao]
            lista = proposto.get(campo)
            if not isinstance(lista, list):
                return f"valor_proposto.{campo} ausente ou não é lista: sem contagem não há teto"
            n = len(lista)
        if n < 1:
            return "proposta sem item nenhum"
        if n > int(cfg["max_itens"]):
            return f"{n} itens passam do max_itens {cfg['max_itens']}"
        if "escopos" in cfg and proposto.get("escopo") not in (cfg.get("escopos") or ()):
            return f"escopo {proposto.get('escopo') or '(nenhum)'} fora de escopos {cfg.get('escopos')}"
        if operacao == "lista.criar" and "max_campanhas" in cfg:
            campanhas = proposto.get("campanhas")
            if not isinstance(campanhas, list):
                return "valor_proposto.campanhas ausente ou não é lista"
            if len(campanhas) > int(cfg["max_campanhas"]):
                return f"{len(campanhas)} campanhas passam do max_campanhas {cfg['max_campanhas']}"
        if operacao == "programacao.anuncios" and "modificador_min" in cfg:
            lo, hi = float(cfg["modificador_min"]), float(cfg["modificador_max"])
            for janela in proposto["criar"]:
                bruto = janela.get("modificador") if isinstance(janela, Mapping) else None
                if bruto is None:
                    continue  # sem ajuste = 1.0
                m = _numero(bruto)
                if m is None or m < lo or m > hi:
                    return f"janela com modificador {bruto} fora de [{cfg['modificador_min']}, {cfg['modificador_max']}]"

    elif operacao in ("recomendacao.aplicar", "recomendacao.dispensar"):
        tipo = atual.get("tipo")
        if operacao == "recomendacao.aplicar":
            if tipo is None:
                return ("valor_atual.tipo ausente: sem o tipo lido não dá para saber se a "
                        "recomendação mexe em verba")
            if recomendacao_monetaria(tipo):
                return (f"recomendação {tipo} mexe em verba, lance ou estratégia: monte "
                        "orcamento.diario/lance.alvo, que têm delta e limite")
        if "tipos_permitidos" in cfg and tipo not in (cfg.get("tipos_permitidos") or ()):
            return f"recomendação {tipo or '(tipo não lido)'} fora de tipos_permitidos {cfg.get('tipos_permitidos')}"

    else:
        return f"{operacao} não é operação sem delta do vocabulário da v17_03"
    return None
