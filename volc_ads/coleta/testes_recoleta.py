"""Recoleta da janela madura (W11): custo por campanha-dia relido por N dias.

Hermético: o Google é um dublê que responde à janela da GAQL a partir de uma
"verdade" sintética, e o banco é um dublê da RPC v12_04 que aplica a chave
(conta, campanha, data) e a precedência D0 < D-1 < backfill com desempate por
`colhida_em`. O dublê NÃO substitui a prova SQL da própria RPC (lab.sh,
suítes v12_04): ele mostra que o coletor manda o que a RPC precisa para que a
leitura mais nova vença sem duplicar linha.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from google.ads.googleads.v25.enums.types.advertising_channel_type import AdvertisingChannelTypeEnum
from google.ads.googleads.v25.enums.types.campaign_status import CampaignStatusEnum
from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

import volc_ads.coleta.__main__ as cli
from volc_ads.coleta import persistencia
from volc_ads.coleta.contrato import RECOLETA_DIAS_MAXIMO, janela_recoleta
from volc_ads.coleta.familias.testes_campanha_dia import violacoes_documento
from volc_ads.gads import client as gads_client

RAIZ = Path(__file__).resolve().parents[2]
CONTA, MCC = "5478096539", "4904074301"
SENAC, OUTRA = 24278665189, 23000000001


# ── a janela ────────────────────────────────────────────────────────────────

def teste_janela_sao_os_n_dias_fechados_antes_do_d1():
    assert janela_recoleta(date(2026, 10, 15), 7) == (date(2026, 10, 7), date(2026, 10, 13))
    assert janela_recoleta(date(2026, 10, 15), 1) == (date(2026, 10, 13), date(2026, 10, 13))
    # virada de mês e de ano
    assert janela_recoleta(date(2027, 1, 2), 3) == (date(2026, 12, 29), date(2026, 12, 31))


@pytest.mark.parametrize("dias", [0, -1, RECOLETA_DIAS_MAXIMO + 1, True, 7.0, "7"])
def teste_janela_recusa_dias_fora_do_contrato(dias):
    with pytest.raises(ValueError, match="recoleta exige"):
        janela_recoleta(date(2026, 10, 15), dias)


# ── dublês ──────────────────────────────────────────────────────────────────

def _row(campaign_id: int, dia: str, custo_micros: int, cliques: int) -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.customer.id = int(CONTA)
    r.campaign.id = campaign_id
    r.campaign.name = f"C{campaign_id}"
    r.campaign.status = CampaignStatusEnum.CampaignStatus.ENABLED
    r.campaign.advertising_channel_type = AdvertisingChannelTypeEnum.AdvertisingChannelType.SEARCH
    r.segments.date = dia
    r.metrics.cost_micros = custo_micros
    r.metrics.clicks = cliques
    r.metrics.impressions = cliques * 10
    return r


class GoogleDuble:
    """Responde só às datas da janela da GAQL — e registra cada consulta."""

    def __init__(self, verdade: dict[tuple[int, str], tuple[int, int]]):
        self.verdade = dict(verdade)
        self.consultas: list[tuple[str, str]] = []

    def __call__(self, customer_id, gaql, *, login_customer_id):
        assert login_customer_id == MCC
        self.consultas.append((customer_id, gaql))
        ini, fim = re.search(r"segments\.date BETWEEN '([\d-]+)' AND '([\d-]+)'", gaql).groups()
        return iter([_row(c, d, custo, cliques) for (c, d), (custo, cliques) in sorted(self.verdade.items())
                     if ini <= d <= fim])


class BancoDuble:
    """A parte da v12_04 que a recoleta exercita: chave, precedência e ledger."""

    PRECEDENCIA = {"D0": 1, "D-1": 2, "backfill": 3}

    def __init__(self, *a, **k):
        self.fatos: dict[tuple[str, str, str], dict] = {}
        self.ledger: list[dict] = []
        self.documentos: list[dict] = []

    def mapa_volc(self, customer_id):
        return {}

    def execucoes_do_passo(self, prefixo):
        return [l for l in self.ledger if l["execucao_chave"].startswith(prefixo + ":")]

    def __call__(self, rpc, doc):
        assert rpc == "volc_registrar_gads_campanha_dia"
        self.documentos.append(doc)
        aceitas = preteridas = 0
        prec = self.PRECEDENCIA[doc["origem_janela"]]
        for l in doc["linhas"]:
            chave = (l["customer_id"], l["campaign_id"], l["metric_date"])
            atual = self.fatos.get(chave)
            if atual is None or prec > atual["precedencia"] or (
                    prec == atual["precedencia"] and l["colhida_em"] > atual["colhida_em"]):
                self.fatos[chave] = {**l, "precedencia": prec, "origem_janela": doc["origem_janela"]}
                aceitas += 1
            else:
                preteridas += 1
        self.ledger.append({"execucao_chave": doc["execucao_chave"], "tipo_lote": doc["tipo_lote"],
                            "resultado": doc["resultado"]})
        projetou = bool(doc.get("projetar_compat"))
        return {"linhas_aceitas": aceitas, "linhas_preteridas": preteridas, "linhas_rejeitadas": 0,
                "resultado": doc["resultado"],
                "projecao_estado": "aplicada" if projetou else "nao_solicitada",
                "projecao_linhas": aceitas if projetou else 0}


def _relogio(monkeypatch, instante: datetime):
    class Fixo(datetime):
        @classmethod
        def now(cls, tz=None):
            return instante.astimezone(tz) if tz else instante.replace(tzinfo=None)

    monkeypatch.setattr(cli, "datetime", Fixo)


@pytest.fixture
def ambiente(monkeypatch):
    banco = BancoDuble()
    banco.contas_lidas = []
    monkeypatch.setattr(cli, "_conta",
                        lambda cid, mcc: banco.contas_lidas.append(cid) or ("America/Sao_Paulo", "BRL"))
    monkeypatch.setattr(persistencia, "RPC", lambda *a, **k: banco)

    def usar_google(verdade):
        g = GoogleDuble(verdade)
        monkeypatch.setattr(gads_client, "buscar", g)
        return g

    return banco, usar_google


# ── o CLI ───────────────────────────────────────────────────────────────────

def teste_recoleta_le_a_janela_madura_so_do_custo_e_grava_como_backfill(ambiente, monkeypatch, tmp_path):
    banco, usar_google = ambiente
    google = usar_google({(SENAC, "2026-10-08"): (40_000_000, 50),
                          (SENAC, "2026-10-13"): (59_660_000, 66),
                          (SENAC, "2026-10-14"): (1, 1)})       # D-1: fora da recoleta
    _relogio(monkeypatch, datetime(2026, 10, 15, 10, 20, tzinfo=timezone.utc))  # 07:20 em SP
    recibo = tmp_path / "r.json"

    saida = cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "6",
                      "--agenda", "rec", "--recibo", str(recibo)])

    assert saida == 0
    assert len(google.consultas) == 1, "só campanha_dia por padrão"
    assert "BETWEEN '2026-10-08' AND '2026-10-13'" in google.consultas[0][1]
    lote, fecho = banco.documentos
    assert violacoes_documento(lote) == []
    assert lote["origem_janela"] == "backfill" and lote["disparo"] == "agenda"
    assert (lote["janela_inicio"], lote["janela_fim"]) == ("2026-10-08", "2026-10-13")
    assert lote["execucao_chave"].startswith(
        f"gads_campanha_dia:{CONTA}:backfill:2026-10-08:2026-10-13:passorec:")
    assert fecho["tipo_lote"] == "fechamento" and fecho["resultado"] == "ok"
    # dias fechados não voltam à tabela legada (lá o spend dispara comissão)
    assert lote["projetar_compat"] is False and fecho["projecao_estado"] == "nao_solicitada"
    assert {l["metric_date"] for l in lote["linhas"]} == {"2026-10-08", "2026-10-13"}
    for l in lote["linhas"]:
        assert type(l["custo_micros"]) is int, "micros ficam inteiros"
        assert l["currency_code"] == "BRL" and l["colhida_em"] == "2026-10-15T10:20:00+00:00"
    r = json.loads(recibo.read_text())
    assert r["janela"] == ["2026-10-08", "2026-10-13"] and r["recoleta_dias"] == 6
    assert r["moeda"] == "BRL" and r["origem"] == "backfill" and r["saida"] == 0


def teste_dois_dias_de_recoleta_a_leitura_mais_nova_vence_sem_duplicar(ambiente, monkeypatch):
    """O caso que motiva a recoleta: o Google estorna cliques inválidos depois."""
    banco, usar_google = ambiente
    usar_google({(SENAC, "2026-10-12"): (59_660_000, 66), (OUTRA, "2026-10-12"): (10_000_000, 9),
                 (SENAC, "2026-10-13"): (30_000_000, 30)})
    _relogio(monkeypatch, datetime(2026, 10, 15, 10, 20, tzinfo=timezone.utc))
    assert cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "3", "--agenda", "rec"]) == 0

    # um dia depois: 12/10 da Senac foi ajustado para baixo; a janela andou
    usar_google({(SENAC, "2026-10-12"): (57_100_000, 63), (OUTRA, "2026-10-12"): (10_000_000, 9),
                 (SENAC, "2026-10-13"): (30_000_000, 30), (SENAC, "2026-10-14"): (20_000_000, 20)})
    _relogio(monkeypatch, datetime(2026, 10, 16, 10, 20, tzinfo=timezone.utc))
    assert cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "3", "--agenda", "rec"]) == 0

    assert sorted(banco.fatos) == [(CONTA, str(OUTRA), "2026-10-12"), (CONTA, str(SENAC), "2026-10-12"),
                                   (CONTA, str(SENAC), "2026-10-13"), (CONTA, str(SENAC), "2026-10-14")]
    ajustado = banco.fatos[(CONTA, str(SENAC), "2026-10-12")]
    assert ajustado["custo_micros"] == 57_100_000 and ajustado["cliques"] == 63
    assert ajustado["colhida_em"] == "2026-10-16T10:20:00+00:00"


def teste_backfill_da_recoleta_supera_o_d1_do_mesmo_dia(ambiente, monkeypatch):
    banco, usar_google = ambiente
    usar_google({(SENAC, "2026-10-13"): (59_660_000, 66)})
    _relogio(monkeypatch, datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc))
    assert cli.main(["--conta", CONTA, "--mcc", MCC, "--origem", "D-1", "--agenda", "06",
                     "--familias", "campanha_dia"]) == 0
    usar_google({(SENAC, "2026-10-13"): (57_100_000, 63)})
    _relogio(monkeypatch, datetime(2026, 10, 15, 10, 20, tzinfo=timezone.utc))
    assert cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "1", "--agenda", "rec",
                     "--familias", "campanha_dia"]) == 0
    fato = banco.fatos[(CONTA, str(SENAC), "2026-10-13")]
    assert (fato["origem_janela"], fato["custo_micros"]) == ("backfill", 57_100_000)
    # o D-1 continua projetando como antes; só a recoleta deixa de projetar
    d1, rec = banco.documentos[0], banco.documentos[2]
    assert (d1["origem_janela"], d1["projetar_compat"]) == ("D-1", True)
    assert (rec["origem_janela"], rec["projetar_compat"]) == ("backfill", False)


def teste_mesmo_passo_no_mesmo_dia_nao_rele_o_google(ambiente, monkeypatch):
    banco, usar_google = ambiente
    google = usar_google({(SENAC, "2026-10-13"): (59_660_000, 66)})
    _relogio(monkeypatch, datetime(2026, 10, 15, 10, 20, tzinfo=timezone.utc))
    argv = ["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "7", "--agenda", "rec"]
    assert cli.main(argv) == 0
    _relogio(monkeypatch, datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc))  # catch-up do timer
    assert cli.main(argv) == 0
    assert len(google.consultas) == 1 and len(banco.documentos) == 2


def teste_janela_vazia_ainda_registra_lote_e_fechamento(ambiente, monkeypatch):
    """"Li e veio zero" é fato; não ler é outro. A recoleta não some no silêncio."""
    banco, usar_google = ambiente
    usar_google({})
    _relogio(monkeypatch, datetime(2026, 10, 15, 10, 20, tzinfo=timezone.utc))
    assert cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "3", "--agenda", "rec"]) == 0
    lote, fecho = banco.documentos
    assert lote["linhas"] == [] and fecho["tipo_lote"] == "fechamento"


def teste_seco_nao_chama_a_rpc(ambiente, monkeypatch):
    banco, usar_google = ambiente
    usar_google({(SENAC, "2026-10-13"): (59_660_000, 66)})
    _relogio(monkeypatch, datetime(2026, 10, 15, 10, 20, tzinfo=timezone.utc))
    assert cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "3", "--seco"]) == 0
    assert banco.documentos == [] and banco.fatos == {}


@pytest.mark.parametrize("extra", [["--data", "2026-10-01"], ["--ate", "2026-10-02"],
                                   ["--origem", "D0"], ["--origem", "D-1"], ["--origem", "backfill"]])
def teste_recoleta_nao_aceita_janela_manual_nem_origem(extra, ambiente):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", "3", *extra])
    assert exc.value.code == 2


@pytest.mark.parametrize("dias", ["0", "-1", str(RECOLETA_DIAS_MAXIMO + 1)])
def teste_recoleta_com_dias_fora_do_contrato_sai_antes_de_falar_com_o_google(dias, ambiente):
    banco, usar_google = ambiente
    google = usar_google({})
    with pytest.raises(SystemExit) as exc:
        cli.main(["--conta", CONTA, "--mcc", MCC, "--recoleta-dias", dias])
    assert exc.value.code == 2
    assert banco.contas_lidas == [] and google.consultas == []


# ── o contrato de invocação (run.sh), com um python e um flock de mentira ──
#
# ⚠️ O run.sh roda no Hetzner (Linux, util-linux `flock`). O macOS não tem
# `flock`, e o teste não pode depender dele: um `skipif` deixaria a trava sem
# prova justamente onde o integrador roda a suíte. Então os testes montam um
# PATH "de Mac" (só bash, env, date, mkdir, rmdir, sleep, cat — sem flock) e põem
# na frente um flock DUBLÊ que implementa a semântica que o run.sh usa:
#   `flock -n 9`     tenta a vez uma vez; sem vez, sai 1
#   `flock -w S 9`   tenta por até S segundos; sem vez, sai 1
# A trava é um diretório (`mkdir` é atômico em qualquer SO) com o PID de quem a
# segurou; dono morto = trava livre, como o fd que o kernel fecha na saída.
# O dublê anota cada chamada, e os testes conferem os argumentos exatos.

RUN = RAIZ / "deploy" / "gads-coleta" / "run.sh"

FLOCK_DUBLE = """#!/usr/bin/env bash
echo "$*" >> "$VOLC_TESTE_FLOCK_LOG"
case "$1" in
  -n) espera=0; shift ;;
  -w) espera="$2"; shift 2 ;;
  *) echo "flock dublê: uso fora do contrato do run.sh: $*" >&2; exit 2 ;;
