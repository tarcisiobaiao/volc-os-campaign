"""Review the exact Studio bytes before they become account media.

Human-only review is the operator's chosen default. It is never presented as
automated inspection or Meta approval. A valid approval is bound to this
immutable master/version and paid Meta use. Reviews are recomputed before upload, not accepted
from a browser-provided verdict. Copy is deliberately outside this media-only
receipt and remains a separate campaign compilation concern.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.criativo import politica
from app.criativo.politica.inspecao import (
    CAPACIDADES_EXIGIDAS, detectores_de_pixel_registrados,
)
from app.criativo.politica.detectores.gemini_marcas import detector_meta_se_autorizado
from app.trafego.meta_execucao.registro_de_midia import (
    ErroDeRegistroDeMidia, PecaParaRegistrar,
)


FINALIDADE = "meta_ads"


def _capacidades_com(gemini: Any) -> dict[str, Any]:
    presentes = {
        capacidade for detector in (*detectores_de_pixel_registrados(), *((gemini,) if gemini else ()))
        for capacidade in getattr(detector, "capacidades", ())
    }
    faltantes = sorted(set(CAPACIDADES_EXIGIDAS) - presentes)
    return {"disponivel": not faltantes, "capacidades_ausentes": faltantes}


def capacidades_de_inspecao(*, automatizada: bool = False) -> dict[str, Any]:
    if not automatizada:
        return {"disponivel": True, "capacidades_ausentes": [], "modo": "HUMAN_ONLY", "envia_para_ia": False}
    return _capacidades_com(detector_meta_se_autorizado())


async def revisar_pecas(
    pecas: list[PecaParaRegistrar], *, repo: Any, ator: str, account_ref: str,
    automatizada: bool = False,
) -> list[dict[str, Any]]:
    resultados = []
    # Do not even instantiate a paid detector on the human-only path, including
    # the second review performed by the upload endpoint.
    gemini = detector_meta_se_autorizado() if automatizada else None
    capacidades = _capacidades_com(gemini) if automatizada else None
    for index, peca in enumerate(pecas):
        master = await repo.buscar_master_do_dono(peca.master_ref, criado_por=ator)
        if not master:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_MASTER_NOT_FOUND", f"Imagem {index + 1}: a peça não existe ou não pertence a você.")
        if master.get("arquivado_em"):
            raise ErroDeRegistroDeMidia(
                "META_ASSET_MASTER_ARCHIVED", f"Imagem {index + 1}: uma peça arquivada não pode ser enviada.")
        if master.get("content_hash") != "sha256:" + peca.content_sha256:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_CUSTODY_HASH_DIVERGED", f"Imagem {index + 1}: a peça mudou; revise novamente.")
        versao = int(master.get("versao") or 1)
        decisoes = await repo.aprovacoes_de("master", peca.master_ref)
        aprovacao = next((d for d in decisoes if (
            d.get("decisao") == "aprovado" and d.get("revogada_em") is None
            and d.get("finalidade") == FINALIDADE and d.get("ator_id") == ator
            and int(d.get("versao") or 0) == versao
        )), None)
        # Synthetic provenance comes from the owned immutable master, never
        # from a field supplied by the operator. Imported content still needs
        # its separate, server-resolved rights evidence (not supported here).
        procedencia = "GENERATED" if master.get("sintetico") is True else "HUMAN_UPLOAD"
        if not automatizada:
            resultados.append({
                "master_ref": peca.master_ref, "content_sha256": peca.content_sha256,
                "versao": versao, "aprovacao_humana": bool(aprovacao),
                "aprovacao_ref": str(aprovacao["id"]) if aprovacao else None,
                "finalidade": FINALIDADE, "modo_revisao": "HUMAN_ONLY",
                "politica": {"decisao": "HUMAN_REVIEW", "detectores": [],
                             "motivos": ["Decisão humana. Sem inspeção automática e sem aprovação da Meta."]},
                "utilizavel": bool(aprovacao),
                "codigo": None if aprovacao else "META_ASSET_FINAL_APPROVAL_REQUIRED",
            })
            continue
        if not capacidades["disponivel"]:
            resultados.append({
                "master_ref": peca.master_ref, "content_sha256": peca.content_sha256,
                "versao": versao, "aprovacao_humana": bool(aprovacao),
                "aprovacao_ref": str(aprovacao["id"]) if aprovacao else None,
                "finalidade": FINALIDADE,
                "politica": {"decisao": "INSPECTION_UNAVAILABLE",
                             "motivos": capacidades["capacidades_ausentes"], "detectores": []},
                "utilizavel": False, "codigo": "META_ASSET_POLICY_UNAVAILABLE",
            })
            continue
        recibo = await asyncio.to_thread(politica.avaliar,
            asset_ref=peca.master_ref, content_sha256=peca.content_sha256,
            bytes_da_peca=peca.conteudo, mime=peca.mime_type, copy=None,
            nome_do_arquivo=None, prompt=None, identity_ref=f"{ator}:{account_ref}",
            identidade_propria=None, procedencia=procedencia, canal="META_ADS",
            natureza="producao", exigir_pixel=True,
            detectores_adicionais=(gemini,) if gemini else (),
        )
        erro_detector = any(d.resultado == "ERROR" for d in recibo.detectores)
        # This upload boundary always requires complete inspection, even if a
        # legacy caller has deliberately relaxed its own policy flag.
        politica_ok = recibo.libera_midia_paga() and not erro_detector
        codigo = None
        if not politica_ok:
            codigo = "META_ASSET_POLICY_UNAVAILABLE" if erro_detector else "META_ASSET_POLICY_BLOCKED"
        elif not aprovacao:
            codigo = "META_ASSET_FINAL_APPROVAL_REQUIRED"
        resultados.append({
            "master_ref": peca.master_ref, "content_sha256": peca.content_sha256,
            "versao": versao, "aprovacao_humana": bool(aprovacao),
            "aprovacao_ref": str(aprovacao["id"]) if aprovacao else None,
            "finalidade": FINALIDADE, "politica": recibo.publico(),
            "utilizavel": politica_ok and bool(aprovacao), "codigo": codigo,
        })
    return resultados


def exigir_revisoes(
    resultados: list[dict[str, Any]], confirmados: dict[str, str],
) -> None:
    if len(confirmados) != len(resultados) or set(confirmados) != {r["master_ref"] for r in resultados}:
        raise ErroDeRegistroDeMidia(
            "META_ASSET_REVIEW_SET_MISMATCH", "Revise exatamente as peças selecionadas antes do envio.")
    for resultado in resultados:
        if confirmados[resultado["master_ref"]] != resultado["content_sha256"]:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_REVIEW_HASH_DIVERGED", "A imagem mudou depois da sua revisão.")
        if not resultado["utilizavel"]:
            mensagens = {
                "META_ASSET_POLICY_UNAVAILABLE": "A inspeção da imagem está indisponível. Nenhuma peça foi enviada.",
                "META_ASSET_POLICY_BLOCKED": "A inspeção recusou uma imagem. Revise o resultado antes de enviar.",
                "META_ASSET_FINAL_APPROVAL_REQUIRED": "Aprove a imagem final para uso em Meta Ads antes do envio.",
            }
            raise ErroDeRegistroDeMidia(resultado["codigo"], mensagens.get(resultado["codigo"], "Esta peça não pode ser enviada. Confira a revisão."))
