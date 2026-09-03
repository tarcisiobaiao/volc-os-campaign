"""As regras do plano de controle de prova visual, sem rede e sem processo filho.

## O que este arquivo prova, e por que cada prova existe

Este modulo cobre a camada que decide ANTES de qualquer efeito: qual URL pode
ser aberta, qual endpoint do AdsPower e aceitavel, qual transicao de estado e
legitima, o que pode aparecer num recibo e como duas execucoes da mesma
intencao produzem a mesma impressao digital.

Tres decisoes deste dominio nao sao obvias e por isso tem prova propria:

1. **O veredito automatico nunca e `approved`.** A avaliacao automatica so
   produz `eligible_for_human_review`, `needs_correction` ou `indeterminate`.
   `approved` e um ato humano, e o unico caminho ate ele passa por
   `VisualProofJob.aprovar(...)` com revisor nomeado. Um motor que aprova
   sozinho transforma "a captura nao encontrou problema" em "a pagina esta
   certa" — que sao afirmacoes diferentes.

2. **Falha do AdsPower nao reprova a pagina.** Timeout, recusa de autenticacao
   ou endpoint fora da fronteira produzem `indeterminate` ou `failed`, nunca
   `needs_correction`. E o guarda escrito no ADR de distribuicao organica.

3. **Ausencia de DNS falha FECHADA.** Um host que nao resolve nao e "publico
   por enquanto": e desconhecido, e desconhecido nao passa.
"""
from __future__ import annotations

import json

import pytest

from app.visual_proof import dominio as dom


# ─────────────────────────────────────────────────────────────────────────────
# 1. Politica de URL da superficie publicada
# ─────────────────────────────────────────────────────────────────────────────


def _resolver_falso(mapa: dict[str, list[str]]):
    """Duple de `socket.getaddrinfo` — devolve so os enderecos declarados.

    Injetado de proposito: uma prova de SSRF que depende do DNS real mede a
    internet, nao o codigo. E um host que hoje resolve para IP publico pode
    resolver para 127.0.0.1 amanha.
    """

    def resolver(host: str) -> list[str]:
        try:
            return mapa[host]
        except KeyError:
            raise dom.NomeNaoResolvido(host) from None

    return resolver


#: ⚠️ Os endereços aqui são ROTEÁVEIS de propósito, e a primeira versão deste
#: arquivo usava `203.0.113.x` (TEST-NET-3, RFC 5737). A política recusou todos
#: — corretamente: as faixas de documentação são `is_reserved`, ou seja, não
#: públicas. O teste media a coisa errada, não o código. A recusa das faixas de
#: documentação virou prova própria logo abaixo.
PUBLICO = _resolver_falso({
    "exemplo.com.br": ["93.184.216.34"],
    "www.exemplo.com.br": ["93.184.216.34"],
    "blog.exemplo.com.br": ["93.184.216.35"],
    "outro.com.br": ["104.18.32.7"],
    "duas-caras.com.br": ["93.184.216.34", "10.0.0.5"],
    "metadata-disfarcado.com.br": ["169.254.169.254"],
    "documentacao.com.br": ["203.0.113.10"],
})


def test_faixa_de_documentacao_nao_conta_como_publica():
    """RFC 5737 (`192.0.2/24`, `198.51.100/24`, `203.0.113/24`) não é roteável.

    Um host que resolve para elas não é uma superfície publicada: é um exemplo.
    Aceitá-lo faria o QA visual declarar sucesso sobre um endereço que ninguém
    consegue abrir.
    """
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(
            "https://documentacao.com.br/post", dominio_esperado=None, resolver=PUBLICO)


def test_url_publica_https_e_aceita():
    assert dom.exigir_url_de_superficie(
        "https://exemplo.com.br/post/123",
        dominio_esperado="exemplo.com.br",
        resolver=PUBLICO,
    ) == "https://exemplo.com.br/post/123"


def test_url_preserva_query_porque_post_publicado_carrega_query():
    """Divergencia DELIBERADA de `publisher_quality/fetch.py`.

    Aquele modulo apaga query e fragmento porque persiste artefato de leitura
    publica e nao quer guardar id de campanha. Aqui a query e parte do endereco
    a conferir: `?p=123` do WordPress e `?story_fbid=` do Facebook mudam a
    pagina. Apagar a query faria o QA visual conferir uma pagina diferente da
    publicada. O sigilo volta em `sanitizar_url_para_recibo`, que redige os
    VALORES da query antes de o endereco virar recibo.
    """
    assert dom.exigir_url_de_superficie(
        "https://exemplo.com.br/?p=123",
        dominio_esperado="exemplo.com.br",
        resolver=PUBLICO,
    ) == "https://exemplo.com.br/?p=123"


