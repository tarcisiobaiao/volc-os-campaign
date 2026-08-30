"""Construção do grafo a partir do que está em disco.

Cinco fontes que hoje não se falam entram aqui e saem como uma estrutura só:

    psique.py            as 7 tensões — o ativo universal, estável
    familias_rpm.json    a taxonomia de arquétipos (só os NOMES e as regras)
    mapa_entidades.json  73 entidades locais em 5 países, com gancho e sazonalidade
    calendario_br.json   64 eventos datados
    iab.py               a categoria padronizada de cada arquétipo

## O cuidado que atravessa o módulo

De `familias_rpm.json` vêm **apenas os nomes dos arquétipos e as regras de
classificação**. O `rpm_familia` fica de fora, e não é preciosismo: aquele
número foi derivado de `lucro` numa carteira onde `spend` sozinho previa o
desfecho com AUC 0,971. Trazê-lo para cá reinjetaria no grafo a decisão de verba
de outra equipe, disfarçada de propriedade do mundo.

O estado de cada célula (`forte`, `subexplorado`, `perdeu`, `vazio`) vem do mapa
de entidades, que é PRESENÇA — alguém já achou o nome local e rodou lá — e não
rentabilidade. Presença é fato sobre o mundo; rentabilidade era fato sobre eles.
"""

from __future__ import annotations

import json
import pathlib
import re
import unicodedata

from .. import iab as I
from .. import psique as P
from .modelo import Grafo

_DADOS = pathlib.Path(__file__).resolve().parents[1] / "dados"

# País → spread do mercado (RPM/CPC relativo ao Brasil). Estimativas de um
# levantamento externo, NÃO medições — e é por isso que carregam `natureza`.
# O eixo `spread` do espaço lê daqui, e o dia em que houver Keyword Planner
# ligado, estes números são os primeiros a serem substituídos por medição.
# Formato de consumo dominante para "como fazer" de burocracia. O eixo que
# faltava, e a crítica que o revelou é a mais forte contra a tese de
# transposição: a tensão psicológica atravessa fronteira, o CANAL não.
#
# Em mercados de adoção digital mais recente, o "como fazer" acontece em
# WhatsApp, tutorial no YouTube, busca por voz e intermediário humano — não em
# artigo indexado. Um arquétipo perfeito num país assim é um funil que não fecha.
#
# Natureza: `estimado` em todos. É candidato a medição pelo próprio Analytics
# assim que houver tráfego lá.
FORMATO_PAIS = {
    "BR": "texto_busca", "PT": "texto_busca", "ES": "texto_busca",
    "AR": "texto_busca", "CL": "texto_busca", "UY": "texto_busca",
    "CO": "misto", "PE": "misto", "MX": "misto",
    "US": "texto_busca", "CA": "texto_busca", "CA-FR": "texto_busca",
    "GB": "texto_busca", "PL": "texto_busca", "RO": "texto_busca",
    "ZA": "misto", "TR": "misto", "TH": "misto",
    "IN": "video_social", "ID": "video_social", "PH": "video_social",
    "VN": "video_social", "NG": "video_social", "BD": "voz_ou_humano",
}

SPREAD_PAIS = {
    "BR": ("neutro", "observado"),
    "AR": ("bom", "estimado"),
    "CL": ("bom", "estimado"),
    "CO": ("bom", "estimado"),
    "PE": ("bom", "estimado"),
    "MX": ("bom", "estimado"),
    "US": ("ruim", "estimado"),
    "CA": ("ruim", "estimado"),
    "CA-FR": ("neutro", "hipotese"),   # leilão francófono é separado e mais raso
    "GB": ("ruim", "estimado"),
    "ES": ("neutro", "estimado"),
    "PT": ("bom", "estimado"),
    "PL": ("bom", "estimado"),
    "RO": ("excelente", "estimado"),
    "ZA": ("bom", "estimado"),
    "PH": ("excelente", "estimado"),
    "ID": ("excelente", "estimado"),
    "IN": ("excelente", "estimado"),
    "TH": ("excelente", "estimado"),
    "VN": ("excelente", "estimado"),
    "NG": ("excelente", "estimado"),
    "TR": ("excelente", "estimado"),
}


