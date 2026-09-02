"""Mede um arquivo de vídeo com `ffprobe`. Ausência é `None`, nunca `0`.

## Por que este adaptador existe

`medir_imagem` lê PNG, JPEG e GIF com a stdlib e recusa deliberadamente uma
dependência que o ambiente de produção pode não ter. Vídeo não tem esse caminho:
um MP4 é um contêiner com átomos aninhados, e reimplementar o parser aqui seria
escrever um decodificador pior do que o que já está instalado.

A diferença que importa é a **fronteira do modo de falha**: quando `ffprobe` não
está disponível, este módulo devolve `Medida()` inteira em `None` e diz por quê
em `erro`. Ele nunca devolve `0`, nunca devolve dimensão parcial e nunca devolve
uma medida que não leu do arquivo.

## O que ele NÃO faz

Não julga. `criativo/validacao.py` já registrou o dono dessa decisão: "não abre
arquivo, não mede pixel... ele julga o que já foi medido; medir é trabalho do
adaptador". Aqui só se mede.

## FPS como fração

`fps_num`/`fps_den` viajam como a fração que o `ffprobe` devolve, e não como
float. `30000/1001` — o NTSC de 29,97 — vira `29.97` num `round(2)` e volta como
outra coisa. A diferença entre 29,97 e 30 acumula um quadro a cada mil, e é
exatamente o que dessincroniza áudio num corte longo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

#: Teto de espera do `ffprobe`. Um arquivo corrompido pode fazer o demuxer
#: procurar cabeçalho até o fim do arquivo; sem teto, o operário que chama isto
#: fica preso segurando um lease.
TEMPO_LIMITE_S = 30.0


@dataclass(frozen=True)
class MedidaDeVideo:
    """Tudo `None` quando não deu para medir. `erro` diz por quê."""

    codec_video: str | None = None
    codec_audio: str | None = None
    largura: int | None = None
    altura: int | None = None
    fps_num: int | None = None
    fps_den: int | None = None
    #: Quadros CONTADOS, não estimados pelo cabeçalho. Um `nb_frames` de
    #: cabeçalho é declaração do muxer; contar decodifica.
    quadros: int | None = None
    duracao_s: float | None = None
    sample_rate: int | None = None
    canais: int | None = None
    bytes_: int | None = None
    formato: str | None = None
    #: Versão do medidor que produziu isto. Duas versões de ffprobe podem
    #: discordar, e o recibo precisa saber qual leu.
    fonte: str | None = None
    erro: str | None = None

    @property
    def mediu(self) -> bool:
        return self.erro is None and self.largura is not None

    @property
    def tem_audio(self) -> bool | None:
        """`None` quando nem o arquivo foi lido — ausência de leitura não é
        ausência de áudio."""
        if self.erro is not None:
            return None
        return self.codec_audio is not None


def _versao() -> str | None:
    caminho = shutil.which("ffprobe")
    if caminho is None:
        return None
    try:
        saida = subprocess.run(  # noqa: S603 — binário resolvido por which
            [caminho, "-version"], capture_output=True, text=True, timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    primeira = (saida.stdout or "").splitlines()[:1]
    return primeira[0].strip() if primeira else "ffprobe"


def _fracao(texto: str | None) -> tuple[int | None, int | None]:
    if not texto or "/" not in texto:
        return (None, None)
    num, _, den = texto.partition("/")
    try:
        n, d = int(num), int(den)
    except ValueError:
        return (None, None)
    # `0/0` é o que o ffprobe devolve para faixa sem taxa de quadros. Ele
    # significa "não se aplica", e virar `0` faria um vídeo parecer parado.
    if d == 0:
        return (None, None)
    return (n, d)


def medir(caminho: str) -> MedidaDeVideo:
    """Lê o arquivo com `ffprobe` e devolve o que ele disse — ou o motivo."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return MedidaDeVideo(erro="ffprobe ausente nesta maquina")

    argumentos = [
        ffprobe, "-v", "error",
        "-count_frames",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,"
        "nb_read_frames,sample_rate,channels",
        "-show_entries", "format=duration,size,format_name",
        "-of", "json", caminho,
    ]
    try:
        saida = subprocess.run(  # noqa: S603 — binário resolvido por which
            argumentos, capture_output=True, text=True, timeout=TEMPO_LIMITE_S,
        )
    except subprocess.TimeoutExpired:
        return MedidaDeVideo(erro=f"ffprobe nao respondeu em {TEMPO_LIMITE_S:.0f}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return MedidaDeVideo(erro=f"ffprobe nao executou: {type(exc).__name__}")
    if saida.returncode != 0:
        return MedidaDeVideo(erro="ffprobe recusou o arquivo")

    try:
        dados = json.loads(saida.stdout or "{}")
    except json.JSONDecodeError:
        return MedidaDeVideo(erro="ffprobe devolveu saida ilegivel")

    fluxos = dados.get("streams") or []
    formato = dados.get("format") or {}
    video = next((f for f in fluxos if f.get("codec_type") == "video"), None)
    audio = next((f for f in fluxos if f.get("codec_type") == "audio"), None)
    if video is None:
        return MedidaDeVideo(erro="o arquivo nao tem faixa de video")

    num, den = _fracao(video.get("r_frame_rate"))
    quadros = video.get("nb_read_frames")
    try:
        quadros_i = int(quadros) if quadros not in (None, "N/A") else None
    except (TypeError, ValueError):
        quadros_i = None

    def _int(valor: object) -> int | None:
        try:
            n = int(valor)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        # ⚠️ Zero aqui seria medida impossível (largura zero, zero canais) e a
        # regra da casa é que ausência é `None`. Devolver `0` faria a validação
        # reprovar culpando quem mediu.
        return n if n > 0 else None

    def _float(valor: object) -> float | None:
        try:
            f = float(valor)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return f if f > 0 else None

    return MedidaDeVideo(
        codec_video=video.get("codec_name"),
        codec_audio=(audio or {}).get("codec_name"),
        largura=_int(video.get("width")),
        altura=_int(video.get("height")),
        fps_num=num,
        fps_den=den,
        quadros=quadros_i,
        duracao_s=_float(formato.get("duration")),
        sample_rate=_int((audio or {}).get("sample_rate")),
        canais=_int((audio or {}).get("channels")),
        bytes_=_int(formato.get("size")),
        formato=formato.get("format_name"),
        fonte=_versao(),
    )


@dataclass(frozen=True)
class MedidaDeLoudness:
    """LUFS integrado e true peak, em NÚMERO.

    ⚠️ O legado reduzia os dois a PASS/FAIL, e um gate que só diz "passou"
    impede a próxima pergunta: passou por quanto? A margem é o que decide se vale
    remixar. Por isso `MedidaDeAudio`, no contrato da bancada, guarda números.
    """

    lufs_integrado: float | None = None
    true_peak_dbtp: float | None = None
    fonte: str | None = None
    erro: str | None = None


def medir_loudness(caminho: str) -> MedidaDeLoudness:
    """Mede com o filtro `ebur128` do ffmpeg — a implementação da EBU R128."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return MedidaDeLoudness(erro="ffmpeg ausente nesta maquina")
    argumentos = [
        ffmpeg, "-hide_banner", "-nostats", "-i", caminho,
        "-filter_complex", "ebur128=peak=true", "-f", "null", "-",
    ]
    try:
        saida = subprocess.run(  # noqa: S603 — binário resolvido por which
            argumentos, capture_output=True, text=True, timeout=TEMPO_LIMITE_S,
        )
    except subprocess.TimeoutExpired:
        return MedidaDeLoudness(erro=f"ffmpeg nao respondeu em {TEMPO_LIMITE_S:.0f}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return MedidaDeLoudness(erro=f"ffmpeg nao executou: {type(exc).__name__}")
    if saida.returncode != 0:
        return MedidaDeLoudness(erro="ffmpeg recusou o arquivo")

    # O resumo do ebur128 sai no fim do stderr, em blocos indentados.
    texto = saida.stderr or ""
    lufs = _apos(texto, "Integrated loudness", "I:")
    pico = _apos(texto, "True peak", "Peak:")
    if lufs is None and pico is None:
        return MedidaDeLoudness(erro="o resumo do ebur128 nao apareceu na saida")
    return MedidaDeLoudness(
        lufs_integrado=lufs, true_peak_dbtp=pico, fonte="ffmpeg ebur128",
    )


def _apos(texto: str, secao: str, rotulo: str) -> float | None:
    """Lê o número que segue `rotulo` dentro do bloco `secao`.

    ⚠️ Procurar `rotulo` no texto inteiro pegaria o `I:` do resumo por trecho,
    que é outro número. A seção delimita.
    """
    inicio = texto.rfind(secao)
    if inicio < 0:
        return None
    trecho = texto[inicio : inicio + 400]
    pos = trecho.find(rotulo)
    if pos < 0:
        return None
    resto = trecho[pos + len(rotulo):].strip().split()
    if not resto:
        return None
    bruto = resto[0]
    try:
        return float(bruto)
    except ValueError:
        # `-inf` é o que o ebur128 devolve para silêncio absoluto. Não é
        # ausência de medida: é a medida do silêncio, e vira `float('-inf')`.
        if bruto.lstrip("-").lower().startswith("inf"):
            return float("-inf") if bruto.startswith("-") else float("inf")
        return None