@pytest.mark.parametrize("url", [
    "http://exemplo.com.br/post",          # sem TLS
    "ftp://exemplo.com.br/post",           # esquema fora do contrato
    "https://user:senha@exemplo.com.br/",  # credencial embutida
    "https://exemplo.com.br:8443/post",    # porta fora do padrao
    "//exemplo.com.br/post",               # sem esquema
    "https:///post",                       # sem host
    "",
])
def test_url_malformada_ou_arriscada_e_recusada(url):
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(url, dominio_esperado="exemplo.com.br", resolver=PUBLICO)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/post",
    "https://localhost/post",
    "https://[::1]/post",
    "https://10.0.0.5/post",
    "https://192.168.1.10/post",
    "https://172.16.0.9/post",
    "https://169.254.169.254/latest/meta-data/",
    "https://100.100.100.200/latest/meta-data/",
    "https://metadata.google.internal/computeMetadata/v1/",
    "https://painel.internal/post",
    "https://impressora.local/post",
])
def test_endereco_privado_ou_de_metadados_e_recusado(url):
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(url, dominio_esperado=None, resolver=PUBLICO)


def test_host_que_nao_resolve_falha_fechado():
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(
            "https://nunca-existiu.example/post", dominio_esperado=None, resolver=PUBLICO)


def test_host_com_um_endereco_privado_entre_varios_e_recusado():
    """DNS rebinding barato: um A publico e um A privado no mesmo nome.

    Aceitar porque "pelo menos um e publico" deixa o navegador escolher o
    privado. A regra e TODOS publicos, ou nenhum.
    """
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(
            "https://duas-caras.com.br/post", dominio_esperado=None, resolver=PUBLICO)


def test_host_publico_que_resolve_para_metadados_e_recusado():
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(
            "https://metadata-disfarcado.com.br/", dominio_esperado=None, resolver=PUBLICO)


def test_dominio_esperado_e_confinamento_nao_sugestao():
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(
            "https://outro.com.br/post", dominio_esperado="exemplo.com.br", resolver=PUBLICO)


def test_subdominio_do_dominio_esperado_e_aceito():
    assert dom.exigir_url_de_superficie(
        "https://blog.exemplo.com.br/post", dominio_esperado="exemplo.com.br", resolver=PUBLICO)


def test_sufixo_parecido_nao_e_subdominio():
    """`malexemplo.com.br` termina com `exemplo.com.br` e NAO pertence a ele."""
    resolver = _resolver_falso({"malexemplo.com.br": ["104.18.32.99"]})
    with pytest.raises(dom.UrlRecusada):
        dom.exigir_url_de_superficie(
            "https://malexemplo.com.br/post", dominio_esperado="exemplo.com.br", resolver=resolver)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fronteira do endpoint do AdsPower
# ─────────────────────────────────────────────────────────────────────────────


def test_endpoint_em_loopback_na_porta_documentada_e_aceito():
    assert dom.exigir_endpoint_do_adspower("http://127.0.0.1:50325") == "http://127.0.0.1:50325"


def test_endpoint_aceita_porta_alternativa_declarada():
    assert dom.exigir_endpoint_do_adspower(
        "http://127.0.0.1:51999", portas_permitidas=(51999,)) == "http://127.0.0.1:51999"


@pytest.mark.parametrize("base", [
    "http://198.51.100.7:50325",              # host remoto
    "https://api.adspower.com",               # nuvem do fornecedor
    "http://local.adspower.net:50325",        # nome que resolve fora do controle local
    "http://127.0.0.1:8080",                  # porta fora da allowlist
    "http://127.0.0.1:50325/api/v1/browser",  # caminho embutido na base
    "file:///etc/passwd",
    "",
])
def test_endpoint_fora_da_fronteira_e_recusado(base):
    with pytest.raises(dom.EndpointRecusado):
        dom.exigir_endpoint_do_adspower(base)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Maquina de estados
# ─────────────────────────────────────────────────────────────────────────────


def test_os_dez_estados_minimos_existem():
    assert set(dom.ESTADOS_DO_JOB) >= {
        "requested", "authorized", "running", "captured", "approved",
        "needs_correction", "indeterminate", "failed", "cancelled", "expired",
    }


