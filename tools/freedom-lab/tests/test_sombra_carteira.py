"""Motor shadow da carteira (W13): um experimento conferido por campanha da conta,
receita só pelo câmbio versionado, ausência nunca vira zero, nada é executado.

Tudo sintético: ids de campanha e conta inventados, nenhuma rede, nenhum banco.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from volc_lab.experimentos import validar
from volc_lab.sombra_carteira import adaptadores, aplicacao, dominio
from volc_lab.sombra_carteira.__main__ import main as cli
from volc_lab.sombra_carteira.portas import ContratoQuebrado, Cotacao, CustoDia, Leitura, ReceitaObservada

CONTA = "1112223334"
HOJE = date(2026, 10, 15)
LIDO = "2026-10-15T12:00:00Z"
BASE_REF = "a8059ba0"
SUF = "20261015t120000z"   # instante da leitura (LIDO) no nome do experimento
CAMP_RUIM, CAMP_BOA, CAMP_SEM_CAMBIO, CAMP_POUCA = "900000000001", "900000000002", "900000000003", "900000000004"


def custo(cid, d, micros, cliques=40, *, conta=CONTA, segmentos=None, fechada=True, moeda="BRL",
          valor_conv=10.0, origem="D-1", nome=None, status="ENABLED"):
    return {"customer_id": conta, "campaign_id": cid, "metric_date": d.isoformat(),
            "segmentos": segmentos or {}, "custo_micros": micros, "cliques": cliques,
            "currency_code": moeda, "janela_fechada": fechada, "campaign_name": nome or f"camp {cid[-1]}",
            "campaign_status": status, "valor_conversoes": valor_conv, "colhida_em": LIDO,
            "origem_janela": origem}


def receita(cid, d, usd, *, brl=None, modo="anterior", fonte="joinads", dominio_="a.com.br", taxa=5.4,
            moeda="USD"):
    chave = {"date": d.isoformat(), "utm_campaign_value": cid}
    chave["joinads_domain" if fonte == "joinads" else "gam_accounts_id"] = dominio_
    if brl is None and modo in ("exata", "anterior") and usd is not None:
        brl = round(usd * taxa, 4)
    return {"fonte": fonte, "chave": chave, "data_referencia": d.isoformat(), "moeda": moeda,
            "receita": usd, "receita_brl": brl, "cambio_modo": modo,
            "cambio_taxa": taxa if modo in ("exata", "anterior") else None,
            "cambio_defasagem_dias": 1 if modo == "anterior" else (40 if modo == "defasada" else None),
            "coletado_em": LIDO, "removida": False}


def cot(par, d, modo="anterior", taxa=5.4, defasagem=None):
    """Uma resposta de cambio_resolver (v23_01) para (par, d)."""
    com_taxa = modo in ("exata", "anterior")
    if defasagem is None:
        defasagem = {"exata": 0, "anterior": 1, "defasada": 40}.get(modo)
    return {"par": par, "data": d.isoformat(), "modo": modo, "taxa": taxa if com_taxa else None,
            "data_cotacao": None if modo == "sem_cotacao" else (d - timedelta(days=defasagem)).isoformat(),
            "defasagem_dias": defasagem, "cotacao_id": None if modo == "sem_cotacao" else 7,
            "fonte": None if modo == "sem_cotacao" else "ptax"}


# Câmbio por par, igual para todo dia: USD com cotação da véspera; EUR só com
# cotação velha demais (defasada). A receita da CAMP_SEM_CAMBIO é em EUR.
CAMBIO_PADRAO = {"USD/BRL": ("anterior", 5.4), "EUR/BRL": ("defasada", None)}


def dias(n=20):
    return [HOJE - timedelta(days=i) for i in range(1, n + 1)]


def carteira():
    c, r = [], []
    for d in dias():
        # Ruim: R$ 30/dia, 40 cliques, US$ 0,30 de receita (ROAS ~0,05).
        c.append(custo(CAMP_RUIM, d, 30_000_000))
        r.append(receita(CAMP_RUIM, d, 0.30))
        # Boa: R$ 20/dia, receita US$ 6,00 em dois domínios (ROAS ~1,6).
        c.append(custo(CAMP_BOA, d, 20_000_000))
        r.append(receita(CAMP_BOA, d, 4.0, dominio_="a.com.br"))
        r.append(receita(CAMP_BOA, d, 2.0, dominio_="b.com.br"))
        # Sem câmbio: receita existe em EUR e a cotação EUR/BRL é velha demais.
        c.append(custo(CAMP_SEM_CAMBIO, d, 10_000_000))
        r.append(receita(CAMP_SEM_CAMBIO, d, 5.0, modo="defasada", moeda="EUR"))
        # Pouca amostra: 2 cliques/dia.
        c.append(custo(CAMP_POUCA, d, 5_000_000, cliques=2))
        r.append(receita(CAMP_POUCA, d, 0.5))
        # Linha segmentada (por dispositivo): não é total e não pode somar.
        c.append(custo(CAMP_RUIM, d, 999_000_000, segmentos={"device": "MOBILE"}))
    # Receita de campanha de outra rede (adset Meta, por exemplo): fica fora.
    r.append(receita("123456789012", dias()[0], 50.0))
    return c, r


class Fonte:
    def __init__(self, c, r, lido=LIDO, cambio=None):
        self.c, self.r, self.lido = c, r, lido
        self.cambio = CAMBIO_PADRAO if cambio is None else cambio
        self.pedidos_cambio: list = []

    def custo_campanha_dia(self, conta, inicio, fim):
        return Leitura(tuple(self.c), self.lido, "teste: google_ads_campanha_dia sintético")

    def receita_vigente(self, inicio, fim):
        return Leitura(tuple(self.r), self.lido, "teste: receita_as_of sintética")

    def cotacoes(self, pedidos, conhecido_ate, max_defasagem_dias):
        self.pedidos_cambio.append((list(pedidos), conhecido_ate, max_defasagem_dias))
        linhas = []
        for par, d in pedidos:
            regra = self.cambio(par, d) if callable(self.cambio) else self.cambio.get(par)
            if regra is not None:
                linhas.append(cot(par, d, *regra))
        return Leitura(tuple(linhas), self.lido, "teste: cambio_resolver sintético")


def gerar(destino, c=None, r=None, *, cambio=None, **kw):
    if c is None:
        c, r = carteira()
    f = Fonte(c, r, cambio=cambio)
    return aplicacao.gerar_lote(CONTA, f, f, f, destino, base_ref=BASE_REF, hoje=HOJE, **kw)


def resultado(destino, cid, sufixo=None):
    return json.loads((destino / f"gads-{cid}-sombra-{sufixo or SUF}" / "resultado.json").read_text())


def arvore(raiz: Path) -> dict[str, bytes]:
    return {str(p.relative_to(raiz)): p.read_bytes() for p in sorted(raiz.rglob("*")) if p.is_file()}


# ── um experimento por campanha, no formato que a tela do W7 já lê ──────────

def test_um_experimento_valido_por_campanha(tmp_path):
    saida = gerar(tmp_path)
    assert saida["resumo"]["campanhas"] == 4
    assert sorted(saida["novos"]) == sorted(f"gads-{c}-sombra-{SUF}"
                                             for c in (CAMP_RUIM, CAMP_BOA, CAMP_SEM_CAMBIO, CAMP_POUCA))
    for eid in saida["novos"]:
        pasta = tmp_path / eid
        manifesto = json.loads((pasta / "experimento.json").read_text())
        assert validar(manifesto, pasta) == [], eid
        assert manifesto["method"]["external_calls"] == {"mode": "none", "count": 0}
        assert manifesto["result"]["reproducible"] == "identical"
        assert {a["path"] for a in manifesto["artifacts"]} >= {"resultado.json", "transformacao.csv",
                                                               "cambio_lido.json"}


def test_direcoes_da_carteira(tmp_path):
    gerar(tmp_path)
    assert resultado(tmp_path, CAMP_RUIM)["recomendacao"]["direcao"] == "pausar"
    assert resultado(tmp_path, CAMP_BOA)["recomendacao"]["direcao"] == "aumentar"
    pouca = resultado(tmp_path, CAMP_POUCA)
    assert pouca["estado_dado"] == dominio.AMOSTRA_INSUFICIENTE
    assert pouca["recomendacao"]["direcao"] == "evidencia_insuficiente"


def test_nada_executa_nem_sugere_valor(tmp_path):
    saida = gerar(tmp_path)
    for eid in saida["novos"]:
        rec = json.loads((tmp_path / eid / "resultado.json").read_text())["recomendacao"]
        assert rec["executada"] is False
        assert rec["valor_sugerido"] is None
    lote = json.loads(Path(saida["caminho"]).read_text())
    assert lote["isolamento"] == {"chamadas_externas_alem_das_portas": 0, "mutacoes_executadas": 0,
                                  "oferece_aplicar": False}
    assert all(i["executada"] is False for i in lote["experimentos"])


# ── ausência nunca vira zero ────────────────────────────────────────────────

def test_cambio_defasado_e_sem_dado_nunca_zero(tmp_path):
    gerar(tmp_path)
    r = resultado(tmp_path, CAMP_SEM_CAMBIO)
    assert r["estado_dado"] == dominio.SEM_DADO
    assert r["recomendacao"]["direcao"] == "evidencia_insuficiente"
    assert r["janela_madura"]["roas"] is None and r["janela_madura"]["receita_brl"] is None
    assert "cambio_defasado" in r["custo_maduro_sem_receita_por_estado"]
    csv = (tmp_path / f"gads-{CAMP_SEM_CAMBIO}-sombra-{SUF}" / "transformacao.csv").read_text().splitlines()
    cab = csv[0].split(",")
    for linha in csv[1:]:
        celulas = dict(zip(cab, linha.split(",")))
        assert celulas["receita_brl"] == ""      # vazio, nunca 0
        assert celulas["receita_moeda_origem"] == "5.0"


def test_sem_cotacao_tambem_e_sem_dado():
    c = [CustoDia.da_linha(custo(CAMP_RUIM, d, 30_000_000)) for d in dias()]
    r = [ReceitaObservada.da_linha(receita(CAMP_RUIM, d, 1.0, modo="sem_cotacao")) for d in dias()]
    av = dominio.avaliar(CAMP_RUIM, c, r, HOJE)
    assert av.estado_dado == dominio.SEM_DADO
    assert {d.estado for d in av.dias if d.maduro} == {"sem_cotacao"}
    assert all(d.receita_brl is None for d in av.dias)


def test_um_dominio_sem_valor_nao_soma_o_outro():
    d = dias()[5]
    r = [ReceitaObservada.da_linha(receita(CAMP_BOA, d, 4.0)),
         ReceitaObservada.da_linha(receita(CAMP_BOA, d, None, modo="sem_receita", dominio_="b.com.br"))]
    c = [CustoDia.da_linha(custo(CAMP_BOA, d, 20_000_000))]
    (dia,), _ = dominio.reconciliar(CAMP_BOA, c, r, HOJE)
    assert dia.estado == "receita_parcial" and dia.receita_brl is None


def test_gam_sem_roteador_e_sobreposicao_nao_reconciliam():
    d = dias()[5]
    c = [CustoDia.da_linha(custo(CAMP_RUIM, d, 30_000_000))]
    so_gam = [ReceitaObservada.da_linha(receita(CAMP_RUIM, d, 9.0, fonte="gam", dominio_="7"))]
    ambos = so_gam + [ReceitaObservada.da_linha(receita(CAMP_RUIM, d, 1.0))]
    assert dominio.reconciliar(CAMP_RUIM, c, so_gam, HOJE)[0][0].estado == "gam_sem_atribuicao"
    (dia,), _ = dominio.reconciliar(CAMP_RUIM, c, ambos, HOJE)
    assert dia.estado == "sobreposicao_gam_joinads" and dia.receita_brl is None


def test_dia_maduro_so_com_d0_conta_como_sem_receita_e_dias_recentes_nao_decidem(tmp_path):
    c, r = carteira()
    c = [x | {"janela_fechada": False, "origem_janela": "D0"} if x["metric_date"] == dias()[10].isoformat() else x
         for x in c]
    # Receita gigante nos 3 dias imaturos não muda nada.
    r = [x | {"receita": 1e6, "receita_brl": 5.4e6}
         if x["data_referencia"] >= dias()[2].isoformat() and x["cambio_modo"] == "anterior" else x
         for x in r]
    gerar(tmp_path, c, r)
    ruim = resultado(tmp_path, CAMP_RUIM)
    assert ruim["recomendacao"]["direcao"] == "pausar"
    linha = [l for l in (tmp_path / f"gads-{CAMP_RUIM}-sombra-{SUF}" / "transformacao.csv").read_text().splitlines()
             if l.startswith(dias()[10].isoformat())][0]
    # Maduro pelo calendário; não reconcilia; pesa na fração e aparece nas lacunas.
    assert linha.endswith("true,janela_aberta")
    assert ruim["custo_maduro_sem_receita_por_estado"]["janela_aberta"] == 30.0
    assert any("janela_aberta" in l for l in ruim["recomendacao"]["lacunas"])


def test_valor_de_conversao_do_google_nao_decide(tmp_path):
    c, r = carteira()
    gerar(tmp_path / "a", c, r)
    gerar(tmp_path / "b", [x | {"valor_conversoes": 1e9} for x in c], r)
    for cid in (CAMP_RUIM, CAMP_BOA, CAMP_SEM_CAMBIO, CAMP_POUCA):
        assert (resultado(tmp_path / "a", cid)["recomendacao"]
                == resultado(tmp_path / "b", cid)["recomendacao"])


def test_segmentada_nao_soma_e_duplicada_recusa():
    d = dias()[5]
    c = [CustoDia.da_linha(custo(CAMP_RUIM, d, 30_000_000)),
         CustoDia.da_linha(custo(CAMP_RUIM, d, 999_000_000, segmentos={"device": "MOBILE"}))]
    (dia,), _ = dominio.reconciliar(CAMP_RUIM, c, [], HOJE)
    assert dia.custo_brl == 30.0
    with pytest.raises(ContratoQuebrado, match="repetido"):
        dominio.reconciliar(CAMP_RUIM, c + [CustoDia.da_linha(custo(CAMP_RUIM, d, 1))], [], HOJE)


def test_campo_ausente_no_contrato_quebra_em_vez_de_virar_zero():
    linha = custo(CAMP_RUIM, dias()[0], 1)
    del linha["custo_micros"]
    with pytest.raises(ContratoQuebrado, match="custo_micros"):
        CustoDia.da_linha(linha)
    rl = receita(CAMP_RUIM, dias()[0], 1.0)
    del rl["cambio_modo"]
    with pytest.raises(ContratoQuebrado, match="cambio_modo"):
        ReceitaObservada.da_linha(rl)
    # receita_brl com modo que o CHECK da v23_01 proíbe: não é a fonte do contrato.
    with pytest.raises(ContratoQuebrado, match="receita_brl"):
        ReceitaObservada.da_linha(receita(CAMP_RUIM, dias()[0], 1.0, modo="defasada", brl=5.0))


# ── conta, sigilo e origem dos números ──────────────────────────────────────

def test_outra_conta_recusa_o_lote_inteiro(tmp_path):
    c, r = carteira()
    c.append(custo("900000000099", dias()[0], 1, conta="9998887776"))
    with pytest.raises(ContratoQuebrado, match="outra conta"):
        gerar(tmp_path, c, r)
    assert not tmp_path.exists() or arvore(tmp_path) == {}


def test_conta_so_aparece_mascarada(tmp_path):
    gerar(tmp_path)
    for nome, b in arvore(tmp_path).items():
        assert CONTA.encode() not in b, nome


def test_cada_numero_declara_a_fonte_e_nunca_o_painel_legado(tmp_path):
    gerar(tmp_path)
    r = resultado(tmp_path, CAMP_RUIM)
    assert "google_ads_campanha_dia" in r["fontes"]["custo_brl"]
    assert "receita_as_of" in r["fontes"]["receita_brl"]
    assert "cambio_resolver" in r["fontes"]["receita_brl"]
    assert "revenue_converted" in r["fontes"]["receita_brl"]   # declarado como NÃO usado
    texto = json.dumps(r)
    assert "daily_campaign_metrics" not in texto
    csv = (tmp_path / f"gads-{CAMP_RUIM}-sombra-{SUF}" / "transformacao.csv").read_text()
    assert ",D-1," in csv   # custo_origem por dia


# ── experimento assinado não é reescrito ────────────────────────────────────

def test_rodar_de_novo_com_o_mesmo_dado_e_idempotente(tmp_path):
    primeira = gerar(tmp_path)
    antes = arvore(tmp_path)
    segunda = gerar(tmp_path)
    assert segunda["novos"] == [] and sorted(segunda["repetidos"]) == sorted(primeira["novos"])
    assert segunda["lote_sha256"] == primeira["lote_sha256"]
    assert arvore(tmp_path) == antes


def test_dado_diferente_no_mesmo_as_of_recusa_sem_escrever_nada(tmp_path):
    gerar(tmp_path)
    antes = arvore(tmp_path)
    c, r = carteira()
    r = [x | {"receita": 99.0, "receita_brl": 534.6} if x["chave"]["utm_campaign_value"] == CAMP_RUIM else x
         for x in r]
    with pytest.raises(aplicacao.LoteRecusado, match="não é reescrito"):
        gerar(tmp_path, c, r)
    assert arvore(tmp_path) == antes


def test_experimento_senac_de_data_so_nao_colide_com_o_instante_da_leitura(tmp_path):
    antigo = tmp_path / "senac-shadow-20261015"
    antigo.mkdir(parents=True)
    (antigo / "resultado.json").write_text(json.dumps({"campanha": CAMP_RUIM, "as_of": "2026-10-15"}))
    (antigo / "experimento.json").write_text("{}")
    assert len(gerar(tmp_path)["novos"]) == 4


def test_outro_experimento_da_campanha_no_mesmo_as_of_recusa(tmp_path):
    intruso = tmp_path / "senac-shadow-20261015"
    intruso.mkdir(parents=True)
    (intruso / "resultado.json").write_text(json.dumps({"campanha": CAMP_RUIM, "as_of": "2026-10-15T12:00:00Z"}))
    (intruso / "experimento.json").write_text("{}")
    antes = arvore(tmp_path)
    with pytest.raises(aplicacao.LoteRecusado, match="ambiguidade"):
        gerar(tmp_path)
    assert arvore(tmp_path) == antes


def test_resultado_ilegivel_existente_recusa(tmp_path):
    quebrado = tmp_path / "qualquer"
    quebrado.mkdir(parents=True)
    (quebrado / "resultado.json").write_text("{nao json")
    (quebrado / "experimento.json").write_text("{}")
    with pytest.raises(aplicacao.LoteRecusado, match="ilegível"):
        gerar(tmp_path)


def test_nao_sobra_pasta_temporaria(tmp_path):
    gerar(tmp_path)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp")]
    assert not list(tmp_path.rglob("*.tmp"))


# ── replay ──────────────────────────────────────────────────────────────────

def test_replay_reproduz_bytes_e_detecta_adulteracao(tmp_path):
    saida = gerar(tmp_path)
    pasta = tmp_path / saida["novos"][0]
    assert aplicacao.replay(pasta) == {"experimento_id": pasta.name, "identico": True, "divergentes": []}
    entrada = json.loads((pasta / "receita_observada.json").read_text())
    for l in entrada["linhas"]:
        l["receita"] = (l["receita"] or 0) * 3
    (pasta / "receita_observada.json").write_bytes(aplicacao._json_bytes(entrada))
    assert aplicacao.replay(pasta) == {"experimento_id": pasta.name, "identico": False,
                                       "divergentes": ["resultado.json", "transformacao.csv"]}


def test_cli_gera_e_recusa_com_codigos(tmp_path):
    c, r = carteira()
    (tmp_path / "custo.json").write_text(json.dumps({"lido_em": LIDO, "linhas": c}))
    (tmp_path / "receita.json").write_text(json.dumps({"lido_em": LIDO, "linhas": r}))
    f = Fonte(c, r)
    pedidos = aplicacao._pedidos_de_cambio(r)
    (tmp_path / "cambio.json").write_text(json.dumps(
        {"lido_em": LIDO, "linhas": list(f.cotacoes(pedidos, LIDO, 7).linhas)}))
    args = ["gerar", "--conta", "111-222-3334", "--custo", str(tmp_path / "custo.json"),
            "--receita", str(tmp_path / "receita.json"), "--cambio", str(tmp_path / "cambio.json"),
            "--destino", str(tmp_path / "exp"), "--base-ref", BASE_REF]
    assert cli(args) == 0
    pasta = next(p for p in (tmp_path / "exp").iterdir() if p.name.startswith("gads-"))
    assert cli(["replay", str(pasta)]) == 0
    r[0]["receita"] = 77.0
    r[0]["receita_brl"] = 415.8
    (tmp_path / "receita.json").write_text(json.dumps({"lido_em": LIDO, "linhas": r}))
    assert cli(args) == 2
    with pytest.raises(SystemExit):
        cli([a for a in args if a not in ("--cambio", str(tmp_path / "cambio.json"))])


# ── porta PostgREST: só leitura, só a autoridade operacional ────────────────

def test_postgrest_recusa_supabase_fora_da_autoridade():
    with pytest.raises(ValueError, match="autoridade"):
        adaptadores.PostgrestSoLeitura("https://abc.supabase.co", "x")
    with pytest.raises(ValueError, match="service_role"):
        adaptadores.PostgrestSoLeitura("https://database.agenciavolc.com.br", "")


class ServidorFalso:
    """PostgREST de mentira: aplica order/gt/limit e um teto de linhas do servidor
    (PGRST_DB_MAX_ROWS) menor que a página pedida. `entre_paginas` roda depois
    da primeira página, como uma escrita concorrente."""

    def __init__(self, custo_linhas, receita_linhas, max_rows=7, entre_paginas=None, cambio=None):
        self.tabelas = {"/rest/v1/google_ads_campanha_dia": ("fato_id", list(custo_linhas)),
                        "/rest/v1/rpc/receita_as_of": ("id", list(receita_linhas))}
        self.max_rows, self.entre_paginas = max_rows, entre_paginas
        self.cambio = cambio or {}
        self.pedidos: list = []

    def __call__(self, metodo, url, cab, corpo):
        import urllib.parse as up
        partes = up.urlsplit(url)
        q = dict(up.parse_qsl(partes.query))
        self.pedidos.append((metodo, partes.path, q, corpo))
        if partes.path == "/rest/v1/rpc/cambio_resolver":
            b = json.loads(corpo)
            regra = self.cambio.get(b["p_par"])
            if regra is None:
                return 200, json.dumps([{"cotacao_id": None, "par": b["p_par"], "taxa": None,
                                         "data_cotacao": None, "as_of": None, "fonte": None,
                                         "modo": "sem_cotacao", "defasagem_dias": None}]).encode()
            linha = cot(b["p_par"], date.fromisoformat(b["p_data"]), *regra)
            return 200, json.dumps([{**linha, "as_of": None}]).encode()
        chave, linhas = self.tabelas[partes.path]
        assert q["order"] == f"{chave}.asc"
        chave_de = (lambda l: int(l[chave])) if chave == "id" else (lambda l: l[chave])
        if chave in q:
            piso = q[chave].removeprefix("gt.")
            piso = int(piso) if chave == "id" else piso
            linhas = [l for l in linhas if chave_de(l) > piso]
        pagina = sorted(linhas, key=chave_de)[: min(int(q["limit"]), self.max_rows)]
        if self.entre_paginas and chave in q and not getattr(self, "_rodou", False):
            self._rodou = True
            self.entre_paginas(self)
        return 200, json.dumps(pagina).encode()


def _com_fato_id(linhas):
    return [l | {"fato_id": f"00000000-0000-0000-0000-{i:012d}"} for i, l in enumerate(linhas, 1)]


def _com_id(linhas):
    return [l | {"id": i, "tabela_origem": "joinads_metrics"} for i, l in enumerate(linhas, 1)]


def _leitor(servidor):
    return adaptadores.PostgrestSoLeitura("https://database.agenciavolc.com.br", "segredo-de-teste",
                                          transporte=servidor)


def test_postgrest_so_le_e_pagina_por_chave_alem_do_teto_do_servidor():
    c, r = carteira()
    srv = ServidorFalso(_com_fato_id(c), _com_id(r), max_rows=7, cambio={"USD/BRL": ("exata", 5.1)})
    leitor = _leitor(srv)
    custo_lido = leitor.custo_campanha_dia(CONTA, dias()[-1], HOJE)
    receita_lida = leitor.receita_vigente(dias()[-1], HOJE)
    # Teto de 7 linhas por resposta (< PAGINA): nada some, a leitura só termina na página vazia.
    assert len(custo_lido.linhas) == len(c) and len(receita_lida.linhas) == len(r)
    assert [l["fato_id"] for l in custo_lido.linhas] == sorted(l["fato_id"] for l in custo_lido.linhas)
    cambio_lido = leitor.cotacoes([("USD/BRL", dias()[0]), ("EUR/BRL", dias()[0])],
                                  receita_lida.lido_em, 7)
    assert [x["modo"] for x in cambio_lido.linhas] == ["exata", "sem_cotacao"]
    assert {(m, caminho) for m, caminho, _, _ in srv.pedidos} == {
        ("GET", "/rest/v1/google_ads_campanha_dia"), ("POST", "/rest/v1/rpc/receita_as_of"),
        ("POST", "/rest/v1/rpc/cambio_resolver")}
    assert not any("offset" in q for _, _, q, _ in srv.pedidos)
    rpc = [json.loads(b) for m, caminho, _, b in srv.pedidos if caminho.endswith("receita_as_of")]
    assert {x["p_conhecido_ate"] for x in rpc} == {receita_lida.lido_em}
    fx = [json.loads(b) for _, caminho, _, b in srv.pedidos if caminho.endswith("cambio_resolver")]
    assert {x["p_conhecido_ate"] for x in fx} == {receita_lida.lido_em}
    assert all(x["p_max_defasagem_dias"] == 7 for x in fx)
    custo_q = [q for _, caminho, q, _ in srv.pedidos if caminho.endswith("campanha_dia")][0]
    assert custo_q["customer_id"] == "eq.1112223334"
    with pytest.raises(PermissionError):
        leitor._uma("POST", "/rest/v1/google_ads_campanha_dia", {})
    with pytest.raises(PermissionError):
        leitor._uma("DELETE", "/rest/v1/google_ads_campanha_dia", {})
    with pytest.raises(PermissionError):
        leitor._uma("POST", "/rest/v1/rpc/receita_observar", {})


def test_versao_nova_entre_paginas_nao_some_nem_dobra():
    """A falha da paginação por offset: uma linha entra no meio da leitura e
    desloca as páginas. Por chave, a versão nova aparece no fim e a antiga cai."""
    c, r = carteira()
    receita_ids = _com_id(r)
    alvo = receita_ids[2]

    def nova_versao(srv):
        _, linhas = srv.tabelas["/rest/v1/rpc/receita_as_of"]
        linhas.append(alvo | {"id": 10_000, "receita": 0.31})

    srv = ServidorFalso(_com_fato_id(c), receita_ids, max_rows=5, entre_paginas=nova_versao)
    lida = _leitor(srv).receita_vigente(dias()[-1], HOJE)
    assert len(lida.linhas) == len(r)                          # nenhuma chave some nem dobra
    por_id = {l["id"]: l for l in lida.linhas}
    assert 10_000 in por_id and alvo["id"] not in por_id       # vale a versão mais nova
    assert "1 versão(ões) antiga(s)" in lida.fonte


def test_pagina_fora_de_ordem_ou_sem_chave_e_recusada():
    c, _ = carteira()
    linhas = _com_fato_id(c)
    srv = ServidorFalso(linhas, [], max_rows=5)
    srv.tabelas["/rest/v1/google_ads_campanha_dia"] = ("fato_id", linhas)

    def desordenado(metodo, url, cab, corpo):
        status, b = srv(metodo, url, cab, corpo)
        pagina = json.loads(b)
        if "fato_id=gt." in url and pagina:
            pagina[0] = linhas[0]          # volta para trás: o servidor não respeitou a ordem
        return status, json.dumps(pagina).encode()

    with pytest.raises(ContratoQuebrado, match="fora de ordem"):
        _leitor(desordenado).custo_campanha_dia(CONTA, dias()[-1], HOJE)
    sem_chave = [{k: v for k, v in l.items() if k != "fato_id"} for l in linhas[:3]]
    with pytest.raises(ContratoQuebrado, match="sem fato_id"):
        _leitor(lambda *a: (200, json.dumps(sem_chave).encode())).custo_campanha_dia(CONTA, dias()[-1], HOJE)


def test_cambio_resolver_com_resposta_fora_do_contrato_e_recusado():
    leitor = _leitor(lambda *a: (200, b"[]"))
    with pytest.raises(ContratoQuebrado, match="0 linhas"):
        leitor.cotacoes([("USD/BRL", dias()[0])], LIDO, 7)


def test_codigo_nao_importa_cliente_de_escrita():
    raiz = Path(aplicacao.__file__).parent
    for arq in raiz.glob("*.py"):
        texto = arq.read_text()
        for proibido in ("google.ads", "googleads", "mutate", "PATCH", "DELETE\"", "requests.post"):
            assert proibido not in texto, (arq.name, proibido)


def test_env_nao_e_lido_fora_do_cli():
    raiz = Path(aplicacao.__file__).parent
    for arq in raiz.glob("*.py"):
        if arq.name != "__main__.py":
            assert "os.environ" not in arq.read_text(), arq.name


# ── equivalência com a prova Senac ──────────────────────────────────────────

def test_motor_da_carteira_reproduz_a_prova_senac_com_o_mesmo_cambio():
    """Os snapshots reais da Senac, vestidos no contrato W11/W12 com o câmbio
    fixo 5,25 que a prova usou (como cotação `anterior`), dão os mesmos números
    e a mesma direção. Prova que generalizar não mudou a regra."""
    exp = Path(__file__).resolve().parents[1] / "experimentos" / "senac-shadow-20261015"
    custo_doc = json.loads((exp / "custo_ads_snapshot.json").read_text())
    receita_doc = json.loads((exp / "receita_joinads_snapshot.json").read_text())
    senac = json.loads((exp / "resultado.json").read_text())
    cid = senac["campanha"]
    custos = [CustoDia.da_linha(custo(cid, date.fromisoformat(l["date"]), l["cost_micros"], l["clicks"],
                                      valor_conv=l["conversions_value"])) for l in custo_doc["linhas"]]
    receitas = [ReceitaObservada.da_linha(
        receita(cid, date.fromisoformat(l["date"]), l["revenue_usd"], taxa=5.25)
        if l["revenue_usd"] is not None else
        receita(cid, date.fromisoformat(l["date"]), None, modo="sem_receita"))
        for l in receita_doc["linhas"]]
    av = dominio.avaliar(cid, custos, receitas, date.fromisoformat(senac["as_of"]))
    assert av.corte_maturidade.isoformat() == senac["corte_maturidade"]
    assert av.janela_madura == senac["janela_madura"]
    assert av.janela_madura_recente == senac["janela_madura_recente"]
    assert av.fracao_custo_maduro_sem_receita == senac["fracao_custo_maduro_sem_receita"]
    assert av.recomendacao.direcao == senac["recomendacao"]["direcao"] == "pausar"
    assert av.estado_dado == dominio.COMPLETO


# ── ciclo corretivo 1 (revisão adversarial de 2436b94) ──────────────────────

def test_receita_repetida_na_mesma_chave_recusa_em_vez_de_somar(tmp_path):
    """Duas versões do diário (ou página deslocada) não podem dobrar a receita."""
    c, r = carteira()
    r.append(dict(r[0]))
    with pytest.raises(ContratoQuebrado, match="receita repetida"):
        gerar(tmp_path, c, r)
    assert not tmp_path.exists() or arvore(tmp_path) == {}


def test_d1_falhando_em_dias_maduros_vira_sem_dado():
    # Só 2 dos 17 dias maduros têm D-1; o resto ficou com o D0 (janela aberta).
    c = [CustoDia.da_linha(custo(CAMP_BOA, d, 20_000_000, cliques=120, fechada=i in (3, 4),
                                 origem="D-1" if i in (3, 4) else "D0"))
         for i, d in enumerate(dias())]
    r = [ReceitaObservada.da_linha(receita(CAMP_BOA, d, 6.0)) for d in dias()]
    av = dominio.avaliar(CAMP_BOA, c, r, HOJE)
    assert av.estado_dado == dominio.SEM_DADO
    assert av.recomendacao.direcao == "evidencia_insuficiente"
    assert av.fracao_custo_maduro_sem_receita > 0.5


def test_custo_nao_lido_em_muitos_dias_maduros_vira_sem_dado():
    c = [CustoDia.da_linha(custo(CAMP_RUIM, d, None if i > 5 else 30_000_000, cliques=80))
         for i, d in enumerate(dias())]
    r = [ReceitaObservada.da_linha(receita(CAMP_RUIM, d, 0.3)) for d in dias()]
    av = dominio.avaliar(CAMP_RUIM, c, r, HOJE)
    assert av.estado_dado == dominio.SEM_DADO and "sem custo lido" in av.motivo_estado_dado


def test_clique_nao_lido_e_sem_dado_e_nao_amostra_insuficiente():
    c = [CustoDia.da_linha(custo(CAMP_RUIM, d, 30_000_000, cliques=None if i == 8 else 40))
         for i, d in enumerate(dias())]
    r = [ReceitaObservada.da_linha(receita(CAMP_RUIM, d, 0.3)) for d in dias()]
    av = dominio.avaliar(CAMP_RUIM, c, r, HOJE)
    assert av.estado_dado == dominio.SEM_DADO and "cliques" in av.motivo_estado_dado


def test_leitura_de_custo_vazia_recusa_sem_gravar_lote(tmp_path):
    with pytest.raises(aplicacao.LoteRecusado, match="vazia"):
        gerar(tmp_path, [], [])
    assert not tmp_path.exists() or arvore(tmp_path) == {}


def test_segunda_rodada_no_mesmo_dia_e_mais_recente_e_nao_colide(tmp_path):
    c, r = carteira()
    gerar(tmp_path, c, r)
    f = Fonte(c, r, lido="2026-10-15T15:00:00Z")
    saida = aplicacao.gerar_lote(CONTA, f, f, f, tmp_path, base_ref=BASE_REF, hoje=HOJE)
    assert len(saida["novos"]) == 4 and saida["repetidos"] == []
    assert all(n.endswith("20261015t150000z") for n in saida["novos"])
    assert len(list((tmp_path / "_lotes").glob("*.json"))) == 2


def test_lido_em_sem_fuso_quebra_o_contrato(tmp_path):
    c, r = carteira()
    f = Fonte(c, r, lido="2026-10-15T01:30:00")
    with pytest.raises(ContratoQuebrado, match="sem fuso"):
        aplicacao.gerar_lote(CONTA, f, f, f, tmp_path, base_ref=BASE_REF, hoje=HOJE)


@pytest.mark.parametrize("valor", ["NaN", "Infinity", float("nan"), True])
def test_numero_nao_finito_ou_booleano_quebra_o_contrato(valor):
    with pytest.raises(ContratoQuebrado):
        ReceitaObservada.da_linha(receita(CAMP_RUIM, dias()[0], 1.0) | {"receita": valor})


def test_chave_sem_o_componente_quebra_o_contrato():
    linha = receita(CAMP_RUIM, dias()[0], 1.0)
    del linha["chave"]["joinads_domain"]
    with pytest.raises(ContratoQuebrado, match="joinads_domain"):
        ReceitaObservada.da_linha(linha)


def test_reproducible_vem_do_replay_dos_bytes(tmp_path, monkeypatch):
    """Se o recálculo a partir do recorte gravado diverge, o manifesto não diz identical."""
    original = aplicacao.calcular
    chamadas = {"n": 0}

    def instavel(*a, **kw):
        chamadas["n"] += 1
        art = original(*a, **kw)
        if chamadas["n"] % 2 == 0:
            art = {**art, "transformacao.csv": art["transformacao.csv"] + b"\n"}
        return art

    monkeypatch.setattr(aplicacao, "calcular", instavel)
    saida = gerar(tmp_path)
    m = json.loads((tmp_path / saida["novos"][0] / "experimento.json").read_text())
    assert m["result"]["reproducible"] == "not_reproduced"
    assert m["decision"] != "adopt"


def test_transporte_real_transforma_http_e_redirecionamento_em_recusa():
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if "redir" in self.path:
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:1/roubo")
            else:
                self.send_response(404)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        assert adaptadores._transporte_urllib("GET", base + "/x", {}, None)[0] == 404
        assert adaptadores._transporte_urllib("GET", base + "/redir", {}, None)[0] == 302
    finally:
        srv.shutdown()
    leitor = adaptadores.PostgrestSoLeitura("https://database.agenciavolc.com.br", "k",
                                            transporte=lambda *a: (404, b""))
    with pytest.raises(ContratoQuebrado, match="HTTP 404"):
        leitor.receita_vigente(dias()[-1], HOJE)


# ── ciclo corretivo 2 (revisor de nuvem 2 sobre e8c795c) ────────────────────

def test_ptax_que_chega_depois_cura_o_dia_porque_o_cambio_e_da_leitura(tmp_path):
    """O W12 congela receita_brl na ingestão: um dia ingerido como `defasada`
    continua sem BRL para sempre no diário. O motor reconverte na leitura, então
    a rodada depois da PTAX reconcilia o dia, sem precisar de nova receita."""
    c, r = carteira()
    congelada = [x | {"moeda": "USD", "cambio_modo": "defasada", "cambio_taxa": None, "receita_brl": None,
                      "cambio_defasagem_dias": 40}
                 if x["chave"]["utm_campaign_value"] == CAMP_BOA else x for x in r]
    gerar(tmp_path / "antes", c, congelada, cambio={"USD/BRL": ("defasada", None), "EUR/BRL": ("defasada", None)})
    assert resultado(tmp_path / "antes", CAMP_BOA)["estado_dado"] == dominio.SEM_DADO
    gerar(tmp_path / "depois", c, congelada, cambio={"USD/BRL": ("exata", 5.0), "EUR/BRL": ("defasada", None)})
    boa = resultado(tmp_path / "depois", CAMP_BOA)
    assert boa["estado_dado"] == dominio.COMPLETO
    assert boa["janela_madura"]["receita_brl"] == pytest.approx(6.0 * 5.0 * boa["janela_madura"]["dias"])
    assert boa["recomendacao"]["direcao"] == "aumentar"


def test_taxa_gravada_na_ingestao_e_ignorada(tmp_path):
    c, r = carteira()
    # Ingestão gravou 5,4; a regra versionada, no corte da leitura, diz 5,0.
    gerar(tmp_path, c, r, cambio={"USD/BRL": ("exata", 5.0), "EUR/BRL": ("defasada", None)})
    pasta = tmp_path / f"gads-{CAMP_RUIM}-sombra-{SUF}"
    cab, *linhas = (pasta / "transformacao.csv").read_text().splitlines()
    col = dict(zip(cab.split(","), linhas[-1].split(",")))
    assert float(col["receita_brl"]) == pytest.approx(0.30 * 5.0) and col["cambio_modo"] == "exata"
    cambio = json.loads((pasta / "cambio_lido.json").read_text())
    assert {x["par"] for x in cambio["linhas"]} == {"USD/BRL"} and len(cambio["linhas"]) == 20
    assert aplicacao.replay(pasta)["identico"] is True


def test_cambio_e_pedido_uma_vez_no_corte_da_receita(tmp_path):
    c, r = carteira()
    f = Fonte(c, r, lido="2026-10-15T12:00:00Z")
    aplicacao.gerar_lote(CONTA, f, f, f, tmp_path, base_ref=BASE_REF, hoje=HOJE)
    ((pedidos, conhecido_ate, maximo),) = f.pedidos_cambio
    assert conhecido_ate == "2026-10-15T12:00:00Z" and maximo == 7
    # Só os pares/dias das campanhas da conta; a receita do adset Meta não pede câmbio.
    assert {p for p, _ in pedidos} == {"USD/BRL", "EUR/BRL"} and len(pedidos) == 40


def test_cotacao_repetida_ou_fora_do_contrato_quebra():
    d = dias()[0]
    r = [ReceitaObservada.da_linha(receita(CAMP_RUIM, d, 1.0))]
    with pytest.raises(ContratoQuebrado, match="repetida"):
        dominio.cambio_na_leitura(r, [Cotacao.da_linha(cot("USD/BRL", d))] * 2)
    with pytest.raises(ContratoQuebrado, match="com taxa"):
        Cotacao.da_linha(cot("USD/BRL", d, "defasada") | {"taxa": 5.0})
    with pytest.raises(ContratoQuebrado, match="sem taxa"):
        Cotacao.da_linha(cot("USD/BRL", d, "exata") | {"taxa": 0})
    with pytest.raises(ContratoQuebrado, match="modo"):
        Cotacao.da_linha(cot("USD/BRL", d) | {"modo": "constante"})


def test_dia_sem_resposta_de_cambio_e_sem_cotacao_nunca_taxa_padrao():
    d = dias()[0]
    (r,) = dominio.cambio_na_leitura([ReceitaObservada.da_linha(receita(CAMP_RUIM, d, 1.0))], [])
    assert r.cambio_modo == "sem_cotacao" and r.receita_brl is None and r.cambio_taxa is None


@pytest.mark.parametrize("campo,valor", [("custo_micros", -1), ("cliques", -3)])
def test_custo_negativo_quebra_o_contrato(campo, valor):
    with pytest.raises(ContratoQuebrado, match="negativ"):
        CustoDia.da_linha(custo(CAMP_RUIM, dias()[0], 1) | {campo: valor})


def test_receita_negativa_quebra_o_contrato():
    with pytest.raises(ContratoQuebrado, match="negativ"):
        ReceitaObservada.da_linha(receita(CAMP_RUIM, dias()[0], -1.0))


def test_linha_estranha_de_outra_campanha_nao_derruba_a_conta(tmp_path):
    c, r = carteira()
    estranha = receita("123456789012", dias()[0], 1.0)
    del estranha["cambio_modo"]
    assert len(gerar(tmp_path, c, r + [estranha])["novos"]) == 4
    # A mesma estranheza na campanha da conta quebra, como antes.
    estranha["chave"]["utm_campaign_value"] = CAMP_RUIM
    with pytest.raises(ContratoQuebrado, match="cambio_modo"):
        gerar(tmp_path / "outra", c, r + [estranha])


def test_senac_ponta_a_ponta_pelo_lote_disco_e_replay(tmp_path):
    """A mesma equivalência, agora pelo caminho de produção: gerar_lote com
    câmbio resolvido na leitura (5,25 `anterior`), gravado em disco, relido
    pela pasta e reproduzido pelo replay."""
    exp = Path(__file__).resolve().parents[1] / "experimentos" / "senac-shadow-20261015"
    custo_doc = json.loads((exp / "custo_ads_snapshot.json").read_text())
    receita_doc = json.loads((exp / "receita_joinads_snapshot.json").read_text())
    senac = json.loads((exp / "resultado.json").read_text())
    cid = senac["campanha"]
    c = [custo(cid, date.fromisoformat(l["date"]), l["cost_micros"], l["clicks"],
               valor_conv=l["conversions_value"]) for l in custo_doc["linhas"]]
    # O diário guarda a receita com o câmbio da ingestão (aqui, defasado): não pode importar.
    r = [receita(cid, date.fromisoformat(l["date"]), l["revenue_usd"], modo="defasada")
         if l["revenue_usd"] is not None else
         receita(cid, date.fromisoformat(l["date"]), None, modo="sem_receita")
         for l in receita_doc["linhas"]]
    as_of = date.fromisoformat(senac["as_of"])
    f = Fonte(c, r, lido=f"{as_of.isoformat()}T15:00:00Z", cambio={"USD/BRL": ("anterior", 5.25)})
    saida = aplicacao.gerar_lote(CONTA, f, f, f, tmp_path, base_ref=BASE_REF, hoje=as_of)
    (eid,) = saida["novos"]
    pasta = tmp_path / eid
    doc = json.loads((pasta / "resultado.json").read_text())
    assert doc["as_of_data"] == senac["as_of"]
    assert doc["corte_maturidade"] == senac["corte_maturidade"]
    assert doc["janela_madura"] == senac["janela_madura"]
    assert doc["janela_madura_recente"] == senac["janela_madura_recente"]
    assert doc["fracao_custo_maduro_sem_receita"] == senac["fracao_custo_maduro_sem_receita"]
    assert doc["recomendacao"]["direcao"] == senac["recomendacao"]["direcao"] == "pausar"
    assert validar(json.loads((pasta / "experimento.json").read_text()), pasta) == []
    assert aplicacao.replay(pasta)["identico"] is True
