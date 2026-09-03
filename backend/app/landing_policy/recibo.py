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
    EXIGENCIAS_POR_PONTO,
    POLICY_CONTRACT_VERSION,
    SCHEMA_VERSION,
    STATUS_CONCLUSIVOS,
    TODAS_AS_VERIFICACOES,
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
    impressao_do_conteudo: str | None = None,
    escopo_da_impressao: str = "artifact",
    carimbo_epoch: float | None = None,
    janela_de_frescor_s: int | None = None,
    papel_declarado: str = "",
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
        # A projeção estrutural: é ela que decide deriva, e o byte acima é a
        # evidência de igualdade. Ver `varredura.impressao_canonica`.
        "content_fingerprint": impressao_do_conteudo,
        # ⚠️ DE QUE DOCUMENTO É ESSA IMPRESSÃO.
        #
        # "artifact" = o corpo que o motor produziu. "live" = a página que o
        # WordPress serve, com o tema em volta. São documentos diferentes por
        # construção, e comparar entre escopos reprovava 100% das páginas
        # corretas. `varrer_recibo` só compara quando os escopos batem.
        "fingerprint_scope": escopo_da_impressao,
        "observed_at": carimbo,
        # ⚠️ O CARIMBO COMPARÁVEL, ao lado do carimbo legível.
        #
        # `observed_at` é texto e tem default determinístico de propósito (dois
        # recibos do mesmo artefato local precisam bater byte a byte). Frescor,
        # porém, é aritmética: parsear data em três formatos é como o frescor
        # deixa de valer. `None` significa "esta avaliação não é datável" — e
        # `varrer_recibo` trata isso como `unavailable`, nunca como recente.
        "observed_at_epoch": carimbo_epoch,
        "freshness_window_s": janela_de_frescor_s,
        # As duas versões, porque elas mudam por motivos diferentes: a do
        # CONTRATO é a forma da avaliação, a da FONTE é o texto das regras.
        "policy_contract_version": POLICY_CONTRACT_VERSION,
        "policy_source_version": versao_da_fonte(fontes),
        # O papel que alguém DECLAROU, ao lado do papel efetivamente avaliado.
        # Divergir não é erro: no ponto de campanha o papel é FORÇADO, e ver as
        # duas linhas é como o operador entende por que o rigor subiu.
        "role_declared": papel_declarado or None,
        "gate_point_requires": sorted(
            EXIGENCIAS_POR_PONTO.get(avaliacao.ponto, frozenset())
        ),
        "policy_sources_consulted": sorted(
            {
                (r.get("url") or "")
                for r in (fontes.get("rules") or {}).values()
                if r.get("url")
            }
        ),
        "verdict": avaliacao.veredito.value,
        # ── COMPLETUDE DA EVIDÊNCIA ────────────────────────────────────────
        #
        # Quantas das dez verificações chegaram a um desfecho conclusivo. Sem
        # isto, um recibo com poucos achados parece um recibo de página limpa —
        # e a diferença entre "olhei tudo e está limpo" e "não consegui olhar"
        # é o assunto inteiro deste contrato.
        "evidence_completeness": {
            "conclusive": sorted(
                v.nome for v in avaliacao.verificacoes if v.status in STATUS_CONCLUSIVOS
            ),
            "inconclusive": sorted(
                v.nome for v in avaliacao.verificacoes if v.status not in STATUS_CONCLUSIVOS
            ),
            "required_here": sorted(EXIGENCIAS_POR_PONTO.get(avaliacao.ponto, frozenset())),
            "ratio": (
                f"{sum(1 for v in avaliacao.verificacoes if v.status in STATUS_CONCLUSIVOS)}"
                f"/{len(TODAS_AS_VERIFICACOES)}"
            ),
        },
        # ── PRONTIDÃO, EM LINGUAGEM QUE NÃO COLAPSA ESTADOS ────────────────
        #
        # `paid_destination_ready` responde uma pergunta estreita. A tela precisa
        # de mais: "apto segundo o VOLC" não é "publicado", que não é "verificado
        # ao vivo", que não é "aprovado pelo Google" — e essa última NUNCA é
        # conhecida por este portão. Colapsá-las num único verde foi como uma
        # LP com sete links de governo virou destino de campanha.
        "readiness": {
            "volc_gate": (
                "ready" if avaliacao.paid_destination_ready
                else ("blocked" if avaliacao.bloqueios else "indeterminate")
            ),
            "live_verified": any(
                v.nome == "live_drift" and v.status in STATUS_CONCLUSIVOS
                for v in avaliacao.verificacoes
            ),
            "google_approval": "unknown",
            "google_approval_note": (
                "Este portão lê HTML; ele não lê a decisão do revisor do Google. "
                "'ready' aqui significa apenas: nesta avaliação, neste ponto de "
                "portão, contra esta versão da política, não sobrou bloqueio nem "
                "desconhecido."
            ),
        },
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
