"""SIGN IN WITH CHATGPT + Responses API — testes herméticos (sem rede, sem
Keychain real, sem token real). Casos [1]..[13] da missão de 07/10/2026.
"""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import typer
from pydantic import BaseModel

from funnelforge.adapters import chatgpt_oauth as oa
from funnelforge.adapters.credenciais import (
    ArmazemEmArquivo,
    ArmazemKeychain,
    ChatGPTPlanCredentialProvider,
)
from funnelforge.adapters.openai_responses import (
    ModeloIndisponivel,
    ModeloTrocadoPeloServidor,
    OpenAIResponsesClient,
    RespostaHTTP,
    RoteadorDeLLM,
    SaidaEstruturadaInvalida,
    TetoDeChamadas,
)
from funnelforge.cli import conferir_modelos_do_plano
from funnelforge.config.settings import (
    OpenAIConfig,
    StepConfig,
    aplicar_modo_openai,
    problemas_do_modo_openai,
)
from funnelforge.pipeline.budget import OrcamentoEstourado
from funnelforge.pipeline.recibo_canario import recibo_do_canario
from funnelforge.pipeline.runner import LLMStepError, Runner
from funnelforge.ports.llm import LLMResult

ACESSO = "SEGREDO-ACESSO-nao-pode-vazar"
REFRESH = "SEGREDO-REFRESH-nao-pode-vazar"
ESCOPO_OK = oa.ESCOPO


def _token(**kw) -> oa.TokenSet:
    base = dict(access_token=ACESSO, refresh_token=REFRESH, expires_at=time.time() + 3600,
                scope=ESCOPO_OK, client_id="oaiapp_teste")
    return oa.TokenSet(**{**base, **kw})


class _Memoria:
    nome = "memoria"

    def __init__(self, dados=None):
        self.dados, self.gravacoes = dados, 0

    def ler(self):
        return dict(self.dados) if self.dados else None

    def gravar(self, dados):
        self.dados, self.gravacoes = dict(dados), self.gravacoes + 1

    def apagar(self):
        self.dados = None


def _provedor(tmp_path, token=None, post=None, agora=time.time):
    return ChatGPTPlanCredentialProvider(
        _Memoria(token.to_dict() if token else None), pasta_da_trava=tmp_path / "trava",
        post=post or (lambda url, form: (500, {})), agora=agora)


def _sse(*eventos) -> list[str]:
    return [f"data: {json.dumps(e)}" for e in eventos]