def _json(nome: str) -> dict | list | None:
    p = _DADOS / nome
    return json.loads(p.read_text()) if p.exists() else None


def _chave(s: str) -> str:
    """Chave de casamento entre fontes: minúsculo, sem acento, sem pontuação."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _regras_arquetipo(fam: dict) -> list[tuple[str, list]]:
    """Regras de classificação vindas de `familias_rpm.json`.

    Só as REGRAS. O `rpm_familia` do mesmo arquivo fica de fora — ver o
    docstring do módulo.
    """
    return [(r["familia"], [re.compile(p, re.IGNORECASE) for p in r["padroes"]])
            for r in sorted(fam.get("regras_classificacao", []),
                            key=lambda r: r["ordem"])]


def _classificar(termo: str, regras) -> str | None:
    for familia, padroes in regras:
        if any(p.search(termo) for p in padroes):
            return familia
    return None


def construir(*, paises_extra: list[str] | None = None) -> Grafo:
    g = Grafo()

    # ── 1. as tensões: a camada que não muda ────────────────────────────────
    for nome, d in P.TENSOES.items():
        g.no(f"t:{nome}", "tensao", nome,
             pergunta=d["pergunta"], intensidade=d["intensidade"])

    # ── 2. arquétipos: só nomes e taxonomia, sem RPM ────────────────────────
    fam = _json("familias_rpm.json") or {"familias": {}}
    for nome in fam.get("familias", {}):
        if nome == "outros":
            continue
        m = I.de(nome)
        g.no(f"a:{nome}", "arquetipo", nome,
             iab_id=(m.iab_id if m else None),
             iab_caminho=(m.caminho if m else ""),
             orfao_iab=bool(m and m.orfao))
        tensao = P.por_arquetipo(nome)
        if tensao:
            g.liga(f"a:{nome}", f"t:{tensao}", "aciona")

    # ── 3. países ───────────────────────────────────────────────────────────
    do_mapa = {e.get("pais") for e in (_json("mapa_entidades.json") or {}).get("entidades", [])}
    for cc in sorted({*do_mapa, *SPREAD_PAIS, *(paises_extra or [])} - {None, ""}):
        nivel, natureza = SPREAD_PAIS.get(cc, (None, "desconhecido"))
        g.no(f"p:{cc}", "pais", cc, spread=nivel, spread_natureza=natureza,
             formato_consumo=FORMATO_PAIS.get(cc))

    # ── 4. entidades: a pele local do invariante ────────────────────────────
    mapa = _json("mapa_entidades.json") or {}
    for e in mapa.get("entidades", []):
        arq, cc = e.get("arquetipo"), e.get("pais")
        if not arq or not cc or f"a:{arq}" not in g.nos:
            continue
        eid = f"e:{cc}:{e['entidade']}"
        g.no(eid, "entidade", e["entidade"], pais=cc, arquetipo=arq,
             o_que_e=e.get("o_que_e", ""), gancho=e.get("gancho_local", ""),
             sazonalidade=e.get("sazonalidade", ""), janela=e.get("janela", ""),
             buscas=e.get("buscas_provaveis", []), confianca=e.get("confianca", ""),
             orgao=e.get("orgao", ""))
        g.liga(eid, f"a:{arq}", "instancia")
        g.liga(eid, f"p:{cc}", "habita")

    # ── 5. o estado de cada célula, vindo de PRESENÇA ───────────────────────
    for cc, linha in (mapa.get("matriz", {}).get("matriz", {}) or {}).items():
        if f"p:{cc}" not in g.nos:
            continue
        for arq, cel in (linha or {}).items():
            if f"a:{arq}" not in g.nos:
                continue
            estado = cel.get("estado")
            if estado and estado != "nunca_tentado":
                g.liga(f"a:{arq}", f"p:{cc}", "explora",
                       estado=estado, n_temas=cel.get("n", 0))

    # ── 6. eventos: o pulso do lado esquerdo ────────────────────────────────
    # Dois cuidados aqui, e ambos custaram um bug de junção.
    #
    # (a) NORMALIZAÇÃO — o calendário escreve "saque aniversario fgts" e o mapa
    #     "saque aniversário fgts". Casar por string crua perdia a aresta.
    #
    # (b) O EVENTO CRIA A ENTIDADE quando ela não existe. Calendário e mapa
    #     cobrem universos diferentes de propósito: um traz o que está agendado,
    #     o outro o que foi descoberto. A interseção era de UMA entidade em 16.
    #     Mas um evento oficial sobre "bolsa familia" É a evidência de que a
    #     entidade existe naquele país — exigir que ela já estivesse no mapa
    #     jogaria fora justamente o lado esquerdo do sistema.
    indice = {_chave(n.rotulo): n.id for n in g.por_tipo("entidade")
              if n.atributos.get("pais") == "BR"}
    regras = _regras_arquetipo(fam)

    cal = _json("calendario_br.json") or {"eventos": []}
    for ev in cal.get("eventos", []):
        if not ev.get("verificado"):
            continue
        nome = ev["entidade"]
        vid = f"v:BR:{nome}:{ev['data_ref']}"
        g.no(vid, "evento", nome, data=ev["data_ref"], pais="BR",
             tipo_evento=ev.get("tipo", ""), orgao=ev.get("orgao", ""),
             recorrencia=ev.get("recorrencia", ""), fonte=ev.get("fonte_url", ""))

        alvo = indice.get(_chave(nome))
        if alvo is None:
            arq = _classificar(nome, regras)
            if arq is None or f"a:{arq}" not in g.nos:
                continue                      # sem arquétipo, o evento fica solto
            alvo = f"e:BR:{nome}"
            g.no(alvo, "entidade", nome, pais="BR", arquetipo=arq,
                 o_que_e=ev.get("descricao", ""), origem="calendario",
                 sazonalidade={"mensal": "sazonal_mensal", "anual": "sazonal_anual",
                               "unico": "evento_unico"}.get(ev.get("recorrencia"), ""))
            g.liga(alvo, f"a:{arq}", "instancia")
            g.liga(alvo, "p:BR", "habita")
            indice[_chave(nome)] = alvo
        g.liga(vid, alvo, "ativa")
    return g


def integrar_descobertas(g: Grafo, descobertas: list[dict]) -> dict:
    """Entra o que o harness diário descobriu. Devolve o que é NOVO.

    A distinção é o coração do ciclo diário: entidade já conhecida não vira
    alerta de novo. Sem isso o sentinela repete a mesma lista todo dia e morre
    de tédio na segunda semana — que é como esse tipo de ferramenta morre.
    """
    novas, conhecidas, rejeitadas = [], [], []
    for d in descobertas:
        arq, cc, nome = d.get("arquetipo"), (d.get("pais") or "").upper(), d.get("entidade")
        if not (arq and cc and nome):
            rejeitadas.append({**d, "motivo": "faltou arquetipo, pais ou entidade"})
            continue
        if f"a:{arq}" not in g.nos:
            rejeitadas.append({**d, "motivo": f"arquétipo {arq!r} não existe no grafo"})
            continue
        if f"p:{cc}" not in g.nos:
            nivel, nat = SPREAD_PAIS.get(cc, (None, "desconhecido"))
            g.no(f"p:{cc}", "pais", cc, spread=nivel, spread_natureza=nat,
                 formato_consumo=FORMATO_PAIS.get(cc))

        eid = f"e:{cc}:{nome}"
        ja = eid in g.nos
        g.no(eid, "entidade", nome, pais=cc, arquetipo=arq,
             o_que_e=d.get("o_que_e", ""), gancho=d.get("gancho_local", ""),
             sazonalidade=d.get("sazonalidade", ""),
             buscas=d.get("buscas_provaveis", []),
             confianca=d.get("confianca", ""), origem="descoberta")
        g.liga(eid, f"a:{arq}", "instancia")
        g.liga(eid, f"p:{cc}", "habita")
        (conhecidas if ja else novas).append(d)

    return {"novas": novas, "conhecidas": conhecidas, "rejeitadas": rejeitadas}
