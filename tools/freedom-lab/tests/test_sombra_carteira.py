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
from volc_lab.sombra_carteira.portas import ContratoQuebrado, CustoDia, Leitura, ReceitaObservada

CONTA = "1112223334"
HOJE = date(2026, 10, 15)
LIDO = "2026-10-15T12:00:00Z"
BASE_REF = "a8059ba0"
CAMP_RUIM, CAMP_BOA, CAMP_SEM_CAMBIO, CAMP_POUCA = "900000000001", "900000000002", "900000000003", "900000000004"


def custo(cid, d, micros, cliques=40, *, conta=CONTA, segmentos=None, fechada=True, moeda="BRL",
          valor_conv=10.0, origem="D-1", nome=None, status="ENABLED"):
    return {"customer_id": conta, "campaign_id": cid, "metric_date": d.isoformat(),
            "segmentos": segmentos or {}, "custo_micros": micros, "cliques": cliques,
            "currency_code": moeda, "janela_fechada": fechada, "campaign_name": nome or f"camp {cid[-1]}",
            "campaign_status": status, "valor_conversoes": valor_conv, "colhida_em": LIDO,
            "origem_janela": origem}


def receita(cid, d, usd, *, brl=None, modo="anterior", fonte="joinads", dominio_="a.com.br", taxa=5.4):
    chave = {"date": d.isoformat(), "utm_campaign_value": cid}
    chave["joinads_domain" if fonte == "joinads" else "gam_accounts_id"] = dominio_
    if brl is None and modo in ("exata", "anterior") and usd is not None:
        brl = round(usd * taxa, 4)
    return {"fonte": fonte, "chave": chave, "data_referencia": d.isoformat(), "moeda": "USD",
            "receita": usd, "receita_brl": brl, "cambio_modo": modo,
            "cambio_taxa": taxa if modo in ("exata", "anterior") else None,
            "cambio_defasagem_dias": 1 if modo == "anterior" else (40 if modo == "defasada" else None),
            "coletado_em": LIDO, "removida": False}


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
        # Sem câmbio: receita existe em USD, câmbio defasado (W12 devolve brl nulo).
        c.append(custo(CAMP_SEM_CAMBIO, d, 10_000_000))
        r.append(receita(CAMP_SEM_CAMBIO, d, 5.0, modo="defasada"))
        # Pouca amostra: 2 cliques/dia.
        c.append(custo(CAMP_POUCA, d, 5_000_000, cliques=2))
        r.append(receita(CAMP_POUCA, d, 0.5))
        # Linha segmentada (por dispositivo): não é total e não pode somar.
        c.append(custo(CAMP_RUIM, d, 999_000_000, segmentos={"device": "MOBILE"}))
    # Receita de campanha de outra rede (adset Meta, por exemplo): fica fora.
    r.append(receita("123456789012", dias()[0], 50.0))
    return c, r


class Fonte:
    def __init__(self, c, r, lido=LIDO):
        self.c, self.r, self.lido = c, r, lido

    def custo_campanha_dia(self, conta, inicio, fim):
        return Leitura(tuple(self.c), self.lido, "teste: google_ads_campanha_dia sintético")

    def receita_vigente(self, inicio, fim):
        return Leitura(tuple(self.r), self.lido, "teste: receita_as_of sintética")


def gerar(destino, c=None, r=None, **kw):
    if c is None:
        c, r = carteira()
    f = Fonte(c, r)
    return aplicacao.gerar_lote(CONTA, f, f, destino, base_ref=BASE_REF, hoje=HOJE, **kw)


def resultado(destino, cid, as_of="20261015"):
    return json.loads((destino / f"gads-{cid}-sombra-{as_of}" / "resultado.json").read_text())


def arvore(raiz: Path) -> dict[str, bytes]:
    return {str(p.relative_to(raiz)): p.read_bytes() for p in sorted(raiz.rglob("*")) if p.is_file()}


# ── um experimento por campanha, no formato que a tela do W7 já lê ──────────

def test_um_experimento_valido_por_campanha(tmp_path):
    saida = gerar(tmp_path)
    assert saida["resumo"]["campanhas"] == 4
    assert sorted(saida["novos"]) == sorted(f"gads-{c}-sombra-20261015"
                                             for c in (CAMP_RUIM, CAMP_BOA, CAMP_SEM_CAMBIO, CAMP_POUCA))
    for eid in saida["novos"]:
        pasta = tmp_path / eid
        manifesto = json.loads((pasta / "experimento.json").read_text())
        assert validar(manifesto, pasta) == [], eid
        assert manifesto["method"]["external_calls"] == {"mode": "none", "count": 0}
        assert manifesto["result"]["reproducible"] == "identical"
        assert {a["path"] for a in manifesto["artifacts"]} >= {"resultado.json", "transformacao.csv"}


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
    csv = (tmp_path / f"gads-{CAMP_SEM_CAMBIO}-sombra-20261015" / "transformacao.csv").read_text().splitlines()
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