def test_transicao_legitima_e_aceita():
    assert dom.transicao_permitida("requested", "authorized")
    assert dom.transicao_permitida("authorized", "running")
    assert dom.transicao_permitida("running", "captured")
    assert dom.transicao_permitida("captured", "approved")


@pytest.mark.parametrize("de,para", [
    ("requested", "running"),      # pular a autorizacao
    ("requested", "approved"),     # aprovar sem capturar
    ("running", "approved"),       # aprovar sem captura registrada
    ("approved", "running"),       # ressuscitar terminal
    ("failed", "captured"),
    ("cancelled", "authorized"),
])
def test_transicao_ilegitima_e_recusada(de, para):
    assert not dom.transicao_permitida(de, para)
    with pytest.raises(dom.TransicaoInvalida):
        dom.exigir_transicao(de, para)


def test_estados_terminais_nao_saem_de_si():
    for terminal in dom.ESTADOS_TERMINAIS:
        for destino in dom.ESTADOS_DO_JOB:
            assert not dom.transicao_permitida(terminal, destino)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Veredito
# ─────────────────────────────────────────────────────────────────────────────


def _captura(**kwargs):
    base = dict(
        url_final="https://exemplo.com.br/post/123",
        url_esperada="https://exemplo.com.br/post/123",
        dominio_esperado="exemplo.com.br",
        status_http=200,
        console_erros=0,
        rede_falhas=0,
        redirecionamentos=0,
        artefato_bytes=48_000,
        conteudo_sha256="a" * 64,
        conteudo_sha256_esperado=None,
    )
    base.update(kwargs)
    return dom.LeituraDaSuperficie(**base)


def test_avaliacao_automatica_nunca_devolve_approved():
    """A prova central deste bloco.

    Nenhuma combinacao de leitura limpa produz `approved`: o melhor veredito
    automatico e `eligible_for_human_review`. Aprovar e ato humano.
    """
    veredito = dom.avaliar_captura(_captura())
    assert veredito.resultado == "eligible_for_human_review"
    assert veredito.resultado in dom.VEREDITOS_AUTOMATICOS
    assert "approved" not in dom.VEREDITOS_AUTOMATICOS


def test_url_final_divergente_pede_correcao():
    veredito = dom.avaliar_captura(_captura(url_final="https://exemplo.com.br/404"))
    assert veredito.resultado == "needs_correction"
    assert any("endereço" in j.lower() for j in veredito.justificativas)


def test_dominio_final_fora_do_esperado_pede_correcao():
    veredito = dom.avaliar_captura(
        _captura(url_final="https://outro.com.br/post/123"))
    assert veredito.resultado == "needs_correction"


def test_status_http_de_erro_pede_correcao():
    assert dom.avaliar_captura(_captura(status_http=404)).resultado == "needs_correction"
    assert dom.avaliar_captura(_captura(status_http=500)).resultado == "needs_correction"


def test_artefato_vazio_e_indeterminado_e_nao_reprovacao():
    """Screenshot de zero byte nao diz que a pagina esta errada: diz que nao vimos."""
    veredito = dom.avaliar_captura(_captura(artefato_bytes=0))
    assert veredito.resultado == "indeterminate"


def test_hash_de_conteudo_divergente_pede_correcao():
    veredito = dom.avaliar_captura(
        _captura(conteudo_sha256="b" * 64, conteudo_sha256_esperado="c" * 64))
    assert veredito.resultado == "needs_correction"


def test_erro_de_console_sozinho_nao_reprova_mas_e_registrado():
    veredito = dom.avaliar_captura(_captura(console_erros=3))
    assert veredito.resultado in ("eligible_for_human_review", "indeterminate")
    assert any("console" in j.lower() for j in veredito.justificativas)


def test_falha_tecnica_do_adspower_e_indeterminada_nunca_reprovacao():
    for motivo in ("timeout", "endpoint_recusado", "autenticacao_recusada", "perfil_indisponivel"):
        veredito = dom.veredito_de_falha_tecnica(motivo)
        assert veredito.resultado == "indeterminate", motivo
        assert veredito.resultado != "needs_correction"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Sanitizacao — o que nunca pode sair num recibo
# ─────────────────────────────────────────────────────────────────────────────


SENTINELA = "VOLC-SENTINELA-SEGREDO-4c1f9a2b7e"


