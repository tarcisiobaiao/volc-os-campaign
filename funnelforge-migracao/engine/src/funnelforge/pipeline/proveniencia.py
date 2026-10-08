"""Proveniência de fonte, hints do operador e fatos derivados — o que o
dossiê precisa para não decidir AUTORIDADE só pelo hostname e para aceitar um
valor matematicamente derivável sem exigir que ele apareça literalmente.

* PROVENIÊNCIA (qualquer país, idioma e nicho): o emissor DECLARADO pela
  estruturação ou pelo hint só vale quando a frase dele aparece no cabeçalho ou
  no título do próprio DOCUMENTO; só então escopo, jurisdição (ISO 3166) e tipo
  de emissor contam. Cópia em outro host é aceita se o documento se identifica
  como do emissor; página que só CITA o emissor, não. Nenhuma lista de domínios.
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
_CABECALHO = 3000


# ---------------------------------------------------------------------------
# proveniência
# ---------------------------------------------------------------------------

#: O que a pesquisa (ou o hint) DECLARA sobre a fonte. Só vale depois de
#: conferido no documento.
CAMPOS_DECLARADOS = ("emissor", "tipo_de_emissor", "escopo", "jurisdicao")


def proveniencia_do_documento(url: str, doc: dict, declarado: dict | None = None) -> dict:
    """A proveniência de uma fonte, genérica para qualquer país, idioma e nicho.

    O emissor DECLARADO (pela estruturação ou pelo hint) só é comprovado quando
    a frase do emissor aparece, contígua, no cabeçalho ou no título do próprio
    documento. Sem isso, escopo e jurisdição declarados não valem: a fonte fica
    com escopo desconhecido. O hostname não decide autoridade."""
    d = {k: str((declarado or {}).get(k) or "").strip() for k in CAMPOS_DECLARADOS}
    publicador = (urlparse(url).hostname or "").lower().removeprefix("www.")
    t = texto_normal(doc.get("texto") or "")
    titulo = texto_normal(doc.get("titulo") or "")
    cabeca = t[:_CABECALHO]
    frase = " ".join(texto_normal(d["emissor"]).split())
    achado = -1
    if len(frase) >= 3:
        achado = cabeca.find(frase)
        if achado < 0 and frase in titulo:
            achado = 0
    verificado = achado >= 0
    versao = re.search(r"\b(?:versao|version|versione|versión)\s*:?\s*(\d+(?:\.\d+)?)", t)
    return {
        "issuer": d["emissor"], "emissor_verificado": verificado,
        "tipo_de_emissor": d["tipo_de_emissor"] if verificado else "",
        "escopo": d["escopo"] if verificado else "desconhecido",
        "jurisdicao": d["jurisdicao"].upper() if verificado else "",
        "declarado": d, "publisher_domain": publicador, "canonical_url": url,
        "document_title": str(doc.get("titulo") or "")[:160],
        "document_version": versao.group(1) if versao else "",
        "content_sha256": doc.get("sha256", ""),
        "trecho_de_autoria": (cabeca[max(0, achado - 60):achado + len(frase) + 60].strip()
                              if achado > 0 else (titulo[:160] if verificado else "")),
    }


def escopo_do_fato(f: FatoDoDossie) -> tuple[str, str]:
    from funnelforge.pipeline.dossie import escopo_do_fato as _e
    return _e(f)


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
        declarado = {k: h.get(k, "") for k in CAMPOS_DECLARADOS}
        fato = {"afirmacao": h.get("afirmacao", ""), "tipo": h.get("tipo", ""),
                "valor": h.get("valor", ""), "unidade": h.get("unidade", ""), "fonte": url,
                "vigente_desde": h.get("vigente_desde", ""),
                "dispositivo": h.get("dispositivo", ""), "paginas": h.get("paginas", []),
                "requisitos": h.get("requisitos", []), "origem": "hint_do_operador"}
        recibo = {"hint": url, "afirmacao_do_operador": fato["afirmacao"]}
        doc = ler_documento(url) if ler_documento else {"ok": False, "motivo": "sem leitor"}
        recibo.update(http=doc.get("status"), content_type=doc.get("content_type"),
                      content_sha256=doc.get("sha256", ""), leitura=doc.get("motivo") or "ok")
        fato["declarado"] = declarado
        if not doc.get("ok"):
            # Fonte inacessível ao nosso UA = INDISPONÍVEL, não falsa.
            fato["motivo_nao_verificado"] = f"hint não lido: {doc.get('motivo')}"
            fato["indisponivel"] = True
        else:
            fato["proveniencia"] = proveniencia_do_documento(url, doc, declarado)
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
            jurisdicoes = {j for _, j in escopos}
            if (len(jurisdicoes) != 1 or "" in jurisdicoes
                    or any(e == "desconhecido" for e, _ in escopos)):
                recusa(f"jurisdição divergente ou não comprovada entre as premissas: "
                       f"{sorted(escopos)}")
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
            jurisdicao_comum = next(iter(jurisdicoes))
            escopo = ("nacional" if all(e in ("internacional", "nacional") for e, _ in escopos)
                      else "subnacional")
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
                           "escopo": escopo, "jurisdicao": jurisdicao_comum,
                           "oficial": True}))
    return derivados, recusas