def _resposta_ok(texto="ok", modelo="gpt-6.1-sol", uso=(120, 45)):
    return RespostaHTTP(200, _sse(
        {"type": "response.output_text.delta", "delta": texto[: len(texto) // 2]},
        {"type": "response.output_text.delta", "delta": texto[len(texto) // 2:]},
        {"type": "response.completed", "response": {
            "id": "resp_abc123", "model": modelo,
            "usage": {"input_tokens": uso[0], "output_tokens": uso[1]}}}), {})


# ---------------------------------------------------------------------------
# [1] PKCE e state
# ---------------------------------------------------------------------------

def test_1_pkce_s256_e_state_aleatorio():
    verifier, challenge = oa.gerar_pkce()
    assert 43 <= len(verifier) <= 128
    esperado = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == esperado.decode()
    assert len({oa.gerar_state() for _ in range(50)}) == 50
    assert len({oa.gerar_pkce()[0] for _ in range(20)}) == 20


def test_1_url_de_autorizacao_segue_a_doc_oficial():
    url = oa.url_de_autorizacao(client_id="oaiapp_volc", redirect=oa.redirect_uri(1455),
                                state="st", nonce="nn", challenge="ch")
    partes = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(partes.query).items()}
    assert f"{partes.scheme}://{partes.netloc}{partes.path}" == oa.AUTHORIZE_URL
    assert q["client_id"] == "oaiapp_volc" and q["response_type"] == "code"
    assert q["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"
    assert q["scope"] == "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
    assert q["resource"] == "https://api.openai.com/v1"
    assert q["code_challenge_method"] == "S256" and q["state"] == "st" and q["nonce"] == "nn"
    assert "agent_name_hint" not in q
    reg = {k: v[0] for k, v in parse_qs(urlparse(oa.url_de_autorizacao(
        client_id="", redirect=oa.redirect_uri(1455), state="s", nonce="n", challenge="c",
        host_id="urn:uuid:24d99ca9-30dc-49c2-bc37-3fc01efd378b")).query).items()}
    assert reg["client_id"] == "dynamic_agent_client"
    assert reg["ext_agent_host_id"] == "urn:uuid:24d99ca9-30dc-49c2-bc37-3fc01efd378b"
    assert reg["agent_name_hint"] == "VOLC FunnelForge"
    # o formato recusado pelo provedor em 07/10 (`volc-<hex>`) não sai mais
    with pytest.raises(oa.ErroDeAutenticacao, match="urn:uuid"):
        oa.url_de_autorizacao(client_id="", redirect="r", state="s", nonce="n", challenge="c",
                              host_id="volc-24d99ca930dc49c2bc373fc01efd378b")
    with pytest.raises(oa.ErroDeAutenticacao):
        oa.url_de_autorizacao(client_id="", redirect="x", state="s", nonce="n", challenge="c")


# ---------------------------------------------------------------------------
# [2] callback inválido
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,trecho", [
    ("code=c&state=OUTRO", "state"),
    ("error=access_denied&state=st", "recusado"),
    ("state=st", "sem code"),
])
def test_2_callback_invalido_e_recusado(query, trecho):
    with pytest.raises(oa.CallbackInvalido, match=trecho):
        oa.validar_callback(query, "st", registrando=False)


def test_2_registro_exige_client_id_emitido():
    with pytest.raises(oa.CallbackInvalido, match="oaiapp_"):
        oa.validar_callback("code=c&state=st", "st", registrando=True)
    assert oa.validar_callback("code=c&state=st&client_id=oaiapp_novo", "st",
                               registrando=True)["client_id"] == "oaiapp_novo"


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_2_servidor_loopback_ignora_caminho_errado_e_valida_state():
    porta = _porta_livre()
    saida: dict = {}

    def esperar():
        try:
            saida["ok"] = oa.esperar_callback(porta, "st", registrando=False, timeout_s=10)
        except oa.ErroDeAutenticacao as exc:
            saida["erro"] = exc
    t = threading.Thread(target=esperar)
    t.start()
    time.sleep(0.3)
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"http://127.0.0.1:{porta}/callback?code=c&state=st")
    urllib.request.urlopen(f"http://127.0.0.1:{porta}/auth/callback?code=CODIGO&state=st")
    t.join(5)
    assert saida["ok"]["code"] == "CODIGO"


def test_2_servidor_loopback_tem_timeout():
    with pytest.raises(oa.CallbackInvalido, match="tempo esgotado"):
        oa.esperar_callback(_porta_livre(), "st", registrando=False, timeout_s=0.5)


# ---------------------------------------------------------------------------
# [3] token expirado  [4] rotação do refresh token
# ---------------------------------------------------------------------------

def test_3_sem_sessao_e_sessao_expirada_pedem_login(tmp_path):
    with pytest.raises(oa.SessaoExpirada, match="auth login"):
        _provedor(tmp_path).access_token()
    expirado = _token(expires_at=time.time() - 10)
    prov = _provedor(tmp_path, expirado, post=lambda u, f: (400, {"error": "invalid_grant"}))
    with pytest.raises(oa.SessaoExpirada, match="expirada ou revogada"):
        prov.access_token()


def test_3_escopo_do_plano_ausente_e_explicito(tmp_path):
    with pytest.raises(oa.EscopoAusente):
        _provedor(tmp_path, _token(scope="openid profile email")).access_token()
    with pytest.raises(oa.EscopoAusente):
        oa.trocar_codigo(client_id="oaiapp_x", code="c", verifier="v", redirect="r",
                         post=lambda u, f: (200, {"access_token": "a", "refresh_token": "r",
                                                  "expires_in": 3600, "scope": "openid"}))


def test_4_refresh_rotativo_grava_o_novo_e_descarta_o_antigo(tmp_path):
    chamadas = []

    def post(url, form):
        chamadas.append(dict(form))
        return 200, {"access_token": "NOVO-ACESSO", "refresh_token": "NOVO-REFRESH",
                     "expires_in": 3600, "scope": ESCOPO_OK}
    prov = _provedor(tmp_path, _token(expires_at=time.time() + 30), post=post)
    assert prov.access_token() == "NOVO-ACESSO"
    assert prov.armazem.dados["refresh_token"] == "NOVO-REFRESH"
    assert chamadas[0]["grant_type"] == "refresh_token"
    assert chamadas[0]["refresh_token"] == REFRESH and chamadas[0]["client_id"] == "oaiapp_teste"
    assert prov.access_token() == "NOVO-ACESSO"          # já válido: não renova de novo
    assert len(chamadas) == 1


def test_4_quem_pega_a_trava_rele_antes_de_renovar(tmp_path):
    """Dois processos: o segundo encontra o perfil já renovado pelo primeiro."""
    armazem = _Memoria(_token(expires_at=time.time() + 30).to_dict())
    renovado = _token(access_token="RENOVADO-POR-OUTRO", refresh_token="R2",
                      expires_at=time.time() + 3600).to_dict()
    leituras = {"n": 0}
    original = armazem.ler

    def ler():
        leituras["n"] += 1
        return renovado if leituras["n"] > 1 else original()
    armazem.ler = ler
    prov = ChatGPTPlanCredentialProvider(armazem, pasta_da_trava=tmp_path / "t",
                                         post=lambda u, f: pytest.fail("não podia renovar"))
    assert prov.access_token() == "RENOVADO-POR-OUTRO"


# ---------------------------------------------------------------------------
# [5] armazenamento seguro
# ---------------------------------------------------------------------------

def test_5_arquivo_fora_do_repo_com_700_600_e_escrita_atomica(tmp_path):
    armazem = ArmazemEmArquivo(tmp_path / "perfil")
    armazem.gravar(_token().to_dict())
    assert stat.S_IMODE(armazem.pasta.stat().st_mode) == 0o700
    assert stat.S_IMODE(armazem.caminho.stat().st_mode) == 0o600
    assert armazem.ler()["client_id"] == "oaiapp_teste"
    with pytest.raises(TypeError):
        armazem.gravar({"x": object()})                   # falha no meio da escrita
    assert armazem.ler()["client_id"] == "oaiapp_teste"   # o anterior sobrevive
    assert [p.name for p in armazem.pasta.iterdir()] == ["perfil-chatgpt.json"]
    with pytest.raises(RuntimeError, match="dentro do repositório"):
        ArmazemEmArquivo(Path(__file__).resolve().parents[3] / "perfil-proibido")


def test_5_keychain_usa_item_proprio_e_atualizacao_no_lugar():
    comandos = []

    def executar(args, **kw):
        comandos.append(args)
        if args[1] == "find-generic-password":
            return subprocess.CompletedProcess(args, 0, json.dumps({"client_id": "oaiapp_k"}), "")
        return subprocess.CompletedProcess(args, 0, "", "")
    kc = ArmazemKeychain(executar=executar)
    kc.gravar({"client_id": "oaiapp_k"})
    assert comandos[0][:3] == ["security", "add-generic-password", "-U"]
    assert "volc-funnelforge.chatgpt" in comandos[0]
    assert kc.ler() == {"client_id": "oaiapp_k"}


# ---------------------------------------------------------------------------
# [6] redação via Responses API  [7] saída estruturada inválida
# ---------------------------------------------------------------------------

def _cliente(tmp_path, respostas, modelos=("gpt-6.1-sol",)):
    enviados = []

    def enviar(url, headers, body, timeout):
        enviados.append({"url": url, "headers": headers, "body": body})
        return respostas.pop(0)

    def obter(url, headers, timeout):
        return 200, {"models": [{"slug": m, "display_name": m, "visibility": "list"}
                                for m in modelos]}
    cli = OpenAIResponsesClient(_provedor(tmp_path, _token()), enviar=enviar, obter=obter)
    return cli, enviados


def test_6_redacao_pela_responses_api(tmp_path):
    cli, enviados = _cliente(tmp_path, [_resposta_ok("Texto da página")])
    res = cli.complete("chatgpt/gpt-6.1-sol", [], [{"role": "user", "content": "escreva"}],
                       0.7, reasoning_effort="high")
    assert res.text == "Texto da página"
    assert res.model_used == "chatgpt/gpt-6.1-sol" and res.auth_mode == "chatgpt_plan"
    assert (res.prompt_tokens, res.completion_tokens) == (120, 45)
    assert res.cost_usd == 0.0 and res.response_id == "resp_abc123"
    corpo = enviados[0]["body"]
    assert enviados[0]["url"] == "https://api.openai.com/v1/responses"
    assert corpo["store"] is False and corpo["stream"] is True
    assert corpo["reasoning"] == {"effort": "high"} and "temperature" not in corpo
    assert corpo["model"] == "gpt-6.1-sol"


class _Veredito(BaseModel):
    approved: bool


def test_7_saida_estruturada_invalida_falha_explicito(tmp_path):
    cli, enviados = _cliente(tmp_path, [_resposta_ok("isto não é json")])
    with pytest.raises(SaidaEstruturadaInvalida):
        cli.complete("chatgpt/gpt-6.1-sol", [], [{"role": "user", "content": "x"}], 0.0,
                     response_schema=_Veredito)
    assert enviados[0]["body"]["text"]["format"]["type"] == "json_schema"
    cli2, _ = _cliente(tmp_path, [_resposta_ok('{"approved": true}')])
    assert cli2.complete("chatgpt/gpt-6.1-sol", [], [{"role": "user", "content": "x"}], 0.0,
                         response_schema=_Veredito).parsed.approved is True


# ---------------------------------------------------------------------------
# [8] gpt-6.1-sol indisponível falha fechado
# ---------------------------------------------------------------------------

def test_8_modelo_indisponivel_nao_tenta_outro(tmp_path):
    cli, enviados = _cliente(tmp_path, [RespostaHTTP(404, [], {"error": {"code": "model_not_found"}})])
    with pytest.raises(ModeloIndisponivel, match="Nenhum outro modelo"):
        cli.complete("chatgpt/gpt-6.1-sol", [], [{"role": "user", "content": "x"}], 0.0)
    assert len(enviados) == 1


def test_8_servidor_trocou_o_modelo_falha_fechado(tmp_path):
    cli, _ = _cliente(tmp_path, [_resposta_ok(modelo="gpt-6-luna")])
    with pytest.raises(ModeloTrocadoPeloServidor):
        cli.complete("chatgpt/gpt-6.1-sol", [], [{"role": "user", "content": "x"}], 0.0)


def test_8_runner_nao_retenta_erro_do_plano(tmp_path):
    cli, enviados = _cliente(tmp_path, [RespostaHTTP(404, [], {"error": {"code": "model_not_found"}})] * 3)
    runner = Runner(llm=RoteadorDeLLM(object(), cli), max_retries=2, runs_dir=tmp_path / "runs")
    cfg = StepConfig(model="chatgpt/gpt-6.1-sol", fallbacks=[], reasoning_effort="high")
    with pytest.raises(LLMStepError):
        runner.run_llm_step("judge_p2", cfg, [{"role": "user", "content": "x"}], {}, run_id="r")
    assert len(enviados) == 1


def test_8_preflight_para_quando_o_modelo_nao_esta_na_conta(tmp_path):
    cli, enviados = _cliente(tmp_path, [], modelos=("gpt-6-luna",))
    settings = type("S", (), {"steps": {"judge": StepConfig(model="chatgpt/gpt-6.1-sol")}})()
    with pytest.raises(typer.BadParameter, match="gpt-6.1-sol"):
        conferir_modelos_do_plano(settings, RoteadorDeLLM(object(), cli))
    assert enviados == []


# ---------------------------------------------------------------------------
# [9] api_key intacto  [10] sem fallback silencioso
# ---------------------------------------------------------------------------

class _LiteLLMFalso:
    def __init__(self):
        self.chamadas = []

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False, **kw):
        self.chamadas.append((model, tuple(fallbacks), web_search, kw))
        return LLMResult(text="ok", model_used=model, auth_mode="api_key")


