"""Motor de imagem `gpt-image-2` da OpenAI — provider de primeira classe.

Implementa `volc_ads.criativo.porta.MotorDeCriativo`. Não reimplementa nenhum
vocabulário: `Asset`, `Procedencia`, `Falha` e os erros tipados já existem em
`volc_ads/criativo/`, e duplicá-los aqui criaria divergência no dia um.

## Por que este arquivo NÃO é o `MotorGeminiImagem` renomeado

Porque os dois falam protocolos diferentes o suficiente para que uma classe só
com um `if` no meio mentisse sobre os dois. O Gemini manda um JSON para
`:generateContent` e pede a proporção em `imageConfig.aspectRatio`; o
`gpt-image-2` tem DOIS endpoints (`/v1/images/generations`, JSON, e
`/v1/images/edits`, multipart), pede a medida em pixels no campo `size` sob
quatro regras aritméticas, e sempre devolve base64. Além disso o preço é por
token. Exemplos publicados de custo de saída não constituem um teto total
para nossos tamanhos e entradas variáveis.

Fundir os dois faria a identidade do que rodou depender de leitura de
configuração, e a pergunta que este produto precisa responder — "o que gerou e
cobrou esta peça?" — passaria a ter duas respostas possíveis para o mesmo nome.

## O que é imposto aqui e não é negociável pelo chamador

    model    = "gpt-image-2"   (constante do módulo, nunca parâmetro de pedido)
    quality  = "medium"        (constante do módulo, nunca parâmetro de pedido)

Nenhum dos dois entra por `PedidoDeGeracao`, por header, por query ou por
variável de ambiente. A autorização de gasto que o operador assina nomeia
`openai:gpt-image-2` e a qualidade `medium`; se qualquer uma delas pudesse ser
trocada por configuração, a assinatura estaria cobrindo um ato diferente do que
rodaria.

⚠️ Também não há substituição silenciosa por Gemini. Este motor não conhece
outro provider, não importa `gemini_imagem` e não tem fallback: sem
`OPENAI_API_KEY` ele **falha fechado**, e quem escolhe qual motor sobe é
`backend/app/routers/criativos.py::obter_motor`, uma camada acima, também sem
troca automática.

## `input_fidelity` é omitido de propósito

A documentação oficial do `gpt-image-2` diz literalmente para OMITIR o
parâmetro: o modelo já processa toda entrada em alta fidelidade e a API não
aceita mudar isso. Mandá-lo "por garantia" é o tipo de cópia de código de
`gpt-image-1` que troca uma geração paga por um 400.

## O preço: `None`, e isso é uma afirmação, não uma lacuna

A documentação publica preços por tokens e exemplos de custo de saída para
algumas medidas. Esses exemplos não incluem todo o custo de entrada, nem
cobrem automaticamente nossos canvases. Sem um estimador implementado e
verificado por tamanho e entrada, `PRECO_REFERENCIA_USD_POR_IMAGEM = None`.
O plano mostra "estimativa indisponível", nunca zero ou teto garantido.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from volc_ads.criativo.contrato import (
    TIPOS_DE_IMAGEM,
    EspecificacaoDeAsset,
    TipoDeAsset,
)
from volc_ads.criativo.porta import (
    ArquivoGerado,
    GeracaoFracassada,
    ImagemDeReferencia,
    MotorIndisponivel,
    PedidoDeGeracao,
    PedidoDesconhecido,
    PedidoRecusado,
    RespostaDoMotor,
)

from ..enquadramento import enquadrar
from ..envelope_openai import FONTE_DO_ENVELOPE, Canvas, canvas_para, tamanho_aceito

_BASE = "https://api.openai.com/v1"

#: O modelo. Constante, nunca parâmetro. Ver o cabeçalho.
MODELO = "gpt-image-2"

#: A qualidade. Constante, nunca parâmetro. Ver o cabeçalho.
QUALIDADE = "medium"

#: O formato de saída pedido ao provider.
#:
#: PNG e não JPEG porque o hash de conteúdo é a identidade do asset, e um
#: recodificador com perdas faria o mesmo pedido produzir bytes diferentes
#: conforme a versão da libjpeg. É a mesma escolha que `enquadramento.py` já faz
#: na normalização final, e as duas precisam concordar.
FORMATO_DE_SAIDA = "png"

VERSAO_DO_ADAPTADOR = "1.1.0"

#: A identidade do motor no registro (`criativo_motor.slug`).
#:
#: ⚠️ `nome` e `slug` são coisas diferentes. `nome` carrega o modelo
#: ("openai:gpt-image-2") e muda quando o modelo muda; `slug` é a identidade do
#: MOTOR e não pode mudar, senão a FK `criativo_job.motor_id` passa a apontar
#: para outro patrimônio. O valor respeita `criativo_motor_slug_forma`
#: (`^[a-z0-9][a-z0-9_.:-]{1,62}$`).
SLUG = "openai-gpt-image-2"

#: Não há estimador total implementado para nossos canvases. Ver o cabeçalho.
#:
#: `None` e não `0.0`: zero é um preço, e um "custo estimado US$ 0,00" ao lado de
#: um botão que gasta é a frase mais cara que a interface poderia dizer.
PRECO_REFERENCIA_USD_POR_IMAGEM: float | None = None

FONTE_DO_PRECO = (
    "developers.openai.com/api/docs/guides/image-generation (consultado em 08/09/2026): "
    "gpt-image-2 é cobrado por tokens; há exemplos de custo de saída por medida e "
    "qualidade. Eles não são teto total. O estimador para nossos canvases e entradas "
    "ainda não está implementado; nenhuma estimativa total é exibida."
)

#: Tetos do endpoint de edição, conforme a documentação oficial.
MAX_IMAGENS_DE_REFERENCIA = 16
MAX_BYTES_POR_REFERENCIA = 50 * 1024 * 1024

#: Os MIMEs que `/v1/images/edits` aceita como imagem de entrada.
MIMES_DE_REFERENCIA: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/webp"}
)


def _chave_do_ambiente() -> str:
    """A credencial do provider, do ambiente ou do `.env`. Nunca de payload.

    Ambiente primeiro, `.env` depois: as duas fontes não são a mesma nesta casa
    (ver `armazenamento._do_ambiente_ou_settings`). Lendo só do ambiente,
    `configurado` sairia `False` localmente com a chave presente em
    `backend/.env`, e a rota responderia 503 com a chave no lugar certo.
    """
    valor = os.environ.get("OPENAI_API_KEY")
    if valor:
        return valor
    try:
        from app.config import get_settings  # noqa: PLC0415

        return getattr(get_settings(), "openai_api_key", None) or ""
    except Exception:  # noqa: BLE001 — fora do backend o engine roda sem config
        return ""


# ── transporte ───────────────────────────────────────────────────────────────


class TransporteHTTP(Protocol):
    """A única superfície de rede deste módulo, e ela é injetada.

    Dois métodos porque a API tem dois protocolos: `/generations` é JSON puro e
    `/edits` é `multipart/form-data`. Um método só obrigaria o adaptador a
    montar multipart na mão e o teste a decodificar multipart para conferir o
    pedido — trocando prova de contrato por prova de serialização.
    """

    def post_json(
        self, url: str, payload: dict[str, Any], chave: str, timeout: float
    ) -> dict[str, Any]:
        ...

    def post_multipart(
        self,
        url: str,
        campos: dict[str, str],
        arquivos: list[ImagemDeReferencia],
        chave: str,
        timeout: float,
    ) -> dict[str, Any]:
        ...


@dataclass
class RespostaHTTP(Exception):
    """Erro de transporte com status e corpo, para o motor traduzir sem adivinhar."""

    status: int
    corpo: str

    def __str__(self) -> str:  # pragma: no cover - representação
        return f"HTTP {self.status}"


class TransporteHttpx:
    """Implementação real. `httpx` já é dependência declarada do backend."""

    def _cabecalhos(self, chave: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {chave}"}

    def _resposta(self, r: Any) -> dict[str, Any]:
        if r.status_code >= 400:
            raise RespostaHTTP(status=r.status_code, corpo=r.text[:4000])
        try:
            return r.json()
        except json.JSONDecodeError as e:
            raise GeracaoFracassada(f"resposta do motor não é JSON: {e}") from e

    def post_json(
        self, url: str, payload: dict[str, Any], chave: str, timeout: float
    ) -> dict[str, Any]:
        import httpx  # noqa: PLC0415

        try:
            r = httpx.post(
                url, json=payload, headers=self._cabecalhos(chave), timeout=timeout
            )
        except httpx.TimeoutException as e:
            raise MotorIndisponivel(f"tempo esgotado ao falar com o motor: {e}") from e
        except httpx.HTTPError as e:
            raise MotorIndisponivel(f"falha de rede ao falar com o motor: {e}") from e
        return self._resposta(r)

    def post_multipart(
        self,
        url: str,
        campos: dict[str, str],
        arquivos: list[ImagemDeReferencia],
        chave: str,
        timeout: float,
    ) -> dict[str, Any]:
        import httpx  # noqa: PLC0415

        # O campo é `image[]` quando há mais de um arquivo: a documentação
        # descreve `image` como singular que aceita sequência, e é assim que o
        # multipart repetido é lido do outro lado.
        campo = "image[]" if len(arquivos) > 1 else "image"
        payload = [
            (campo, (a.nome, io.BytesIO(a.conteudo), a.mime)) for a in arquivos
        ]
        try:
            r = httpx.post(
                url,
                data=campos,
                files=payload,
                headers=self._cabecalhos(chave),
                timeout=timeout,
            )
        except httpx.TimeoutException as e:
            raise MotorIndisponivel(f"tempo esgotado ao falar com o motor: {e}") from e
        except httpx.HTTPError as e:
            raise MotorIndisponivel(f"falha de rede ao falar com o motor: {e}") from e
        return self._resposta(r)


# ── o motor ──────────────────────────────────────────────────────────────────


class MotorOpenAIImagem:
    """`gpt-image-2`: a peça é composta pelo modelo no canvas nativo pedido.

    Cumpre o contrato de dois passos guardando o resultado debaixo do id, como o
    próprio `porta.py` prevê para motor síncrono. Quem dá assincronia ao produto
    é o executor de jobs, um nível acima: **o request HTTP nunca espera o render**.
    """

    tipos_suportados = TIPOS_DE_IMAGEM
    aceita_referencia = True

    #: Lido por `studio/adaptador.py` e por `execucao.py` para calcular o custo.
    #: `None` significa "o provider não publica preço por imagem", nunca zero.
    preco_referencia_usd_por_imagem: float | None = PRECO_REFERENCIA_USD_POR_IMAGEM
    fonte_do_preco = FONTE_DO_PRECO

    def __init__(
        self,
        *,
        chave: str | None = None,
        transporte: TransporteHTTP | None = None,
        timeout_s: float = 240.0,
    ) -> None:
        # ⚠️ NÃO há parâmetro `modelo` nem `qualidade`. Ver o cabeçalho: os dois
        # são constantes do módulo porque a autorização de gasto os nomeia, e um
        # construtor que os aceitasse permitiria assinar um ato e rodar outro.
        self._chave = chave if chave is not None else _chave_do_ambiente()
        self.modelo = MODELO
        self.qualidade = QUALIDADE
        self.nome = f"openai:{MODELO}"
        self.slug = SLUG
        self.versao = VERSAO_DO_ADAPTADOR
        self._transporte = transporte or TransporteHttpx()
        self._timeout = timeout_s
        self._resultados: dict[str, RespostaDoMotor] = {}
        self._trava = threading.Lock()

    @property
    def configurado(self) -> bool:
        """Há credencial para falar com o provider?

        Consultado ANTES de criar o job, para que a interface diga "não
        configurado" em vez de aceitar um pedido que vai falhar depois.
        """
        return bool(self._chave)

    # ── passo 1 ──────────────────────────────────────────────────────────────

    def solicitar_geracao(self, pedido: PedidoDeGeracao) -> str:
        if pedido.tipo not in self.tipos_suportados:
            raise PedidoRecusado(
                f"{pedido.tipo.value} não é imagem: este motor só produz imagem",
                pedido=pedido.referencia,
            )
        if not self._chave:
            # `permanente=False`: configurar a chave faz o mesmo pedido passar.
            # Falha FECHADA — não existe caminho que troque de provider aqui.
            raise MotorIndisponivel(
                "motor de imagem sem credencial configurada no servidor",
                pedido=pedido.referencia,
            )

        id_do_pedido = f"oai_{uuid.uuid4().hex[:16]}"
        resposta = self._gerar(id_do_pedido, pedido)
        with self._trava:
            self._resultados[id_do_pedido] = resposta
        return id_do_pedido

    # ── passo 2 ──────────────────────────────────────────────────────────────

    def receber(self, id_do_pedido: str) -> RespostaDoMotor:
        """Entrega o resultado UMA vez e o solta da memória.

        Soltar na primeira leitura evita o vazamento medido no motor irmão: um
        dicionário que só cresce dentro de um objeto guardado em global de
        processo retém alguns MB por job, para sempre. Quem quiser o resultado
        de novo tem o banco, que é onde ele foi persistido.
        """
        with self._trava:
            resposta = self._resultados.pop(id_do_pedido, None)
        if resposta is None:
            raise PedidoDesconhecido(
                "este motor nunca emitiu o pedido informado", pedido=id_do_pedido
            )
        return resposta

    # ── tradução ─────────────────────────────────────────────────────────────

    def _gerar(self, id_do_pedido: str, pedido: PedidoDeGeracao) -> RespostaDoMotor:
        largura, altura = _medida_alvo(pedido.especificacao, pedido.tipo)
        canvas = canvas_para(largura, altura)

        # Cinto e suspensório: `canvas_para` já garante o envelope, mas um
        # canvas inválido chegando ao provider é uma chamada paga que falha, e a
        # asserção custa nanossegundos.
        if not tamanho_aceito(canvas.largura, canvas.altura):
            raise PedidoRecusado(
                f"o canvas {canvas.size} não cabe no envelope do provider",
                pedido=pedido.referencia,
            )

        referencias = _referencias_do_pedido(pedido)
        prompt = _instrucao(pedido, canvas, largura, altura, com_referencia=bool(referencias))
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        if referencias:
            bruto = self._editar(prompt, canvas, referencias, pedido.referencia)
        else:
            bruto = self._compor(prompt, canvas, pedido.referencia)

        servido = _modelo_servido(bruto)
        dados = bruto.get("data") or []
        arquivos: list[ArquivoGerado] = []
        for item in dados:
            b64 = (item or {}).get("b64_json")
            if not b64:
                continue
            try:
                cru = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError) as e:
                raise GeracaoFracassada(
                    "o motor devolveu imagem ilegível", pedido=pedido.referencia
                ) from e

            enquadrada = enquadrar(cru, largura, altura)
            arquivos.append(
                ArquivoGerado(
                    conteudo=enquadrada.conteudo,
                    mime=enquadrada.mime or f"image/{FORMATO_DE_SAIDA}",
                    largura=enquadrada.largura,
                    altura=enquadrada.altura,
                    # `custo_usd` ausente porque o provider reporta token, nunca
                    # dólar, e não há tabela de dólar por imagem publicada.
                    custo_usd=None,
                    metadados={
                        "motor": self.nome,
                        "modelo_pedido": MODELO,
                        "modelo_servido": servido or "",
                        "qualidade": QUALIDADE,
                        "adaptador_versao": self.versao,
                        "canvas_largura": str(canvas.largura),
                        "canvas_altura": str(canvas.altura),
                        "canvas_derivado": "sim" if canvas.derivado else "nao",
                        "canvas_motivo": canvas.motivo,
                        "canvas_fonte": FONTE_DO_ENVELOPE,
                        "enquadramento": enquadrada.enquadramento,
                        "nativo_largura": str(enquadrada.nativa_largura or ""),
                        "nativo_altura": str(enquadrada.nativa_altura or ""),
                        "transformacoes": " | ".join(enquadrada.transformacoes),
                        "prompt_sha256": prompt_sha256,
                        "prompt_efetivo": prompt,
                        "referencias_sha256": ",".join(r.sha256 for r in referencias),
                        "custo_fonte": FONTE_DO_PRECO,
                        "tokens_saida": str(_tokens_de_saida(bruto) or ""),
                        "tokens_entrada": str(_tokens_de_entrada(bruto) or ""),
                    },
                )
            )

        if not arquivos:
            # 200 sem imagem: quase sempre bloqueio de política. Retentar o
            # MESMO insumo erra igual, então é permanente.
            raise PedidoRecusado(
                "o motor respondeu sem imagem", pedido=pedido.referencia
            )

        return RespostaDoMotor(pedido=id_do_pedido, arquivos=tuple(arquivos), custo_usd=None)

    def _compor(self, prompt: str, canvas: Canvas, referencia: str) -> dict[str, Any]:
        """`POST /v1/images/generations` — corpo JSON, sem imagem de entrada."""
        payload = {
            "model": MODELO,
            "prompt": prompt,
            "size": canvas.size,
            "quality": QUALIDADE,
            "output_format": FORMATO_DE_SAIDA,
            "n": 1,
            # ⚠️ `input_fidelity` NÃO entra: a documentação do gpt-image-2 manda
            # omiti-lo. `response_format` também não: modelos GPT-image sempre
            # devolvem base64, e o parâmetro pertence ao DALL-E.
        }
        try:
            return self._transporte.post_json(
                f"{_BASE}/images/generations", payload, self._chave, self._timeout
            )
        except RespostaHTTP as e:
            raise _traduzir_status(e, referencia) from e

    def _editar(
        self,
        prompt: str,
        canvas: Canvas,
        referencias: list[ImagemDeReferencia],
        referencia: str,
    ) -> dict[str, Any]:
        """`POST /v1/images/edits` — multipart, com as imagens de referência.

        É o caminho da fotografia real. O endpoint aceita até 16 arquivos de até
        50 MB cada; os dois tetos são conferidos aqui e viram recusa PERMANENTE,
        porque reenviar o mesmo arquivo grande erra igual.
        """
        if len(referencias) > MAX_IMAGENS_DE_REFERENCIA:
            raise PedidoRecusado(
                f"o provider aceita no máximo {MAX_IMAGENS_DE_REFERENCIA} imagens "
                f"de referência e este pedido tem {len(referencias)}",
                pedido=referencia,
            )
        for arquivo in referencias:
            if arquivo.mime not in MIMES_DE_REFERENCIA:
                raise PedidoRecusado(
                    f"o provider não aceita {arquivo.mime} como imagem de referência",
                    pedido=referencia,
                )
            if len(arquivo.conteudo) > MAX_BYTES_POR_REFERENCIA:
                raise PedidoRecusado(
                    "a imagem de referência passa do limite de 50 MB do provider",
                    pedido=referencia,
                )

        campos = {
            "model": MODELO,
            "prompt": prompt,
            "size": canvas.size,
            "quality": QUALIDADE,
            "output_format": FORMATO_DE_SAIDA,
            "n": "1",
        }
        try:
            return self._transporte.post_multipart(
                f"{_BASE}/images/edits", campos, referencias, self._chave, self._timeout
            )
        except RespostaHTTP as e:
            raise _traduzir_status(e, referencia) from e


# ── auxiliares ───────────────────────────────────────────────────────────────


def _medida_alvo(spec: EspecificacaoDeAsset | None, tipo: TipoDeAsset) -> tuple[int, int]:
    """A dimensão pedida, com recusa explícita quando ela não veio.

    Sem dimensão não dá para escolher o canvas nativo, e gerar "uma imagem" para
    descobrir depois que ela não cabe no slot é pagar duas vezes pela mesma peça.
    """
    if spec is None or spec.largura_recomendada is None or spec.altura_recomendada is None:
        raise PedidoRecusado(
            f"{tipo.value}: pedido sem dimensão alvo, e o motor não adivinha formato"
        )
    return spec.largura_recomendada, spec.altura_recomendada


def _referencias_do_pedido(pedido: PedidoDeGeracao) -> list[ImagemDeReferencia]:
    """As imagens de referência que o chamador anexou ao pedido.

    Viajam em `PedidoDeGeracao.referencias`, campo declarado da porta. Quem não
    anexa nada segue pelo caminho de composição pura, sem mudança de
    comportamento: a lista vazia é o caso normal.
    """
    cru = pedido.referencias or ()
    referencias: list[ImagemDeReferencia] = []
    for item in cru:
        if isinstance(item, ImagemDeReferencia):
            referencias.append(item)
            continue
        raise PedidoRecusado(
            "referência de imagem em formato desconhecido", pedido=pedido.referencia
        )
    return referencias


def _instrucao(
    pedido: PedidoDeGeracao,
    canvas: Canvas,
    largura: int,
    altura: int,
    *,
    com_referencia: bool,
) -> str:
    """O prompt enviado ao modelo, orientado para o canvas.

    A orientação de canvas é o que faz as peças serem composições diferentes e
    não a mesma imagem em três recortes: o modelo recebe a proporção e a
    instrução de reservar área para texto NAQUELE formato.

    ⚠️ Quando há foto real, o texto NÃO promete preservação de rosto. O endpoint
    de edição re-renderiza a imagem inteira; prometer "mantenha a pessoa
    idêntica" no prompt seria escrever no produto uma garantia que o provider não
    dá. A preservação literal dos pixels é feita fora daqui, pelo compositor
    determinístico, e é ele que a interface chama de modo híbrido.
    """
    # ⚠️ O dicionário de contexto NÃO entra no prompt, e a razão é literal.
    #
    # Até 10/09/2026 esta função terminava com o despejo cru de `pedido.contexto`
    # ordenado, o que colocava na ÚLTIMA linha do prompt — a posição de maior
    # recência que o modelo lê — o par `formato: Retrato`. `formato.rotulo` para
    # o slot 4x5 é a string "Retrato" (app/criativo/dominio.py:95), um rótulo de
    # PROPORÇÃO na nossa interface e um pedido de RETRATO DE PESSOA em português.
    # As quatro peças do lote reclamado eram, todas, retratos de adolescente.
    # `modo_de_composicao: sem_foto` vinha logo em seguida, contradizendo o
    # parágrafo que o prompt gasta explicando que sem_foto não proíbe cena.
    #
    # Estes dados continuam viajando em `metadados` e no recibo, que é onde a
    # pergunta "o que gerou esta peça?" se responde. Prompt é direção de arte.
    inspiracao = pedido.contexto.get("modo_de_composicao") == "referencia_visual"
    referencia = (
        "A imagem anexada inspira somente estilo, paleta e composição. "
        "Não é referência de identidade, marca, fatos ou texto.\n"
        if com_referencia and inspiracao else
        "As imagens anexadas são material de referência da marca e do assunto. "
        "Use-as como base visual da composição.\n"
        if com_referencia
        else ""
    )
    # ⚠️ Esta linha CALA quando a tipografia é do código, e a razão custou uma
    # imagem paga. `compilar_prompt` já emite "Não escreva NENHUM texto…" para
    # peça com plano de composição — é assim que a cena chega limpa e a PRENSA
    # escreve a letra com fonte real, medida no DOM. Mandar as duas coisas no
    # mesmo prompt é pedir ao modelo que escreva e não escreva: em 10/09/2026 o
    # `gpt-image-2` obedeceu a esta e devolveu a headline desenhada, com o
    # caderno da cena cheio de rabisco ilegível no lugar da escrita à mão.
    #
    # A política NÃO cala junto: logotipo e marca d'água viajam com os pixels
    # nos dois caminhos, porque são restrição de conteúdo e não de tipografia.
    politica = "Sem logotipos ou marcas d'água copiados.\n"
    por_codigo = pedido.contexto.get("tipografia") == "codigo"
    texto = politica if por_codigo else (
        "O texto explicitamente aprovado no briefing deve aparecer na arte final, "
        "com todas as palavras e acentos, em hierarquia legível. "
        "Não invente texto quando não foi solicitado. "
        "Use apenas o texto na arte aprovado no briefing, nunca o texto da referência. "
        + politica
    )
    # A única coisa que ESTA camada sabe e o blueprint não é a geometria. Onde o
    # texto vive, se há área chapada e qual a ordem de leitura são decisões de
    # direção de arte, e já viajam em `pedido.insumo`. A versão anterior ditava
    # aqui um layout genérico ("uma área limpa e contínua para o texto") que se
    # contradizia na mesma frase ("sem tarjas") e se repetia idêntico em toda
    # peça de todo lote — era ele, e não o agente, quem desenhava a peça.
    return (
        f"{pedido.insumo}\n\n"
        f"Canvas de geração {canvas.largura}x{canvas.altura} px; "
        f"entrega final {largura}x{altura} px. Componha para esta proporção, "
        f"preenchendo o canvas inteiro.\n"
        f"{referencia}{texto}"
    ).strip()


def _modelo_servido(bruto: dict[str, Any]) -> str | None:
    """O modelo que o provider diz ter usado, quando ele diz.

    É o campo que torna um rebaixamento silencioso detectável: pedir
    `gpt-image-2` e receber outro modelo é um fato que precisa chegar ao recibo,
    não uma diferença que ninguém mede. Ausência devolve `None`, nunca o pedido:
    afirmar que o servido é igual ao pedido sem prova é inventar a prova.
    """
    for chave in ("model", "served_model"):
        valor = bruto.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


def _tokens_de_saida(bruto: dict[str, Any]) -> int | None:
    uso = bruto.get("usage") or {}
    valor = uso.get("output_tokens")
    return valor if isinstance(valor, int) else None


def _tokens_de_entrada(bruto: dict[str, Any]) -> int | None:
    uso = bruto.get("usage") or {}
    valor = uso.get("input_tokens")
    return valor if isinstance(valor, int) else None


def _codigo_do_erro(corpo: str) -> str:
    """`error.code` ou `error.type` do corpo, quando ele é o envelope documentado.

    ⚠️ Isto NÃO é classificação por texto de mensagem. A documentação define o
    envelope `{"error": {message, type, param, code}}`, e `type`/`code` são campos
    fechados. Ler `message` com `if "size" in msg.lower()` — como faz a referência
    do Aprova — transforma a decisão de retentar numa dependência da redação de
    uma frase em inglês que o provider pode mudar sem avisar.

    A mensagem em si nunca é devolvida ao operador nem gravada: ela pode conter o
    prompt inteiro.
    """
    try:
        envelope = json.loads(corpo)
    except (json.JSONDecodeError, TypeError):
        return ""
    erro = envelope.get("error") if isinstance(envelope, dict) else None
    if not isinstance(erro, dict):
        return ""
    for chave in ("code", "type"):
        valor = erro.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _traduzir_status(erro: RespostaHTTP, referencia: str):
    """HTTP -> erro tipado, com `permanente` correto.

    `permanente` decide se o retry acontece. Marcar 429 como permanente
    desistiria de um pedido que ia dar certo; marcar 400 como transitório
    queimaria cota repetindo um payload que o provider já recusou.

    O status é a autoridade; `error.code`/`error.type` só refina o 429, que a
    documentação usa tanto para limite de taxa (retentável) quanto para crédito
    esgotado (não adianta insistir no mesmo minuto, mas continua não-permanente
    porque recarregar crédito faz o mesmo pedido passar).
    """
    codigo = _codigo_do_erro(erro.corpo)
    if erro.status in (401, 403):
        return MotorIndisponivel(
            "credencial do motor de imagem recusada pelo provedor", pedido=referencia
        )
    if erro.status == 429:
        if codigo in ("insufficient_quota", "billing_hard_limit_reached"):
            return MotorIndisponivel(
                "crédito do motor de imagem esgotado", pedido=referencia
            )
        return MotorIndisponivel("cota do motor de imagem esgotada", pedido=referencia)
    if erro.status in (400, 404, 413, 422):
        return PedidoRecusado(
            "o motor recusou o pedido nesta configuração", pedido=referencia
        )
    if erro.status >= 500:
        return MotorIndisponivel(
            "o provedor do motor de imagem está indisponível", pedido=referencia
        )
    # ⚠️ O default do caminho NÃO PREVISTO é transitório, e não permanente.
    #
    # Antes ele era `GeracaoFracassada`, que tem `permanente = True`. As faixas
    # tratadas acima deixam de fora os 4xx transitórios — 408 (Request Timeout),
    # 409, 425 (Too Early), 499 —, e um 408 do gateway matava a peça sem direito
    # a retry: o operador pagaria de novo por um pedido que teria dado certo na
    # segunda tentativa.
    #
    # A assimetria dos dois erros é o argumento: marcar transitório o que era
    # permanente custa UMA chamada a mais; marcar permanente o que era
    # transitório custa a peça inteira e obriga refazer o lote na mão. Status
    # desconhecido é ignorância, e ignorância pede nova tentativa, não desistência.
    return MotorIndisponivel(
        "o motor falhou de forma não prevista", pedido=referencia
    )
