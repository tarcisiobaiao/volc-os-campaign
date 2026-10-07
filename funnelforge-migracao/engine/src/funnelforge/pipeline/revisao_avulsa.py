"""O revisor sobre conteúdo JÁ PUBLICADO, exportado em arquivo (B5).

`funnelforge revisar <conteudo.json|html> --briefing <arq> [--contexto <arq>]`
roda o MESMO revisor do pipeline (`pipeline/revisao.py`), com as mesmas travas
de código, sobre o conteúdo remoto que o integrador exportou (ex.: REST do
WordPress com `context=edit`). Não fala com o WordPress, não publica e não
altera o arquivo de entrada: grava `revisao.json`, `patches.json` e o conteúdo
revisado numa pasta ao lado. Os patches viram LOTE para aprovação humana — a
âncora de correção remota continua vindo do conteúdo remoto, não do run.

Também serve à avaliação offline (`scripts/avaliar_revisor.py`), que monta o
mesmo contexto a partir de cada caso rotulado.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from funnelforge.config.settings import StepConfig
from funnelforge.pipeline.editorial_safety import EDITORIAL_NOTICE
from funnelforge.pipeline.revisao import (
    ContextoDaRevisao,
    Documento,
    Referencias,
    executar_revisao,
)
from funnelforge.pipeline.validators.briefing_contract import numeros
from funnelforge.politicas import carregar_pacote, pacote_para_o_revisor


def documento_do_arquivo(caminho: Path) -> Documento:
    """Lê .html (Gutenberg/HTML do corpo) ou .json (LP do template, objeto
    {conteudo, seotitle, metadescription} ou a resposta REST do WordPress com
    content.raw/title.raw)."""
    texto = caminho.read_text(encoding="utf-8")
    if caminho.suffix.lower() != ".json":
        return Documento(formato="gutenberg", corpo=texto)
    return documento_de_dados(json.loads(texto))


def documento_de_dados(dados: Any) -> Documento:
    if isinstance(dados, dict) and "hero_title" in dados:
        return Documento(formato="lp_json", corpo=json.dumps(dados, ensure_ascii=False))
    if isinstance(dados, dict) and isinstance(dados.get("content"), dict):
        corpo = dados["content"].get("raw") or dados["content"].get("rendered") or ""
        titulo = dados.get("title") or {}
        titulo = titulo.get("raw") or titulo.get("rendered") if isinstance(titulo, dict) else titulo
        return Documento(formato="gutenberg", corpo=str(corpo), seotitle=str(titulo or ""),
                         metadescription=str(dados.get("metadescription") or ""))
    if isinstance(dados, dict) and "conteudo" in dados:
        conteudo = dados["conteudo"]
        if isinstance(conteudo, dict):
            doc = Documento(formato="lp_json", corpo=json.dumps(conteudo, ensure_ascii=False))
        else:
            doc = Documento(formato=str(dados.get("formato") or "gutenberg"), corpo=str(conteudo))
        return Documento(formato=doc.formato, corpo=doc.corpo,
                         seotitle=str(dados.get("seotitle") or ""),
                         metadescription=str(dados.get("metadescription") or ""))
    raise ValueError("formato de conteúdo não reconhecido (esperado LP, REST do WP ou "
                     "{conteudo, seotitle, metadescription})")


def _briefing_como_texto(briefing: dict | None) -> str:
    if not briefing:
        return "BRIEFING AUSENTE."
    if briefing.get("versao") == "briefing-v1" and briefing.get("promessa_da_pagina"):
        from funnelforge.pipeline.briefing import briefing_para_o_redator
        return briefing_para_o_redator(briefing)
    return "BRIEFING (como veio):\n" + json.dumps(briefing, ensure_ascii=False, indent=1)


def _inventario_como_texto(contexto: dict) -> str:
    linhas = ["FATOS (cite pelos ids):"]
    fatos = contexto.get("fatos") or []
    if not fatos:
        linhas.append("  NENHUM fato informado: toda afirmação factual fica sem lastro.")
    for f in fatos:
        partes = [f"  - {f.get('id')} [{f.get('tipo') or 'sem tipo'}] {f.get('texto', '')}"]
        if f.get("fonte"):
            partes.append(f"fonte: {f['fonte']}")
        if f.get("escopo"):
            partes.append(f"escopo: {f['escopo']}")
        if f.get("citavel") is False:
            partes.append("NÃO CITÁVEL (fonte contraditória ou instável)")
        linhas.append(" — ".join(partes))
    fontes = contexto.get("fontes") or []
    if fontes:
        linhas.append("FONTES:")
        linhas += [f"  - {s.get('id')} {s.get('url')}" for s in fontes]
    leitura = contexto.get("perguntas_paa") or []
    if leitura:
        linhas.append("PERGUNTAS REAIS DOS LEITORES (PAA):")
        linhas += [f"  {i}. {q}" for i, q in enumerate(leitura, start=1)]
    return "\n".join(linhas)


def contexto_de_dados(briefing: dict | None, contexto: dict | None, doc: Documento, *,
                      hoje: date | None = None) -> ContextoDaRevisao:
    """O contexto do revisor a partir de arquivos (sem RunState). O que não vier
    no contexto é declarado AUSENTE — nunca inventado."""
    contexto = contexto or {}
    pacote = carregar_pacote(hoje=hoje or date.today())
    fatos = [f for f in contexto.get("fatos") or [] if isinstance(f, dict) and f.get("id")]
    fontes = {str(s.get("id")): str(s.get("url")) for s in contexto.get("fontes") or []
              if isinstance(s, dict) and s.get("id")}
    for f in fatos:
        if f.get("fonte") and f["fonte"] not in fontes.values():
            fontes[f"s{len(fontes) + 1}"] = str(f["fonte"])
    destinos = [d for d in contexto.get("destinos") or [] if isinstance(d, dict) and d.get("id")]
    termos = contexto.get("termos") or {"estado": "ausente",
                                        "motivo_ausencia": "não informado no contexto"}
    anuncio = contexto.get("anuncio") or {"estado": "ausente",
                                          "motivo_ausencia": "não informado no contexto"}
    permitidos: set[str] = set()
    for f in fatos:
        if f.get("citavel") is not False:
            permitidos |= numeros(f.get("texto", ""))
    pagina = {"numero": 1, "slug": "", "papel": "", "h1": ""}
    pagina.update({k: v for k, v in (contexto.get("pagina") or {}).items() if v is not None})
    return ContextoDaRevisao(
        pagina=pagina,
        briefing_texto=_briefing_como_texto(briefing),
        inventario_texto=_inventario_como_texto(contexto),
        origem={"rotas": list(contexto.get("origem") or []), "anuncio": anuncio},
        destinos=destinos, ctas=list(contexto.get("ctas") or []),
        termos=termos,
        identidade={"dominio": contexto.get("dominio", "não informado"),
                    "autor": contexto.get("autor", "não informado"),
                    "aviso_editorial": contexto.get("aviso_editorial", EDITORIAL_NOTICE)},
        politicas=pacote_para_o_revisor(pacote),
        localizadores=list(contexto.get("localizadores") or []),
        referencias=Referencias(
            fatos={str(f["id"]) for f in fatos},
            fatos_nao_citaveis={str(f["id"]) for f in fatos if f.get("citavel") is False},
            fontes=fontes, politicas_bloqueantes=pacote.ids_bloqueantes(),
            politicas_nota=pacote.ids_de_nota(),
            destinos={str(d["id"]): str(d.get("destino") or "") for d in destinos},
            termos=(set(termos.get("amostra") or [])
                    if termos.get("estado") == "presente" else set()),
            paa=len(contexto.get("perguntas_paa") or []),
            anuncio=(len(anuncio.get("titulos") or []) + len(anuncio.get("descricoes") or [])
                     if anuncio.get("estado") == "presente" else 0)),
        numeros_permitidos=permitidos,
        pacote_vencido=pacote.vencido,
    )


def _patches_do_registro(registro: dict) -> tuple[list[dict], list[dict]]:
    aplicaveis: list[dict] = []
    recusados: list[dict] = []
    for rodada in registro.get("rodadas") or []:
        if rodada.get("mantida"):
            aplicaveis += [{**p, "rodada": rodada["rodada"], "estado": "proposto_aplicavel"}
                           for p in rodada.get("patches_aplicados") or []]
        elif rodada.get("retida_pela_trava_de_notas"):
            # o patch passou em tudo o que o código confere; só a trava das notas
            # o reteve: a pessoa decide sobre ele (o texto revisado é o original)
            aplicaveis += [{**p, "rodada": rodada["rodada"],
                            "estado": "proposto_para_decisao_humana"}
                           for p in rodada.get("patches_aplicados") or []]
        recusados += [{**p, "rodada": rodada["rodada"]}
                      for p in rodada.get("patches_recusados") or []]
    return aplicaveis, recusados


def revisar_arquivo(conteudo: Path, briefing: Path, contexto: Path | None,
                    saida: Path | None, *, runner: Any, cfg: StepConfig,
                    hoje: date | None = None) -> dict:
    """Roda o revisor sobre um arquivo e grava revisao.json + patches.json."""
    doc = documento_do_arquivo(conteudo)
    dados_briefing = json.loads(briefing.read_text(encoding="utf-8"))
    dados_contexto = (json.loads(contexto.read_text(encoding="utf-8"))
                      if contexto is not None else {})
    if not doc.seotitle and dados_contexto.get("seotitle"):
        doc = Documento(formato=doc.formato, corpo=doc.corpo,
                        seotitle=str(dados_contexto["seotitle"]),
                        metadescription=str(dados_contexto.get("metadescription") or ""))
    ctx = contexto_de_dados(dados_briefing, dados_contexto, doc, hoje=hoje)
    destino = saida or conteudo.with_name(f"{conteudo.stem}_revisao")
    destino.mkdir(parents=True, exist_ok=True)
    resultado = executar_revisao(doc, ctx, runner=runner, cfg=cfg, run_id="log",
                                 numero=int(ctx.pagina.get("numero") or 1))
    registro = dict(resultado.registro, origem=str(conteudo.name))
    aplicaveis, recusados = _patches_do_registro(registro)
    lote = {
        "versao": "patches-v1", "origem": conteudo.name, "decisao": resultado.decisao,
        "sha256_entrada": registro["sha256_entrada"], "sha256_revisado": registro["sha256"],
        "patches": aplicaveis, "recusados": recusados,
        "aviso": ("Lote para aprovação humana. Nada foi publicado nem enviado ao WordPress; "
                  "aplique só depois da aprovação do lote, ancorando no conteúdo remoto atual."),
    }
    (destino / "revisao.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    (destino / "patches.json").write_text(json.dumps(lote, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    extensao = ".json" if doc.formato == "lp_json" else ".html"
    (destino / f"conteudo_revisado{extensao}").write_text(resultado.documento.corpo,
                                                          encoding="utf-8")
    return {"saida": str(destino), "decisao": resultado.decisao,
            "patches": len(aplicaveis), "recusados": len(recusados)}
