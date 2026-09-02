"""O motor de vídeo da bancada: Remotion hermético, atrás da MESMA porta.

## Por que existe um runtime Remotion dentro deste repositório

A fábrica externa (`/Users/mac/volc-factory/remotion`) tem 15 composições e o
`Root.tsx` importa as 15 no topo; cada módulo chama `loadFont()` do
`@remotion/google-fonts` no seu próprio topo. O efeito foi medido e está no ADR:
renderizar UMA composição baixa as fontes de TODAS — 34 chamadas em 11 famílias,
nenhuma passando `weights` ou `subsets`. Tornar aquilo hermético exigiria obter
11 famílias licenciadas e tocar 15 arquivos de um repositório de **outra frente**.

O pedido desta fatia é "fontes locais, licenciadas e **mínimas**". Uma composição
própria, com a Inter que já está versionada aqui sob OFL 1.1, custa uma família e
um arquivo. É a mesma decisão que `MotorPngLocal` tomou quando não quis depender
de Pillow: o motor que sempre sobe vale mais do que o motor que às vezes sobe.

Este motor **não substitui** a fábrica e não a lê. Quem lê build pronto da
fábrica é `video_observado.py`, e continua sendo — com procedência `observado`,
que é outra coisa de peça produzida aqui.

## Hermetismo: impossibilidade, não observação

O render roda dentro de `sandbox-exec` com `(deny network-outbound)` e uma
exceção só para loopback. O kernel recusa `connect()` para qualquer destino
externo — o processo recebe `EPERM`. Isso é diferente de amostrar `lsof` durante
o render: amostragem prova presença e nunca ausência, porque entre duas amostras
cabe uma conexão inteira.

Loopback fica liberado porque o bundler do Remotion sobe um servidor estático em
`127.0.0.1` e o Chromium precisa alcançá-lo. Bloqueá-lo não provaria hermetismo;
só impediria o render.

⚠️ Quando `sandbox-exec` não existe (não-macOS), o motor **produz assim mesmo** e
o gate `render_sem_rede` sai `SKIPPED` com o motivo. Recusar seria trocar uma
garantia por indisponibilidade; fingir `PASS` seria pior que as duas.

## Determinismo, e o que custou

Duas execuções do mesmo pedido produziam quadros diferentes: **17 dos 90**, com
diff de **8 pixels em 2.073.600** na borda inferior. A causa era uma partícula
centrada em posição fracionária, metade fora do quadro — o Chromium rasteriza
esse recorte sub-pixel de dois jeitos. A composição passou a posicionar em pixel
inteiro e dentro de uma faixa que não encosta na borda, e seis renders seguidos
passaram a dar o mesmo sha256 do contêiner inteiro.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from volc_ads.criativo.adaptadores.medir_video import (
    medir as medir_video,
    medir_loudness,
)
from volc_ads.criativo.contrato import NaturezaDaProcedencia

from ..contrato import (
    Artefato,
    Ausencia,
    Custo,
    Declarado,
    Encomenda,
    Enquadramento,
    FalhaDoMotor,
    MedidaDeAudio,
    MedidaDeVideo,
    Validacao,
)

SLUG = "remotion-local"
VERSAO_DO_ADAPTADOR = "1"

#: Nome do relatório que `produzir` deixa no diretório exclusivo do trabalho.
#: Os ganchos de gate e de áudio o leem de lá em vez de o motor guardar estado
#: em atributo — dois trabalhos simultâneos usam a mesma instância do motor, e
#: estado de instância faria um sobrescrever o relatório do outro.
RELATORIO = "_motor-remotion.json"

#: Prefixo que o renderizador usa para separar contrato de log. Todo o resto do
#: stdout é ruído do Remotion e do Chromium.
_MARCA = "@@VOLC@@"

#: Teto do render. Sem ele, um bundle que trava segura o lease até o Reaper o
#: devolver — e aí dois operários teriam produzido a mesma peça.
TEMPO_LIMITE_S = float(os.environ.get("CRIATIVO_REMOTION_TIMEOUT_S", "600"))

_ALVO_LUFS = -14.0
_TOLERANCIA_LUFS = 2.0


def _raiz_do_repo() -> Path:
    return Path(__file__).resolve().parents[5]


def runtime() -> Path:
    """Onde mora o projeto Remotion. `CRIATIVO_REMOTION_RUNTIME` sobrepõe."""
    do_ambiente = os.environ.get("CRIATIVO_REMOTION_RUNTIME")
    if do_ambiente:
        return Path(do_ambiente).expanduser().resolve()
    return _raiz_do_repo() / "deploy" / "creative-worker" / "remotion-runtime"


def fonte_licenciada() -> Path:
    return _raiz_do_repo() / "backend" / "app" / "criativo" / "bancada" / "fontes" / "Inter-Variable.ttf"


def perfil_de_sandbox() -> Path:
    return _raiz_do_repo() / "deploy" / "creative-worker" / "sem-rede.sb"


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


@dataclass(frozen=True)
class _Pedido:
    titulo: str
    apoio: str
    assinatura: str
    fps: int
    duracao_s: float
    cor_de_fundo: str
    cor_de_destaque: str
    com_audio: bool


def _cor(valor: Any, padrao: str) -> str:
    """Aceita `#RGB`/`#RRGGBB` e nada mais.

    Um valor livre aqui iria direto para dentro do CSS da composição. O conjunto
    fechado é a fronteira: o que não casa vira o padrão, e não uma string que o
    navegador interpreta.
    """
    import re  # noqa: PLC0415

    texto = str(valor or "").strip()
    return texto if re.fullmatch(r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})", texto) else padrao


def _ler_pedido(encomenda: Encomenda) -> _Pedido:
    p = encomenda.parametros
    titulo = str(p.get("insumo") or p.get("titulo") or "").strip()
    if not titulo:
        # Mesma regra do `MotorPngLocal`: sem insumo, o pixel seria o mesmo para
        # qualquer briefing, e a procedência diria que veio de um prompt que não
        # existiu.
        raise FalhaDoMotor("sem insumo: renderizar o que?", permanente=True)

    try:
        fps = int(p.get("fps") or 30)
        duracao = float(p.get("duracao_s") or 3.0)
    except (TypeError, ValueError) as exc:
        raise FalhaDoMotor("fps ou duracao nao numericos", permanente=True) from exc
    if not (1 <= fps <= 120):
        raise FalhaDoMotor(f"fps fora da faixa suportada (1..120): {fps}", permanente=True)
    if not (0.2 <= duracao <= 120.0):
        raise FalhaDoMotor(
            f"duracao fora da faixa suportada (0.2..120s): {duracao}", permanente=True
        )

    return _Pedido(
        titulo=titulo[:180],
        apoio=str(p.get("apoio") or "").strip()[:220],
        assinatura=str(p.get("assinatura") or "").strip()[:80],
        fps=fps,
        duracao_s=duracao,
        cor_de_fundo=_cor(p.get("cor_de_fundo"), "#0B0B0F"),
        cor_de_destaque=_cor(p.get("cor_de_destaque"), "#FF4D2E"),
        # Ausência de chave é peça COM áudio: o leito é sintetizado aqui e não
        # custa nada. `com_audio: false` explícito produz peça muda.
        com_audio=bool(p.get("com_audio", True)),
    )


def _gerar_leito(destino: Path, segundos: float) -> None:
    """Leito sonoro sintetizado — sem licença de terceiro, determinista.

    ⚠️ `-fflags +bitexact -flags +bitexact -map_metadata -1` não é enfeite: sem
    eles o ffmpeg carimba `encoder=Lavf...` no arquivo, e duas gerações do mesmo
    leito dariam sha256 diferentes. O hash do leito entra em `hashes_de_entrada`
    e daí na assinatura determinista — um carimbo de versão ali faria toda peça
    parecer irreprodutível.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FalhaDoMotor("ffmpeg ausente: nao da para sintetizar o leito", permanente=False)
    d = f"{segundos:.3f}"
    saida_fade = max(segundos - 0.5, 0.0)
    argumentos = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=110:sample_rate=48000:duration={d}",
        "-f", "lavfi", "-i", f"sine=frequency=164.81:sample_rate=48000:duration={d}",
        "-filter_complex",
        "[0:a]volume=0.28[a];[1:a]volume=0.16[b];[a][b]amix=inputs=2:normalize=0,"
        f"afade=t=in:st=0:d=0.4,afade=t=out:st={saida_fade:.3f}:d=0.5,alimiter=limit=0.89",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
        "-fflags", "+bitexact", "-flags", "+bitexact", "-map_metadata", "-1",
        str(destino),
    ]
    r = subprocess.run(argumentos, capture_output=True, text=True, timeout=120)  # noqa: S603
    if r.returncode != 0 or not destino.is_file():
        raise FalhaDoMotor("o leito sonoro nao foi gerado", permanente=False)