def test_janela_aberta_e_dias_recentes_nao_decidem(tmp_path):
    c, r = carteira()
    c = [x | {"janela_fechada": False} if x["metric_date"] == dias()[10].isoformat() else x for x in c]
    # Receita gigante nos 3 dias imaturos não muda nada.
    r = [x | {"receita": 1e6, "receita_brl": 5.4e6}
         if x["data_referencia"] >= dias()[2].isoformat() and x["cambio_modo"] == "anterior" else x
         for x in r]
    gerar(tmp_path, c, r)
    ruim = resultado(tmp_path, CAMP_RUIM)
    assert ruim["recomendacao"]["direcao"] == "pausar"
    linha = [l for l in (tmp_path / f"gads-{CAMP_RUIM}-sombra-20261015" / "transformacao.csv").read_text().splitlines()
             if l.startswith(dias()[10].isoformat())][0]
    assert linha.endswith("false,janela_aberta")


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
    texto = json.dumps(r)
    assert "daily_campaign_metrics" not in texto
    csv = (tmp_path / f"gads-{CAMP_RUIM}-sombra-20261015" / "transformacao.csv").read_text()
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


def test_outro_experimento_da_campanha_no_mesmo_as_of_recusa(tmp_path):
    intruso = tmp_path / "senac-shadow-20261015"
    intruso.mkdir(parents=True)
    (intruso / "resultado.json").write_text(json.dumps({"campanha": CAMP_RUIM, "as_of": "2026-10-15"}))
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
        l["receita_brl"] = (l["receita_brl"] or 0) * 3
    (pasta / "receita_observada.json").write_text(json.dumps(entrada))
    assert aplicacao.replay(pasta)["identico"] is False


def test_cli_gera_e_recusa_com_codigos(tmp_path):
    c, r = carteira()
    (tmp_path / "custo.json").write_text(json.dumps({"lido_em": LIDO, "linhas": c}))
    (tmp_path / "receita.json").write_text(json.dumps({"lido_em": LIDO, "linhas": r}))
    args = ["gerar", "--conta", "111-222-3334", "--custo", str(tmp_path / "custo.json"),
            "--receita", str(tmp_path / "receita.json"), "--destino", str(tmp_path / "exp"),
            "--base-ref", BASE_REF]
    assert cli(args) == 0
    pasta = next(p for p in (tmp_path / "exp").iterdir() if p.name.startswith("gads-"))
    assert cli(["replay", str(pasta)]) == 0
    r[0]["receita"] = 77.0
    r[0]["receita_brl"] = 415.8
    (tmp_path / "receita.json").write_text(json.dumps({"lido_em": LIDO, "linhas": r}))
    assert cli(args) == 2


# ── porta PostgREST: só leitura, só a autoridade operacional ────────────────

def test_postgrest_recusa_supabase_fora_da_autoridade():
    with pytest.raises(ValueError, match="autoridade"):
        adaptadores.PostgrestSoLeitura("https://abc.supabase.co", "x")
    with pytest.raises(ValueError, match="service_role"):
        adaptadores.PostgrestSoLeitura("https://database.agenciavolc.com.br", "")


def test_postgrest_so_le_e_pagina():
    pedidos = []

    def transporte(metodo, url, cab, corpo):
        pedidos.append((metodo, url, corpo))
        if "google_ads_campanha_dia" in url:
            n = adaptadores.PAGINA if "offset=0" in url else 3
            return 200, json.dumps([custo(CAMP_RUIM, dias()[0], 1)] * n).encode()
        return 200, json.dumps([receita(CAMP_RUIM, dias()[0], 1.0)]).encode()

    leitor = adaptadores.PostgrestSoLeitura("https://database.agenciavolc.com.br", "segredo-de-teste",
                                            transporte=transporte)
    custo_lido = leitor.custo_campanha_dia(CONTA, dias()[-1], HOJE)
    receita_lida = leitor.receita_vigente(dias()[-1], HOJE)
    assert len(custo_lido.linhas) == adaptadores.PAGINA + 3
    assert len(receita_lida.linhas) == 1
    assert {(m, u.split("?")[0].split(".br")[1]) for m, u, _ in pedidos} == {
        ("GET", "/rest/v1/google_ads_campanha_dia"), ("POST", "/rest/v1/rpc/receita_as_of")}
    corpo_rpc = json.loads([c for m, _, c in pedidos if m == "POST"][0])
    assert corpo_rpc["p_conhecido_ate"] == receita_lida.lido_em
    assert "customer_id=eq.1112223334" in pedidos[0][1]
    with pytest.raises(PermissionError):
        leitor._pedir("POST", "/rest/v1/google_ads_campanha_dia", {})
    with pytest.raises(PermissionError):
        leitor._pedir("DELETE", "/rest/v1/google_ads_campanha_dia", {})


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
