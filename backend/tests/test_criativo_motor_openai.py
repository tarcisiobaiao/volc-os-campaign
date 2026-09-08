"""O contrato do motor `gpt-image-2`, provado sem rede, sem chave e sem gastar.

## O que estas contraprovas existem para impedir

Cada uma delas corresponde a um defeito que já foi observado em código real
deste mesmo domínio — a cópia sanitizada do Aprova que vive em
`services/creative-studio/upstream/` — ou a uma armadilha que a documentação
oficial descreve explicitamente:

  * mandar `input_fidelity` para o `gpt-image-2` (a doc manda OMITIR);
  * omitir `model` e receber `gpt-image-1.5` em `/edits` ou `dall-e-2` em
    `/generations`, que são os defaults documentados;
  * decidir retry lendo o TEXTO da mensagem de erro (`if "size" in msg`);
  * mandar uma dimensão que o envelope recusa e descobrir pagando;
  * transformar "não sei o preço" em `0.0`;
  * cair para outro provider quando o pedido falha.

O transporte é sempre um dublê. `LIVE_GENERATION_VERIFIED` continua `false`:
nenhum teste deste arquivo abre socket.
"""

from __future__ import annotations

import base64
import io
import json

import pytest

from services.creative_engine import envelope_openai as envelope
from services.creative_engine.motores import openai_imagem as motor_mod
from services.creative_engine.motores.openai_imagem import (
    MODELO,
    PRECO_REFERENCIA_USD_POR_IMAGEM,
    QUALIDADE,
    SLUG,
    MotorOpenAIImagem,
    RespostaHTTP,
)
from volc_ads.criativo.contrato import EspecificacaoDeAsset, TipoDeAsset
from volc_ads.criativo.porta import (
    ImagemDeReferencia,
    MotorDeCriativo,
    MotorIndisponivel,
    PedidoDeGeracao,
    PedidoDesconhecido,
    PedidoRecusado,
)


# ── dublês ───────────────────────────────────────────────────────────────────