@pytest.mark.parametrize("texto", [
    "op://VOLC/Pagina Piloto/credential",
    "op://VOLC/Perfil/ADSPOWER_API_KEY",
    "Authorization: Bearer abcdefghijklmnopqrstuvwx",
    "Cookie: c_user=1234567890; xs=abc",
    "http://usuario:senha@proxy.exemplo:8080",
    "-----" + "BEGIN RSA " + "PRIVATE KEY" + "-----",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0",
])
def test_material_sensivel_e_removido_do_texto(texto):
    limpo = dom.sanitizar_texto(texto)
    assert "op://" not in limpo
    assert "Bearer " not in limpo
    assert "c_user" not in limpo
    assert "senha@" not in limpo
    assert "BEGIN RSA" not in limpo
    assert "eyJhbGciOiJIUzI1NiJ9." not in limpo
    assert dom.REDIGIDO in limpo


def test_sanitizar_url_para_recibo_mantem_caminho_e_redige_valor_de_query():
    saida = dom.sanitizar_url_para_recibo("https://exemplo.com.br/post?p=123&token=abcdef")
    assert saida.startswith("https://exemplo.com.br/post?")
    assert "p=" in saida and "token=" in saida
    assert "123" not in saida
    assert "abcdef" not in saida


def test_recusar_valor_sensivel_percorre_documento_inteiro():
    doc = {"a": [{"b": {"c": f"prefixo {SENTINELA} sufixo"}}]}
    with pytest.raises(dom.VazamentoDetectado) as erro:
        dom.recusar_valor_sensivel(doc, sentinelas=(SENTINELA,))
    # A excecao aponta o CAMINHO e nao repete o valor.
    assert "a[0].b.c" in str(erro.value)
    assert SENTINELA not in str(erro.value)


def test_recusar_valor_sensivel_aceita_documento_limpo():
    dom.recusar_valor_sensivel({"perfil_logico": "PERFIL_PILOTO_01"}, sentinelas=(SENTINELA,))


def test_sentinela_curta_demais_e_recusada_como_sentinela():
    """Uma sentinela de 3 caracteres casaria com meio recibo e daria falso alarme."""
    with pytest.raises(ValueError):
        dom.recusar_valor_sensivel({"x": "abc"}, sentinelas=("abc",))


# ─────────────────────────────────────────────────────────────────────────────
# 6. Impressao digital do pedido (idempotencia)
# ─────────────────────────────────────────────────────────────────────────────


def test_impressao_e_estavel_para_o_mesmo_conteudo_em_ordem_diferente():
    a = dom.impressao_do_pedido({"x": 1, "y": [1, 2], "z": {"k": "v"}})
    b = dom.impressao_do_pedido({"z": {"k": "v"}, "y": [1, 2], "x": 1})
    assert a == b and len(a) == 64


def test_impressao_muda_quando_o_conteudo_muda():
    a = dom.impressao_do_pedido({"url": "https://exemplo.com.br/a"})
    b = dom.impressao_do_pedido({"url": "https://exemplo.com.br/b"})
    assert a != b


def test_impressao_recusa_conteudo_nao_serializavel():
    with pytest.raises(TypeError):
        dom.impressao_do_pedido({"x": object()})


# ─────────────────────────────────────────────────────────────────────────────
# 7. Contratos
# ─────────────────────────────────────────────────────────────────────────────


def test_browser_profile_reference_nao_carrega_id_bruto_do_adspower():
    ref = dom.BrowserProfileReference(
        ativo_id="asset:browser-profile:piloto",
        perfil_logico="PERFIL_PILOTO_01",
        owner_sub="sub-a",
        provider="1password",
        credencial_nome_logico="ADSPOWER_API_KEY",
    )
    como_dict = ref.para_dicionario()
    assert "user_id" not in json.dumps(como_dict)
    assert como_dict["perfil_logico"] == "PERFIL_PILOTO_01"
    # Nao existe campo para localizador: a classe nem o aceita.
    with pytest.raises(TypeError):
        dom.BrowserProfileReference(
            ativo_id="asset:browser-profile:piloto", perfil_logico="P", owner_sub="s",
            provider="1password", credencial_nome_logico="K",
            localizador="op://VOLC/x/y",  # type: ignore[call-arg]
        )


def test_perfil_logico_segue_gramatica_de_nome_logico():
    for bom in ("PERFIL_PILOTO_01", "P1"):
        dom.exigir_perfil_logico(bom)
    for ruim in ("perfil", "1PERFIL", "PERFIL-PILOTO", "op://x/y/z", "", "P" * 200):
        with pytest.raises(dom.PayloadRecusado):
            dom.exigir_perfil_logico(ruim)