def test_9_modo_api_key_continua_igual():
    lite = _LiteLLMFalso()
    rot = RoteadorDeLLM(lite, None)
    res = rot.complete("gpt-4.1", ["gemini/gemini-3.5-flash"],
                       [{"role": "user", "content": "x"}], 0.4, None, True)
    assert res.text == "ok"
    assert lite.chamadas == [("gpt-4.1", ("gemini/gemini-3.5-flash",), True, {})]
    s = type("S", (), {})()
    s.openai, s.steps = OpenAIConfig(), {"judge": StepConfig(model="gpt-4.1")}
    assert problemas_do_modo_openai(s) == []


def test_10_erro_do_plano_nunca_cai_para_api_key(tmp_path):
    lite = _LiteLLMFalso()
    cli, _ = _cliente(tmp_path, [RespostaHTTP(403, [], {"error": {
        "code": "subscription_sharing_user_not_eligible"}})])
    rot = RoteadorDeLLM(lite, cli)
    with pytest.raises(oa.PlanoInelegivel):
        rot.complete("chatgpt/gpt-6.1-sol", [], [{"role": "user", "content": "x"}], 0.0)
    with pytest.raises(Exception, match="fallback faturado"):
        rot.complete("chatgpt/gpt-6.1-sol", ["gpt-4.1"], [{"role": "user", "content": "x"}], 0.0)
    with pytest.raises(oa.SessaoExpirada):
        RoteadorDeLLM(lite, None).complete("chatgpt/gpt-6.1-sol", [], [], 0.0)
    assert lite.chamadas == []


