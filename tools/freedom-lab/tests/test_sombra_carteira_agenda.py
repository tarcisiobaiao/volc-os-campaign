"""A agenda da sombra (W13) nasce desligada e falha alto. Hermético: um python
falso no lugar do venv registra a invocação; nada fala com o Supabase."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
RUN = REPO / "deploy" / "sombra-carteira" / "run.sh"
UNIDADES = REPO / "deploy" / "sombra-carteira"


@pytest.fixture()
def raiz(tmp_path):
    (tmp_path / "current").mkdir()
    (tmp_path / "current" / ".base_ref").write_text("a8059ba0\n")
    bin_ = tmp_path / "venv" / "bin"
    bin_.mkdir(parents=True)
    falso = bin_ / "python"
    falso.write_text('#!/usr/bin/env bash\necho "$@" >> "$VOLC_TESTE_REGISTRO"\n'
                     'case "$*" in *9999999999*) exit 3;; esac\nexit 0\n')
    falso.chmod(0o755)
    return tmp_path


def rodar(raiz, **env):
    base = {"PATH": os.environ["PATH"], "VOLC_SOMBRA_RAIZ": str(raiz),
            "VOLC_SOMBRA_LOCK": str(raiz / "lock"), "VOLC_SOMBRA_DESTINO": str(raiz / "exp"),
            "VOLC_TESTE_REGISTRO": str(raiz / "chamadas"), "SERVICE_ROLE_KEY": "x",
            # O contêiner de teste roda como root; a unit nunca define isto.
            "VOLC_SOMBRA_TESTE_PERMITE_ROOT": "1" if os.geteuid() == 0 else ""}
    p = subprocess.run(["bash", str(RUN)], env={**base, **env}, capture_output=True, text=True)
    chamadas = (raiz / "chamadas").read_text().splitlines() if (raiz / "chamadas").exists() else []
    return p.returncode, p.stderr, chamadas


def test_desligada_por_padrao_nao_le_nada(raiz):
    codigo, err, chamadas = rodar(raiz, VOLC_SOMBRA_CONTAS="1112223334")
    assert codigo == 65 and chamadas == [] and "desligada" in err


def test_ligada_roda_cada_conta_so_leitura(raiz):
    codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim",
                                VOLC_SOMBRA_CONTAS="1112223334 5556667778",
                                VOLC_SOMBRA_JANELA_DIAS="28")
    assert codigo == 0 and len(chamadas) == 2
    for c in chamadas:
        assert c.startswith("-m volc_lab.sombra_carteira gerar --conta ")
        assert "--postgrest" in c and "--base-ref a8059ba0" in c and "--janela-dias 28" in c


def test_conta_que_falha_nao_para_as_outras_mas_sai_1(raiz):
    codigo, err, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim",
                                  VOLC_SOMBRA_CONTAS="9999999999 1112223334")
    assert codigo == 1 and len(chamadas) == 2
    assert "999****999" in err and "9999999999" not in err


@pytest.mark.parametrize("env", [
    {"VOLC_SOMBRA_CONTAS": " "},
    {"VOLC_SOMBRA_CONTAS": "1112223334", "VOLC_SOMBRA_MAX_CUSTO_SEM_RECEITA": "0,1"},
])
def test_configuracao_invalida_sai_64_sem_ler(raiz, env):
    codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", **env)
    assert codigo == 64 and chamadas == []


def test_sem_base_ref_sai_64(raiz):
    (raiz / "current" / ".base_ref").unlink()
    codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", VOLC_SOMBRA_CONTAS="1112223334")
    assert codigo == 64 and chamadas == []


def test_execucao_concorrente_sai_75(raiz):
    with open(raiz / "lock", "w") as trava:
        import fcntl
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", VOLC_SOMBRA_CONTAS="1112223334")
    assert codigo == 75 and chamadas == []


def test_unidades_coerentes_e_exemplo_desligado():
    servico = (UNIDADES / "volc-sombra-carteira.service").read_text()
    timer = (UNIDADES / "volc-sombra-carteira.timer").read_text()
    assert "SuccessExitStatus=65 75" in servico   # desligada e concorrente não viram falha
    assert "Unit=volc-sombra-carteira.service" in timer
    assert "VOLC_SOMBRA_HABILITADA=nao" in (UNIDADES / "sombra.env.exemplo").read_text()
    assert "SERVICE_ROLE" not in (UNIDADES / "sombra.env.exemplo").read_text().split("# Sem segredo")[0]


# ── blindagem da unit (ressalva do revisor de nuvem 2 sobre 30e6da3) ────────

def _diretivas(caminho: Path) -> dict[str, list[str]]:
    """Diretivas da unit (só [Service]), cada chave com todos os seus valores."""
    secao, saida = None, {}
    for linha in caminho.read_text().splitlines():
        linha = linha.strip()
        if not linha or linha.startswith(("#", ";")):
            continue
        if linha.startswith("["):
            secao = linha
            continue
        if secao == "[Service]":
            k, _, v = linha.partition("=")
            saida.setdefault(k.strip(), []).append(v.strip())
    return saida


SERVICO = UNIDADES / "volc-sombra-carteira.service"


def test_unit_nao_roda_como_root():
    d = _diretivas(SERVICO)
    assert d["User"] == ["volc-sombra"] and d["Group"] == ["volc-sombra"]
    assert "DynamicUser" not in d
    assert d["CapabilityBoundingSet"] == [""] and d["AmbientCapabilities"] == [""]
    assert "VOLC_SOMBRA_TESTE_PERMITE_ROOT" not in SERVICO.read_text()


def test_unit_carrega_so_o_segredo_e_a_configuracao_nunca_o_env_do_supabase():
    d = _diretivas(SERVICO)
    assert d["EnvironmentFile"] == ["/etc/volc-sombra-carteira/segredo.env",
                                    "/opt/volc-sombra-carteira/sombra.env"]
    assert "/root/" not in "".join(d["EnvironmentFile"])
    segredo = [l for l in (UNIDADES / "segredo.env.exemplo").read_text().splitlines()
               if l.strip() and not l.startswith("#")]
    assert segredo == ["SERVICE_ROLE_KEY="]
    config = [l.split("=")[0] for l in (UNIDADES / "sombra.env.exemplo").read_text().splitlines()
              if l.strip() and not l.startswith("#")]
    assert config and all(k.startswith("VOLC_SOMBRA_") for k in config)
    assert "VOLC_SOMBRA_TESTE_PERMITE_ROOT" not in config


def test_unit_tem_o_hardening_basico():
    d = _diretivas(SERVICO)
    esperado = {
        "NoNewPrivileges": "true", "PrivateTmp": "true", "PrivateDevices": "true",
        "ProtectSystem": "strict", "ProtectHome": "true", "ProtectKernelTunables": "true",
        "ProtectKernelModules": "true", "ProtectKernelLogs": "true", "ProtectControlGroups": "true",
        "ProtectClock": "true", "ProtectHostname": "true", "RestrictSUIDSGID": "true",
        "RestrictRealtime": "true", "RestrictNamespaces": "true", "LockPersonality": "true",
        "SystemCallArchitectures": "native", "UMask": "0027",
        "RestrictAddressFamilies": "AF_INET AF_INET6 AF_UNIX",
    }
    for k, v in esperado.items():
        assert d.get(k) == [v], k
    assert "@system-service" in d["SystemCallFilter"]
    # Única escrita: o StateDirectory (destino) e o RuntimeDirectory (trava).
    assert "ReadWritePaths" not in d
    assert d["StateDirectory"] == ["volc-sombra-carteira"]
    assert d["RuntimeDirectory"] == ["volc-sombra-carteira"]
    assert "VOLC_SOMBRA_DESTINO=/var/lib/volc-sombra-carteira/experimentos" in d["Environment"]
    assert "VOLC_SOMBRA_LOCK=/run/volc-sombra-carteira/lock" in d["Environment"]


def test_unit_passa_no_systemd_analyze_quando_disponivel(tmp_path):
    import shutil
    if not shutil.which("systemd-analyze"):
        pytest.skip("systemd-analyze ausente")
    p = subprocess.run(["systemd-analyze", "security", "--offline=true", "--no-pager",
                        str(SERVICO)], capture_output=True, text=True)
    if "Unknown option" in p.stderr or "unrecognized option" in p.stderr:
        pytest.skip("systemd-analyze sem --offline")
    import re
    nivel = re.search(r"Overall exposure level for \S+: ([0-9.]+)", p.stdout)
    assert nivel, p.stdout[-400:] + p.stderr[-400:]
    # A unit com root e o .env inteiro (30e6da3) dava 8,7 EXPOSED; esta dá 1,3.
    assert float(nivel.group(1)) <= 2.0, p.stdout[-600:]


def test_run_sh_recusa_root_sem_o_escape_de_teste(raiz):
    if os.geteuid() != 0:
        pytest.skip("só demonstrável rodando como root")
    codigo, err, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", VOLC_SOMBRA_CONTAS="1112223334",
                                  VOLC_SOMBRA_TESTE_PERMITE_ROOT="")
    assert codigo == 64 and chamadas == [] and "root" in err


@pytest.mark.parametrize("vazado", ["JWT_SECRET", "POSTGRES_PASSWORD", "DASHBOARD_PASSWORD", "ANON_KEY"])
def test_run_sh_recusa_o_env_inteiro_do_supabase(raiz, vazado):
    codigo, err, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", VOLC_SOMBRA_CONTAS="1112223334",
                                  **{vazado: "segredo-de-teste"})
    assert codigo == 64 and chamadas == [] and vazado in err and "segredo-de-teste" not in err


def test_service_role_nao_chega_ao_python_com_o_nome_do_env(raiz):
    falso = raiz / "venv" / "bin" / "python"
    falso.write_text('#!/usr/bin/env bash\nenv | grep -E "^(SERVICE_ROLE_KEY|SUPABASE_SERVICE_ROLE_KEY)=" '
                     '| cut -d= -f1 >> "$VOLC_TESTE_REGISTRO"\nexit 0\n')
    codigo, _, nomes = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", VOLC_SOMBRA_CONTAS="1112223334")
    assert codigo == 0 and nomes == ["SUPABASE_SERVICE_ROLE_KEY"]
