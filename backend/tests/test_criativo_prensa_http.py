"""O adaptador da PRENSA: falha fechada, motivo preservado, sem rede nos testes."""
import base64, io, json, urllib.error
import pytest

from app.criativo.bancada.adaptadores import prensa_http as prensa


def test_sem_endereco_configurado_falha_ao_inves_de_inventar_padrao(monkeypatch):
    monkeypatch.delenv(prensa.VARIAVEL_DE_ENDERECO, raising=False)
    with pytest.raises(prensa.PrensaIndisponivel, match=prensa.VARIAVEL_DE_ENDERECO):
        prensa.endereco()


def test_recusa_do_motor_vira_veredito_e_nao_erro_de_transporte(monkeypatch):
    """422 é a escada de gates reprovando — e o motivo precisa sobreviver."""
    monkeypatch.setenv(prensa.VARIAVEL_DE_ENDERECO, "http://prensa.local:8020")
    detalhe = json.dumps({"detail": {
        "codigo": "PRENSA_RECUSOU",
        "erro": "gate de contraste: handle 2,56:1 abaixo do piso",
    }}).encode()

    def recusa(*_a, **_k):
        raise urllib.error.HTTPError("u", 422, "Unprocessable", {}, io.BytesIO(detalhe))

    monkeypatch.setattr(prensa.urllib.request, "urlopen", recusa)
    with pytest.raises(prensa.FalhaDaPrensa) as erro:
        prensa.imprimir({"schema_version": "post.spec/1.0.0"})
    assert erro.value.codigo == "PRENSA_RECUSOU"
    assert "contraste" in erro.value.motivo


def test_servico_fora_do_ar_nao_e_confundido_com_recusa(monkeypatch):
    monkeypatch.setenv(prensa.VARIAVEL_DE_ENDERECO, "http://prensa.local:8020")

    def cai(*_a, **_k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(prensa.urllib.request, "urlopen", cai)
    with pytest.raises(prensa.PrensaIndisponivel):
        prensa.imprimir({})


def test_artefato_volta_com_bytes_e_as_duas_provas(monkeypatch):
    monkeypatch.setenv(prensa.VARIAVEL_DE_ENDERECO, "http://prensa.local:8020")
    corpo = json.dumps({"artefatos": [{
        "nome": "peca_s01.png",
        "png_base64": base64.b64encode(b"\x89PNG-falso").decode(),
        "veredito": {"ok": True},
        "pixelgate": {"contraste": 12.4},
    }]}).encode()

    class Resposta(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr(prensa.urllib.request, "urlopen", lambda *_a, **_k: Resposta(corpo))
    pecas = prensa.imprimir({"schema_version": "post.spec/1.0.0"})
    assert len(pecas) == 1 and pecas[0].conteudo == b"\x89PNG-falso"
    assert pecas[0].veredito == {"ok": True} and pecas[0].pixelgate["contraste"] == 12.4
