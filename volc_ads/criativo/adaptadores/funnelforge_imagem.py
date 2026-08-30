"""Ponte para o gerador de imagem do FunnelForge — o único motor real provado.

## O que foi comprovado, e onde

`funnelforge-migracao/engine/src/funnelforge/ports/services.py` declara o port
`ImageGenerator`:

    class ImageGenerator(Protocol):
        def generate(self, prompt: str, size: str = "1536x1024") -> bytes: ...

com telemetria OPCIONAL em `last_usage` (custo medido, latência, modelo). O
adaptador de produção é `adapters/image_openai.py::OpenAIImageGenerator`
(`gpt-image-2`), e `pipeline/steps.py::step_image` o chama exatamente como
`deps.image_gen.generate(text, size=img_size)`. Os tamanhos em uso saem de
`config/settings.py`: `image_size_lp="1024x1536"` e `image_size_post="1536x1024"`.

## Por que este arquivo não importa o FunnelForge

Porque não precisa, e importar criaria um acoplamento que não existe hoje: o
engine vive noutro pacote, com outro venv e outra chave. Aqui o gerador chega
**injetado** — qualquer objeto com `.generate(prompt, size) -> bytes` serve.
Isso mantém a regra da casa (nenhuma credencial em código) e deixa o teste
provar a tradução do contrato sem tocar em rede.

## O buraco que este adaptador NÃO tapa, e que é melhor dizer em voz alta

O gpt-image aceita 1024x1024, 1536x1024 e 1024x1536 — proporções 1:1, 1.5:1 e
0.67:1. O Google Display pede 1.91:1, 1:1 e 4:5. Só o quadrado bate; para os
outros dois, a imagem sai fora de proporção e `validacao.py` a reprova com
`D3.proporcao`, classe SANEAVEL_EM_CODIGO — que é a verdade: falta um passo de
recorte determinístico. O `ImageProcessor` do FunnelForge converte para webp,
não recorta por proporção. Esse recorte é uma dependência aberta, registrada em
`docs/growth-engine/creative-engine.md`, e NÃO foi improvisada aqui: recortar
sem saber onde está o assunto da imagem estraga o criativo em silêncio.
"""

from __future__ import annotations

from ..contrato import TIPOS_DE_IMAGEM, EspecificacaoDeAsset, Falha
from ..porta import (
    ArquivoGerado,
    PedidoDeGeracao,
    PedidoDesconhecido,
    PedidoRecusado,
    RespostaDoMotor,
)

# Os três tamanhos que o motor aceita, lidos de `config/settings.py` do
# FunnelForge (paisagem e retrato em uso) mais o quadrado padrão da API. Não é
# tabela oficial da OpenAI: é o que este motor comprovadamente usa.
TAMANHOS_ACEITOS: tuple[str, ...] = ("1024x1024", "1536x1024", "1024x1536")


def _proporcao(tamanho: str) -> float:
    largura, altura = tamanho.split("x")
    return int(largura) / int(altura)


def tamanho_para(spec: EspecificacaoDeAsset | None,
                 aceitos: tuple[str, ...] = TAMANHOS_ACEITOS) -> str:
    """O tamanho aceito cuja proporção mais se aproxima da exigida.

    Escolher o mais próximo e deixar a validação reprovar é melhor do que
    escolher o maior: o mais próximo é o que exige o MENOR recorte depois, e o
    recorte é o que sobra de trabalho para alguém.
    """
    alvo = spec.proporcao_esperada if spec is not None else None
    if alvo is None:
        return aceitos[0]
    return min(aceitos, key=lambda t: abs(_proporcao(t) - alvo))


def _medir(dados: bytes) -> tuple[int | None, int | None, str | None]:
    """Largura, altura e mime — ou três `None`.

    O motor devolve bytes e mais nada; sem medir aqui, todo asset chegaria ao
    catálogo sem dimensão e seria reprovado por MEDIR_ANTES. Pillow já é
    dependência do FunnelForge (`adapters/images_pillow.py`), mas se ele não
    estiver no ambiente a resposta honesta é "não sei" — nunca zero.
    """
    try:
        import io

        from PIL import Image
    except ImportError:
        return None, None, None
    try:
        with Image.open(io.BytesIO(dados)) as img:
            formato = (img.format or "").lower()
            mime = f"image/{'jpeg' if formato == 'jpg' else formato}" if formato else None
            return img.width, img.height, mime
    except Exception:
        return None, None, None