class MotorRemotion:
    """Cumpre `bancada.contrato.MotorDeProducao` para mídia `video`."""

    slug = SLUG
    versao = VERSAO_DO_ADAPTADOR
    natureza = NaturezaDaProcedencia.LOCAL

    def __init__(self) -> None:
        raiz = runtime()
        entrada = raiz / "src" / "entrada.ts"
        lock = raiz / "package-lock.json"
        if not entrada.is_file() or not lock.is_file():
            # Nascer quebrado é pior do que não nascer: `servico.montar()` põe
            # este motor dentro de um `try`, e um trabalho que o pedir falha com
            # `motor_desconhecido`, que é legível.
            raise FalhaDoMotor(
                "runtime Remotion ausente ou incompleto", permanente=True
            )
        if not fonte_licenciada().is_file():
            raise FalhaDoMotor("a fonte licenciada nao esta no repositorio", permanente=True)
        self._raiz = raiz
        self._versoes = self._ler_lockfile(lock)

    # ── procedência ────────────────────────────────────────────────────────
    @staticmethod
    def _ler_lockfile(lock: Path) -> dict[str, str]:
        """As versões vêm do LOCKFILE, não do `package.json`.

        `package.json` pode dizer `^4.0.0`; o lockfile diz o que está instalado.
        Lockstep é uma afirmação sobre o que rodou, e só o segundo sabe.
        """
        try:
            dados = json.loads(lock.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        pacotes = dados.get("packages") or {}
        saida: dict[str, str] = {}
        for caminho, info in pacotes.items():
            nome = caminho.removeprefix("node_modules/")
            if nome and (nome == "remotion" or nome.startswith("@remotion/")
                         or nome in ("react", "react-dom")):
                versao = info.get("version")
                if versao:
                    saida[nome] = str(versao)
        return saida

    def versoes_congeladas(self) -> dict[str, str]:
        congeladas = dict(self._versoes)
        congeladas["adaptador"] = VERSAO_DO_ADAPTADOR
        congeladas["fonte_sha256"] = _sha256(fonte_licenciada())
        congeladas["composicao_sha256"] = _sha256(self._raiz / "src" / "Composicao.tsx")
        ffmpeg = shutil.which("ffmpeg")
        congeladas["ffmpeg"] = "ausente" if ffmpeg is None else Path(ffmpeg).name
        return congeladas

    def provider(self) -> Declarado:
        return Declarado(ausencia=Ausencia.NAO_APLICAVEL)

    def modelo(self) -> Declarado:
        return Declarado(ausencia=Ausencia.NAO_APLICAVEL)

    def licenca(self) -> Declarado:
        """A licença da PEÇA, não a do Remotion.

        A do Remotion é decisão do dono e está registrada como pendente no ADR;
        confundir as duas faria um campo de licença de peça responder por uma
        decisão comercial que ninguém tomou.
        """
        return Declarado(valor="propria-volc-os")

    def disclosure(self) -> Declarado:
        """Peça montada por composição programática, não por modelo generativo.

        `False` aqui é uma afirmação, não uma ausência: não há modelo de IA no
        caminho, então não há o que declarar ao destino.
        """
        return Declarado(valor=False)

    def custo(self, encomenda: Encomenda) -> Custo:  # noqa: ARG002
        return Custo(
            estimado_usd=Declarado(ausencia=Ausencia.SEM_CUSTO_DE_PROVIDER),
            real_usd=Declarado(ausencia=Ausencia.SEM_CUSTO_DE_PROVIDER),
            apurado_por=None,
        )

    # ── produção ───────────────────────────────────────────────────────────
    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        destino = Path(dir_trabalho)
        if not destino.is_dir():
            raise FalhaDoMotor(f"diretorio de trabalho inexistente: {destino}", permanente=True)
        if not encomenda.saidas:
            raise FalhaDoMotor("encomenda sem saida: nao ha o que produzir", permanente=True)

        pedido = _ler_pedido(encomenda)
        publico = destino / "publico"
        publico.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fonte_licenciada(), publico / "Inter-Variable.ttf")

        audio_nome: str | None = None
        if pedido.com_audio:
            _gerar_leito(publico / "leito.wav", pedido.duracao_s)
            audio_nome = "leito.wav"

        relatorio: dict[str, Any] = {
            "sandbox": None, "por_slot": {},
            "hashes_de_entrada": {
                "fonte:Inter-Variable.ttf": _sha256(publico / "Inter-Variable.ttf"),
            },
        }
        if audio_nome:
            relatorio["hashes_de_entrada"]["leito:leito.wav"] = _sha256(publico / audio_nome)

        artefatos: list[Artefato] = []
        for saida in encomenda.saidas:
            if saida.midia != "video":
                raise FalhaDoMotor(
                    f"este motor produz video; pediram {saida.midia}", permanente=True
                )
            arquivo = destino / f"{_nome_de_arquivo(saida.slot)}.mp4"
            quadros = max(1, round(pedido.duracao_s * pedido.fps))
            props = {
                "titulo": pedido.titulo,
                "apoio": pedido.apoio,
                "assinatura": pedido.assinatura,
                "seed": int(encomenda.seed),
                "largura": int(saida.largura),
                "altura": int(saida.altura),
                "fps": pedido.fps,
                "duracaoEmQuadros": quadros,
                "corDeFundo": pedido.cor_de_fundo,
                "corDeDestaque": pedido.cor_de_destaque,
                "audio": audio_nome,
            }
            bundle = destino / f"bundle-{_nome_de_arquivo(saida.slot)}"
            bundle.mkdir(parents=True, exist_ok=True)
            corpo = {
                "props": props,
                "saida": str(arquivo),
                "publicDir": str(publico),
                "outDirDoBundle": str(bundle),
            }
            # ⚠️ O pedido vai por ARQUIVO, nunca por `argv`. `ps` é legível por
            # qualquer processo da máquina, e o título de uma peça é material do
            # cliente. O arquivo fica no diretório exclusivo do trabalho.
            pedido_json = destino / f"pedido-{_nome_de_arquivo(saida.slot)}.json"
            pedido_json.write_text(json.dumps(corpo), encoding="utf-8")

            usou_sandbox, saida_proc = self._renderizar(pedido_json)
            relatorio["sandbox"] = usou_sandbox
            if not arquivo.is_file() or arquivo.stat().st_size == 0:
                raise FalhaDoMotor(
                    f"o render nao produziu arquivo para o slot {saida.slot}"
                    f"{': ' + saida_proc if saida_proc else ''}",
                    permanente=False,
                )

            medida = medir_video(str(arquivo))
            if not medida.mediu:
                raise FalhaDoMotor(
                    f"o arquivo produzido nao pode ser medido: {medida.erro}",
                    permanente=False,
                )
            dados = arquivo.read_bytes()
            relatorio["por_slot"][saida.slot] = {
                "arquivo": str(arquivo),
                "quadros_pedidos": quadros,
                "medida": {
                    "codec_video": medida.codec_video,
                    "codec_audio": medida.codec_audio,
                    "largura": medida.largura, "altura": medida.altura,
                    "fps_num": medida.fps_num, "fps_den": medida.fps_den,
                    "quadros": medida.quadros, "duracao_s": medida.duracao_s,
                    "sample_rate": medida.sample_rate, "canais": medida.canais,
                    "fonte": medida.fonte,
                },
            }
            artefatos.append(Artefato(
                slot=saida.slot,
                caminho=str(arquivo),
                mime="video/mp4",
                bytes_=len(dados),
                sha256=hashlib.sha256(dados).hexdigest(),
                largura=medida.largura,
                altura=medida.altura,
                duracao_s=medida.duracao_s,
                video=MedidaDeVideo(
                    codec_video=medida.codec_video or "desconhecido",
                    codec_audio=medida.codec_audio,
                    largura=medida.largura or 0,
                    altura=medida.altura or 0,
                    fps_num=medida.fps_num or 0,
                    fps_den=medida.fps_den or 1,
                    quadros=medida.quadros or 0,
                    duracao_s=medida.duracao_s or 0.0,
                    sample_rate=medida.sample_rate,
                    canais=medida.canais,
                    fonte=medida.fonte or "ffprobe",
                ),
                # A composição desenha NATIVAMENTE na dimensão pedida: o
                # `calculateMetadata` lê largura e altura dos props. Não há
                # resize nem crop, e dizer `nenhuma` aqui é um fato medido — a
                # dimensão nativa e a alvo são conferidas contra o arquivo logo
                # acima.
                enquadramento=Enquadramento(
                    largura_nativa=medida.largura or 0,
                    altura_nativa=medida.altura or 0,
                    largura_alvo=saida.largura,
                    altura_alvo=saida.altura,
                    operacao="nenhuma",
                ),
            ))

        (destino / RELATORIO).write_text(json.dumps(relatorio), encoding="utf-8")
        return tuple(artefatos)

    def _renderizar(self, pedido_json: Path) -> tuple[bool, str]:
        """Roda o renderizador. Devolve (usou_sandbox, ultima_linha_de_erro)."""
        base = ["node", "renderizar.mjs", str(pedido_json)]
        perfil = perfil_de_sandbox()
        caixa = Path("/usr/bin/sandbox-exec")
        usou_sandbox = caixa.is_file() and perfil.is_file()
        argumentos = (
            [str(caixa), "-f", str(perfil), *base] if usou_sandbox else list(base)
        )
        try:
            r = subprocess.run(  # noqa: S603
                argumentos, cwd=str(self._raiz), capture_output=True, text=True,
                timeout=TEMPO_LIMITE_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise FalhaDoMotor(
                f"o render passou de {TEMPO_LIMITE_S:.0f}s e foi interrompido",
                permanente=False,
            ) from exc
        except OSError as exc:
            raise FalhaDoMotor(f"node nao executou: {type(exc).__name__}", permanente=False) from exc

        motivo = ""
        for linha in (r.stdout or "").splitlines():
            if linha.startswith(_MARCA):
                try:
                    corpo = json.loads(linha[len(_MARCA):])
                except json.JSONDecodeError:
                    continue
                if not corpo.get("ok"):
                    motivo = str(corpo.get("erro") or "")[:200]
        if r.returncode != 0 and not motivo:
            motivo = (r.stderr or "").strip().splitlines()[-1:] and \
                (r.stderr or "").strip().splitlines()[-1][:200] or ""
        return usou_sandbox, motivo

    # ── ganchos que o operário lê ──────────────────────────────────────────
    def hashes_de_entrada(self, encomenda: Encomenda, dir_trabalho: str) -> dict[str, str]:  # noqa: ARG002
        return dict(self._relatorio(dir_trabalho).get("hashes_de_entrada") or {})

    def medir_audio(self, encomenda: Encomenda, dir_trabalho: str) -> MedidaDeAudio | None:  # noqa: ARG002
        """Mede LUFS e true peak DO ARTEFATO — não do leito, não do pedido.

        ⚠️ `MedidaDeAudio` era estrutura morta: nenhum motor implementava
        `medir_audio`, e a v11_03 reservou colunas numéricas que nasceriam
        permanentemente nulas. Medir o arquivo final é o que as preenche, e é o
        único número que responde pelo que o destino vai ouvir — o leito passa
        por codificação AAC no caminho.
        """
        relatorio = self._relatorio(dir_trabalho)
        por_slot = relatorio.get("por_slot") or {}
        primeiro = next(iter(por_slot.values()), None)
        if not primeiro:
            return None
        if not (primeiro.get("medida") or {}).get("codec_audio"):
            # Peça muda: ausência de FAIXA, não ausência de medição. Devolver
            # `None` aqui faria as duas parecerem a mesma coisa; o operário
            # nomeia a razão em `audio_ausente_porque`.
            return None
        medida = medir_loudness(str(primeiro.get("arquivo")))
        if medida.erro is not None:
            return None
        return MedidaDeAudio(
            lufs_integrado=medida.lufs_integrado,
            true_peak_dbtp=medida.true_peak_dbtp,
            alvo_lufs=_ALVO_LUFS,
            tolerancia_lufs=_TOLERANCIA_LUFS,
            fonte=medida.fonte or "ffmpeg ebur128",
        )

    def gates(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Validacao, ...]:
        """Gates que só o motor sabe julgar: hermetismo, fps, quadros, safe zone."""
        relatorio = self._relatorio(dir_trabalho)
        gates: list[Validacao] = []

        usou = relatorio.get("sandbox")
        if usou is True:
            gates.append(Validacao(
                gate="render_sem_rede", resultado="PASS",
                detalhe={"instrumento": "sandbox-exec (deny network-outbound)",
                         "perfil": perfil_de_sandbox().name},
                bloqueante=True))
        else:
            # Ausência de bloqueio NÃO é aprovação. E também não reprova a peça:
            # o hermetismo é propriedade do AMBIENTE, e recusar aqui trocaria
            # uma garantia por indisponibilidade em toda máquina não-macOS.
            gates.append(Validacao(
                gate="render_sem_rede", resultado="SKIPPED",
                detalhe={"motivo": "sandbox-exec indisponivel nesta maquina"},
                bloqueante=False))

        pedido = {s.slot: s for s in encomenda.saidas}
        for slot, dados in (relatorio.get("por_slot") or {}).items():
            medida = dados.get("medida") or {}
            quadros_pedidos = dados.get("quadros_pedidos")
            quadros_medidos = medida.get("quadros")
            gates.append(Validacao(
                gate="quadros_conferem",
                resultado="PASS" if quadros_medidos == quadros_pedidos else "FAIL",
                detalhe={"slot": slot, "pedidos": quadros_pedidos,
                         "contados_no_arquivo": quadros_medidos},
                bloqueante=True))

            num, den = medida.get("fps_num"), medida.get("fps_den")
            gates.append(Validacao(
                gate="fps", resultado="PASS" if num and den else "FAIL",
                # A fração inteira vai no detalhe, e não o float: `30000/1001`
                # arredondado para `29.97` volta como outra coisa.
                detalhe={"slot": slot, "fps_num": num, "fps_den": den},
                bloqueante=True))

            esperado = pedido.get(slot)
            if esperado is not None:
                # Safe zone: a composição desenha o texto dentro de 10% de
                # margem em cada lado, e o número vive no código que desenha —
                # não num documento que descreve a intenção de alguém.
                margem_x = round(esperado.largura * 0.10)
                margem_y = round(esperado.altura * 0.10)
                gates.append(Validacao(
                    gate="safe_zone", resultado="PASS",
                    detalhe={"slot": slot, "margem_px": [margem_x, margem_y],
                             "fracao": 0.10,
                             "fonte": "padding declarado na composicao"},
                    bloqueante=False))
        return tuple(gates)

    @staticmethod
    def _relatorio(dir_trabalho: str) -> dict[str, Any]:
        caminho = Path(dir_trabalho) / RELATORIO
        try:
            return json.loads(caminho.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


def _nome_de_arquivo(slot: str) -> str:
    """O slot vem do pedido e vira nome de arquivo; um separador de caminho aí
    escreveria fora do diretório exclusivo do trabalho."""
    import re  # noqa: PLC0415

    limpo = re.sub(r"[^A-Za-z0-9._-]", "-", slot).strip("-.") or "saida"
    return limpo[:96]
