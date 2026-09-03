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

⚠️ **Este parágrafo já foi falso, e é por isso que ele está aqui.** Ele dizia que
sem `sandbox-exec` (não-macOS) o motor "produz assim mesmo" e o gate sai
`SKIPPED`. A revisão adversarial derrubou esse desenho, o código mudou — e o
texto ficou. `render_sem_rede` **nunca emite `SKIPPED`**; ele tem três saídas, e
todas são afirmação de alguém:

  · `PASS`  — bloqueante, e quem responde é o KERNEL, por uma sonda que roda
              dentro do próprio processo do render. Existir `sandbox-exec` no
              disco não é prova de nada.
  · `WARN`  — não-bloqueante, e é a ÚNICA forma de uma peça sair sem hermetismo
              provado. Exige `CRIATIVO_PERMITIR_RENDER_COM_REDE`, e o nome da
              variável fica no recibo: alguém dispensou, e está dito quem.
  · `FAIL`  — bloqueante, e é o padrão onde não há sandbox. Sem prova de que a
              rede não foi alcançada, o trabalho NÃO chega a `rendered`.

Um contrato publicado que descreve o comportamento anterior é pior que nenhum:
quem lê planeja o deploy em Linux contando com um `SKIPPED` que não existe.

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
import platform
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

#: Códigos com que o kernel RECUSA a saída. `ENETUNREACH`/`ECONNREFUSED` não
#: entram: eles significam "não cheguei lá", que uma máquina sem rede também
#: produz — e provar hermetismo com ausência de rede é provar outra coisa.
_CODIGOS_DE_RECUSA: frozenset[str] = frozenset({"EPERM", "EACCES"})


def _permitir_render_com_rede() -> bool:
    """Escape explícito para máquina sem `sandbox-exec`.

    Existe porque recusar todo render fora do macOS trocaria uma garantia por
    indisponibilidade. Mas ele é EXPLÍCITO e nomeado: o default recusa, e quem
    dispensa o hermetismo deixa a decisão registrada no recibo.
    """
    return os.environ.get("CRIATIVO_PERMITIR_RENDER_COM_REDE", "").strip() in ("1", "true", "True")


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


def _versao_de_ferramenta(nome: str) -> str:
    """A primeira linha de `<nome> -version`, ou `ausente`. Nunca o basename."""
    caminho = shutil.which(nome)
    if caminho is None:
        return "ausente"
    try:
        r = subprocess.run(  # noqa: S603 — binário resolvido por which
            [caminho, "-version"], capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "nao_apurada"
    primeira = (r.stdout or "").splitlines()[:1]
    return primeira[0].strip()[:120] if primeira else "nao_apurada"


def _versao_do_chromium(raiz: Path) -> str:
    """A versão do Chrome Headless Shell que o Remotion baixou, do arquivo VERSION."""
    for candidato in (raiz / "node_modules" / ".remotion" / "chrome-headless-shell" / "VERSION",):
        try:
            return candidato.read_text("utf-8").strip()[:64]
        except OSError:
            continue
    return "nao_baixado"


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


def _numero(p: dict[str, Any], chave: str, *, padrao: float, converte: Any) -> Any:
    """Ausente usa o padrão declarado; PRESENTE-porém-inválido é recusado.

    A distinção é o ponto: "o operador não pediu fps" e "o operador pediu fps
    zero" são fatos diferentes, e o `or` da versão anterior os colapsava.
    """
    if chave not in p or p[chave] is None:
        return converte(padrao)
    try:
        valor = converte(p[chave])
    except (TypeError, ValueError) as exc:
        raise FalhaDoMotor(f"{chave} nao e numero", permanente=True) from exc
    if valor <= 0:
        raise FalhaDoMotor(f"{chave} precisa ser positivo, veio {valor}", permanente=True)
    return valor


def _booleano(p: dict[str, Any], chave: str, *, padrao: bool) -> bool:
    if chave not in p or p[chave] is None:
        return padrao
    valor = p[chave]
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str) and valor.strip().lower() in ("true", "false"):
        return valor.strip().lower() == "true"
    raise FalhaDoMotor(f"{chave} nao e booleano: {valor!r}", permanente=True)


