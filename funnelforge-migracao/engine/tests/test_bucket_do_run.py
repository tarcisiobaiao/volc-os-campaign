"""Bucket do run: um download por documento, cache com validade, cópia que fica."""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from funnelforge.adapters.bucket import BucketDoRun, id_do_documento
from funnelforge.adapters.pesquisa_plano import trecho_pertinente

URL = "https://www.gov.br/aneel/tarifa-social"
TEXTO = ("A Tarifa Social de Energia Elétrica é um benefício federal. "
         "Desde 5 de julho de 2025, o desconto é integral nos primeiros 80 kWh do mês "
         "para as famílias inscritas no CadÚnico que atendem às regras. "
         "O consumo acima desse limite segue a tarifa normal. Outras informações gerais.")


class Leitor:
    def __init__(self, ok=True, espera=0.0):
        self.chamadas, self.ok, self.espera = [], ok, espera
        self.trava = threading.Lock()

    def __call__(self, url):
        with self.trava:
            self.chamadas.append(url)
        time.sleep(self.espera)
        if not self.ok:
            return {"ok": False, "motivo": "página respondeu HTTP 503"}
        return {"ok": True, "status": 200, "sha256": "abc", "titulo": "Tarifa Social",
                "texto": TEXTO, "url_final": URL + "/"}


def test_mesma_url_em_paralelo_baixa_uma_vez(tmp_path):
    leitor = Leitor(espera=0.05)
    bucket = BucketDoRun(cache=tmp_path / "cache", ler=leitor)
    resultados = []
    threads = [threading.Thread(target=lambda: resultados.append(bucket.documento(URL)))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(leitor.chamadas) == 1 and len(resultados) == 8
    assert all(r["texto"] == TEXTO for r in resultados)
    recibo = bucket.recibo()
    assert recibo["idas_a_rede"]["documento"] == 1
    assert recibo["repeticoes_evitadas"]["documento"] == 7
    assert bucket.ler_pagina(URL) == (TEXTO, "")


def test_cache_compartilhado_vale_ate_expirar_e_a_copia_do_run_fica(tmp_path):
    agora = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    primeiro = Leitor()
    BucketDoRun(cache=tmp_path / "cache", ler=primeiro, agora=lambda: agora).documento(URL)
    run = BucketDoRun(cache=tmp_path / "cache", ler=Leitor(),
                      agora=lambda: agora + timedelta(hours=2))
    doc = run.documento(URL)
    assert doc["origem"] == "cache_compartilhado" and doc["coletado_em"].startswith("2026-10-10T12")
    run.gravar(tmp_path / "run")
    copia = tmp_path / "run" / "bucket" / "documentos" / f"{id_do_documento(URL)}.json"
    for f in (tmp_path / "cache").iterdir():           # o cache expira ou é limpo
        f.unlink()
    assert json.loads(copia.read_text())["texto"] == TEXTO
    recibo = json.loads((tmp_path / "run" / "bucket" / "recibo_de_rede.json").read_text())
    assert recibo["por_operacao"]["documento"] == {"cache_compartilhado": 1}
    vencido = Leitor()
    BucketDoRun(cache=tmp_path / "cache", ler=vencido,
                agora=lambda: agora + timedelta(days=3)).documento(URL)
    assert len(vencido.chamadas) == 1


def test_falha_de_leitura_nao_entra_no_cache_compartilhado(tmp_path):
    BucketDoRun(cache=tmp_path / "cache", ler=Leitor(ok=False)).documento(URL)
    assert not (tmp_path / "cache").exists() or not list((tmp_path / "cache").iterdir())
    bucket = BucketDoRun(cache=tmp_path / "cache", ler=Leitor(ok=False))
    assert bucket.ler_pagina(URL) == ("", "página respondeu HTTP 503")


def test_sonda_e_links_da_raiz_uma_vez_por_run(tmp_path):
    bucket = BucketDoRun(cache=None, ler=Leitor())
    chamadas = []
    for _ in range(5):
        assert bucket.memo("sonda_de_anuncio", URL + "/", lambda: chamadas.append(1) or False) \
            is False
    assert chamadas == [1]
    assert bucket.recibo()["por_operacao"]["sonda_de_anuncio"] == {"rede": 1, "memoria": 4}


def test_trecho_pertinente_traz_o_pedaco_da_fonte_ou_nada():
    trecho = trecho_pertinente(TEXTO, "Desconto integral nos primeiros 80 kWh do mês", "80")
    assert "80 kWh" in trecho and len(trecho) <= 360
    assert trecho_pertinente(TEXTO, "Prazo para pedir revisão do cadastro escolar", "") == ""