class MotorDeImagemFunnelForge:
    """Cumpre `porta.MotorDeCriativo` sobre um `ImageGenerator` do FunnelForge.

    O motor de baixo é síncrono: `solicitar_geracao` já gera e guarda o
    resultado debaixo do id, e `receber` só serve. É o custo de uma linha para
    honrar um contrato de dois passos que os motores de vídeo vão precisar.
    """

    tipos_suportados = frozenset(TIPOS_DE_IMAGEM)

    def __init__(self, gerador, *, versao: str = "", tamanhos: tuple[str, ...] = TAMANHOS_ACEITOS) -> None:
        if not hasattr(gerador, "generate"):
            raise TypeError(
                "o gerador injetado não cumpre o port ImageGenerator do FunnelForge "
                "(falta `.generate(prompt, size) -> bytes`)"
            )
        self._gerador = gerador
        self._tamanhos = tamanhos
        modelo = getattr(gerador, "model", "") or gerador.__class__.__name__
        self.nome = f"funnelforge:{modelo}"
        self.versao = versao or str(getattr(gerador, "quality", "") or "")
        self._resultados: dict[str, RespostaDoMotor] = {}
        self._contador = 0

    def solicitar_geracao(self, pedido: PedidoDeGeracao) -> str:
        if pedido.tipo not in self.tipos_suportados:
            raise PedidoRecusado(
                f"{self.nome} gera imagem; {pedido.tipo.value} não é imagem"
            )
        self._contador += 1
        id_do_pedido = f"ff-{self._contador:03d}"
        tamanho = tamanho_para(pedido.especificacao, self._tamanhos)

        arquivos: list[ArquivoGerado] = []
        falhas: list[Falha] = []
        custo_total = 0.0
        houve_custo = False

        for i in range(pedido.quantidade):
            try:
                dados = self._gerador.generate(pedido.insumo, size=tamanho)
            except Exception as e:  # noqa: BLE001 — traduzir, não deixar vazar cru
                # Um item recusado não derruba os outros: vira dado e o laço segue.
                falhas.append(Falha(
                    referencia=f"{id_do_pedido}#{i}",
                    motivo=f"{type(e).__name__}: {e}",
                    codigo=_codigo_do_erro(e),
                    tipo=pedido.tipo,
                    permanente=_e_permanente(e),
                ))
                continue

            largura, altura, mime = _medir(dados)
            custo = _custo_da_ultima(self._gerador)
            if custo is not None:
                custo_total += custo
                houve_custo = True
            arquivos.append(ArquivoGerado(
                conteudo=dados,
                mime=mime,
                largura=largura,
                altura=altura,
                custo_usd=custo,
                metadados={
                    "tamanho_pedido": tamanho,
                    "rotulo": f"{pedido.referencia} {pedido.tipo.value} {i}",
                },
            ))

        self._resultados[id_do_pedido] = RespostaDoMotor(
            pedido=id_do_pedido,
            arquivos=tuple(arquivos),
            falhas=tuple(falhas),
            custo_usd=custo_total if houve_custo else None,
        )
        return id_do_pedido

    def receber(self, id_do_pedido: str) -> RespostaDoMotor:
        resposta = self._resultados.get(id_do_pedido)
        if resposta is None:
            raise PedidoDesconhecido(
                f"{id_do_pedido!r} não foi emitido por este motor", pedido=id_do_pedido
            )
        return resposta


def _custo_da_ultima(gerador) -> float | None:
    """Lê `last_usage.cost_usd` — o contrato OPCIONAL de telemetria do port.

    `None` quando o motor não reporta. Não `0.0`: fingir que a imagem foi de
    graça é o defeito que o `image_pricing` do FunnelForge já pagou para
    aprender ("custo 0.0 com fonte desconhecido" era mentira no ledger).
    """
    uso = getattr(gerador, "last_usage", None)
    custo = getattr(uso, "cost_usd", None)
    return float(custo) if isinstance(custo, (int, float)) else None


def _status_http(e: Exception) -> int | None:
    resposta = getattr(e, "response", None)
    codigo = getattr(resposta, "status_code", None)
    return codigo if isinstance(codigo, int) else None


def _e_permanente(e: Exception) -> bool:
    """4xx que não é 408/429 não melhora se for retentado com o mesmo insumo.

    Mesma lição de `copy/ciclo.py`: retentar política não é ineficiência, é
    chamar atenção. 429 e 5xx são transporte e valem nova tentativa.
    """
    status = _status_http(e)
    if status is None:
        return False
    return 400 <= status < 500 and status not in (408, 429)


def _codigo_do_erro(e: Exception) -> str:
    status = _status_http(e)
    if status is None:
        return "MOTOR.indisponivel"
    return f"MOTOR.http_{status}"
