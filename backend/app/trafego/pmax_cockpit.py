"""A observabilidade de Performance Max, projetada para o cockpit.

## O que este módulo faz, e o que ele recusa a fazer

`volc_ads/observabilidade_pmax/` já resolve a parte difícil: ele lê a conta,
projeta os assets, avalia a cobertura estrutural de cada grupo de recursos e
devolve um veredito com procedência. O que faltava era um tradutor entre aquele
vocabulário e o JSON que a tela consome.

⚠️ **Este módulo NÃO reimplementa a semântica de ausência.** `ObservationState`
e `CollectionState` já distinguem, com sete e cinco estados, exatamente o que
este contrato precisa preservar:

    PRESENT            observado, e tem valor
    MEASURED_ZERO      observado, e o valor é zero — que NÃO é ausência
    FIELD_ABSENT       o campo não veio na resposta da API
    NOT_COLLECTED      ninguém pediu este dado
    NOT_APPLICABLE     a pergunta não cabe neste recurso
    COLLECTION_FAILED  pedimos, e a leitura falhou
    STALE              temos, e está velho demais para decidir

Inventar uma segunda tradução aqui — "presente/ausente", ou pior, um `0` — seria
criar duas verdades sobre o mesmo fato e perder cinco distinções no caminho. Os
nomes atravessam a fronteira HTTP **como estão**, e a tela aprende os sete.

## O que ele NUNCA faz: chamar o Google

O cockpit abre a cada navegação. Uma coleta aqui gastaria quota da conta do
cliente para pintar uma tela. Este módulo recebe um relatório JÁ COLETADO e o
projeta; quando não há nenhum, ele responde `NOT_COLLECTED` com a razão — que é
diferente de "a campanha não tem grupos de recursos" e diferente de "a leitura
falhou".
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence


#: A fonte, dita uma vez. Não é caminho de arquivo do servidor: é o nome
#: operacional da leitura, e é o que a tela mostra ao lado do veredito.
FONTE = "leitura estrutural de Performance Max"

#: Por que o cockpit não coletou. A frase é para o operador — ela não manda
#: ninguém rodar comando nenhum, porque quem abre a tela não opera o servidor.
SEM_COLETA = (
    "a estrutura desta campanha ainda não foi lida nesta sessão. O cockpit não "
    "consulta a conta do Google ao abrir — isso gastaria quota do cliente a "
    "cada navegação — e por isso a resposta aqui é 'não sei', e não 'não há'.")


def _valor_observado(observado: Any) -> Dict[str, Any]:
    """Um `ObservedValue` como JSON, com o estado inteiro preservado.

    ⚠️ `valor: null` sozinho seria indistinguível entre cinco situações
    diferentes. É o `estado` que separa "medi e deu zero" de "o campo não veio"
    de "não pedi" — e as três levam a decisões diferentes sobre confiar no
    número ao lado.
    """
    if observado is None:
        return {"valor": None, "estado": "NOT_COLLECTED", "origem": None,
                "erro": None}
    estado = getattr(observado, "state", None)
    valor = getattr(observado, "value", None)
    return {
        "valor": getattr(valor, "value", valor) if valor is not None else None,
        "estado": getattr(estado, "value", str(estado)),
        "origem": getattr(observado, "source_path", None),
        "erro": getattr(observado, "error_message", None),
    }


def _cobertura_de_campo(c: Any) -> Dict[str, Any]:
    """A cobertura de um papel de asset — quantos vieram, quantos são exigidos.

    ⚠️ `actual_count=0` aqui é um ZERO MEDIDO, e por isso viaja como número. A
    diferença com o resto do contrato é deliberada: quem chegou até aqui já
    atravessou `CollectionState.PRESENT`, então contar zero é um fato. É o
    `evidence_complete` que diz se a contagem pode ser levada a sério.
    """
    return {
        "papel": getattr(getattr(c, "field_type", None), "value",
                         str(getattr(c, "field_type", ""))),
        "quantidade": c.actual_count,
        "minimo_exigido": c.min_required,
        "maximo_permitido": c.max_allowed,
        "obrigatorio": c.is_mandatory,
        "minimo_satisfeito": c.is_min_satisfied,
        "maximo_excedido": c.is_max_exceeded,
        # ⚠️ `False` significa que a contagem acima é incompleta — parte dos
        # assets não trouxe evidência suficiente. Mostrar o número sem esta
        # marca daria precisão a uma conta que não a tem.
        "evidencia_completa": c.evidence_complete,
        "por_estado": dict(getattr(c, "primary_status_counts", {}) or {}),
        "por_politica": dict(getattr(c, "policy_approval_counts", {}) or {}),
        "observacoes": list(getattr(c, "observations", ()) or ()),
    }


def _grupo_de_recursos(g: Any) -> Dict[str, Any]:
    return {
        "id": g.asset_group_id,
        "nome": g.asset_group_name,
        "estado": g.status,
        "forca_do_anuncio": _valor_observado(getattr(g, "ad_strength", None)),
        "total_de_assets": g.total_assets,
        "cobertura": [_cobertura_de_campo(c) for c in g.field_coverages],
        "veredito": getattr(g.verdict, "value", str(g.verdict)),
        # ⚠️ TRI-ESTADO, e ele é o coração deste módulo. `None` é "não deu para
        # concluir"; `False` é "faltam papéis obrigatórios"; `True` é "a
        # estrutura está completa". Colapsar `None` em `False` transformaria
        # uma leitura incompleta numa acusação.
        "estruturalmente_completo": g.is_structurally_complete,
        "lacunas": list(getattr(g, "structural_gaps", ()) or ()),
        "avisos": list(getattr(g, "warnings", ()) or ()),
        "sinais": g.signals_count,
    }


def projetar_relatorio(relatorio: Any) -> Dict[str, Any]:
    """Um `PMaxCampaignCoverageReport` como JSON do cockpit."""
    return {
        "campaign_id": relatorio.campaign_id,
        "nome": relatorio.campaign_name,
        "estado": getattr(relatorio.campaign_status, "value",
                          str(relatorio.campaign_status)),
        "veiculacao": _valor_observado(getattr(relatorio, "serving_status", None)),
        "grupos_de_recursos": {
            "total": relatorio.total_asset_groups,
            # ⚠️ `None` sobrevive: "quantos estão elegíveis" é `Optional[int]`
            # no relatório porque a elegibilidade pode não ter sido lida.
            "elegiveis": relatorio.eligible_asset_groups,
            "historicos": relatorio.historical_asset_groups,
        },
        "grupos": [_grupo_de_recursos(g) for g in relatorio.asset_group_reports],
        "veredito": getattr(relatorio.verdict, "value", str(relatorio.verdict)),
        "todos_os_grupos_completos": relatorio.all_asset_groups_complete,
        "observacoes": list(getattr(relatorio, "summary_observations", ()) or ()),
        "avaliado_em": (relatorio.evaluated_at.isoformat()
                        if getattr(relatorio, "evaluated_at", None) else None),
        # A ressalva que o próprio módulo de observabilidade carrega. Ela viaja
        # inteira: é ela que impede o veredito de ser lido como promessa de
        # desempenho.
        "ressalva": getattr(relatorio, "disclaimer", None),
    }


def observabilidade_de_pmax(
        relatorios: Optional[Sequence[Any]] = None,
        *,
        estado_da_coleta: Optional[str] = None,
        causa: Optional[str] = None) -> Dict[str, Any]:
    """O bloco de observabilidade de PMax para o cockpit.

    ⚠️ `relatorios=None` e `relatorios=[]` são coisas DIFERENTES, e este é o
    lugar em que a diferença mais custa: `None` é "não coletei" e `[]` é
    "coletei, e a conta não tem campanha de Performance Max". A primeira não
    autoriza conclusão nenhuma; a segunda é um fato sobre a conta.
    """
    if relatorios is None:
        return {
            "estado_da_coleta": estado_da_coleta or "NOT_COLLECTED",
            "fonte": FONTE,
            "causa": causa or SEM_COLETA,
            "campanhas": None,
            "quantidade": None,
        }
    projetados = [projetar_relatorio(r) for r in relatorios]
    return {
        "estado_da_coleta": estado_da_coleta or (
            "PRESENT" if projetados else "PRESENT_EMPTY"),
        "fonte": FONTE,
        "causa": (None if projetados else
                  "a leitura aconteceu e não encontrou campanha de Performance "
                  "Max nesta conta. Zero medido não é leitura ausente."),
        "campanhas": projetados,
        "quantidade": len(projetados),
    }


def papeis_obrigatorios() -> Dict[str, Any]:
    """O contrato de assets de Performance Max, do módulo que o define.

    ⚠️ Lido do registro, nunca copiado. Uma segunda lista de papéis
    obrigatórios divergiria no primeiro papel que a API mudasse, e a tela
    passaria a cobrar um asset que ninguém mais exige — ou a deixar de cobrar
    um que virou obrigatório.
    """
    try:
        import pathlib
        import sys

        raiz = pathlib.Path(__file__).resolve().parents[3]
        if str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        from volc_ads.observabilidade_pmax.coverage import (
            PMAX_FIELD_REQUIREMENTS,
        )
    except Exception as exc:  # noqa: BLE001 — ausência do módulo é estado
        return {
            "estado": "NOT_COLLECTED",
            "causa": ("o contrato de assets de Performance Max não pôde ser "
                      f"lido neste servidor ({type(exc).__name__})."),
            "papeis": None,
        }
    papeis = [
        {
            "papel": getattr(campo, "value", str(campo)),
            "minimo": r.min_count,
            "maximo": r.max_count,
            "obrigatorio": r.is_mandatory,
            "descricao": r.description,
        }
        for campo, r in PMAX_FIELD_REQUIREMENTS.items()
    ]
    return {"estado": "PRESENT", "causa": None, "papeis": papeis}