def _ler_pedido(encomenda: Encomenda) -> _Pedido:
    p = encomenda.parametros
    titulo = str(p.get("insumo") or p.get("titulo") or "").strip()
    if not titulo:
        # Mesma regra do `MotorPngLocal`: sem insumo, o pixel seria o mesmo para
        # qualquer briefing, e a procedência diria que veio de um prompt que não
        # existiu.
        raise FalhaDoMotor("sem insumo: renderizar o que?", permanente=True)

    # ⚠️ ACHADO ADVERSARIAL. Antes era `int(p.get("fps") or 30)`: `None` virava 30,
    # `0` virava 30 e `"0"` virava 30. Ausencia virando valor, no arquivo que
    # existe para nao deixar ausencia virar valor — e o pior tipo, porque o
    # recibo depois AFIRMA 30 fps como se alguem tivesse pedido.
    #
    # Agora a ausencia tem default DECLARADO (a peca precisa de algum fps) e o
    # valor PRESENTE-porem-invalido e recusado com o motivo, em vez de
    # silenciosamente substituido.
    fps = _numero(p, "fps", padrao=30, converte=int)
    duracao = _numero(p, "duracao_s", padrao=3.0, converte=float)
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
        #
        # ⚠️ `bool()` puro aceitava `"false"` como VERDADEIRO (string não-vazia) e
        # `None` como falso — duas leituras erradas do mesmo campo. Um booleano
        # que vem de JSON tem de ser booleano, e o que não é diz por quê.
        com_audio=_booleano(p, "com_audio", padrao=True),
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
    #: O que este motor produz. O catalogo pergunta; ele nao chuta.
    midias = ("video",)

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
        # ⚠️ ACHADO ADVERSARIAL. Isto gravava o BASENAME (`"ffmpeg"`), que é a
        # mesma string em qualquer máquina e em qualquer versão. Uma "versão
        # congelada" que não distingue ffmpeg 6 de ffmpeg 8 congela nada, e o
        # ffmpeg participa do render: ele encoda o vídeo e sintetiza o leito.
        #
        # Chromium e plataforma entram pelo mesmo motivo, e por um mais forte: a
        # equivalência de pixel macOS ↔ Linux é NÃO PROVADA, e sem estes dois
        # campos dois recibos de plataformas diferentes pareceriam comparáveis.
        congeladas["ffmpeg"] = _versao_de_ferramenta("ffmpeg")
        congeladas["ffprobe"] = _versao_de_ferramenta("ffprobe")
        congeladas["chrome_headless_shell"] = _versao_do_chromium(self._raiz)
        congeladas["plataforma"] = f"{platform.system()}-{platform.machine()}"
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

            usou_sandbox, saida_proc, do_renderizador = self._renderizar(pedido_json)
            relatorio["sandbox"] = usou_sandbox
            # A sonda de rede vem DE DENTRO do processo que renderizou. Sem ela o
            # gate `render_sem_rede` nao tem em que se apoiar, e reprova — que e o
            # comportamento certo: ausencia de prova nao e prova de ausencia.
            relatorio["rede"] = do_renderizador.get("rede")
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
            # ⚠️ ACHADO ADVERSARIAL. A versão anterior montava `MedidaDeVideo` com
            # `medida.largura or 0`, `medida.fps_num or 0`, `medida.fps_den or 1` e
            # `medida.codec_video or "desconhecido"`. Isso transformava ausência de
            # medição em NÚMERO — e o recibo passava a AFIRMAR `0 fps`, `0 quadros`
            # e um codec chamado "desconhecido", que é exatamente o que este
            # sistema inteiro existe para não fazer.
            #
            # Um artefato que o ffprobe não conseguiu medir por inteiro não é um
            # artefato com medidas zeradas: é um artefato que ninguém sabe se
            # serve. O motor recusa, e o operário registra a falha com o motivo.
            faltando = [
                nome for nome, valor in (
                    ("codec_video", medida.codec_video), ("largura", medida.largura),
                    ("altura", medida.altura), ("fps_num", medida.fps_num),
                    ("fps_den", medida.fps_den), ("quadros", medida.quadros),
                    ("duracao_s", medida.duracao_s),
                ) if valor is None
            ]
            if faltando:
                raise FalhaDoMotor(
                    "o arquivo produzido foi medido pela metade; sem "
                    + ", ".join(faltando),
                    permanente=False,
                )
            dados = arquivo.read_bytes()
            relatorio["por_slot"][saida.slot] = {
                "arquivo": str(arquivo),
                "quadros_pedidos": quadros,
                "fps_pedido": pedido.fps,
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
                    # Sem `or 0`: o bloco acima já recusou a medida incompleta,
                    # então aqui todo valor é uma medida de verdade.
                    codec_video=medida.codec_video,
                    codec_audio=medida.codec_audio,
                    largura=medida.largura,
                    altura=medida.altura,
                    fps_num=medida.fps_num,
                    fps_den=medida.fps_den,
                    quadros=medida.quadros,
                    duracao_s=medida.duracao_s,
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
                    largura_nativa=medida.largura,
                    altura_nativa=medida.altura,
                    largura_alvo=saida.largura,
                    altura_alvo=saida.altura,
                    operacao="nenhuma",
                ),
            ))

        (destino / RELATORIO).write_text(json.dumps(relatorio), encoding="utf-8")
        return tuple(artefatos)

    def _renderizar(self, pedido_json: Path) -> tuple[bool, str, dict[str, Any]]:
        """Roda o renderizador.

        Devolve `(usou_sandbox, motivo_do_erro, relatorio_do_renderizador)`. O
        terceiro item carrega a sonda de rede, e e o que sustenta o gate de
        hermetismo: o veredito vem do kernel respondendo DENTRO do processo que
        renderizou, e nao de dois arquivos existirem no disco.
        """
        base = ["node", "renderizar.mjs", str(pedido_json)]
        perfil = perfil_de_sandbox()
        caixa = Path("/usr/bin/sandbox-exec")
        usou_sandbox = caixa.is_file() and perfil.is_file()
        argumentos = (
            [str(caixa), "-f", str(perfil), *base] if usou_sandbox else list(base)
        )
        # ⚠️ ACHADO ADVERSARIAL. `subprocess.run(timeout=...)` mata o processo
        # `node` e mais nada: o Chromium que ele lançou é filho, e sobrevive.
        # Um render abortado por timeout deixava um navegador headless de 193 MB
        # rodando, e o próximo timeout deixava outro.
        #
        # `start_new_session=True` põe o render num grupo de processos próprio, e
        # o `killpg` derruba a árvore inteira — inclusive o compositor do Remotion,
        # que também é filho.
        processo = subprocess.Popen(  # noqa: S603
            argumentos, cwd=str(self._raiz), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            saida_padrao, saida_erro = processo.communicate(timeout=TEMPO_LIMITE_S)
        except subprocess.TimeoutExpired as exc:
            _derrubar_arvore(processo)
            processo.communicate()
            raise FalhaDoMotor(
                f"o render passou de {TEMPO_LIMITE_S:.0f}s e foi interrompido",
                permanente=False,
            ) from exc
        r = subprocess.CompletedProcess(
            argumentos, processo.returncode, saida_padrao, saida_erro
        )
        motivo = ""
        do_renderizador: dict[str, Any] = {}
        for linha in (r.stdout or "").splitlines():
            if linha.startswith(_MARCA):
                try:
                    corpo = json.loads(linha[len(_MARCA):])
                except json.JSONDecodeError:
                    continue
                do_renderizador = corpo
                if not corpo.get("ok"):
                    motivo = str(corpo.get("erro") or "")[:200]
        if r.returncode != 0 and not motivo:
            linhas = (r.stderr or "").strip().splitlines()
            motivo = linhas[-1][:200] if linhas else ""
        return usou_sandbox, motivo, do_renderizador

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

        # ⚠️ ACHADO ADVERSARIAL, e era o pior desta fatia. A versão anterior
        # marcava `PASS` porque `/usr/bin/sandbox-exec` e o perfil EXISTEM no
        # disco — afirmando que o sandbox foi aplicado a partir de dois arquivos
        # estarem lá. E, onde eles não existem, saía `SKIPPED` não-bloqueante: o
        # trabalho chegava a `rendered` com rede liberada, e o hermetismo deixava
        # de ser invariante do motor para virar propriedade do sistema
        # operacional de quem rodou.
        #
        # Agora quem responde é o KERNEL, de dentro do próprio processo que
        # renderizou: `renderizar.mjs` tenta uma conexão externa antes do bundle e
        # relata o código de erro. `EPERM` é recusa do sandbox. `TIMEOUT` NÃO
        # prova bloqueio — pode ser máquina sem rede —, e as duas coisas levam a
        # conclusões diferentes.
        rede = relatorio.get("rede") or {}
        codigo = str(rede.get("codigo") or "sem-sonda")
        bloqueou = rede.get("saiu") is False and codigo in _CODIGOS_DE_RECUSA
        permitido = _permitir_render_com_rede()
        if bloqueou:
            gates.append(Validacao(
                gate="render_sem_rede", resultado="PASS",
                detalhe={"instrumento": "sonda no processo do render",
                         "resposta_do_kernel": codigo,
                         "sandbox": relatorio.get("sandbox"),
                         "perfil": perfil_de_sandbox().name},
                bloqueante=True))
        elif permitido:
            # Escape EXPLÍCITO, e é a única forma de uma peça sair sem hermetismo
            # provado. Ele é `WARN` e não `SKIPPED`: alguém decidiu, e a decisão
            # fica no recibo com o nome da variável que a tomou.
            gates.append(Validacao(
                gate="render_sem_rede", resultado="WARN",
                detalhe={"motivo": "hermetismo dispensado por CRIATIVO_PERMITIR_RENDER_COM_REDE",
                         "resposta_da_sonda": codigo,
                         "sandbox": relatorio.get("sandbox")},
                bloqueante=False))
        else:
            gates.append(Validacao(
                gate="render_sem_rede", resultado="FAIL",
                detalhe={"motivo": "o render alcancou a rede, ou nao houve prova de que nao alcancou",
                         "resposta_da_sonda": codigo,
                         "sandbox": relatorio.get("sandbox"),
                         "como_dispensar": "CRIATIVO_PERMITIR_RENDER_COM_REDE=1"},
                bloqueante=True))

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

            # ⚠️ ACHADO ADVERSARIAL. O gate só conferia se numerador e
            # denominador eram truthy — um pedido de 24 fps com arquivo medido em
            # 30 passava PASS. Um gate que não compara com o pedido não é gate.
            num, den = medida.get("fps_num"), medida.get("fps_den")
            pedido_fps = dados.get("fps_pedido")
            if not num or not den:
                gates.append(Validacao(
                    gate="fps", resultado="FAIL",
                    detalhe={"slot": slot, "motivo": "o arquivo nao declarou taxa de quadros"},
                    bloqueante=True))
            else:
                # A fração inteira, e não o float: `30000/1001` arredondado para
                # `29.97` volta como outra coisa, e um quadro a cada mil é o que
                # dessincroniza áudio num corte longo.
                bate = pedido_fps is not None and num == pedido_fps * den
                gates.append(Validacao(
                    gate="fps", resultado="PASS" if bate else "FAIL",
                    detalhe={"slot": slot, "fps_num": num, "fps_den": den,
                             "fps_pedido": pedido_fps},
                    bloqueante=True))

            esperado = pedido.get(slot)
            if esperado is not None:
                # ⚠️ ACHADO ADVERSARIAL. Isto era `resultado="PASS"` fixo,
                # calculado a partir do PEDIDO, sem abrir o arquivo. Um gate que
                # sempre aprova não pode reprovar nada, e um gate que não pode
                # reprovar é decoração — o que a própria docstring do operário
                # diz sobre `VALIDATING`.
                #
                # A margem é real e vive no código que DESENHA
                # (`Composicao.tsx`, `padding: height*0.1 / width*0.1`), mas
                # ninguém mede os pixels do quadro para conferir que a tinta
                # respeitou. Enquanto essa medição não existir, o honesto é
                # `SKIPPED` com o motivo: ausência de medição não é aprovação.
                margem_x = round(esperado.largura * 0.10)
                margem_y = round(esperado.altura * 0.10)
                gates.append(Validacao(
                    gate="safe_zone", resultado="SKIPPED",
                    detalhe={"slot": slot,
                             "margem_declarada_px": [margem_x, margem_y],
                             "fracao_declarada": 0.10,
                             "fonte": "padding declarado em Composicao.tsx",
                             "motivo": (
                                 "a margem e declarada pela composicao e nao medida "
                                 "nos pixels do quadro"
                             )},
                    bloqueante=False))
        return tuple(gates)

    @staticmethod
    def _relatorio(dir_trabalho: str) -> dict[str, Any]:
        caminho = Path(dir_trabalho) / RELATORIO
        try:
            return json.loads(caminho.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


def _derrubar_arvore(processo: subprocess.Popen) -> None:
    """SIGTERM no grupo, e SIGKILL no que sobrar."""
    import os as _os  # noqa: PLC0415
    import signal  # noqa: PLC0415
    import time  # noqa: PLC0415

    try:
        grupo = _os.getpgid(processo.pid)
    except (OSError, AttributeError):
        processo.kill()
        return
    for sinal, prazo in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 0.0)):
        try:
            _os.killpg(grupo, sinal)
        except OSError:
            return
        if prazo <= 0:
            return
        fim = time.monotonic() + prazo
        while time.monotonic() < fim:
            if processo.poll() is not None:
                return
            time.sleep(0.1)


def _nome_de_arquivo(slot: str) -> str:
    """O slot vem do pedido e vira nome de arquivo; um separador de caminho aí
    escreveria fora do diretório exclusivo do trabalho."""
    import re  # noqa: PLC0415

    limpo = re.sub(r"[^A-Za-z0-9._-]", "-", slot).strip("-.") or "saida"
    return limpo[:96]
