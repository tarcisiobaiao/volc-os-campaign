"""Proveniência de fonte, hints do operador e fatos derivados — o que o
dossiê precisa para não decidir AUTORIDADE só pelo hostname e para aceitar um
valor matematicamente derivável sem exigir que ele apareça literalmente.

* PROVENIÊNCIA: a autoridade emissora é lida no DOCUMENTO. Espelho regional
  só vira nacional se o próprio documento se identificar, no cabeçalho, como do
  Departamento/Conselho Nacional; a versão em `dn.senac.br` (ou norma federal)
  é a canônica e é preferida.
* HINT DO OPERADOR: uma URL + a afirmação esperada. Não é fato: passa pelo
  mesmo fetch, o código localiza no documento o trecho com o valor (e a data,
  quando há vigência), confere a afirmação contra esse trecho, registra a
  proveniência e o recibo; a verificação ao vivo vem depois, como para todos.
* DERIVADO: só a operação declarada no contrato do requisito
  (`RequisitoFactual.derivacao`) e permitida pelo código — hoje,
  multiplicação de dois fatores —, com premissas verificadas, unidade,
  jurisdição e vigência compatíveis, aritmética exata (`Decimal`, sem
  arredondamento) e a linhagem inteira no fato. Recalculado a cada
  compilação: premissa que muda ou cai invalida o derivado.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import urlparse

from funnelforge.domain.dossie import (
    FatoDoDossie,
    id_do_fato,
    nucleo_da_unidade,
    numeros_do_texto,
    texto_normal,
)

#: Operações que o CÓDIGO sabe fazer. Fórmula livre não existe.
METODOS = {"multiplicacao": "deterministic_multiplication"}
_MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro")
_CABECALHO = 3000
_UFS = frozenset("ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se "
                 "to".split())


# ---------------------------------------------------------------------------
# proveniência
# ---------------------------------------------------------------------------

def _uf_do_host(host: str) -> str:
    return next((r for r in host.split(".")[:-2] if r in _UFS), "")


def _data_por_extenso(t: str) -> str:
    m = re.search(r"a partir de (\d{1,2})o? de (" + "|".join(_MESES) + r") de (\d{4})", t)
    if not m:
        return ""
    return f"{m.group(3)}-{_MESES.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}"


def proveniencia_do_documento(url: str, doc: dict) -> dict:
    """Quem emite, com que escopo, em que versão e desde quando — lido no
    documento. `doc` = saída de `ler_documento` (texto, titulo, sha256)."""
    host = (urlparse(url).hostname or "").lower()
    publicador = host.removeprefix("www.")
    t = texto_normal(doc.get("texto") or "")
    cabeca = t[:_CABECALHO]
    uf = _uf_do_host(publicador)
    federal = (publicador == "gov.br" or publicador.endswith(".gov.br")) and not uf
    nacional = re.search(r"(departamento nacional|conselho nacional)", cabeca)
    regional = re.search(r"departamento regional", cabeca)
    prov = {"issuer": publicador, "issuer_scope": "", "publisher_domain": publicador,
            "canonical_url": url, "document_title": str(doc.get("titulo") or "")[:160],
            "document_version": "", "jurisdiction": "", "effective_from": _data_por_extenso(t),
            "content_sha256": doc.get("sha256", ""), "trecho_de_autoria": "",
            "canonica": False, "espelho": False}
    versao = re.search(r"vers[a]o\s*:?\s*(\d+(?:\.\d+)?)", t)
    if versao:
        prov["document_version"] = versao.group(1)
    if federal and ("presidente da republica" in t or "decreto" in cabeca):
        inicio = t.find("presidente da republica")
        prov.update(issuer="Presidência da República" if inicio >= 0 else "Governo Federal",
                    issuer_scope="national", jurisdiction="BR", canonica=True,
                    trecho_de_autoria=t[max(0, inicio - 60):inicio + 120].strip()
                    if inicio >= 0 else cabeca[:180].strip())
    elif nacional and "senac" in cabeca and (not regional or nacional.start() < regional.start()):
        prov.update(issuer="Senac — " + ("Departamento Nacional"
                                         if "departamento nacional" in nacional.group(1)
                                         else "Conselho Nacional"),
                    issuer_scope="national", jurisdiction="BR",
                    canonica=publicador == "dn.senac.br", espelho=publicador != "dn.senac.br",
                    trecho_de_autoria=cabeca[max(0, nacional.start() - 80):
                                             nacional.end() + 80].strip())
    elif uf:
        prov.update(issuer=f"Senac {uf.upper()}" if "senac" in publicador else publicador,
                    issuer_scope="regional", jurisdiction=uf.upper(),
                    trecho_de_autoria=(cabeca[max(0, regional.start() - 60):regional.end() + 80]
                                       .strip() if regional else ""))
    return prov


def escopo_do_fato(f: FatoDoDossie) -> tuple[str, str]:
    """('nacional' | 'regional' | 'outra', uf) do fato: derivado pelas
    premissas; com proveniência, pelo emissor; sem ela, pelo host."""
    if f.origem == "derivado":
        return f.derivacao.get("escopo", "outra"), f.derivacao.get("uf", "")
    escopo = (f.proveniencia or {}).get("issuer_scope")
    if escopo == "national":
        return "nacional", ""
    if escopo == "regional":
        return "regional", str(f.proveniencia.get("jurisdiction", "")).lower()
    from funnelforge.pipeline.dossie import abrangencia_da_fonte
    return abrangencia_da_fonte(f.source_url)


# ---------------------------------------------------------------------------
# hints do operador
# ---------------------------------------------------------------------------

def data_no_trecho(iso: str, trecho: str) -> bool:
    from funnelforge.adapters.pesquisa_plano import data_no_trecho as _d
    return _d(iso, trecho)


def _sentencas(texto: str) -> list[str]:
    plano = re.sub(r"\s+", " ", texto or "")
    return [s.strip() for s in re.split(r"(?<=[.;:])\s+", plano) if s.strip()]


def trecho_com_valor(texto: str, valor: str, afirmacao: str, vigencia: str = "") -> str:
    """O trecho do documento que contém os números do valor — e a data, se
    houver vigência —, o mais parecido com a afirmação. Vazio = não achou."""
    from funnelforge.adapters.pesquisa_plano import _termos
    alvo = numeros_do_texto(valor)
    termos = _termos(afirmacao)
    sent = _sentencas(texto)
    melhor, nota = "", -1.0
    for i, s in enumerate(sent):
        if alvo and not alvo <= numeros_do_texto(s):
            continue
        janela = s
        if vigencia and not data_no_trecho(vigencia, janela):
            vizinhas = " ".join(sent[max(0, i - 1):i + 2])
            if not data_no_trecho(vigencia, vizinhas):
                continue
            janela = vizinhas
        n = len(termos & _termos(janela)) / max(1, len(termos))
        if n > nota:
            melhor, nota = janela, n
    return melhor[:600]


def verificar_hints(hints: list[dict], ler_documento: Callable[[str], dict] | None):
    """Os hints do operador como uma rodada SEM chamada a modelo. Saída:
    `RespostaDaPesquisa` (fato só com `motivo_nao_verificado` vazio quando o
    documento sustenta a afirmação)."""
    from funnelforge.adapters.pesquisa_plano import (
        SOBREPOSICAO_NA_PAGINA, canonica, sustentado)
    from funnelforge.pipeline.dossie import RespostaDaPesquisa
    fatos, recibos, sustentadas = [], [], []
    for h in hints:
        url = canonica(h.get("url"))
        fato = {"afirmacao": h.get("afirmacao", ""), "tipo": h.get("tipo", ""),
                "valor": h.get("valor", ""), "unidade": h.get("unidade", ""), "fonte": url,
                "vigente_desde": h.get("vigente_desde", ""),
                "dispositivo": h.get("dispositivo", ""), "paginas": h.get("paginas", []),
                "requisitos": h.get("requisitos", []), "origem": "hint_do_operador"}
        recibo = {"hint": url, "afirmacao_do_operador": fato["afirmacao"]}
        doc = ler_documento(url) if ler_documento else {"ok": False, "motivo": "sem leitor"}
        recibo.update(http=doc.get("status"), content_type=doc.get("content_type"),
                      content_sha256=doc.get("sha256", ""), leitura=doc.get("motivo") or "ok")
        if not doc.get("ok"):
            fato["motivo_nao_verificado"] = f"hint não lido: {doc.get('motivo')}"
        else:
            fato["proveniencia"] = proveniencia_do_documento(url, doc)
            recibo["proveniencia"] = fato["proveniencia"]
            trecho = trecho_com_valor(doc["texto"], fato["valor"], fato["afirmacao"],
                                      fato["vigente_desde"])
            recibo["trecho_extraido"] = trecho
            motivo = ("o documento não traz o valor (e a vigência) do hint" if not trecho
                      else sustentado(fato["afirmacao"], fato["valor"], trecho,
                                      minimo=SOBREPOSICAO_NA_PAGINA))
            if motivo:
                fato["motivo_nao_verificado"] = f"hint não sustentado: {motivo}"
            else:
                fato["evidencia_resumida"] = re.sub(r"\s+", " ", trecho)[:300]
                sustentadas.append(url)
        recibo["resultado"] = fato.get("motivo_nao_verificado") or "sustentado pelo documento"
        fatos.append(fato)
        recibos.append(recibo)
    return RespostaDaPesquisa(dados={"fatos": fatos}, citacoes=sustentadas,
                              modelo_pedido="", modelo_servido="", auth_mode="hint_do_operador",
                              custo_usd=0.0, custo_informado=True, metadados=recibos)


# ---------------------------------------------------------------------------
# fatos derivados
# ---------------------------------------------------------------------------

def _decimal(valor: str) -> Decimal | None:
    nums = numeros_do_texto(valor)
    if len(nums) != 1:
        return None
    alvo = texto_normal(valor)
    bruto = re.findall(r"\d+(?:[.,]\d+)*", alvo)
    if len(bruto) != 1:
        return None
    n = bruto[0]
    n = (n.replace(".", "").replace(",", ".") if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", n)
         else n.replace(",", "."))
    try:
        return Decimal(n)
    except InvalidOperation:
        return None


def _brl(d: Decimal) -> str:
    inteiro, centavos = f"{d:.2f}".split(".")
    return f"{int(inteiro):,}".replace(",", ".") + "," + centavos


def _operando(d: Decimal) -> str:
    return str(d.normalize()) if d == d.to_integral() else str(d)


def derivar_fatos(fatos: list[FatoDoDossie], pages: list, hoje: date,
                  oficial: Callable[[FatoDoDossie], bool]
                  ) -> tuple[list[FatoDoDossie], list[dict]]:
    """Os derivados declarados nos requisitos das páginas, e as recusas."""
    from funnelforge.pipeline.dossie import _melhor_por_escopo, requisitos_da_pagina
    derivados, recusas = [], []
    for page in pages:
        duvida = page.jornada.duvida_id
        for r in requisitos_da_pagina(page):
            d = getattr(r, "derivacao", None)
            if d is None:
                continue

            def recusa(motivo: str) -> None:
                recusas.append({"pagina": page.page_number, "requisito": r.id, "motivo": motivo})

            if d.operacao not in METODOS or len(d.fatores) != 2:
                recusa(f"operação '{d.operacao}' não permitida pelo código")
                continue
            premissas, valores = [], []
            for fator in d.fatores:
                cands = [f for f in fatos if f.status == "verified" and f.origem != "derivado"
                         and fator.requisito in f.requisitos and duvida in f.paginas
                         and nucleo_da_unidade(f.unidade) == fator.unidade and oficial(f)]
                escolhido = _melhor_por_escopo(cands)
                valor = _decimal(escolhido.valor) if escolhido else None
                if escolhido is None:
                    recusa(f"premissa '{fator.requisito}' ({fator.unidade}) sem fato verificado "
                           "de fonte oficial")
                    break
                if valor is None:
                    recusa(f"premissa '{fator.requisito}' com valor ambíguo: '{escolhido.valor}'")
                    break
                premissas.append(escolhido)
                valores.append(valor)
            if len(premissas) != 2:
                continue
            escopos = {escopo_do_fato(p) for p in premissas}
            if len(escopos) != 1 or next(iter(escopos))[0] not in ("nacional", "regional"):
                recusa(f"jurisdição divergente entre as premissas: {sorted(escopos)}")
                continue
            # Vigências compatíveis = todas as premissas em vigor na data do
            # derivado (a mais recente delas). Premissa que ainda não vigora em
            # `hoje` torna o derivado impossível; o derivado vale a partir da
            # premissa mais nova, enquanto ela vigorar.
            datas = [p.vigente_desde for p in premissas if p.vigente_desde]
            futuras = [x for x in datas if x > hoje]
            if futuras:
                recusa("vigência incompatível: premissa ainda não vigente em "
                       f"{hoje.isoformat()} ({', '.join(x.isoformat() for x in futuras)})")
                continue
            resultado = valores[0] * valores[1]
            if resultado != resultado.quantize(Decimal("0.01")):
                recusa(f"resultado {resultado} exigiria arredondamento")
                continue
            formula = " × ".join(_operando(v) for v in valores)
            valor = _brl(resultado)
            vigencia = max(datas) if datas else None
            escopo, uf = next(iter(escopos))
            ids = [p.fact_id for p in premissas]
            derivados.append(FatoDoDossie(
                fact_id=id_do_fato("derivado:" + "|".join(ids), "numero", formula, valor),
                afirmacao=(f"{r.descricao}: {d.unidade_resultado} {valor}, derivado por código "
                           f"({formula}) das premissas {ids[0]} e {ids[1]}; não é valor publicado "
                           "literalmente por uma fonte"),
                tipo="numero", valor=valor, unidade=d.unidade_resultado, source_url="",
                tipo_da_fonte="oficial", verificado_em=hoje, vigente_desde=vigencia,
                status="verified", origem="derivado", paginas=[duvida], requisitos=[r.id],
                evidencia=formula,
                dispositivo=(f"derivado: {formula} = {valor} a partir de "
                             + " e ".join(f"{p.fact_id} ({p.source_url})" for p in premissas)),
                derivacao={"metodo": METODOS[d.operacao], "operacao": d.operacao,
                           "formula": formula, "resultado": valor,
                           "unidade": d.unidade_resultado,
                           "operandos": [str(v) for v in valores], "premissas": ids,
                           "fontes_das_premissas": [p.source_url for p in premissas],
                           "fonte_base": next((p.source_url for p in premissas
                                               if nucleo_da_unidade(p.unidade)
                                               == nucleo_da_unidade(d.unidade_resultado)),
                                              premissas[0].source_url),
                           "vigente_desde": vigencia.isoformat() if vigencia else "",
                           "escopo": escopo, "uf": uf,
                           "jurisdicao": "BR" if escopo == "nacional" else uf.upper(),
                           "oficial": True}))
    return derivados, recusas