def _png(largura: int, altura: int) -> bytes:
    """Um PNG real, para que `enquadrar` tenha o que medir e recortar."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), (40, 90, 160)).save(buffer, format="PNG")
    return buffer.getvalue()


def _corpo(largura: int = 1024, altura: int = 1024, **extra) -> dict:
    corpo = {
        "data": [{"b64_json": base64.b64encode(_png(largura, altura)).decode("ascii")}],
        "usage": {"input_tokens": 120, "output_tokens": 4160},
    }
    corpo.update(extra)
    return corpo


class TransporteFalso:
    """Registra o que foi pedido e devolve o que mandarem. Nunca abre socket."""

    def __init__(self, resposta=None, erro: Exception | None = None) -> None:
        self.resposta = resposta if resposta is not None else _corpo()
        self.erro = erro
        self.chamadas: list[dict] = []

    def post_json(self, url, payload, chave, timeout):
        self.chamadas.append(
            {"tipo": "json", "url": url, "payload": payload, "chave": chave}
        )
        if self.erro:
            raise self.erro
        return self.resposta

    def post_multipart(self, url, campos, arquivos, chave, timeout):
        self.chamadas.append(
            {
                "tipo": "multipart",
                "url": url,
                "campos": campos,
                "arquivos": list(arquivos),
                "chave": chave,
            }
        )
        if self.erro:
            raise self.erro
        return self.resposta


def _pedido(largura: int = 1080, altura: int = 1080, referencias=()) -> PedidoDeGeracao:
    return PedidoDeGeracao(
        referencia="estudio/1x1",
        tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
        insumo="Mesa de estudo com luz natural.",
        especificacao=EspecificacaoDeAsset(
            tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
            largura_recomendada=largura,
            altura_recomendada=altura,
            fonte_dos_numeros="teste",
        ),
        referencias=tuple(referencias),
    )


def _rodar(motor: MotorOpenAIImagem, pedido: PedidoDeGeracao):
    return motor.receber(motor.solicitar_geracao(pedido))


# ═══════════════════════════════════════════════════════════════════════════
# 1. IDENTIDADE — o modelo e a qualidade são impostos, não configuráveis
# ═══════════════════════════════════════════════════════════════════════════


def test_o_motor_cumpre_a_porta_e_se_identifica_sem_ambiguidade():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    assert isinstance(motor, MotorDeCriativo)
    assert motor.nome == "openai:gpt-image-2"
    assert motor.slug == SLUG == "openai-gpt-image-2"
    # O slug precisa caber em `criativo_motor_slug_forma`.
    import re

    assert re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{1,62}", motor.slug)


def test_o_pedido_carrega_exatamente_gpt_image_2_e_medium():
    """A autorização de gasto nomeia estes dois valores. Eles não podem variar."""
    transporte = TransporteFalso()
    _rodar(MotorOpenAIImagem(chave="x", transporte=transporte), _pedido())

    payload = transporte.chamadas[0]["payload"]
    assert payload["model"] == "gpt-image-2"
    assert payload["quality"] == "medium"


def test_o_construtor_nao_aceita_trocar_modelo_nem_qualidade():
    """Um construtor que aceitasse os dois permitiria assinar um ato e rodar outro."""
    with pytest.raises(TypeError):
        MotorOpenAIImagem(chave="x", modelo="gpt-image-1")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        MotorOpenAIImagem(chave="x", qualidade="high")  # type: ignore[call-arg]


def test_o_modulo_do_motor_nao_conhece_gemini():
    """Sem import de Gemini não existe substituição silenciosa a implementar."""
    from pathlib import Path

    fonte = Path(motor_mod.__file__).read_text(encoding="utf-8")
    codigo = "\n".join(
        linha for linha in fonte.splitlines() if not linha.strip().startswith("#")
    )
    # O cabeçalho cita o motor irmão em prosa; o que não pode existir é IMPORT.
    assert "import gemini" not in codigo
    assert "from ..motores.gemini" not in codigo
    assert "MotorGeminiImagem" not in codigo


# ═══════════════════════════════════════════════════════════════════════════
# 2. ENVELOPE — nenhuma dimensão inventada chega ao provider
# ═══════════════════════════════════════════════════════════════════════════


def test_o_size_enviado_sempre_passa_nas_quatro_regras_oficiais():
    from app.criativo import dominio

    for formato in dominio.FORMATOS:
        transporte = TransporteFalso()
        motor = MotorOpenAIImagem(chave="x", transporte=transporte)
        _rodar(motor, _pedido(formato.largura, formato.altura))
        size = transporte.chamadas[0]["payload"]["size"]
        largura, altura = (int(p) for p in size.split("x"))
        assert envelope.tamanho_aceito(largura, altura), (
            f"{formato.slot}: o motor pediria {size}, que o provider recusa"
        )


def test_nenhum_formato_comercial_e_enviado_cru_ao_provider():
    """1080 e 628 não são múltiplos de 16: pedir a medida final é um 400 pago."""
    from app.criativo import dominio

    for formato in dominio.FORMATOS:
        assert not envelope.tamanho_aceito(formato.largura, formato.altura), (
            f"{formato.slot} passou a caber no envelope; este teste precisa ser revisto"
        )


def test_a_peca_final_sai_na_dimensao_pedida_e_nao_na_nativa():
    transporte = TransporteFalso(_corpo(1024, 1280))
    motor = MotorOpenAIImagem(chave="x", transporte=transporte)
    resposta = _rodar(motor, _pedido(1080, 1350))

    arquivo = resposta.arquivos[0]
    assert (arquivo.largura, arquivo.altura) == (1080, 1350)
    assert arquivo.metadados["canvas_largura"] == "1024"
    assert arquivo.metadados["canvas_altura"] == "1280"


def test_o_canvas_de_4x5_preserva_a_proporcao_exata():
    """1024x1280 é 0,8 exato. 1088x1344 seria 0,8095 e recortaria 1,19% à toa."""
    canvas = envelope.canvas_para(1080, 1350)
    assert (canvas.largura, canvas.altura) == (1024, 1280)
    assert canvas.derivado is True
    assert canvas.largura / canvas.altura == pytest.approx(1080 / 1350)


def test_proporcao_fora_do_envelope_cai_para_canvas_NOMEADO_e_diz_por_que():
    """3,33:1 passa do limite de 3:1. O desvio é geométrico e declarado."""
    canvas = envelope.canvas_para(2000, 600)
    assert canvas.derivado is False
    assert (canvas.largura, canvas.altura) in envelope.NOMEADO_POR_ORIENTACAO.values()
    assert canvas.motivo
    assert envelope.tamanho_aceito(canvas.largura, canvas.altura)


def test_o_piso_de_pixels_do_provider_e_respeitado():
    """655.360 px é o piso oficial: 512x512 seria recusado."""
    assert not envelope.tamanho_aceito(512, 512)
    canvas = envelope.canvas_para(512, 512)
    assert canvas.pixels >= envelope.PIXELS_MINIMOS
    assert envelope.tamanho_aceito(canvas.largura, canvas.altura)


def test_pedido_sem_dimensao_e_recusado_antes_da_rede():
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave="x", transporte=transporte)
    pedido = PedidoDeGeracao(
        referencia="estudio/1x1",
        tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
        insumo="algo",
    )
    with pytest.raises(PedidoRecusado):
        motor.solicitar_geracao(pedido)
    assert transporte.chamadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. PARÂMETROS — o que nunca pode ser enviado
# ═══════════════════════════════════════════════════════════════════════════


def test_input_fidelity_nunca_e_enviado():
    """A doc do gpt-image-2 manda OMITIR. Mandar "por garantia" é um 400 pago."""
    for referencias in ((), (ImagemDeReferencia("f.png", _png(64, 64), "image/png"),)):
        transporte = TransporteFalso()
        _rodar(
            MotorOpenAIImagem(chave="x", transporte=transporte),
            _pedido(referencias=referencias),
        )
        chamada = transporte.chamadas[0]
        corpo = chamada.get("payload") or chamada.get("campos")
        assert "input_fidelity" not in corpo


def test_response_format_nunca_e_enviado():
    """Modelos GPT-image sempre devolvem base64; o parâmetro é do DALL-E."""
    transporte = TransporteFalso()
    _rodar(MotorOpenAIImagem(chave="x", transporte=transporte), _pedido())
    assert "response_format" not in transporte.chamadas[0]["payload"]


def test_model_e_sempre_explicito_nos_dois_endpoints():
    """O default de /edits é gpt-image-1.5 e o de /generations é dall-e-2."""
    sem_foto = TransporteFalso()
    _rodar(MotorOpenAIImagem(chave="x", transporte=sem_foto), _pedido())
    assert sem_foto.chamadas[0]["payload"]["model"] == MODELO

    com_foto = TransporteFalso()
    _rodar(
        MotorOpenAIImagem(chave="x", transporte=com_foto),
        _pedido(referencias=(ImagemDeReferencia("f.png", _png(64, 64), "image/png"),)),
    )
    assert com_foto.chamadas[0]["campos"]["model"] == MODELO


# ═══════════════════════════════════════════════════════════════════════════
# 4. OS DOIS ENDPOINTS — JSON sem anexo, multipart com anexo
# ═══════════════════════════════════════════════════════════════════════════


def test_sem_anexo_usa_generations_com_corpo_json():
    transporte = TransporteFalso()
    _rodar(MotorOpenAIImagem(chave="x", transporte=transporte), _pedido())
    chamada = transporte.chamadas[0]
    assert chamada["tipo"] == "json"
    assert chamada["url"] == "https://api.openai.com/v1/images/generations"


def test_com_anexo_usa_edits_com_multipart_e_os_bytes_do_anexo():
    foto = ImagemDeReferencia("foto.png", _png(300, 400), "image/png")
    transporte = TransporteFalso()
    _rodar(
        MotorOpenAIImagem(chave="x", transporte=transporte), _pedido(referencias=(foto,))
    )
    chamada = transporte.chamadas[0]
    assert chamada["tipo"] == "multipart"
    assert chamada["url"] == "https://api.openai.com/v1/images/edits"
    assert chamada["arquivos"][0].conteudo == foto.conteudo
    assert chamada["campos"]["quality"] == QUALIDADE


def test_anexo_acima_do_teto_do_provider_e_recusa_permanente_sem_chamada():
    grande = ImagemDeReferencia(
        "f.png", b"\x89PNG" + b"0" * (motor_mod.MAX_BYTES_POR_REFERENCIA + 1), "image/png"
    )
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave="x", transporte=transporte)
    with pytest.raises(PedidoRecusado) as capturado:
        motor.solicitar_geracao(_pedido(referencias=(grande,)))
    assert capturado.value.permanente is True
    assert transporte.chamadas == []


def test_mais_de_dezesseis_anexos_e_recusa_permanente_sem_chamada():
    fotos = tuple(
        ImagemDeReferencia(f"f{i}.png", _png(32, 32), "image/png") for i in range(17)
    )
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave="x", transporte=transporte)
    with pytest.raises(PedidoRecusado):
        motor.solicitar_geracao(_pedido(referencias=fotos))
    assert transporte.chamadas == []


def test_mime_que_o_provider_nao_aceita_e_recusado_sem_chamada():
    ruim = ImagemDeReferencia("f.gif", _png(32, 32), "image/gif")
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave="x", transporte=transporte)
    with pytest.raises(PedidoRecusado):
        motor.solicitar_geracao(_pedido(referencias=(ruim,)))
    assert transporte.chamadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. RESPOSTA — base64, modelo servido, e o que vai para o recibo
# ═══════════════════════════════════════════════════════════════════════════


def test_le_b64_json_e_devolve_bytes_de_imagem():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    resposta = _rodar(motor, _pedido())
    assert resposta.arquivos[0].conteudo.startswith(b"\x89PNG")


def test_modelo_servido_divergente_chega_aos_metadados():
    """Um rebaixamento silencioso do modelo é o gasto que mais importa detectar."""
    transporte = TransporteFalso(_corpo(model="gpt-image-1.5"))
    motor = MotorOpenAIImagem(chave="x", transporte=transporte)
    arquivo = _rodar(motor, _pedido()).arquivos[0]
    assert arquivo.metadados["modelo_pedido"] == "gpt-image-2"
    assert arquivo.metadados["modelo_servido"] == "gpt-image-1.5"


def test_modelo_servido_ausente_nao_e_preenchido_com_o_pedido():
    """Afirmar que servido == pedido sem prova é inventar a prova."""
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso(_corpo()))
    arquivo = _rodar(motor, _pedido()).arquivos[0]
    assert arquivo.metadados["modelo_servido"] == ""


def test_a_qualidade_e_o_hash_do_prompt_viajam_no_recibo():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    arquivo = _rodar(motor, _pedido()).arquivos[0]
    assert arquivo.metadados["qualidade"] == "medium"
    assert len(arquivo.metadados["prompt_sha256"]) == 64
    int(arquivo.metadados["prompt_sha256"], 16)


def test_o_hash_do_anexo_viaja_no_recibo():
    foto = ImagemDeReferencia("foto.png", _png(300, 400), "image/png")
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    arquivo = _rodar(motor, _pedido(referencias=(foto,))).arquivos[0]
    assert arquivo.metadados["referencias_sha256"] == foto.sha256


def test_resposta_200_sem_imagem_e_recusa_permanente():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso({"data": []}))
    with pytest.raises(PedidoRecusado) as capturado:
        _rodar(motor, _pedido())
    assert capturado.value.permanente is True


def test_base64_ilegivel_vira_falha_e_nao_asset_corrompido():
    from services.creative_engine.motores.openai_imagem import GeracaoFracassada

    motor = MotorOpenAIImagem(
        chave="x", transporte=TransporteFalso({"data": [{"b64_json": "não é base64!!"}]})
    )
    with pytest.raises(GeracaoFracassada):
        _rodar(motor, _pedido())


# ═══════════════════════════════════════════════════════════════════════════
# 6. CUSTO — não sei nunca vira zero
# ═══════════════════════════════════════════════════════════════════════════


def test_o_motor_declara_que_nao_ha_preco_por_imagem_publicado():
    assert PRECO_REFERENCIA_USD_POR_IMAGEM is None
    assert MotorOpenAIImagem(chave="x").preco_referencia_usd_por_imagem is None


def test_o_custo_do_arquivo_e_None_e_nao_zero():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    resposta = _rodar(motor, _pedido())
    assert resposta.custo_usd is None
    assert resposta.arquivos[0].custo_usd is None


def test_o_preco_do_gemini_nao_aparece_neste_motor():
    from pathlib import Path

    fonte = Path(motor_mod.__file__).read_text(encoding="utf-8")
    assert "0.039" not in fonte


def test_os_tokens_reportados_pelo_provider_chegam_aos_metadados():
    """Token é o que o provider mede. Sem ele não há como reconciliar fatura."""
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    arquivo = _rodar(motor, _pedido()).arquivos[0]
    assert arquivo.metadados["tokens_saida"] == "4160"
    assert arquivo.metadados["tokens_entrada"] == "120"


# ═══════════════════════════════════════════════════════════════════════════
# 7. ERROS — status e código fechado, nunca texto de mensagem
# ═══════════════════════════════════════════════════════════════════════════


def _erro(status: int, codigo: str = "", mensagem: str = "") -> RespostaHTTP:
    corpo = json.dumps(
        {"error": {"message": mensagem, "type": "invalid_request_error", "code": codigo}}
    )
    return RespostaHTTP(status=status, corpo=corpo)


@pytest.mark.parametrize(
    "status,esperado,permanente",
    [
        (401, MotorIndisponivel, False),
        (403, MotorIndisponivel, False),
        (429, MotorIndisponivel, False),
        (400, PedidoRecusado, True),
        (404, PedidoRecusado, True),
        (413, PedidoRecusado, True),
        (422, PedidoRecusado, True),
        (500, MotorIndisponivel, False),
        (503, MotorIndisponivel, False),
    ],
)
def test_status_http_vira_erro_tipado_com_permanencia_correta(
    status, esperado, permanente
):
    motor = MotorOpenAIImagem(
        chave="x", transporte=TransporteFalso(erro=_erro(status))
    )
    with pytest.raises(esperado) as capturado:
        _rodar(motor, _pedido())
    assert capturado.value.permanente is permanente


def test_a_classificacao_do_erro_nao_depende_do_texto_da_mensagem():
    """A referência do Aprova decide retry com `if "size" in msg.lower()`.

    Aqui a mesma mensagem em dois status precisa dar dois resultados, e dois
    textos diferentes no mesmo status precisam dar o mesmo — que é a definição de
    "a mensagem não participa da decisão".
    """
    frases = ["invalid size parameter", "algo completamente diferente", ""]
    for frase in frases:
        motor = MotorOpenAIImagem(
            chave="x", transporte=TransporteFalso(erro=_erro(400, mensagem=frase))
        )
        with pytest.raises(PedidoRecusado):
            _rodar(motor, _pedido())

    for frase in frases:
        motor = MotorOpenAIImagem(
            chave="x", transporte=TransporteFalso(erro=_erro(500, mensagem=frase))
        )
        with pytest.raises(MotorIndisponivel):
            _rodar(motor, _pedido())


def test_erro_de_size_nao_e_reenviado_num_tamanho_diferente():
    """A referência do Aprova retenta em `STANDARD_SIZES` lendo o texto do erro.

    Retentar é uma SEGUNDA chamada paga decidida por uma frase em inglês. Aqui o
    desvio de canvas acontece antes, por geometria, e um 400 é um 400.
    """
    transporte = TransporteFalso(erro=_erro(400, codigo="invalid_size"))
    motor = MotorOpenAIImagem(chave="x", transporte=transporte)
    with pytest.raises(PedidoRecusado):
        _rodar(motor, _pedido())
    assert len(transporte.chamadas) == 1


def test_a_mensagem_do_provider_nunca_sobe_para_o_operador():
    """O corpo do erro pode conter o prompt inteiro."""
    segredo = "PROMPT-SECRETO-QUE-NAO-PODE-VAZAR"
    motor = MotorOpenAIImagem(
        chave="x", transporte=TransporteFalso(erro=_erro(400, mensagem=segredo))
    )
    with pytest.raises(PedidoRecusado) as capturado:
        _rodar(motor, _pedido())
    assert segredo not in str(capturado.value)
    assert segredo not in capturado.value.motivo


# ═══════════════════════════════════════════════════════════════════════════
# 8. CREDENCIAL — falha fechada, e a chave não vaza
# ═══════════════════════════════════════════════════════════════════════════


def test_sem_chave_falha_ANTES_de_qualquer_chamada():
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave="", transporte=transporte)
    assert motor.configurado is False
    with pytest.raises(MotorIndisponivel):
        motor.solicitar_geracao(_pedido())
    assert transporte.chamadas == []


def test_sem_chave_nao_ha_troca_de_provider():
    """Falhar fechado é o contrato. Um fallback aqui geraria com outro modelo."""
    motor = MotorOpenAIImagem(chave="", transporte=TransporteFalso())
    with pytest.raises(MotorIndisponivel) as capturado:
        motor.solicitar_geracao(_pedido())
    assert "gemini" not in str(capturado.value).lower()


def test_a_chave_nao_aparece_na_url_nem_nos_metadados():
    """Chave em query string vaza em log de proxy. Ela vai no header."""
    segredo = "sk-CHAVE-SECRETA-DE-TESTE"
    transporte = TransporteFalso()
    motor = MotorOpenAIImagem(chave=segredo, transporte=transporte)
    arquivo = _rodar(motor, _pedido()).arquivos[0]

    assert segredo not in transporte.chamadas[0]["url"]
    assert segredo not in json.dumps(transporte.chamadas[0]["payload"])
    assert segredo not in json.dumps(arquivo.metadados, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# 9. O CONTRATO DE DOIS PASSOS
# ═══════════════════════════════════════════════════════════════════════════


def test_receber_entrega_uma_vez_e_solta_da_memoria():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    identificador = motor.solicitar_geracao(_pedido())
    assert motor.receber(identificador).arquivos
    with pytest.raises(PedidoDesconhecido):
        motor.receber(identificador)


def test_id_desconhecido_e_erro_permanente():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    with pytest.raises(PedidoDesconhecido) as capturado:
        motor.receber("oai_inexistente")
    assert capturado.value.permanente is True


def test_tipo_que_nao_e_imagem_e_recusado():
    motor = MotorOpenAIImagem(chave="x", transporte=TransporteFalso())
    pedido = PedidoDeGeracao(
        referencia="x", tipo=TipoDeAsset.VIDEO, insumo="algo"
    )
    with pytest.raises(PedidoRecusado):
        motor.solicitar_geracao(pedido)