def test_10_configuracao_que_permitiria_cobranca_acidental_e_recusada(tmp_path):
    from funnelforge.config.settings import load_settings
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
run: {}
site: {domain: https://site.exemplo.com.br, post_type: rec}
openai: {auth_mode: chatgpt_plan, client_id: oaiapp_volc, judge_model: gpt-6.1-sol,
         reviewer_model: gpt-6.1-sol, reasoning_effort: high, somente_plano: true}
steps:
  judge:   {model: gpt-4.1, fallbacks: [gemini/gemini-3.5-flash], temperature: 0.0}
  revisor: {model: gpt-4.1, fallbacks: [], temperature: 0.0}
  seo:     {model: gpt-4.1, fallbacks: [], temperature: 0.4}
""", encoding="utf-8")
    s = load_settings(tmp_path / "nada.env", cfg)
    assert s.steps["judge"].model == "chatgpt/gpt-6.1-sol"
    assert s.steps["judge"].fallbacks == []                    # fallback faturado removido
    assert s.steps["judge"].reasoning_effort == "high"
    problemas = problemas_do_modo_openai(s)
    assert any("steps.seo" in p and "faturado" in p for p in problemas)
    # api_key: o mesmo arquivo sem `openai` não troca modelo nenhum
    assert aplicar_modo_openai(s.model_copy(update={'openai': OpenAIConfig()})).steps['seo'].model == 'gpt-4.1'


def test_10_teto_rigido_de_chamadas():
    rot = RoteadorDeLLM(_LiteLLMFalso(), None, max_chamadas=2)
    rot.complete("gpt-4.1", [], [], 0.0)
    rot.complete("gpt-4.1", [], [], 0.0)
    with pytest.raises(TetoDeChamadas) as exc:
        rot.complete("gpt-4.1", [], [], 0.0)
    assert isinstance(exc.value, OrcamentoEstourado) and exc.value.escopo == "run"
    assert "Teto rígido de 2 chamadas" in str(exc.value)


# ---------------------------------------------------------------------------
# [11] nada de token em log, recibo, status ou repr
# ---------------------------------------------------------------------------

def test_11_logs_recibos_e_status_nao_contem_token(tmp_path):
    from funnelforge.domain.models import RunState
    cli, _ = _cliente(tmp_path, [_resposta_ok("ok")])
    runner = Runner(llm=RoteadorDeLLM(object(), cli), max_retries=0, runs_dir=tmp_path / "runs")
    _, res = runner.run_llm_step("judge_p2", StepConfig(model="chatgpt/gpt-6.1-sol",
                                                        reasoning_effort="high"),
                                 [{"role": "user", "content": "x"}], {}, run_id="r")
    assert (res.auth_mode, res.reasoning_effort, res.response_id) == ("chatgpt_plan", "high",
                                                                      "resp_abc123")
    state = RunState(run_id="r")
    state.step_status["judge_p2"] = res
    settings = type("S", (), {})()
    settings.openai = OpenAIConfig(auth_mode="chatgpt_plan", client_id="oaiapp_teste")
    settings.run = type("R", (), {"max_chamadas_llm": 40, "imagens_habilitadas": False,
                                  "publish": False, "publish_status": "draft"})()
    recibo = recibo_do_canario(state, settings, publisher_ligado=False, image_gen_ligado=False,
                               chamadas=1)
    textos = [
        (tmp_path / "runs" / "r" / "log.jsonl").read_text(),
        json.dumps(recibo), state.to_json(), repr(_token()),
        json.dumps(_provedor(tmp_path, _token()).status()),
    ]
    for texto in textos:
        assert ACESSO not in texto and REFRESH not in texto
    assert recibo["etapas"][0]["custo"].startswith("não aplicável")
    assert recibo["publicacao"]["nada_publicado"] is True


# ---------------------------------------------------------------------------
# [12] publish=false não toca o publisher  ([13] ouro V1: test_editorial_v2_flag_off_identico)
# ---------------------------------------------------------------------------

def test_12_publish_false_nunca_chama_o_publisher(tmp_path, monkeypatch):
    from funnelforge.pipeline.pipeline import run_pipeline
    from tests.cenario_editorial import congelar_data, montar_deps, responder_v1, settings_do_cenario
    from tests.test_jornada_senac import arquitetura
    from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
    congelar_data(monkeypatch)

    class _PublisherBomba:
        def __getattr__(self, nome):
            raise AssertionError(f"publisher tocado: {nome}")
    settings = settings_do_cenario(tmp_path)
    settings.run.imagens_habilitadas = False
    _, deps = montar_deps(tmp_path, settings, responder_v1)
    deps.publisher = _PublisherBomba()
    state = run_pipeline(None, deps, publish=False, timestamp="20261007-130000",
                         plan=plano_do_funnel_architecture(arquitetura()))
    assert not state.published
    assert not any(k.startswith("publish_p") for k in state.step_status)
    assert not any(k.startswith(("image_p", "image_gen_p")) for k in state.step_status)


def test_id_do_host_e_urn_uuid_estavel_e_migra_o_formato_recusado(tmp_path):
    from funnelforge.adapters.credenciais import id_do_host
    (tmp_path / "h").mkdir()
    (tmp_path / "h" / "host-id").write_text("volc-24d99ca930dc49c2bc373fc01efd378b")
    assert id_do_host(tmp_path / "h") == "urn:uuid:24d99ca9-30dc-49c2-bc37-3fc01efd378b"
    assert id_do_host(tmp_path / "h") == "urn:uuid:24d99ca9-30dc-49c2-bc37-3fc01efd378b"
    novo = id_do_host(tmp_path / "outro")
    assert novo.startswith("urn:uuid:") and id_do_host(tmp_path / "outro") == novo


def _id_token_assinado(**claims):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(chave.public_key()))
    jwk.update({"kid": "k1", "alg": "RS256", "use": "sig"})
    base = {"iss": "https://auth.openai.com", "aud": "oaiapp_volc", "nonce": "N1",
            "iat": int(time.time()), "exp": int(time.time()) + 600, "email": "tarcisio@agencia.com.br"}
    token = jwt.encode({**base, **claims}, chave, algorithm="RS256", headers={"kid": "k1"})
    return token, {"keys": [jwk]}


def test_id_token_valida_assinatura_issuer_audience_nonce_e_expiracao():
    token, jwks = _id_token_assinado()
    claims = oa.validar_id_token(token, client_id="oaiapp_volc", nonce="N1", jwks=jwks)
    assert oa.mascarar_conta(claims["email"]) == "ta***@ag***.br"
    for ruim, kw in ((_id_token_assinado(aud="oaiapp_outro"), {}),
                     (_id_token_assinado(iss="https://outro"), {}),
                     (_id_token_assinado(exp=int(time.time()) - 3600), {}),
                     (_id_token_assinado(), {"nonce": "OUTRO"})):
        with pytest.raises(oa.ErroDeAutenticacao):
            oa.validar_id_token(ruim[0], client_id="oaiapp_volc",
                                nonce=kw.get("nonce", "N1"), jwks=ruim[1])
    token2, _ = _id_token_assinado()
    with pytest.raises(oa.ErroDeAutenticacao):               # assinatura de outra chave
        oa.validar_id_token(token2, client_id="oaiapp_volc", nonce="N1", jwks=jwks)


def test_procedencia_sobrevive_aos_passos_que_remontam_o_resultado():
    """Achado do canário real de 07/10: engajamento, widget e revisor montavam
    o próprio StepResult e perdiam auth_mode/esforço/id da resposta."""
    from funnelforge.domain.models import StepResult, StepStatus, procedencia
    from funnelforge.pipeline.revisao import _somar
    pago = StepResult(step="x", status=StepStatus.OK, model_used="chatgpt/gpt-6.1-sol",
                      model_requested="chatgpt/gpt-6.1-sol", auth_mode="chatgpt_plan",
                      reasoning_effort="high", response_id="resp_1", attempts=1)
    assert procedencia(pago) == {"model_requested": "chatgpt/gpt-6.1-sol",
                                 "auth_mode": "chatgpt_plan", "reasoning_effort": "high",
                                 "response_id": "resp_1"}
    total = StepResult(step="revisor_p1", status=StepStatus.OK)
    _somar(total, pago)
    assert (total.auth_mode, total.reasoning_effort) == ("chatgpt_plan", "high")