esac
[ "$1" = 9 ] && [ "$#" -eq 1 ] || { echo "flock dublê: esperava só o fd 9: $*" >&2; exit 2; }
trava="$VOLC_GADS_LOCK.trava"
limite=$(( $(date +%s) + espera ))
while :; do
  if mkdir "$trava" 2>/dev/null; then echo "$PPID" > "$trava/pid"; exit 0; fi
  dono="$(cat "$trava/pid" 2>/dev/null || true)"
  # Dono morto OU zumbi (terminou e ninguém fez wait: `kill -0` ainda responde)
  # libera a trava, como o kernel fecha o fd na saída do processo.
  estado="$(ps -o stat= -p "$dono" 2>/dev/null || true)"
  if [ -n "$dono" ] && { ! kill -0 "$dono" 2>/dev/null || [ "${estado#Z}" != "$estado" ] || [ "${estado# Z}" != "$estado" ]; }; then
    rm -rf "$trava"; continue
  fi
  [ "$(date +%s)" -lt "$limite" ] || exit 1
  sleep 0.1
done
"""

FERRAMENTAS_DO_MAC = ("bash", "env", "date", "mkdir", "rmdir", "rm", "sleep", "cat", "ps")

#: Teto por execução do run.sh. Uma regressão na trava (ex.: D-1 esperando em
#: vez de desistir) vira falha em segundos, não uma suíte pendurada no Mac.
TETO_DO_RUN_S = 60


def _path_de_mac(tmp_path: Path, *, com_duble: bool = True) -> str:
    """PATH sem `flock` real; com o dublê na frente quando pedido."""
    import shutil

    mac = tmp_path / "bin-mac"
    if not mac.exists():
        mac.mkdir(parents=True)
        for nome in FERRAMENTAS_DO_MAC:
            (mac / nome).symlink_to(shutil.which(nome))
    assert shutil.which("flock", path=str(mac)) is None
    if not com_duble:
        return str(mac)
    duble = tmp_path / "bin-duble"
    if not duble.exists():
        duble.mkdir()
        (duble / "flock").write_text(FLOCK_DUBLE)
        (duble / "flock").chmod(0o755)
    return f"{duble}{os.pathsep}{mac}"


def _rodar(tmp_path, modo, contas="5478096539,1112223334", falha="", *, com_duble=True, **env_extra):
    import shutil

    tmp_path.mkdir(parents=True, exist_ok=True)
    raiz = tmp_path / "opt"
    (raiz / "venv" / "bin").mkdir(parents=True, exist_ok=True)
    py = raiz / "venv" / "bin" / "python"
    py.write_text('#!/usr/bin/env bash\n'
                  'echo "$*" >> "$VOLC_TESTE_LOG"\n'
                  'case "$*" in *"--conta $VOLC_TESTE_FALHA "*) exit 1 ;; esac\n'
                  'exit 0\n')
    py.chmod(0o755)
    log = tmp_path / "chamadas.log"
    env = {"PATH": _path_de_mac(tmp_path, com_duble=com_duble), "VOLC_GADS_ROOT": str(raiz),
           "VOLC_GADS_LOCK": str(tmp_path / "lock"), "VOLC_GADS_RECIBOS": str(tmp_path / "recibos"),
           "VOLC_GADS_CONTAS": contas, "VOLC_GADS_MCC": MCC, "SERVICE_ROLE_KEY": "dublê-sem-valor",
           "VOLC_TESTE_LOG": str(log), "VOLC_TESTE_FALHA": falha or "nenhuma",
           "VOLC_TESTE_FLOCK_LOG": str(tmp_path / "flock.log"), **env_extra}
    p = subprocess.run([shutil.which("bash"), str(RUN), modo], env=env, capture_output=True,
                       text=True, timeout=TETO_DO_RUN_S)
    chamadas = log.read_text().splitlines() if log.exists() else []
    return p, chamadas


def _flock_chamado(tmp_path) -> list[str]:
    arq = tmp_path / "flock.log"
    return arq.read_text().splitlines() if arq.exists() else []


class _Dono:
    """Segura a trava do dublê como outro processo seguraria o fd: enquanto o
    processo vive, a vez é dele; morto, a trava fica livre."""

    def __init__(self, tmp_path, segundos):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(["sleep", str(segundos)])
        trava = tmp_path / "lock.trava"
        trava.mkdir()
        (trava / "pid").write_text(str(self.proc.pid))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.proc.kill()
        self.proc.wait()


def teste_o_path_de_mac_nao_tem_flock_e_sem_o_duble_o_run_sh_quebra(tmp_path):
    """Prova que a simulação é fiel: sem o dublê, é o erro que o Mac deu."""
    p, chamadas = _rodar(tmp_path, "d1", com_duble=False)
    assert p.returncode != 0 and chamadas == []
    assert "flock" in p.stderr


def teste_run_recoleta_chama_o_cli_por_conta_com_a_janela_e_o_passo(tmp_path):
    p, chamadas = _rodar(tmp_path, "recoleta")
    assert p.returncode == 0, p.stderr
    assert len(chamadas) == 2
    for conta, linha in zip(("5478096539", "1112223334"), chamadas):
        assert f"--conta {conta} --mcc {MCC} --recoleta-dias 7 --agenda rec --recibo " in linha
        assert linha.endswith(f"-recoleta-{conta}.json")


def teste_run_recoleta_respeita_dias_configurados_e_recusa_lixo(tmp_path):
    p, chamadas = _rodar(tmp_path, "recoleta", VOLC_GADS_RECOLETA_DIAS="30")
    assert p.returncode == 0 and all("--recoleta-dias 30 " in c for c in chamadas)
    for i, ruim in enumerate(("7;rm", "7d", " 7", "0", "91", "")):
        p, chamadas = _rodar(tmp_path / f"b{i}", "recoleta", VOLC_GADS_RECOLETA_DIAS=ruim)
        if ruim == "":  # vazio = padrão 7 (o `:-` do bash)
            assert p.returncode == 0
            continue
        assert p.returncode == 64 and chamadas == [], ruim


def teste_run_dias_torto_nao_derruba_d0_nem_d1(tmp_path):
    for modo in ("d0", "d1"):
        p, chamadas = _rodar(tmp_path / modo, modo, VOLC_GADS_RECOLETA_DIAS="7d")
        assert p.returncode == 0 and len(chamadas) == 2, (modo, p.stderr)


def teste_run_d0_usa_a_hora_de_sao_paulo_como_passo(tmp_path):
    antes = subprocess.run(["date", "+%H"], env={"TZ": "America/Sao_Paulo"},
                           capture_output=True, text=True).stdout.strip()
    p, chamadas = _rodar(tmp_path, "d0")
    depois = subprocess.run(["date", "+%H"], env={"TZ": "America/Sao_Paulo"},
                            capture_output=True, text=True).stdout.strip()
    assert p.returncode == 0 and len(chamadas) == 2
    passos = {re.search(r"--origem D0 --agenda (\d\d) ", c).group(1) for c in chamadas}
    assert passos <= {antes, depois}


@pytest.mark.parametrize("contas", [",", " , ", " "])
def teste_run_lista_de_contas_vazia_e_erro_de_configuracao(tmp_path, contas):
    p, chamadas = _rodar(tmp_path, "recoleta", contas=contas)
    assert p.returncode == 64 and chamadas == []


def teste_run_uma_conta_que_falha_nao_impede_as_outras(tmp_path):
    p, chamadas = _rodar(tmp_path, "recoleta", falha="5478096539")
    assert p.returncode == 1 and len(chamadas) == 2
    assert "conta 5478096539: coleta recoleta falhou" in p.stderr


def teste_run_d1_continua_com_o_passo_06_e_aceita_a_conta_unica_de_antes(tmp_path):
    p, chamadas = _rodar(tmp_path, "d1", contas="", VOLC_GADS_CONTA="5478096539")
    assert p.returncode == 0, p.stderr
    assert chamadas == [c for c in chamadas if "--origem D-1 --agenda 06 " in c] and len(chamadas) == 1


def teste_run_recusa_modo_desconhecido(tmp_path):
    p, chamadas = _rodar(tmp_path, "d7")
    assert p.returncode == 64 and chamadas == []


def teste_run_d1_pede_a_vez_sem_esperar_e_a_recoleta_espera(tmp_path):
    _rodar(tmp_path / "d1", "d1")
    _rodar(tmp_path / "d0", "d0")
    _rodar(tmp_path / "rec", "recoleta")
    _rodar(tmp_path / "rec5", "recoleta", VOLC_GADS_RECOLETA_ESPERA_S="5")
    assert _flock_chamado(tmp_path / "d1") == ["-n 9"]
    assert _flock_chamado(tmp_path / "d0") == ["-n 9"]
    assert _flock_chamado(tmp_path / "rec") == ["-w 1800 9"]
    assert _flock_chamado(tmp_path / "rec5") == ["-w 5 9"]


def teste_run_d1_concorrente_sai_75_sem_ler(tmp_path):
    with _Dono(tmp_path, 10):
        p, chamadas = _rodar(tmp_path, "d1")
    assert p.returncode == 75 and chamadas == [], p.stderr


def teste_run_recoleta_espera_a_vez_em_vez_de_desistir(tmp_path):
    import threading

    with _Dono(tmp_path, 30) as dono:
        # o dono termina (e é recolhido: zumbi ainda responde a `kill -0`) no meio da espera
        threading.Timer(1.0, lambda: (dono.proc.kill(), dono.proc.wait())).start()
        p, chamadas = _rodar(tmp_path, "recoleta", VOLC_GADS_RECOLETA_ESPERA_S="20")
    assert p.returncode == 0 and len(chamadas) == 2, p.stderr


def teste_run_recoleta_que_nao_pega_a_vez_falha_em_vez_de_sair_75(tmp_path):
    """75 é sucesso na unit (`SuccessExitStatus=75`): a recoleta perdida sumiria."""
    with _Dono(tmp_path, 10):
        p, chamadas = _rodar(tmp_path, "recoleta", VOLC_GADS_RECOLETA_ESPERA_S="1")
    assert p.returncode == 1 and chamadas == []
    assert "FALHOU" in p.stderr


def teste_dono_zumbi_nao_segura_a_trava(tmp_path):
    """Revisão R1: processo que terminou sem `wait()` ainda responde a `kill -0`.
    O flock real liberaria na saída; o dublê também precisa liberar."""
    import time

    tmp_path.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["sleep", "0.1"])
    trava = tmp_path / "lock.trava"
    trava.mkdir()
    (trava / "pid").write_text(str(proc.pid))
    time.sleep(0.5)                       # terminou, não recolhido: zumbi
    try:
        os.kill(proc.pid, 0)              # pré-condição: kill -0 "vê" o zumbi
        inicio = time.monotonic()
        p, chamadas = _rodar(tmp_path, "d1")
        assert p.returncode == 0 and len(chamadas) == 2, p.stderr
        assert time.monotonic() - inicio < 10
    finally:
        proc.wait()


def teste_trava_e_liberada_quando_o_run_sh_termina(tmp_path):
    """Duas passadas seguidas do mesmo modo: a segunda pega a vez (o kernel
    fecharia o fd; no dublê, o dono morto libera)."""
    p1, c1 = _rodar(tmp_path, "d1")
    p2, c2 = _rodar(tmp_path, "d1")
    assert (p1.returncode, p2.returncode) == (0, 0) and (len(c1), len(c2)) == (2, 4)


@pytest.mark.skipif(__import__("shutil").which("flock") is None,
                    reason="sem flock do SO (macOS): a semântica fica provada pelo dublê acima")
def teste_com_o_flock_real_d1_concorrente_sai_75(tmp_path):
    """Revisão R3: no Linux (onde o run.sh roda de verdade) a prova também vale
    contra o util-linux `flock`, não só contra a sintaxe do dublê."""
    import shutil
    import time

    tmp_path.mkdir(parents=True, exist_ok=True)
    lock = tmp_path / "lock"
    segura = subprocess.Popen(["flock", "-x", str(lock), "sleep", "10"])
    time.sleep(0.3)
    try:
        raiz = tmp_path / "opt"
        (raiz / "venv" / "bin").mkdir(parents=True)
        py = raiz / "venv" / "bin" / "python"
        py.write_text("#!/usr/bin/env bash\necho chamado >> \"$VOLC_TESTE_LOG\"\n")
        py.chmod(0o755)
        log = tmp_path / "chamadas.log"
        env = {"PATH": os.environ["PATH"], "VOLC_GADS_ROOT": str(raiz), "VOLC_GADS_LOCK": str(lock),
               "VOLC_GADS_RECIBOS": str(tmp_path / "recibos"), "VOLC_GADS_CONTAS": CONTA,
               "VOLC_GADS_MCC": MCC, "SERVICE_ROLE_KEY": "dublê-sem-valor", "VOLC_TESTE_LOG": str(log)}
        p = subprocess.run([shutil.which("bash"), str(RUN), "d1"], env=env, capture_output=True,
                           text=True, timeout=TETO_DO_RUN_S)
        assert p.returncode == 75 and not log.exists(), p.stderr
        p = subprocess.run([shutil.which("bash"), str(RUN), "recoleta"], env={**env,
                           "VOLC_GADS_RECOLETA_ESPERA_S": "1"}, capture_output=True, text=True,
                           timeout=TETO_DO_RUN_S)
        assert p.returncode == 1 and not log.exists(), p.stderr
    finally:
        segura.kill()
        segura.wait()


def teste_timer_da_recoleta_aponta_a_instancia_e_roda_depois_do_d1():
    timer = (RAIZ / "deploy/gads-coleta/volc-gads-coleta-recoleta.timer").read_text()
    d1 = (RAIZ / "deploy/gads-coleta/volc-gads-coleta-d1.timer").read_text()
    assert "Unit=volc-gads-coleta@recoleta.service" in timer
    hora = lambda t: re.search(r"OnCalendar=\*-\*-\* (\d\d:\d\d)", t).group(1)  # noqa: E731
    assert hora(timer) > hora(d1)