def test_visual_proof_job_carrega_os_campos_minimos_da_missao():
    job = dom.VisualProofJob.novo(
        job_id="vpj_0001",
        owner_sub="sub-a",
        ativo_id="asset:facebook-page:piloto",
        perfil=dom.BrowserProfileReference(
            ativo_id="asset:browser-profile:piloto", perfil_logico="PERFIL_PILOTO_01",
            owner_sub="sub-a", provider="1password", credencial_nome_logico="ADSPOWER_API_KEY"),
        url_esperada="https://exemplo.com.br/post/123",
        dominio_esperado="exemplo.com.br",
        viewport=dom.Viewport(largura=1366, altura=768),
        timezone="America/Sao_Paulo",
        classe_de_agente="desktop-chromium",
        chave_idempotencia="vpj-piloto-2026-09-02-01",
        criado_em="2026-09-02T12:00:00+00:00",
        timeout_s=45,
    )
    d = job.para_dicionario()
    for campo in (
        "job_id", "owner_sub", "ativo_id", "perfil", "url_esperada", "url_final",
        "dominio_esperado", "viewport", "timezone", "classe_de_agente",
        "criado_em", "timeout_s", "tentativas", "chave_idempotencia",
        "conteudo_sha256_esperado", "artefato", "console_resumo", "rede_resumo",
        "redirecionamentos", "checagens", "recibo_id", "veredito",
        "justificativas", "revisao_humana", "estado",
    ):
        assert campo in d, campo
    assert d["estado"] == "requested"
    # Fingerprint de navegador NAO entra: classe, e nao impressao digital.
    assert "user_agent" not in d and "fingerprint" not in json.dumps(d)


def test_job_aprovado_exige_revisor_humano():
    job = _job_capturado()
    with pytest.raises(dom.TransicaoInvalida):
        job.aprovar(revisor=None, nota="ok")  # type: ignore[arg-type]
    job.aprovar(revisor="tarcisio", nota="conferi a pagina publicada")
    assert job.estado == "approved"
    assert job.revisao_humana and job.revisao_humana["revisor"] == "tarcisio"


def test_job_nao_pode_ser_aprovado_direto_de_requested():
    job = _job_novo()
    with pytest.raises(dom.TransicaoInvalida):
        job.aprovar(revisor="tarcisio", nota="sem captura")


def test_artefato_guarda_referencia_e_hash_nunca_os_bytes():
    artefato = dom.VisualProofArtifact(
        referencia="vpartifact://piloto/vpj_0001/captura.png",
        sha256="d" * 64, bytes_=48_000, mime="image/png",
        criado_em="2026-09-02T12:00:10+00:00")
    d = artefato.para_dicionario()
    assert set(d) == {"referencia", "sha256", "bytes", "mime", "criado_em"}
    assert "conteudo" not in d and "base64" not in d


def _job_novo() -> dom.VisualProofJob:
    return dom.VisualProofJob.novo(
        job_id="vpj_0001", owner_sub="sub-a", ativo_id="asset:facebook-page:piloto",
        perfil=dom.BrowserProfileReference(
            ativo_id="asset:browser-profile:piloto", perfil_logico="PERFIL_PILOTO_01",
            owner_sub="sub-a", provider="1password", credencial_nome_logico="ADSPOWER_API_KEY"),
        url_esperada="https://exemplo.com.br/post/123", dominio_esperado="exemplo.com.br",
        viewport=dom.Viewport(largura=1366, altura=768), timezone="America/Sao_Paulo",
        classe_de_agente="desktop-chromium", chave_idempotencia="vpj-piloto-2026-09-02-01",
        criado_em="2026-09-02T12:00:00+00:00", timeout_s=45)


def _job_capturado() -> dom.VisualProofJob:
    job = _job_novo()
    job.autorizar()
    job.iniciar(recibo_id="rcp_0001")
    job.registrar_captura(
        url_final="https://exemplo.com.br/post/123",
        artefato=dom.VisualProofArtifact(
            referencia="vpartifact://piloto/vpj_0001/captura.png", sha256="d" * 64,
            bytes_=48_000, mime="image/png", criado_em="2026-09-02T12:00:10+00:00"),
        console_resumo={"erros": 0, "avisos": 1},
        rede_resumo={"falhas": 0, "requisicoes": 12},
        redirecionamentos=[],
        checagens=[{"nome": "url_final", "resultado": "ok"}],
        veredito=dom.avaliar_captura(_captura()),
    )
    return job
