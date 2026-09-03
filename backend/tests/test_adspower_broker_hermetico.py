"""E2E hermético do broker contra um AdsPower FALSO — os 25 casos da missão.

## O que este arquivo é

Um teste de ponta a ponta com sockets de verdade: sobe o duplê HTTP do AdsPower
em `127.0.0.1:0`, sobe o broker em `127.0.0.1:0`, e exercita o caminho
`referência → resolução efêmera → Local API → perfil → navegação → captura →
recibo sanitizado`. Nenhuma chamada sai do loopback, nenhum navegador é aberto,
nenhum segredo real é lido.

## O que este arquivo NÃO é

Prova de que o AdsPower real responde assim. Ele responde assim SEGUNDO A
DOCUMENTAÇÃO OFICIAL consultada em 02/09/2026 (as fontes estão no docstring de
`fake/adspower.py`), e dois pontos permanecem inferidos e marcados: o path de
fechar o navegador e o comportamento com Bearer errado.

## A sentinela

`SENTINELA` é o valor sintético que o resolvedor devolve no lugar do segredo.
Ela é longa e inconfundível, e cada caso que produz recibo é varrido atrás
dela. Se ela aparecer, a contenção falhou — e é muito melhor descobrir isso com
um valor que não vale nada.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tools" / "adspower-broker"))

from app.visual_proof import dominio as dom  # noqa: E402
from broker import adspower as ads  # noqa: E402
from broker import configuracao as cfg  # noqa: E402
from broker import segredo as seg  # noqa: E402
from broker.execucao import ExecutorDoBroker, RegistroDeIdempotencia  # noqa: E402
from broker.servidor import ServidorDoBroker  # noqa: E402
from fake.adspower import (  # noqa: E402
    PNG_MINIMO, CenarioDeNavegacao, EstadoDoDuple, ServidorFalsoDoAdsPower,
)
from fake.navegador import NavegadorViaDuple  # noqa: E402

SENTINELA = "VOLC-SENTINELA-ADSPOWER-9f3c71b8d24e5a06"
TOKEN_DO_BROKER = "volc-broker-token-de-teste-0123456789abcdef"
USER_ID = "duplekm001"
DONO_A = "sub-dono-a"
DONO_B = "sub-dono-b"
URL = "https://exemplo.com.br/post/123"
DOMINIO = "exemplo.com.br"

#: DNS injetado. Uma prova de SSRF que depende do resolvedor real mede a
#: internet, não o código.
DNS = {
    "exemplo.com.br": ["93.184.216.34"],
    "blog.exemplo.com.br": ["93.184.216.35"],
    "outro.com.br": ["104.18.32.7"],
    #: Subdomínio LEGÍTIMO do domínio esperado que aponta para a rede interna.
    #: É o caso difícil: a allowlist de domínio o aceita, e só a resolução o
    #: recusa. Um guarda que só olhasse o nome deixaria passar.
    "interno.exemplo.com.br": ["10.0.0.9"],
}


def _dns(host: str) -> list[str]:
    try:
        return DNS[host]
    except KeyError:
        raise dom.NomeNaoResolvido(host) from None


# ─────────────────────────────────────────────────────────────────────────────
# Montagem
# ─────────────────────────────────────────────────────────────────────────────


def _allowlist(tmp_path: Path, **sobrescritas) -> Path:
    perfil = {
        "perfil_logico": "PERFIL_PILOTO_01",
        "user_id": USER_ID,
        "owner_sub": DONO_A,
        "ativo_id": "asset:facebook-page:piloto",
        "operacoes": ["estado_do_perfil", "abrir_perfil", "capturar_superficie", "fechar_perfil"],
        "credencial_nome_logico": "ADSPOWER_API_KEY",
        "localizador": "op://VOLC/Perfil Piloto/ADSPOWER_API_KEY",
        "dominios_permitidos": [DOMINIO],
    }
    perfil.update(sobrescritas)
    caminho = tmp_path / "perfis.json"
    caminho.write_text(json.dumps({"perfis": [perfil]}), encoding="utf-8")
    caminho.chmod(0o600)
    return caminho


def _config(tmp_path: Path, base_do_adspower: str, **kwargs) -> cfg.ConfiguracaoDoBroker:
    return cfg.carregar(
        allowlist=kwargs.pop("allowlist", None) or _allowlist(tmp_path),
        token=TOKEN_DO_BROKER,
        bind_host="127.0.0.1",
        bind_porta=0,
        adspower_base=base_do_adspower,
        artefatos_dir=tmp_path / "artefatos",
        verificacao_de_api_ativa=True,
        portas_do_adspower=(urlport(base_do_adspower),),
        ambiente={},
        **kwargs,
    )


def urlport(base: str) -> int:
    return int(base.rsplit(":", 1)[1])


def _executor(config: cfg.ConfiguracaoDoBroker, duple: ServidorFalsoDoAdsPower,
              *, resolvedor=None, navegador=None, registro=None) -> ExecutorDoBroker:
    return ExecutorDoBroker(
        config=config,
        resolvedor=resolvedor or seg.ResolvedorSentinela(
            valores={"ADSPOWER_API_KEY": SENTINELA}),
        cliente=ads.ClienteDoAdsPower(
            config.adspower_base, portas_permitidas=(urlport(config.adspower_base),),
            intervalo_minimo_s=0.0),
        navegador=navegador if navegador is not None else NavegadorViaDuple(chave=SENTINELA),
        registro=registro,
        resolvedor_de_dns=_dns,
    )


def _estado(**kwargs) -> EstadoDoDuple:
    base = dict(chave_esperada=SENTINELA, perfis_conhecidos={USER_ID})
    base.update(kwargs)
    return EstadoDoDuple(**base)


def _pedido(**kwargs) -> dom.AdsPowerBrokerRequest:
    perfil = kwargs.pop("perfil", None) or dom.BrowserProfileReference(
        ativo_id="asset:facebook-page:piloto", perfil_logico="PERFIL_PILOTO_01",
        owner_sub=DONO_A, provider="1password", credencial_nome_logico="ADSPOWER_API_KEY")
    corpo = dict(
        pedido_id="ped_0001", chave_idempotencia="vpj-piloto-2026-09-02-01",
        operacao="capturar_superficie", perfil=perfil, owner_sub=DONO_A,
        ativo_id="asset:facebook-page:piloto", timeout_s=20, url_alvo=URL,
        dominio_esperado=DOMINIO, viewport=dom.Viewport(largura=1366, altura=768),
        timezone="America/Sao_Paulo",
    )
    corpo.update(kwargs)
    return dom.AdsPowerBrokerRequest(**corpo)


@pytest.fixture
def cenario(tmp_path):
    """Duplê + broker montados, prontos para uso. Encerra os dois no teardown."""
    estado = _estado()
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple)
        yield estado, duple, config, executor


def _varrer(recibo: dom.AdsPowerBrokerReceipt) -> dict:
    """Projeta o recibo e prova, no ato, que a sentinela não está nele."""
    projecao = recibo.para_dicionario()
    dom.recusar_valor_sensivel(projecao, sentinelas=(SENTINELA, TOKEN_DO_BROKER))
    return projecao


# ─────────────────────────────────────────────────────────────────────────────
# 1–4 · caminho feliz
# ─────────────────────────────────────────────────────────────────────────────


def test_01_pagina_e_perfil_do_mesmo_dono_seguem(cenario):
    _estado_duple, _duple, config, executor = cenario
    perfil = config.perfil("PERFIL_PILOTO_01")
    assert perfil.owner_sub == DONO_A == _pedido().owner_sub
    recibo = executor.executar(_pedido())
    assert recibo.estado == "executado", recibo.motivo


def test_02_referencia_op_valida_chega_ao_resolvedor(cenario, tmp_path):
    _e, duple, config, _x = cenario
    resolvedor = seg.ResolvedorSentinela(valores={"ADSPOWER_API_KEY": SENTINELA})
    executor = _executor(config, duple, resolvedor=resolvedor)
    executor.executar(_pedido())
    # O resolvedor foi chamado pelo NOME LÓGICO, e o endereço veio da allowlist —
    # não do pedido. O chamador não tem como pedir outro endereço.
    assert resolvedor.chamadas == ["ADSPOWER_API_KEY"]


def test_03_segredo_falso_so_existe_em_memoria_efemera(cenario):
    _e, duple, config, _x = cenario
    guardados: list[seg.SegredoEfemero] = []

    class ResolvedorObservado(seg.ResolvedorSentinela):
        def resolver(self, *, nome_logico, localizador):
            segredo = super().resolver(nome_logico=nome_logico, localizador=localizador)
            guardados.append(segredo)
            return segredo

    executor = _executor(config, duple, resolvedor=ResolvedorObservado(
        valores={"ADSPOWER_API_KEY": SENTINELA}))
    executor.executar(_pedido())
    assert guardados and all(s.descartado for s in guardados)
    with pytest.raises(seg.SegredoJaDescartado):
        with guardados[0].usar():
            pass
    # E o `repr` nunca foi o valor.
    assert SENTINELA not in repr(guardados[0]) and SENTINELA not in f"{guardados[0]}"


def test_04_broker_autentica_no_adspower_falso(cenario):
    estado, _duple, _config, executor = cenario
    executor.executar(_pedido())
    assert estado.autorizacoes_recebidas
    assert all(cab == f"Bearer {SENTINELA}" for cab in estado.autorizacoes_recebidas)


# ─────────────────────────────────────────────────────────────────────────────
# 5–8 · recusas de autorização
# ─────────────────────────────────────────────────────────────────────────────


def test_05_perfil_nao_autorizado_e_recusado(cenario):
    _e, _d, _c, executor = cenario
    outro = dom.BrowserProfileReference(
        ativo_id="asset:facebook-page:piloto", perfil_logico="PERFIL_NAO_LISTADO",
        owner_sub=DONO_A, provider="1password", credencial_nome_logico="ADSPOWER_API_KEY")
    recibo = executor.executar(_pedido(perfil=outro))
    assert recibo.estado == "recusado" and recibo.motivo_codigo == "nao_autorizado"


def test_06_operacao_fora_da_allowlist_e_recusada(tmp_path):
    estado = _estado()
    with ServidorFalsoDoAdsPower(estado) as duple:
        allowlist = _allowlist(tmp_path, operacoes=["estado_do_perfil"])
        config = _config(tmp_path, duple.base, allowlist=allowlist)
        executor = _executor(config, duple)
        recibo = executor.executar(_pedido(operacao="capturar_superficie"))
        assert recibo.estado == "recusado" and recibo.motivo_codigo == "nao_autorizado"
        assert estado.chamadas == {}, "recusa não pode ter falado com o AdsPower"


def test_07_endpoint_do_adspower_fora_da_fronteira_e_recusado(tmp_path):
    with pytest.raises(dom.EndpointRecusado):
        cfg.carregar(
            allowlist=_allowlist(tmp_path), token=TOKEN_DO_BROKER, bind_host="127.0.0.1",
            bind_porta=0, adspower_base="http://198.51.100.7:50325",
            artefatos_dir=tmp_path / "a", verificacao_de_api_ativa=True, ambiente={})


def test_08_modo_sem_verificacao_de_api_e_recusado_no_preflight(tmp_path):
    with pytest.raises(cfg.PreflightRecusado) as erro:
        cfg.carregar(
            allowlist=_allowlist(tmp_path), token=TOKEN_DO_BROKER, bind_host="127.0.0.1",
            bind_porta=0, adspower_base="http://127.0.0.1:50325",
            artefatos_dir=tmp_path / "a", verificacao_de_api_ativa=False, ambiente={})
    assert "verificação de API" in str(erro.value)


def test_08b_bind_publico_e_recusado_no_preflight(tmp_path):
    for host in ("0.0.0.0", "192.168.1.10", "::"):
        with pytest.raises(cfg.PreflightRecusado):
            cfg.carregar(
                allowlist=_allowlist(tmp_path), token=TOKEN_DO_BROKER, bind_host=host,
                bind_porta=0, adspower_base="http://127.0.0.1:50325",
                artefatos_dir=tmp_path / "a", verificacao_de_api_ativa=True, ambiente={})


def test_08c_token_ausente_ou_fraco_e_recusado_no_preflight(tmp_path):
    for token in ("", "curto", "a" * 32):
        with pytest.raises(cfg.PreflightRecusado):
            cfg.carregar(
                allowlist=_allowlist(tmp_path), token=token, bind_host="127.0.0.1",
                bind_porta=0, adspower_base="http://127.0.0.1:50325",
                artefatos_dir=tmp_path / "a", verificacao_de_api_ativa=True, ambiente={})


def test_08d_allowlist_legivel_por_outros_e_recusada(tmp_path):
    caminho = _allowlist(tmp_path)
    caminho.chmod(0o644)
    with pytest.raises(cfg.PreflightRecusado) as erro:
        cfg.carregar(
            allowlist=caminho, token=TOKEN_DO_BROKER, bind_host="127.0.0.1", bind_porta=0,
            adspower_base="http://127.0.0.1:50325", artefatos_dir=tmp_path / "a",
            verificacao_de_api_ativa=True, ambiente={})
    assert "0600" in str(erro.value)


# ─────────────────────────────────────────────────────────────────────────────
# 9–11 · SSRF, DNS e redirect
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("alvo", [
    "https://127.0.0.1/post",
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/post",
    "https://painel.internal/post",
])
def test_09_url_privada_de_loopback_ou_de_metadados_e_recusada(cenario, alvo):
    estado, _d, _c, executor = cenario
    recibo = executor.executar(_pedido(url_alvo=alvo, dominio_esperado=None))
    assert recibo.estado == "recusado" and recibo.motivo_codigo == "nao_autorizado"
    assert estado.chamadas == {}, "recusa de destino não pode abrir perfil"


def test_10_dns_que_nao_resolve_falha_fechado(cenario):
    estado, _d, _c, executor = cenario
    recibo = executor.executar(
        _pedido(url_alvo="https://nunca-existiu.example/post", dominio_esperado=None))
    assert recibo.estado == "recusado"
    assert estado.chamadas == {}


def test_11_redirect_para_endereco_privado_e_recusado(tmp_path):
    """A validação de entrada não alcança o redirect: ele acontece depois dela.

    O destino é `interno.exemplo.com.br` — DENTRO do domínio autorizado, e
    resolvendo para `10.0.0.9`. A allowlist de domínio o aceita; quem o recusa é
    a resolução. Se a política fosse só de nome, este salto passaria.

    Por isso a URL FINAL e cada salto passam pela mesma política, já com o
    perfil aberto — e a recusa vem com o perfil fechado na limpeza.
    """
    interno = "https://interno.exemplo.com.br/painel"
    estado = _estado(cenarios={
        URL: CenarioDeNavegacao(url_final=interno, redirecionamentos=(interno,)),
    })
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple)
        recibo = executor.executar(_pedido())
        assert recibo.estado == "recusado"
        assert recibo.motivo_codigo == "destino_recusado"
        assert not estado.perfis_ativos, "o perfil aberto tinha de ser fechado"
        assert estado.chamadas.get("/api/v1/browser/stop") == 1


# ─────────────────────────────────────────────────────────────────────────────
# 12–17 · execução e recibo
# ─────────────────────────────────────────────────────────────────────────────


def test_12_perfil_e_iniciado_uma_vez_so(cenario):
    estado, _d, _c, executor = cenario
    executor.executar(_pedido(operacao="abrir_perfil", chave_idempotencia="abre-uma-vez-1"))
    executor.executar(_pedido(operacao="abrir_perfil", chave_idempotencia="abre-uma-vez-2"))
    assert estado.chamadas.get("/api/v1/browser/start") == 1
    assert estado.chamadas.get("/api/v1/browser/active") == 2


def test_13_navegacao_so_acontece_na_url_autorizada(tmp_path):
    visitadas: list[str] = []

    class NavegadorEspiao(NavegadorViaDuple):
        def capturar(self, *, ws_endpoint, url, viewport, timezone, timeout_s):
            visitadas.append(url)
            return super().capturar(ws_endpoint=ws_endpoint, url=url, viewport=viewport,
                                    timezone=timezone, timeout_s=timeout_s)

    estado = _estado()
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple, navegador=NavegadorEspiao(chave=SENTINELA))
        executor.executar(_pedido())
        executor.executar(_pedido(url_alvo="https://outro.com.br/post",
                                  chave_idempotencia="fora-do-dominio-1"))
    assert visitadas == [URL], "só a URL autorizada pode ter sido aberta"


def test_14_15_screenshot_vira_referencia_e_hash(cenario):
    _e, _d, _c, executor = cenario
    recibo = executor.executar(_pedido())
    assert recibo.artefato is not None
    assert recibo.artefato.sha256 == dom.sha256_de_bytes(PNG_MINIMO)
    assert recibo.artefato.bytes_ == len(PNG_MINIMO)
    assert recibo.artefato.referencia.startswith("vpartifact://PERFIL_PILOTO_01/")
    # A referência não é um caminho de disco: nada de `/home`, `/Users`, `/tmp`.
    for trecho in ("/home/", "/Users/", "/tmp/", "C:\\"):
        assert trecho not in recibo.artefato.referencia


def test_16_console_e_rede_saem_resumidos_e_sanitizados(tmp_path):
    estado = _estado(cenarios={URL: CenarioDeNavegacao(
        console=(
            {"nivel": "error", "texto": f"falhou com Authorization: Bearer {SENTINELA}"},
            {"nivel": "warning", "texto": "aviso comum"},
        ),
        rede=(
            {"host": "exemplo.com.br", "status": 200},
            {"host": "ads.terceiro.com", "status": 500},
        ),
    )})
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        recibo = _executor(config, duple).executar(_pedido())
    assert recibo.console_resumo["erros"] == 1
    assert recibo.console_resumo["avisos"] == 1
    assert recibo.rede_resumo == {"requisicoes": 2, "falhas": 1,
                                  "hosts": {"exemplo.com.br": 1, "ads.terceiro.com": 1}}
    projecao = _varrer(recibo)  # levanta se a sentinela tiver sobrevivido
    assert dom.REDIGIDO in json.dumps(projecao, ensure_ascii=False)


def test_17_recibo_e_persistido_e_relido_pela_chave(cenario):
    _e, _d, _c, executor = cenario
    primeiro = executor.executar(_pedido())
    segundo = executor.executar(_pedido(pedido_id="ped_0002"))
    assert primeiro.estado == "executado"
    assert segundo.estado == "replay"
    assert segundo.recibo_id == primeiro.recibo_id
    assert segundo.pedido_id == "ped_0002"


# ─────────────────────────────────────────────────────────────────────────────
# 18–20 · idempotência e concorrência
# ─────────────────────────────────────────────────────────────────────────────


def test_18_retry_nao_duplica_execucao(cenario):
    estado, _d, _c, executor = cenario
    for tentativa in range(4):
        executor.executar(_pedido(pedido_id=f"ped_000{tentativa}"))
    assert estado.chamadas.get("/__fake__/navegar") == 1
    assert estado.chamadas.get("/api/v1/browser/start") == 1


def test_19_mesma_chave_com_payload_diferente_e_recusada(cenario):
    _e, _d, _c, executor = cenario
    executor.executar(_pedido())
    divergente = executor.executar(_pedido(url_alvo="https://blog.exemplo.com.br/outro"))
    assert divergente.estado == "recusado"
    assert divergente.motivo_codigo == "idempotencia_divergente"


def test_20_dois_consumidores_nao_executam_o_mesmo_job(tmp_path):
    """O segundo consumidor tem de ser RECUSADO enquanto o primeiro executa.

    O cenário força a sobreposição: o duplê atrasa a navegação, e o segundo
    pedido entra durante esse atraso.
    """
    estado = _estado(cenarios={URL: CenarioDeNavegacao(atraso_s=0.6)})
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple, registro=RegistroDeIdempotencia())
        recibos: list[dom.AdsPowerBrokerReceipt] = []
        trava = threading.Lock()

        def executar(consumidor: str) -> None:
            recibo = executor.executar(_pedido(pedido_id=f"ped-{consumidor}"),
                                       consumidor=consumidor)
            with trava:
                recibos.append(recibo)

        primeira = threading.Thread(target=executar, args=("a",))
        primeira.start()
        time.sleep(0.2)
        executar("b")
        primeira.join(timeout=10)

    estados = sorted(r.estado for r in recibos)
    assert estados == ["executado", "recusado"], estados
    recusado = next(r for r in recibos if r.estado == "recusado")
    assert recusado.motivo_codigo == "em_execucao"
    assert estado.chamadas.get("/__fake__/navegar") == 1


# ─────────────────────────────────────────────────────────────────────────────
# 21–22 · timeout e limpeza
# ─────────────────────────────────────────────────────────────────────────────


def test_21_timeout_vira_falha_tecnica_e_nunca_reprovacao(tmp_path):
    estado = _estado(cenarios={URL: CenarioDeNavegacao(atraso_s=2.0)})
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple)
        recibo = executor.executar(_pedido(timeout_s=1))
    assert recibo.estado == "falhou"
    assert recibo.motivo_codigo in ("timeout", "adspower_indisponivel")
    # E o veredito derivado é indeterminado, não `needs_correction`.
    veredito = dom.veredito_de_falha_tecnica("timeout")
    assert veredito.resultado == "indeterminate"


def test_22_excecao_no_meio_da_captura_ainda_fecha_o_perfil(tmp_path):
    class NavegadorQueExplode:
        def capturar(self, **_kwargs):
            raise ads.AdsPowerIndisponivel("estourou no meio da captura")

    estado = _estado()
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple, navegador=NavegadorQueExplode())
        recibo = executor.executar(_pedido())
        assert recibo.estado == "falhou"
        assert estado.chamadas.get("/api/v1/browser/start") == 1
        assert not estado.perfis_ativos, "o perfil aberto tinha de ser fechado no finally"
        assert estado.chamadas.get("/api/v1/browser/stop") == 1


def test_22b_cofre_trancado_falha_fechado_sem_tocar_no_adspower(cenario):
    estado, duple, config, _x = cenario
    executor = _executor(config, duple,
                         resolvedor=seg.ResolvedorSentinela(modo="cofre_trancado"))
    recibo = executor.executar(_pedido())
    assert recibo.estado == "falhou"
    assert recibo.motivo_codigo == "resolucao_de_segredo_falhou"
    assert estado.chamadas == {}


def test_22c_segredo_ausente_falha_fechado(cenario):
    _e, duple, config, _x = cenario
    executor = _executor(config, duple, resolvedor=seg.ResolvedorSentinela(modo="ausente"))
    assert executor.executar(_pedido()).motivo_codigo == "resolucao_de_segredo_falhou"


def test_22d_segredo_vazio_nao_vira_chave_vazia(cenario):
    _e, duple, config, _x = cenario
    executor = _executor(config, duple, resolvedor=seg.ResolvedorSentinela(modo="vazio"))
    assert executor.executar(_pedido()).motivo_codigo == "resolucao_de_segredo_falhou"


# ─────────────────────────────────────────────────────────────────────────────
# 23–24 · contenção e isolamento por dono
# ─────────────────────────────────────────────────────────────────────────────


def test_23_sentinela_nao_aparece_em_json_log_nem_erro(tmp_path, caplog):
    estado = _estado()
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple)
        with caplog.at_level("DEBUG"):
            recibos = [
                executor.executar(_pedido()),
                executor.executar(_pedido(chave_idempotencia="k2", url_alvo="https://10.0.0.5/x",
                                          dominio_esperado=None)),
                executor.executar(_pedido(chave_idempotencia="k3", operacao="fechar_perfil")),
            ]
        for recibo in recibos:
            _varrer(recibo)
        # Nem no JSON, nem no log, nem na saúde do broker.
        assert SENTINELA not in json.dumps([r.para_dicionario() for r in recibos])
        assert SENTINELA not in caplog.text
        saude = json.dumps(config.saude(), ensure_ascii=False)
        assert SENTINELA not in saude and "op://" not in saude and USER_ID not in saude
        assert str(tmp_path) not in saude and "artefatos_dir" not in saude
        # E o artefato em disco é a imagem, não o segredo.
        artefato = next(p for p in (tmp_path / "artefatos").rglob("*.png"))
        assert SENTINELA.encode() not in artefato.read_bytes()


def test_23b_recibo_que_carregasse_o_valor_seria_descartado(tmp_path):
    """Prova que a última peneira NÃO é decorativa.

    Um navegador que devolvesse a chave dentro da URL final produziria um recibo
    com o segredo. A peneira o troca por `vazamento_contido` — e a prova falha
    se alguém remover a checagem, porque o recibo sairia com a sentinela.
    """
    class NavegadorQueVaza(NavegadorViaDuple):
        def capturar(self, **kwargs):
            bruta = super().capturar(**kwargs)
            return ads.CapturaBruta(
                url_final=bruta.url_final, redirecionamentos=bruta.redirecionamentos,
                status_http=bruta.status_http,
                console=({"nivel": "error", "texto": f"chave={SENTINELA}"},),
                rede=bruta.rede, imagem=bruta.imagem, mime=bruta.mime)

    estado = _estado()
    with ServidorFalsoDoAdsPower(estado) as duple:
        config = _config(tmp_path, duple.base)
        executor = _executor(config, duple, navegador=NavegadorQueVaza(chave=SENTINELA))
        recibo = executor.executar(_pedido())
    # O sanitizador de texto já teria apagado; a peneira é a segunda linha.
    _varrer(recibo)
    assert recibo.estado in ("executado", "recusado")


def test_24_dono_b_nao_usa_o_perfil_do_dono_a(cenario):
    _e, _d, _c, executor = cenario
    perfil_de_b = dom.BrowserProfileReference(
        ativo_id="asset:facebook-page:piloto", perfil_logico="PERFIL_PILOTO_01",
        owner_sub=DONO_B, provider="1password", credencial_nome_logico="ADSPOWER_API_KEY")
    recibo = executor.executar(_pedido(perfil=perfil_de_b, owner_sub=DONO_B))
    assert recibo.estado == "recusado" and recibo.motivo_codigo == "nao_autorizado"


def test_24b_pedido_com_dono_diferente_do_perfil_nem_monta(cenario):
    with pytest.raises(dom.PayloadRecusado):
        _pedido(owner_sub=DONO_B)


def test_24c_ativo_de_outro_dono_e_recusado(cenario):
    _e, _d, _c, executor = cenario
    recibo = executor.executar(_pedido(ativo_id="asset:facebook-page:de-outro"))
    assert recibo.estado == "recusado" and recibo.motivo_codigo == "nao_autorizado"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP do broker
# ─────────────────────────────────────────────────────────────────────────────


def _chamar(base: str, caminho: str, *, token: str | None, corpo: dict | None = None):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    pedido = urllib.request.Request(
        f"{base}{caminho}", data=dados, method="POST" if corpo is not None else "GET",
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:  # noqa: S310
            return resposta.status, json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_http_exige_bearer_proprio(cenario):
    _e, _d, config, executor = cenario
    with ServidorDoBroker(config, executor) as servidor:
        assert _chamar(servidor.base, "/v1/saude", token=None)[0] == 401
        assert _chamar(servidor.base, "/v1/saude", token="errado")[0] == 401
        status, corpo = _chamar(servidor.base, "/v1/saude", token=TOKEN_DO_BROKER)
    assert status == 200
    assert corpo["autenticacao"] == "ativa"
    assert corpo["verificacao_de_api"] == "exigida"
    assert USER_ID not in json.dumps(corpo)


def test_http_executa_operacao_e_devolve_recibo_sanitizado(cenario):
    _e, _d, config, executor = cenario
    with ServidorDoBroker(config, executor) as servidor:
        status, corpo = _chamar(servidor.base, "/v1/operacoes", token=TOKEN_DO_BROKER, corpo={
            "pedido_id": "ped_http_1", "chave_idempotencia": "http-1",
            "operacao": "capturar_superficie",
            "perfil": {"ativo_id": "asset:facebook-page:piloto",
                       "perfil_logico": "PERFIL_PILOTO_01", "owner_sub": DONO_A,
                       "provider": "1password", "credencial_nome_logico": "ADSPOWER_API_KEY"},
            "owner_sub": DONO_A, "ativo_id": "asset:facebook-page:piloto",
            "url_alvo": URL, "dominio_esperado": DOMINIO, "timeout_s": 20,
            "viewport": {"largura": 1366, "altura": 768},
        })
    assert status == 200 and corpo["estado"] == "executado"
    dom.recusar_valor_sensivel(corpo, sentinelas=(SENTINELA, TOKEN_DO_BROKER))
    assert USER_ID not in json.dumps(corpo)


def test_http_recusa_campo_desconhecido_e_localizador(cenario):
    _e, _d, config, executor = cenario
    base_corpo = {
        "pedido_id": "p", "chave_idempotencia": "http-2", "operacao": "estado_do_perfil",
        "perfil": {"ativo_id": "asset:facebook-page:piloto",
                   "perfil_logico": "PERFIL_PILOTO_01", "owner_sub": DONO_A,
                   "provider": "1password", "credencial_nome_logico": "ADSPOWER_API_KEY"},
        "owner_sub": DONO_A, "ativo_id": "asset:facebook-page:piloto",
    }
    with ServidorDoBroker(config, executor) as servidor:
        status, corpo = _chamar(servidor.base, "/v1/operacoes", token=TOKEN_DO_BROKER,
                                corpo={**base_corpo, "user_id": USER_ID})
        assert status == 400 and "user_id" in corpo["mensagem"]

        com_localizador = json.loads(json.dumps(base_corpo))
        com_localizador["perfil"]["localizador"] = "op://VOLC/x/y"
        status, corpo = _chamar(servidor.base, "/v1/operacoes", token=TOKEN_DO_BROKER,
                                corpo=com_localizador)
        assert status == 400 and "localizador" in corpo["mensagem"]


def test_http_nao_expoe_rota_generica(cenario):
    _e, _d, config, executor = cenario
    with ServidorDoBroker(config, executor) as servidor:
        for caminho in ("/v1/proxy", "/api/v1/browser/start", "/"):
            status, _ = _chamar(servidor.base, caminho, token=TOKEN_DO_BROKER, corpo={})
            assert status == 404, caminho


# ─────────────────────────────────────────────────────────────────────────────
# 25 (lado backend) · processos filhos e checkpoint externo
# ─────────────────────────────────────────────────────────────────────────────


def test_cancelamento_nao_deixa_descendente_vivo(tmp_path):
    """O `op run` cria neto; `proc.kill()` mataria só o filho.

    O neto aqui é um `sleep` que escreve num arquivo se sobreviver ao prazo. Se
    o grupo de processos não for morto, o arquivo aparece — e o teste falha.
    """
    marcador = tmp_path / "sobrevivi.txt"
    script = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',\"import time,pathlib;time.sleep(2.5);"
        f"pathlib.Path(r'{marcador}').write_text('vivo')\"]);"
        "time.sleep(30)"
    )
    with pytest.raises(seg.FilhoExpirou):
        seg.executar_isolado([sys.executable, "-c", script], timeout_s=0.6)
    time.sleep(3.2)
    assert not marcador.exists(), "um descendente sobreviveu ao cancelamento"


def test_driver_real_de_captura_recusa_em_vez_de_fingir():
    with pytest.raises(ads.CheckpointExterno):
        ads.NavegadorNaoImplementado().capturar(
            ws_endpoint="ws://127.0.0.1:1/devtools/browser/x", url=URL,
            viewport=dom.Viewport(largura=800, altura=600), timezone=None, timeout_s=1)


def test_broker_nao_importa_o_duple():
    """A dependência é de mão única: `broker/*` nunca conhece `fake/*`.

    Um `import fake` em produção significaria que o processo real carrega o
    servidor que finge ser AdsPower — e um erro de configuração poderia apontar
    para ele.
    """
    raiz = RAIZ / "tools" / "adspower-broker" / "broker"
    for arquivo in raiz.glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        assert "import fake" not in texto and "from fake" not in texto, arquivo.name


def test_preflight_pela_linha_de_comando_recusa_sem_token(tmp_path):
    allowlist = _allowlist(tmp_path)
    concluido = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "broker", "--allowlist", str(allowlist), "--preflight"],
        cwd=str(RAIZ / "tools" / "adspower-broker"),
        env={"PATH": "/usr/bin:/bin", "VOLC_BROKER_TOKEN": ""},
        capture_output=True, text=True, timeout=60)
    assert concluido.returncode == 2
    assert "preflight recusado" in concluido.stderr
