"""Motor de imagem `full_llm` sobre a API de imagem do Gemini.

Implementa `volc_ads.criativo.porta.MotorDeCriativo`. Não reimplementa nenhum
vocabulário: `Asset`, `Procedencia`, `Falha` e os erros tipados já existem em
`volc_ads/criativo/`, e duplicá-los aqui criaria divergência no dia um.

## Por que este motor, e não a PRENSA nem o caminho OpenAI

Levantamento de 27/08/2026, com execução real:

- **OpenAI (`gpt-image-2`)** é o caminho que o Aprova usa com garantia de pixel
  exato. `OPENAI_API_KEY` está **vazia** neste ambiente. Um adapter que não roda
  não prova nada.
- **PRENSA** (`typography_only`) é determinística, sem provider, com gates, e foi
  a única a produzir três PNGs reais do mesmo briefing no levantamento. Ela
  exige, porém, Playwright com **Google Chrome real**, fontes vendorizadas e
  ~2.600 linhas copiadas para dentro do repositório. "Copiar integralmente a
  PRENSA" é proibição explícita desta rodada, e um vendor parcial diverge da
  fonte em silêncio (`PACOTE-REUSO-MOTOR-IMAGEM.json`, risco `path_globals`).
- **Gemini (`gemini-3.1-flash-image`)** é o literal que Aprova e Positivo já
  declaram em `config.py`, a chave existe e responde, e a API aceita
  `imageConfig.aspectRatio` — o que resolve exatamente a fraqueza que o
  levantamento apontou no caminho Gemini do Aprova, que só pedia a proporção em
  texto livre e não conferia nada.

A escolha é estreita de propósito: **um** provider, **um** endpoint, nenhum
Chromium, nenhuma fonte vendorizada, nenhum estado global de processo.

## O que este motor NÃO faz

Não publica, não conhece token de Google Ads nem de Meta, não escreve em disco,
não decide aprovação e não sabe o que é uma campanha. Ele recebe um pedido e
devolve bytes com o que conseguiu medir. Persistência, storage, aprovação e
destino são de outro dono, um nível acima.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from volc_ads.criativo.contrato import TIPOS_DE_IMAGEM, EspecificacaoDeAsset, TipoDeAsset
from volc_ads.criativo.porta import (
    ArquivoGerado,
    GeracaoFracassada,
    MotorIndisponivel,
    PedidoDeGeracao,
    PedidoDesconhecido,
    PedidoRecusado,
    RespostaDoMotor,
)

from ..enquadramento import enquadrar, razao_nativa

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

MODELO_PADRAO = "gemini-3.1-flash-image"
VERSAO_DO_ADAPTADOR = "1.0.0"

# Preço de REFERÊNCIA do provider, não fatura medida.
#
# A distinção não é preciosismo: a API devolve contagem de tokens, nunca dólares.
# Um número derivado de tabela é estimativa, e gravá-lo como custo realizado
# transformaria "acho que custou" em "medi que custou" — que é o defeito que
# `Procedencia.custo_usd` existe para impedir ("`None` quando o motor não
# reporta, não `0.0`").
PRECO_REFERENCIA_USD_POR_IMAGEM = 0.039
FONTE_DO_PRECO = (
    "volc-factory/contrato/motor/mapa.json::custos_referencia.SRC:geminiimg "
    "(US$0.039/img, referência de provider, não fatura)"
)


def _chave_do_ambiente() -> str:
    """A credencial do provider, do ambiente ou do `.env`. Nunca de payload."""
    valor = os.environ.get("GEMINI_API_KEY")
    if valor:
        return valor
    try:
        from app.config import get_settings  # noqa: PLC0415

        return getattr(get_settings(), "gemini_api_key", None) or ""
    except Exception:  # noqa: BLE001 — fora do backend o engine roda sem config
        return ""


class TransporteHTTP(Protocol):
    """A única superfície de rede deste módulo, e ela é injetada.

    Existe para que o teste prove a tradução do contrato (pedido -> payload,
    resposta -> arquivos, erro -> erro tipado) sem tocar em rede e sem gastar.
    É o mesmo desenho de `funnelforge_imagem.py`, que recebe o gerador em vez de
    construí-lo, e pelo mesmo motivo.
    """

    def post_json(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        ...


@dataclass
class RespostaHTTP(Exception):
    """Erro de transporte com status, para o motor traduzir sem ler string."""

    status: int
    corpo: str

    def __str__(self) -> str:  # pragma: no cover - representação
        return f"HTTP {self.status}"


class TransporteHttpx:
    """Implementação real. `httpx` já é dependência declarada do backend."""

    def post_json(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        import httpx  # noqa: PLC0415

        try:
            r = httpx.post(url, json=payload, timeout=timeout)
        except httpx.TimeoutException as e:
            raise MotorIndisponivel(f"tempo esgotado ao falar com o motor: {e}") from e
        except httpx.HTTPError as e:
            raise MotorIndisponivel(f"falha de rede ao falar com o motor: {e}") from e

        if r.status_code >= 400:
            raise RespostaHTTP(status=r.status_code, corpo=r.text[:2000])
        try:
            return r.json()
        except json.JSONDecodeError as e:
            raise GeracaoFracassada(f"resposta do motor não é JSON: {e}") from e


# ── o motor ──────────────────────────────────────────────────────────────────


class MotorGeminiImagem:
    """`full_llm`: a peça inteira é composta pelo modelo, na proporção pedida.

    Cumpre o contrato de dois passos guardando o resultado debaixo do id, como o
    próprio `porta.py` prevê para motor síncrono. Quem dá assincronia ao produto
    é o executor de jobs, um nível acima: **o request HTTP nunca espera o render**.
    """

    tipos_suportados = TIPOS_DE_IMAGEM

    def __init__(
        self,
        *,
        chave: str | None = None,
        modelo: str = MODELO_PADRAO,
        transporte: TransporteHTTP | None = None,
        timeout_s: float = 240.0,
    ) -> None:
        # A chave vem do ambiente do PROCESSO e nunca de payload, banco ou
        # arquivo versionado. Ela não é guardada em atributo público nem entra
        # em nenhum log, mensagem de erro ou objeto devolvido.
        # Ambiente primeiro, `.env` depois: as duas fontes não são a mesma nesta
        # casa (ver `armazenamento._do_ambiente_ou_settings`). Lendo só do
        # ambiente, `motorConfigurado` saía `false` localmente com a chave
        # presente em `backend/.env`, e `POST /jobs` respondia 503.
        self._chave = chave if chave is not None else _chave_do_ambiente()
        self.modelo = modelo
        self.nome = f"gemini:{modelo}"
        # ⚠️ `nome` e `slug` são coisas diferentes e a confusão entre os dois é
        # cara. `nome` carrega o modelo ("gemini:gemini-3.1-flash-image") e muda
        # quando o modelo muda; `slug` é a identidade do MOTOR no registro
        # (`criativo_motor.slug`) e não pode mudar, senão a FK aponta para outro
        # patrimônio. Resolver `criativo_motor` por `nome` devolveria `None` para
        # sempre, e `criativo_job.motor_id` nunca sairia de nulo sem ninguém notar.
        self.slug = "gemini-imagem"
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
            raise MotorIndisponivel(
                "motor de imagem sem credencial configurada no servidor",
                pedido=pedido.referencia,
            )

        id_do_pedido = f"gem_{uuid.uuid4().hex[:16]}"
        resposta = self._gerar(id_do_pedido, pedido)
        with self._trava:
            self._resultados[id_do_pedido] = resposta
        return id_do_pedido

    # ── passo 2 ──────────────────────────────────────────────────────────────

    def receber(self, id_do_pedido: str) -> RespostaDoMotor:
        """Entrega o resultado UMA vez e o solta da memória.

        ⚠️ Antes o dicionário só crescia. Medido num job real de três peças:
        5,8 MB retidos por job, para sempre, num objeto guardado em global de
        processo (`routers/criativos.py::obter_motor`). Cem jobs davam ~580 MB
        e o processo subia até o OOM sem nada no log.

        Soltar na primeira leitura é seguro porque o contrato de dois passos da
        porta é `solicitar` seguido de um `receber`: quem quiser o resultado de
        novo tem o banco, que é onde ele foi persistido. Uma segunda chamada
        levanta `PedidoDesconhecido`, que é a verdade — este motor não guarda
        histórico.
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
        spec = pedido.especificacao
        largura, altura = _medida_alvo(spec, pedido.tipo)
        razao = razao_nativa(largura, altura)

        url = f"{_BASE}/{self.modelo}:generateContent?key={self._chave}"
        payload = {
            "contents": [{"parts": [{"text": _instrucao(pedido, razao, largura, altura)}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": razao},
            },
        }

        try:
            bruto = self._transporte.post_json(url, payload, self._timeout)
        except RespostaHTTP as e:
            raise _traduzir_status(e, pedido.referencia) from e

        arquivos: list[ArquivoGerado] = []
        for parte in _partes(bruto):
            inline = parte.get("inlineData") or parte.get("inline_data")
            if not inline or not inline.get("data"):
                continue
            try:
                cru = base64.b64decode(inline["data"])
            except (ValueError, TypeError) as e:
                raise GeracaoFracassada(
                    "o motor devolveu imagem ilegível", pedido=pedido.referencia
                ) from e

            enquadrada = enquadrar(cru, largura, altura)
            arquivos.append(
                ArquivoGerado(
                    conteudo=enquadrada.conteudo,
                    mime=enquadrada.mime or inline.get("mimeType"),
                    largura=enquadrada.largura,
                    altura=enquadrada.altura,
                    # `custo_usd` fica ausente porque o provider NÃO reporta
                    # dólares. A estimativa viaja em metadados, onde ela não se
                    # confunde com medida.
                    custo_usd=None,
                    metadados={
                        "motor": self.nome,
                        "modelo": self.modelo,
                        "adaptador_versao": self.versao,
                        "razao_pedida": razao,
                        "enquadramento": enquadrada.enquadramento,
                        "nativo_largura": str(enquadrada.nativa_largura or ""),
                        "nativo_altura": str(enquadrada.nativa_altura or ""),
                        "transformacoes": " | ".join(enquadrada.transformacoes),
                        "custo_estimado_usd": f"{PRECO_REFERENCIA_USD_POR_IMAGEM:.6f}",
                        "custo_fonte": FONTE_DO_PRECO,
                        "tokens": str(_tokens_de_imagem(bruto) or ""),
                    },
                )
            )

        if not arquivos:
            # Resposta 200 sem imagem: quase sempre bloqueio de política, e o
            # motivo vem em `finishReason`/`promptFeedback`. Retentar o MESMO
            # insumo erra igual, então é permanente.
            raise PedidoRecusado(
                _motivo_da_recusa(bruto), pedido=pedido.referencia
            )

        return RespostaDoMotor(pedido=id_do_pedido, arquivos=tuple(arquivos), custo_usd=None)


# ── auxiliares ───────────────────────────────────────────────────────────────


def _medida_alvo(spec: EspecificacaoDeAsset | None, tipo: TipoDeAsset) -> tuple[int, int]:
    """A dimensão pedida, com recusa explícita quando ela não veio.

    Sem dimensão não dá para escolher a proporção nativa, e gerar "uma imagem"
    para descobrir depois que ela não cabe no slot é pagar duas vezes pela mesma
    peça, que é exatamente o que `PedidoDeGeracao.especificacao` existe para
    evitar.
    """
    if spec is None or spec.largura_recomendada is None or spec.altura_recomendada is None:
        raise PedidoRecusado(
            f"{tipo.value}: pedido sem dimensão alvo, e o motor não adivinha formato"
        )
    return spec.largura_recomendada, spec.altura_recomendada


def _instrucao(pedido: PedidoDeGeracao, razao: str, largura: int, altura: int) -> str:
    """O prompt enviado ao modelo, orientado para o canvas.

    A orientação de canvas é o que faz as três peças serem composições
    diferentes e não a mesma imagem em três recortes: o modelo recebe a
    proporção e a instrução de reservar área para texto NAQUELE formato.
    """
    contexto = "\n".join(
        f"{chave}: {valor}" for chave, valor in sorted(pedido.contexto.items()) if valor
    )
    return (
        f"{pedido.insumo}\n\n"
        f"Formato de saída: {razao} ({largura}x{altura}).\n"
        f"Componha para este enquadramento especificamente, não para um quadrado "
        f"recortado. Reserve uma área limpa e contínua para texto, adequada a "
        f"esta proporção.\n"
        "Sem texto, sem letras, sem logotipo e sem marca d'água na imagem.\n"
        f"{contexto}"
    ).strip()


def _partes(bruto: dict[str, Any]) -> list[dict[str, Any]]:
    candidatos = bruto.get("candidates") or []
    if not candidatos:
        return []
    return (candidatos[0].get("content") or {}).get("parts") or []


def _tokens_de_imagem(bruto: dict[str, Any]) -> int | None:
    """Tokens de imagem, quando o provider reporta. Ausência é `None`."""
    uso = bruto.get("usageMetadata") or {}
    for detalhe in uso.get("candidatesTokensDetails") or []:
        if detalhe.get("modality") == "IMAGE":
            return detalhe.get("tokenCount")
    return uso.get("candidatesTokenCount")


def _motivo_da_recusa(bruto: dict[str, Any]) -> str:
    """Motivo legível, sem devolver a resposta bruta do provider.

    A resposta bruta pode conter o prompt e detalhes internos; ela não sobe para
    o operador (SPEC §10) e não entra no banco.
    """
    candidatos = bruto.get("candidates") or []
    if candidatos:
        razao = candidatos[0].get("finishReason")
        if razao and razao != "STOP":
            return f"o motor interrompeu a geração ({razao})"
    feedback = bruto.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        return f"o motor recusou o pedido por política ({feedback['blockReason']})"
    return "o motor respondeu sem imagem e sem motivo declarado"


def _traduzir_status(erro: RespostaHTTP, referencia: str):
    """HTTP -> erro tipado, com `permanente` correto.

    `permanente` decide se o retry acontece. Marcar 429 como permanente
    desistiria de um pedido que ia dar certo; marcar 400 como transitório
    queimaria cota repetindo um payload que o provider já recusou.
    """
    if erro.status in (401, 403):
        return MotorIndisponivel(
            "credencial do motor de imagem recusada pelo provedor", pedido=referencia
        )
    if erro.status == 429:
        return MotorIndisponivel("cota do motor de imagem esgotada", pedido=referencia)
    if erro.status in (400, 404, 422):
        return PedidoRecusado(
            "o motor recusou o pedido nesta configuração", pedido=referencia
        )
    if erro.status >= 500:
        return MotorIndisponivel(
            "o provedor do motor de imagem está indisponível", pedido=referencia
        )
    return GeracaoFracassada("o motor falhou de forma não prevista", pedido=referencia)
