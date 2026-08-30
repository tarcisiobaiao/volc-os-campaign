"""O leitor de um vídeo que o VOLC O.S. **não** produziu.

## O que este arquivo protege

A afirmação de autoria. O `short_odete` foi renderizado por uma fábrica de
vídeo externa: outro repositório, outro processo, outro dono. O Estúdio
Criativo mostra esse vídeo porque ele é patrimônio útil, e a única coisa que
separa "mostrar" de "assumir a autoria" é o contrato desta leitura.

Por isso este módulo só sabe dizer uma procedência — `observado` — e o token da
procedência oposta, a de produção própria, **não aparece em lugar nenhum deste
arquivo**. Não é disciplina de quem escreve: é ausência de código, e há um
teste que varre o fonte atrás dele. Um campo booleano escondido em metadados
seria fácil de esquecer na renderização; um token que não existe não é.

## O defeito real que motivou cada decisão

**Dois MP4, e só um é o entregável.** O build grava a saída crua do Remotion
(`render.mp4`, sha256 `447e44bf…`) ao lado do arquivo final pós sound design
(`out/<slug>.mp4`, sha256 `dc2e6cb8…`). Só o segundo é o que a fábrica congela
no snapshot, e só ele foi medido pelo QA. Ler o primeiro daria um vídeo que
existe, toca e está **errado** — sem áudio tratado e com hash que não bate com
nada. Este módulo lê exclusivamente o final e confere o sha256 contra o
snapshot; divergência vira `hash_confere=False`, nunca um dado remendado.

**Ausência é `None`.** Mesmo desenho de `volc_ads/criativo/contrato.py` e de
`app/trafego/dominio.py`, e pelo mesmo motivo medido: um leitor que devolve
`0`/`""`/`False` no lugar do que não leu aprova o que mediu errado e reprova o
que não mediu. Aqui isso tem casos concretos: `licenca: null` é o valor **real**
dos cinco itens de Wikimedia do `short_odete` (a fábrica registrou a fonte e
não registrou a licença), e trocá-lo por `"desconhecida"` transformaria uma
lacuna jurídica em texto tranquilizador. `fatos: []` significa "o build não
registrou fatos", não "não há fontes": o ledger do mesmo build tem 12 insumos
com procedência.

**Nenhum caminho absoluto sai daqui.** Nem no contrato, nem no ledger, nem no
QA, nem na origem. O browser recebe nome de arquivo simples
(`hook_omni_odete.mp4`); a raiz da fábrica fica dentro do processo. É a mesma
regra de `src/types/criativos.ts` ("nenhum caminho de filesystem, nenhum nome
de bucket"), e há teste que varre o JSON serializado atrás de `/Users/`.

**Artefato ausente não derruba a leitura.** O `short_das` existe, é observável
e **não tem** QA visual nem snapshot congelado. Se a leitura fosse tudo ou
nada, um build incompleto viraria erro 500 e o operador não veria nem o que
existe. Toda ausência aqui vira `None`/lista vazia e a leitura continua.

## O que este módulo NÃO faz

Não escreve nada na fábrica, não a executa e não a importa. `VOLC_FACTORY_RAIZ`
é lida em toda chamada, nunca cacheada em constante de import, e a raiz que não
existe devolve `FabricaIndisponivel` — objeto tipado, não exceção e não dado
inventado. Caminho absoluto não vira contrato de produção (ADR-002).

## Fatos medidos em 27/08/2026, sobre o `short_odete`

    MP4 final       40.555.197 bytes, sha256 dc2e6cb8…f2123cbb (bate com o snapshot)
    duração         43,8 s medidos pelo QA técnico (o snapshot diz o mesmo)
    resolução       1080x1920 @ 30 fps
    beats           7 cenas, 7 papéis do arco da skin `gossip`, 6 cortes
    ledger          12 insumos, nenhum com licença declarada, 6 sintéticos
    QA              técnico PASS (15 gates), visual WARN (10 gates, 5 quadros)
    versão do motor não registrada em lugar nenhum do build
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# IDENTIDADE E CONFIGURAÇÃO
# ---------------------------------------------------------------------------

#: Identificador SIMBÓLICO da fábrica. Nunca o caminho: quem lê o painel não
#: precisa saber onde o disco daquela máquina monta, e um caminho num campo de
#: procedência é uma pista de infraestrutura vazando para o browser.
FABRICA = "volc-factory"

VARIAVEL_DE_RAIZ = "VOLC_FACTORY_RAIZ"

#: Default de conveniência para a máquina onde a fábrica vive hoje. É default,
#: não contrato: ADR-002 rejeitou caminho absoluto embutido como configuração
#: de produção, e é por isso que `raiz()` relê a variável a cada chamada em vez
#: de congelar o valor no import.
RAIZ_PADRAO = "/Users/mac/volc-factory"

#: A única procedência que esta leitura sabe produzir.
PROCEDENCIA_EXECUCAO: Literal["observado"] = "observado"

#: O modo do ADR-001 correspondente. Também de valor único, e pelo mesmo motivo.
MODO_DE_PRODUCAO: Literal["observado"] = "observado"

#: Conjunto fechado, para quem quiser assertar em vez de confiar.
PROCEDENCIAS_ADMITIDAS = frozenset({PROCEDENCIA_EXECUCAO})


# ---------------------------------------------------------------------------
# LIMITAÇÃO DECLARADA
# ---------------------------------------------------------------------------
#
# Texto de interface: sem travessão, sem jargão de caminho e sem nome de
# arquivo interno da fábrica. Os três impedimentos são medidos, não supostos
# (contagem de 27/08/2026, com `rg` sobre os 26 geradores da fábrica):
#
#   26 geradores no total
#   21 ainda gravam nos arquivos de trabalho compartilhados da raiz
#    4 já abrem área isolada por build, e nenhum deles tem teste de concorrência
#    1 não grava nenhum dos dois
#
# E o runtime fixa a raiz da fábrica dentro do próprio código, o que impede
# executá-lo de fora da instalação onde ele nasceu.

LIMITACAO_DECLARADA = (
    "O VOLC O.S. ainda não renderiza vídeo novo. O que você vê aqui é a "
    "leitura de um vídeo que a fábrica externa já produziu, com a procedência "
    "e o QA que ela registrou.\n\n"
    "São três impedimentos medidos:\n\n"
    "1. A maior parte dos geradores da fábrica grava o resultado sempre nos "
    "mesmos arquivos de trabalho compartilhados, e não numa área separada por "
    "vídeo. Dois vídeos gerados ao mesmo tempo escrevem um por cima do outro e "
    "os dois saem corrompidos.\n\n"
    "2. Os poucos geradores que já usam área separada por vídeo não têm "
    "nenhum teste automático provando que dois vídeos simultâneos não se "
    "atrapalham. Sem essa prova, liberar a geração aqui seria aposta, não "
    "decisão.\n\n"
    "3. A fábrica só funciona a partir da instalação em que nasceu, porque o "
    "lugar dela está fixo dentro do próprio código. Enquanto isso não for "
    "configurável, nada disso roda a partir do VOLC O.S.\n\n"
    "Enquanto os três não forem resolvidos, criar vídeo continua indisponível "
    "e esta tela é leitura, não produção."
)


def limitacao_declarada() -> str:
    """O texto que a interface mostra no lugar de "Criar vídeo".

    Existe como função além de constante para que a rota devolva a limitação
    junto do vídeo (`VideoObservado.limitacaoDeclarada`) sem a interface ter de
    manter uma cópia própria. Cópia na interface é cópia que envelhece sozinha:
    no dia em que os três impedimentos caírem, o backend muda uma vez e a tela
    para de mentir junto.
    """
    return LIMITACAO_DECLARADA


# ---------------------------------------------------------------------------
# ERROS E INDISPONIBILIDADE TIPADA
# ---------------------------------------------------------------------------


class BuildNaoEncontrado(LookupError):
    """O slug pedido não é observável na fábrica.

    Erro DE DOMÍNIO, e não `FileNotFoundError` cru: um `FileNotFoundError`
    vazando pela rota entrega o caminho do disco na mensagem de erro, que é
    exatamente o que este módulo passa o tempo todo evitando devolver.
    """


@dataclass(frozen=True)
class FabricaIndisponivel:
    """A fábrica não está montada nesta máquina.

    Não é exceção, de propósito. Levantar erro aqui obrigaria toda chamada a
    envolver a leitura num `try`, e a saída fácil desse `try` é um `except`
    devolvendo dado vazio, que é indistinguível de "a fábrica respondeu que não
    tem nada". Objeto tipado força a distinção a ser feita e mostrada.

    `motivo` é texto de operador e NÃO contém caminho: se contivesse, o
    primeiro lugar onde ele apareceria seria a tela de erro do painel.
    """

    codigo: Literal["raiz_ausente"] = "raiz_ausente"
    motivo: str = (
        "A fábrica de vídeo não está montada nesta máquina, então não há build "
        "para observar. Nenhum dado foi inventado no lugar."
    )

    def para_dicts(self) -> dict[str, Any]:
        """Mesma porta de saída de `BuildObservado`, com conteúdo vazio.

        Vazio EXPLÍCITO, não silencioso: `contrato`/`qa`/`origemExterna` vêm
        `None` e `ledger` vem `[]`, e quem consumir tem de decidir o que
        mostrar. Devolver um contrato com campos zerados seria fabricar um
        vídeo que não existe.
        """
        return {
            "contrato": None,
            "ledger": [],
            "qa": None,
            "origemExterna": None,
            "indisponivel": {"codigo": self.codigo, "motivo": self.motivo},
        }


# ---------------------------------------------------------------------------
# NORMALIZADORES — ausência é `None`, sempre
# ---------------------------------------------------------------------------


def _texto_ou_nulo(valor: object) -> str | None:
    """Texto útil, ou `None`. String vazia é ausência, não conteúdo."""
    if not isinstance(valor, str):
        return None
    limpo = valor.strip()
    return limpo or None


def _numero_ou_nulo(valor: object) -> float | int | None:
    """Número medido, ou `None`.

    `bool` é rejeitado antes de tudo porque em Python `True` é `int`, e um
    `commercial_ok: true` lido como duração `1` seria a exata classe de erro que
    a regra "ausência é `None`" existe para impedir.
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return valor
    return None


def _inteiro_ou_nulo(valor: object) -> int | None:
    numero = _numero_ou_nulo(valor)
    if numero is None:
        return None
    return int(numero)


def _bool_ou_nulo(valor: object) -> bool | None:
    """`True`, `False` ou `None`. "Não declarado" não vira `False`.

    `usoComercialOk: null` é "a fábrica não disse"; `false` é "a fábrica disse
    que não pode". Quem libera uma peça para anúncio precisa dos dois separados.
    """
    if isinstance(valor, bool):
        return valor
    return None


def _lista(valor: object) -> list[Any]:
    return valor if isinstance(valor, list) else []


def _dicionario(valor: object) -> dict[str, Any]:
    return valor if isinstance(valor, dict) else {}


def _so_o_nome(valor: object) -> str | None:
    """O nome do arquivo, sem nenhum diretório.

    `img_odete/real_1.jpg` vira `real_1.jpg`. Dois efeitos, os dois desejados:
    nenhum caminho vaza para o browser, e o nome passa a bater com o campo
    `file` do ledger, que é como um beat encontra a procedência do insumo dele.
    """
    texto = _texto_ou_nulo(valor)
    if texto is None:
        return None
    return texto.replace("\\", "/").rsplit("/", 1)[-1] or None


# ---------------------------------------------------------------------------
# LEITURA DE DISCO — falha de arquivo não derruba a leitura
# ---------------------------------------------------------------------------


def _ler_json(caminho: Path) -> Any:
    """JSON do disco, ou `None` se não der para ler.

    Engole ausência E corrupção. O `short_das` prova que o primeiro caso é
    rotina (não tem QA visual nem snapshot); o segundo é a mesma história vista
    de outro ângulo: um JSON truncado por um build interrompido não pode
    apagar da tela o contrato e o ledger que estão íntegros ao lado.
    """
    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


def _sha256(caminho: Path) -> str | None:
    """sha256 em streaming, em blocos de 1 MiB.

    O MP4 do `short_odete` tem 40.555.197 bytes. Lê-lo inteiro para hashear
    custaria 39 MB de pico por leitura, dentro do mesmo processo que serve o
    painel, e o custo cresce com o catálogo, não com o pedido.
    """
    digestor = hashlib.sha256()
    try:
        with caminho.open("rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                digestor.update(bloco)
    except OSError:
        return None
    return digestor.hexdigest()


def _bytes_ou_nulo(caminho: Path) -> int | None:
    try:
        return caminho.stat().st_size
    except OSError:
        return None


# ---------------------------------------------------------------------------
# RAIZ DA FÁBRICA
# ---------------------------------------------------------------------------


def raiz() -> Path:
    """A raiz da fábrica, relida do ambiente a CADA chamada.

    Sem cache de propósito. Uma constante montada no import congela o valor no
    primeiro import do processo, e um teste que aponta a raiz para um diretório
    temporário passaria a depender da ordem em que os módulos foram carregados.
    """
    return Path(os.environ.get(VARIAVEL_DE_RAIZ) or RAIZ_PADRAO)


def disponivel() -> bool:
    """A fábrica está montada e tem onde guardar build?

    Exige `out/builds` e não só a raiz porque uma raiz que existe mas está
    vazia (ponto de montagem que não subiu, por exemplo) responderia "sim" e
    entregaria catálogo vazio, que na tela é indistinguível de "a fábrica não
    produziu nada".
    """
    return (raiz() / "out" / "builds").is_dir()


# ---------------------------------------------------------------------------
# ONDE CADA ARTEFATO MORA
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Artefatos:
    """Os caminhos de um build. Uso INTERNO: nada daqui sai em `para_dicts()`."""

    slug: str
    build: Path
    props: Path
    timings: Path
    ledger: Path
    qa_tecnico: Path
    qa_visual: Path
    freeze: Path
    mp4_final: Path
    quadros: Path


def _artefatos(slug: str) -> _Artefatos:
    base = raiz()
    build = base / "out" / "builds" / slug
    return _Artefatos(
        slug=slug,
        build=build,
        props=build / "props.json",
        timings=build / "timings.json",
        ledger=build / "ledger.json",
        qa_tecnico=base / "out" / f"qa_{slug}.json",
        qa_visual=base / "out" / f"{slug}.qa_visual.json",
        freeze=base / "out" / "meta" / slug / "freeze.json",
        # ⚠️ O FINAL, não `build/render.mp4`. Ver o cabeçalho: são dois arquivos
        # diferentes e só este passou pelo sound design e pelo congelamento.
        mp4_final=base / "out" / f"{slug}.mp4",
        quadros=base / "out" / f"qa_frames_{slug}",
    )


def _config_do_episodio(slug: str, mapa: dict[str, Any], skin: str | None) -> Any:
    """O input humano do episódio, quando a skin é dirigida por configuração.

    Só as skins com `config_driven` guardam um arquivo por episódio; a `holerite`
    do `short_das`, por exemplo, tem o roteiro dentro do próprio gerador, e para
    ela esta função devolve `None` — que é o motivo de os beats daquele build
    saírem sem `copy`, e não um defeito de leitura.

    O `slug` do build (`short_odete`) carrega um prefixo que o arquivo de
    configuração não tem (`odete.json`); as duas formas são tentadas.
    """
    if not skin:
        return None
    pasta = _texto_ou_nulo(_dicionario(mapa.get("skins")).get(skin, {}).get("config_dir"))
    if pasta is None:
        return None

    nomes = [slug]
    if slug.startswith("short_"):
        nomes.append(slug[len("short_"):])

    for nome in nomes:
        candidato = raiz() / pasta / f"{nome}.json"
        conteudo = _ler_json(candidato)
        if not isinstance(conteudo, dict):
            continue
        # ⚠️ Confere o slug declarado dentro do arquivo. Sem isso, uma renomeação
        # na fábrica faria este leitor pendurar os beats de um episódio no vídeo
        # de outro, e o resultado seria plausível o bastante para ninguém notar.
        declarado = _texto_ou_nulo(conteudo.get("slug"))
        if declarado is not None and declarado not in nomes:
            continue
        return conteudo
    return None


def _contrato_resolvido(slug: str) -> Any:
    """O contrato no formato do schema de input, quando a fábrica gravou um.

    Nenhum dos dois builds observáveis hoje tem: são anteriores à camada de
    contrato. É a única fonte capaz de trazer `fatos` e `cta` declarados, e por
    isso continua sendo procurada mesmo sem uso atual: quando aparecer, a
    leitura melhora sozinha, sem `fatos` deixar de ser `[]` por invenção.
    """
    nomes = [slug]
    if slug.startswith("short_"):
        nomes.append(slug[len("short_"):])
    for nome in nomes:
        conteudo = _ler_json(raiz() / "contrato" / "exemplos" / f"{nome}.resolvido.json")
        if isinstance(conteudo, dict):
            return conteudo
    return None


# ---------------------------------------------------------------------------
# O GRAFO DO MOTOR — skin, nicho e arco narrativo
# ---------------------------------------------------------------------------


def _mapa_do_motor() -> dict[str, Any]:
    return _dicionario(_ler_json(raiz() / "contrato" / "motor" / "mapa.json"))


def _skin_da_composicao(mapa: dict[str, Any], comp: str | None) -> str | None:
    """Do nome da composição gravado no ledger (`Gossip`) para a skin (`gossip`).

    O ledger não grava a skin; grava a composição Remotion que a renderizou. O
    grafo do motor é quem liga as duas, e é a única ligação que existe: casar
    por `comp.lower()` funcionaria hoje por coincidência de nomenclatura e
    quebraria calado no primeiro par que não coincidir.
    """
    if comp is None:
        return None
    for nome, definicao in _dicionario(mapa.get("skins")).items():
        if _texto_ou_nulo(_dicionario(definicao).get("comp")) == comp:
            return nome
    return None


def _nicho_da_skin(mapa: dict[str, Any], skin: str | None) -> str | None:
    if skin is None:
        return None
    for nome, definicao in _dicionario(mapa.get("nichos")).items():
        if _texto_ou_nulo(_dicionario(definicao).get("skin")) == skin:
            return nome
    return None


def _papeis_do_arco(mapa: dict[str, Any], skin: str | None, beats: int) -> list[str | None]:
    """Os papéis REAIS do arco da skin, quando eles cabem nos beats deste build.

    O arco da `gossip` tem sete papéis (`hook`, `contexto`, `virada`, `segredo`,
    `suspeitos/opções`, `revelação`, `payoff+cta`) e o `short_odete` tem sete
    beats: a correspondência é posicional e verdadeira. O `short_das` tem cinco
    beats contra os sete da `holerite`, e aí **nenhum** papel é atribuído.

    Alinhar sete rótulos em cinco posições produziria um "susto" onde está o
    "cta", e um papel narrativo errado é pior que papel ausente: `None` faz a
    interface calar, o rótulo errado a faz mentir com confiança.
    """
    vazio: list[str | None] = [None] * beats
    if skin is None or beats <= 0:
        return vazio
    arco = _lista(_dicionario(mapa.get("skins")).get(skin, {}).get("arco"))
    if len(arco) != beats:
        return vazio
    return [_texto_ou_nulo(_dicionario(etapa).get("papel")) for etapa in arco]


# ---------------------------------------------------------------------------
# CONTRATO DE VÍDEO
# ---------------------------------------------------------------------------

#: Chaves de `props.json` que descrevem a MECÂNICA do render, não um elemento de
#: retenção. Tudo que sobra e está preenchido é elemento em uso.
#:
#: É lista de exclusão, e não de inclusão, de propósito: cada skin nova inventa
#: elementos novos (`quiz`, `fichas`, `carimboDuplo`, `fonteBar` só existem na
#: `holerite`), e uma lista de inclusão os deixaria invisíveis em silêncio. Ao
#: errar, esta erra mostrando algo demais, que alguém vê e corrige.
_CHAVES_TECNICAS_DE_PROPS = frozenset({
    "durationInFrames", "fps", "TR", "audio", "title", "badge", "scenes",
    "words", "cutTimes", "microCuts", "dur", "qaProfile", "storyArc",
    "retentionBeats", "heartbeatTimes", "logoBigEnd",
})


def _elementos_de_retencao(props: dict[str, Any]) -> list[str]:
    """Os elementos que este build REALMENTE usa, na ordem em que a fábrica os
    gravou.

    Vem de `props.json` e não do catálogo da skin porque o catálogo diz o que a
    skin PODE usar. O `short_odete` deixou `logo`, `scoreboard`, `ctaCard`,
    `emailAlert` e `celestialCard` em `null`: listá-los seria descrever um vídeo
    que não foi montado.
    """
    usados: list[str] = []
    for chave, valor in props.items():
        if chave in _CHAVES_TECNICAS_DE_PROPS:
            continue
        if valor is None or valor == [] or valor == {} or valor == "":
            continue
        usados.append(chave)
    return usados


def _hook(config: dict[str, Any]) -> dict[str, Any] | None:
    """O gancho declarado no input do episódio.

    Duas formas convivem na fábrica: `hook` (o schema do contrato) e `omni_hook`
    (o formato que os geradores dirigidos por configuração usam). A segunda não
    tem campo `tipo` porque o nome da chave já é o tipo, e é só nesse caso que
    `omni` é afirmado sem estar escrito.

    O `gesture` do `omni_hook` não tem casa no contrato do Estúdio e é
    descartado: inventar um campo para ele aqui criaria vocabulário que o
    frontend não conhece.
    """
    do_schema = _dicionario(config.get("hook"))
    do_runner = _dicionario(config.get("omni_hook"))
    if not do_schema and not do_runner:
        return None

    if do_schema:
        tipo = _texto_ou_nulo(do_schema.get("tipo"))
    else:
        tipo = "omni"

    fonte = do_schema or do_runner
    return {
        "tipo": tipo,
        "linha": _texto_ou_nulo(fonte.get("linha") or fonte.get("line")),
        "segundos": _numero_ou_nulo(fonte.get("segundos", fonte.get("seconds"))),
        "persona": _texto_ou_nulo(fonte.get("persona")),
        "cenario": _texto_ou_nulo(fonte.get("cenario") or fonte.get("setting")),
    }


def _voz(config: dict[str, Any], mapa: dict[str, Any], skin: str | None) -> dict[str, Any] | None:
    """A voz da narração, com estilo só quando dá para provar qual é.

    `provider` é `None` sempre, e é a mesma honestidade de
    `motorVersaoConhecida`: a fábrica escolhe o provedor de TTS em tempo de
    execução e **não grava essa escolha dentro do build**. Herdar do runtime
    daria um campo preenchido que nenhuma evidência do build sustenta.

    `estilo` só é preenchido quando o arquétipo padrão da skin aponta para a
    mesma voz que o episódio pediu. Se o episódio trocou a voz, o estilo do
    arquétipo deixa de valer, e repeti-lo descreveria uma narração que não é a
    que está no arquivo.
    """
    do_schema = _dicionario(config.get("voz"))
    identificador = _texto_ou_nulo(do_schema.get("id") or config.get("voice"))
    velocidade = _numero_ou_nulo(do_schema.get("speed", config.get("speed")))
    if identificador is None and velocidade is None:
        return None

    estilo = None
    arquetipo = _texto_ou_nulo(_dicionario(mapa.get("skins")).get(skin or "", {}).get("voz_default"))
    definicao = _dicionario(_dicionario(mapa.get("vozes")).get(arquetipo or ""))
    if identificador is not None and _texto_ou_nulo(definicao.get("voice")) == identificador:
        estilo = _texto_ou_nulo(definicao.get("style"))

    return {
        "provider": None,
        "id": identificador,
        "estilo": estilo,
        "velocidade": velocidade,
    }


def _beats(
    config: dict[str, Any],
    props: dict[str, Any],
    timings: dict[str, Any],
    papeis: list[str | None],
) -> list[dict[str, Any]]:
    """Os beats, costurando três fontes que medem coisas diferentes.

    - `props.scenes` diz quantas cenas o render tem e quantos frames cada uma
      dura. É a verdade sobre o que está no arquivo, e por isso é ela quem
      define a QUANTIDADE de beats.
    - `timings.cutTimes` diz onde a narração vira de beat. São seis cortes para
      sete beats no `short_odete`, e conferem com as palavras do TTS: o último
      termo do beat 0 acaba em 3,96 s e o primeiro do beat 1 começa em 4,04 s,
      com o corte em 4,01 s.
    - O input do episódio diz o texto falado.

    ⚠️ `inicioS + duracaoS` pode passar do `inicioS` do beat seguinte, e não é
    erro de conta: as cenas se sobrepõem pela transição (`TR`, 12 frames no
    `short_odete`). A cena 0 dura 4,4 s e o corte de narração é aos 4,01 s.
    Forçar os dois a fechar exigiria escolher um para reescrever.

    Copy e cortes só são costurados quando a CONTAGEM bate. Uma configuração
    com mais beats que cenas costurada por posição colaria a fala de uma cena
    na imagem de outra, e o resultado passaria por correto na tela.
    """
    cenas = _lista(props.get("scenes"))
    falas = [f for f in _lista(config.get("beats")) if isinstance(f, str)]
    descricoes = _lista(config.get("scenes"))

    total = len(cenas) or len(falas)
    if total == 0:
        return []

    fps = _numero_ou_nulo(props.get("fps"))
    cortes = [c for c in _lista(timings.get("cutTimes")) if _numero_ou_nulo(c) is not None]
    inicios: list[float | None] = [None] * total
    if len(cortes) == total - 1:
        inicios = [0.0] + [float(c) for c in cortes]

    beats: list[dict[str, Any]] = []
    for indice in range(total):
        cena = _dicionario(cenas[indice]) if indice < len(cenas) else {}
        frames = _inteiro_ou_nulo(cena.get("dur"))
        segundos = None
        if frames is not None and fps:
            segundos = round(frames / float(fps), 4)

        descricao = _dicionario(descricoes[indice]) if indice < len(descricoes) else {}
        beats.append({
            "indice": indice,
            "papel": papeis[indice] if indice < len(papeis) else None,
            "copy": falas[indice] if len(falas) == total else None,
            "visual": _texto_ou_nulo(descricao.get("prompt") or descricao.get("person")),
            "assetArquivo": _so_o_nome(cena.get("src")),
            "duracaoFrames": frames,
            "duracaoS": segundos,
            "inicioS": inicios[indice],
        })
    return beats


def _fatos(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Os fatos verificados que o build registrou.

    ⚠️ `[]` é resposta, não falha. O `short_odete` não registrou fatos, e isso
    NÃO significa que ele não tenha fontes: o ledger do mesmo build tem 12
    insumos com procedência declarada. As duas coisas medem lados diferentes, e
    sintetizar uma a partir da outra apagaria a diferença.
    """
    resultado: list[dict[str, Any]] = []
    for bruto in _lista(config.get("fatos")):
        item = _dicionario(bruto)
        afirmacao = _texto_ou_nulo(item.get("afirmacao"))
        if afirmacao is None:
            continue
        fontes = [f for f in (_texto_ou_nulo(u) for u in _lista(item.get("fontes"))) if f]
        resultado.append({
            "afirmacao": afirmacao,
            "fontes": fontes,
            "calibragem": _texto_ou_nulo(item.get("calibragem")),
        })
    return resultado


def _cta(config: dict[str, Any], props: dict[str, Any]) -> str | None:
    """A chamada para ação, quando o build a registrou como tal.

    O `short_das` tem `storyArc.cta` em `props.json`; o `short_odete` não tem
    nenhum dos dois e sai `None`. Derivar o CTA do texto do último beat seria
    tentador (ele termina em "Segue pra mais mistérios de novela!") e seria
    invenção: "o beat final costuma conter o CTA" é heurística, não registro.
    """
    do_schema = _dicionario(config.get("cta"))
    texto = _texto_ou_nulo(do_schema.get("texto"))
    if texto:
        return texto
    return _texto_ou_nulo(_dicionario(props.get("storyArc")).get("cta"))


def _tema(contrato_resolvido: dict[str, Any], ledger: dict[str, Any]) -> str | None:
    """O assunto do vídeo em uma frase, na ordem em que a fábrica o registra.

    1. O contrato resolvido, quando existe: `tema` é o campo do schema.
    2. O `caso` do ledger: é literalmente isso no `short_das` ("MEI 2026 limite
       de faturamento").
    3. A `novela` do ledger, para os builds de recap, cujo assunto é a obra.

    Nada além disso. Sem os três, `None`: montar um tema a partir do título ou
    do primeiro beat produziria uma frase plausível que ninguém escreveu.
    """
    return (
        _texto_ou_nulo(contrato_resolvido.get("tema"))
        or _texto_ou_nulo(ledger.get("caso"))
        or _texto_ou_nulo(ledger.get("novela"))
    )


# ---------------------------------------------------------------------------
# LEDGER
# ---------------------------------------------------------------------------

#: Marcas que a fábrica escreve na descrição da fonte quando o insumo é gerado.
#: A lista é conservadora de propósito (ver `_sintetico`).
_MARCAS_DE_SINTETICO = (
    "ia (", "ia -", "ia —", "gemini", "gpt-image", "gptimg", "t2v", "i2v",
    "avatar ia", "sintetic", "sintétic", "synthid",
)


def _sintetico(item: dict[str, Any]) -> bool:
    """O insumo foi gerado por IA?

    `synthid` é a declaração explícita e ganha de tudo. Sem ela, a descrição da
    fonte é lida: "IA (gemini) - cena sem rosto" e "Gemini Omni t2v" são
    sintéticos; "Wikimedia Commons" não é.

    ⚠️ Único campo deste módulo em que ausência não vira `None`, porque o
    contrato do frontend declara `sintetico: boolean` e não aceita nulo. A
    leitura então é CONSERVADORA: só afirma `True` com evidência positiva. O
    erro que ela pode cometer é deixar de marcar um sintético, que um humano
    revisando o ledger corrige; o erro oposto, marcar um still de imprensa como
    IA, é acusação falsa contra um fornecedor real.
    """
    declarado = _bool_ou_nulo(item.get("synthid"))
    if declarado is not None:
        return declarado
    fonte = (_texto_ou_nulo(item.get("source")) or "").lower()
    return any(marca in fonte for marca in _MARCAS_DE_SINTETICO)


def _ledger(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Os insumos do build, com licença e direitos exatamente como registrados.

    ⚠️ `licenca: None` é o valor REAL dos cinco itens de Wikimedia do
    `short_odete`: a fábrica gravou `"license": null` e a nota do ledger explica
    o porquê ("licenca implicita de imprensa; CREDITAR"). Substituir por
    "desconhecida" ou "livre" transformaria uma pendência jurídica em texto que
    tranquiliza, e é justamente essa lacuna que alguém precisa ver antes de
    aprovar o vídeo para mídia paga.
    """
    itens: list[dict[str, Any]] = []
    for bruto in _lista(ledger.get("sources")):
        item = _dicionario(bruto)
        arquivo = _so_o_nome(item.get("file"))
        if arquivo is None:
            continue
        itens.append({
            "arquivo": arquivo,
            "cena": _inteiro_ou_nulo(item.get("scene")),
            "fonte": _texto_ou_nulo(item.get("source")) or "não declarada",
            "licenca": _texto_ou_nulo(item.get("license")),
            "credito": _texto_ou_nulo(item.get("credit")),
            "url": _texto_ou_nulo(item.get("url")),
            "usoComercialOk": _bool_ou_nulo(item.get("commercial_ok")),
            "disclosure": _texto_ou_nulo(item.get("disclosure")),
            "sintetico": _sintetico(item),
        })
    return itens


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------

_VEREDITOS = ("PASS", "WARN", "FAIL", "SKIPPED")

#: Severidade, para escolher a PIOR ocorrência de um check visual entre quadros.
#:
#: ⚠️ `SKIPPED` fica ABAIXO de `PASS`, e o sinal negativo é a regra inteira:
#: "não se aplica neste quadro" não é um veredito sobre a peça. O
#: `emoji_errado` do `short_odete` passa em quatro quadros e é pulado no
#: quinto (o quadro final não tem emoji esperado); reportá-lo como `SKIPPED`
#: por causa desse quinto esconderia quatro medições boas atrás de um "não
#: verificado". Como o pior é escolhido por máximo, um check pulado em TODOS
#: os quadros continua saindo `SKIPPED`, que é o único caso em que a palavra
#: descreve a realidade.
_SEVERIDADE = {"SKIPPED": -1, "PASS": 0, "WARN": 2, "FAIL": 3}

_ROTULOS = {
    # técnicos
    "resolucao": "Resolução",
    "fps": "Quadros por segundo",
    "codec": "Codec de vídeo e áudio",
    "audio_sr": "Taxa de amostragem do áudio",
    "duracao": "Duração",
    "loudness_integrado": "Volume integrado",
    "true_peak": "Pico real do áudio",
    "black_frames": "Trechos pretos",
    "freeze_frames": "Imagem congelada",
    "gap_de_voz": "Silêncio no meio da narração",
    "hook_video_min": "Duração do gancho",
    "cobertura_legendas": "Cobertura das legendas",
    "card_sobre_rosto": "Card sobre rosto",
    "ledger_broll": "Uso comercial das imagens",
    "ledger_credit": "Crédito das imagens editoriais",
    "story_arc_v2": "Arco narrativo completo",
    "retention_density_v2": "Densidade de retenção",
    "retention_first_beat_v2": "Primeiro gancho de retenção",
    "retention_gap_v2": "Maior intervalo sem retenção",
    "wow_events_v2": "Eventos de impacto",
    "caption_density_v2": "Densidade de legenda",
    # visuais
    "legenda_cortada": "Legenda cortada",
    "texto_sobre_rosto": "Texto sobre rosto",
    "emoji_errado": "Emoji incorreto",
    "selo_cortado": "Selo cortado",
    "texto_ilegivel": "Texto ilegível",
    "artefato_ia": "Artefato de IA",
    "elemento_esperado": "Elemento esperado presente",
    "ui_occlusion": "Texto na área da interface do aplicativo",
    "rosto_inesperado": "Rosto inesperado",
    "hook_weak": "Força do gancho",
}


def _rotulo(identificador: str) -> str:
    """Nome legível do gate.

    Dicionário para os gates conhecidos, e uma versão desengomada do
    identificador para os que a fábrica inventar depois. O fallback existe para
    que um check novo apareça na tela com nome feio em vez de não aparecer: um
    gate invisível é um gate que ninguém lê antes de aprovar.
    """
    conhecido = _ROTULOS.get(identificador)
    if conhecido:
        return conhecido
    return identificador.replace("_", " ").strip().capitalize() or identificador


def _resultado_de_gate(valor: object) -> tuple[str, str | None]:
    """Normaliza um veredito, e devolve o aviso quando não o reconhece.

    ⚠️ Token desconhecido vira `WARN`, nunca `PASS` nem `SKIPPED`. `PASS`
    aprovaria o que não foi lido; `SKIPPED` afirmaria que o check não rodou,
    quando na verdade ele rodou e nós é que não entendemos a resposta. `WARN` é
    o único dos quatro cujo significado é "um humano precisa olhar isto", que é
    exatamente o estado do caso.
    """
    bruto = _texto_ou_nulo(valor)
    if bruto is None:
        return "WARN", "veredito ausente no build"
    normal = bruto.strip().upper()
    if normal == "SKIP":
        normal = "SKIPPED"
    if normal in _VEREDITOS:
        return normal, None
    return "WARN", f"veredito não reconhecido no build: {bruto}"


def _gates_tecnicos(qa: dict[str, Any]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for bruto in _lista(qa.get("checks")):
        item = _dicionario(bruto)
        identificador = _texto_ou_nulo(item.get("check"))
        if identificador is None:
            continue
        resultado, aviso = _resultado_de_gate(item.get("status"))
        detalhe = _texto_ou_nulo(item.get("detail"))
        gates.append({
            "id": identificador,
            "rotulo": _rotulo(identificador),
            "resultado": resultado,
            "detalhe": aviso or detalhe,
        })
    return gates


def _gates_visuais(qa_visual: dict[str, Any]) -> list[dict[str, Any]]:
    """Um gate por check, com a PIOR ocorrência entre os quadros analisados.

    O QA visual do `short_odete` roda dez checks em cinco quadros: cinquenta
    linhas. Despejá-las na tela esconderia o único achado que importa (um
    `ui_occlusion` em WARN no quadro do gancho) dentro de quarenta e nove
    aprovações. A agregação guarda a contagem de quadros no detalhe, para que
    "passou em todos" continue distinguível de "só teve um quadro".
    """
    pior: dict[str, tuple[int, str, str | None]] = {}
    vistos: dict[str, int] = {}
    pulados: dict[str, int] = {}

    for quadro in _lista(qa_visual.get("frames")):
        for bruto in _lista(_dicionario(quadro).get("checks")):
            item = _dicionario(bruto)
            identificador = _texto_ou_nulo(item.get("id"))
            if identificador is None:
                continue
            vistos[identificador] = vistos.get(identificador, 0) + 1
            resultado, aviso = _resultado_de_gate(item.get("level"))
            if resultado == "SKIPPED":
                pulados[identificador] = pulados.get(identificador, 0) + 1
            peso = _SEVERIDADE.get(resultado, 2)
            atual = pior.get(identificador)
            if atual is None or peso > atual[0]:
                evidencia = aviso or _texto_ou_nulo(item.get("evidence"))
                pior[identificador] = (peso, resultado, evidencia)

    gates: list[dict[str, Any]] = []
    for identificador, (_, resultado, evidencia) in pior.items():
        quantos = vistos[identificador]
        quadros = "1 quadro" if quantos == 1 else f"{quantos} quadros"
        detalhe = f"{quadros} com este check"
        fora = pulados.get(identificador, 0)
        if fora and resultado != "SKIPPED":
            detalhe += f", {fora} em que ele não se aplica"
        if evidencia:
            titulo = "Evidência" if resultado in ("PASS", "SKIPPED") else "Pior ocorrência"
            detalhe += f". {titulo}: {evidencia}"
        gates.append({
            "id": identificador,
            "rotulo": _rotulo(identificador),
            "resultado": resultado,
            "detalhe": detalhe,
        })
    return gates


def _qa(qa_tecnico: dict[str, Any] | None, qa_visual: dict[str, Any] | None) -> dict[str, Any]:
    """Os dois QA lado a lado, cada um podendo estar ausente sozinho.

    ⚠️ `vereditoVisual: None` é o caso do `short_das`, que nunca passou pelo QA
    visual. É diferente de `SKIPPED`, que seria "rodou e pulou", e muito
    diferente de `PASS`. Um build sem QA visual exibido como aprovado é
    exatamente o erro que faz alguém publicar sem revisar.
    """
    tecnico = _dicionario(qa_tecnico)
    visual = _dicionario(qa_visual)

    gates_tecnicos = _gates_tecnicos(tecnico) if qa_tecnico is not None else []
    gates_visuais = _gates_visuais(visual) if qa_visual is not None else []

    veredito_tecnico = None
    if qa_tecnico is not None:
        veredito_tecnico, aviso = _resultado_de_gate(tecnico.get("verdict"))
        if aviso:
            gates_tecnicos.append({
                "id": "veredito_do_build",
                "rotulo": "Veredito registrado pela fábrica",
                "resultado": "WARN",
                "detalhe": aviso,
            })

    veredito_visual = None
    if qa_visual is not None:
        veredito_visual, aviso = _resultado_de_gate(visual.get("verdict"))
        if aviso:
            gates_visuais.append({
                "id": "veredito_do_build",
                "rotulo": "Veredito registrado pela fábrica",
                "resultado": "WARN",
                "detalhe": aviso,
            })

    return {
        "vereditoTecnico": veredito_tecnico,
        "vereditoVisual": veredito_visual,
        "gatesTecnicos": gates_tecnicos,
        "gatesVisuais": gates_visuais,
        "custoQaUsd": _numero_ou_nulo(_dicionario(visual.get("usage")).get("est_cost_usd")),
    }


# ---------------------------------------------------------------------------
# MEDIDAS DO ARQUIVO
# ---------------------------------------------------------------------------

_RESOLUCAO = re.compile(r"(\d{2,5})\s*[x×X]\s*(\d{2,5})")


def _resolucao(qa_tecnico: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """Largura e altura, do gate `resolucao` do QA técnico.

    É a única medida do arquivo final que existe dentro do build. Sem QA
    técnico, `(None, None)`: abrir o MP4 aqui exigiria ffprobe, que é
    dependência de sistema que o backend não tem e não deveria ganhar para
    exibir um vídeo que ele nem produziu.
    """
    for bruto in _lista(_dicionario(qa_tecnico).get("checks")):
        item = _dicionario(bruto)
        if _texto_ou_nulo(item.get("check")) != "resolucao":
            continue
        achado = _RESOLUCAO.search(_texto_ou_nulo(item.get("detail")) or "")
        if achado:
            return int(achado.group(1)), int(achado.group(2))
    return None, None


def _duracao_ms(
    qa_tecnico: dict[str, Any] | None,
    freeze: dict[str, Any] | None,
    props: dict[str, Any],
) -> int | None:
    """A duração em milissegundos, da fonte mais próxima do arquivo final.

    Ordem: o QA técnico (mediu o MP4 final: 43,8 s), depois o snapshot
    congelado (43,8 s, mesma medida), depois `durationInFrames / fps` (43,67 s,
    que descreve o render antes do sound design). As três discordam entre si e
    a mais confiável é a que abriu o arquivo que o operador vai assistir.
    """
    for candidato in (
        _numero_ou_nulo(_dicionario(qa_tecnico).get("duration_s")),
        _numero_ou_nulo(_dicionario(freeze).get("dur_s")),
    ):
        if candidato is not None:
            return int(round(float(candidato) * 1000))

    frames = _numero_ou_nulo(props.get("durationInFrames"))
    fps = _numero_ou_nulo(props.get("fps"))
    if frames is not None and fps:
        return int(round(float(frames) / float(fps) * 1000))
    return None


def _poster(artefatos: _Artefatos, qa_visual: dict[str, Any] | None) -> Path | None:
    """O quadro do gancho, para servir de capa.

    Primeiro o quadro que o QA visual marcou como `hook` (é o quadro que o
    revisor olhou); se não houver QA visual, o primeiro quadro extraído no
    tempo, que na prática é o mesmo `f_0.50.jpg`. Sem quadro nenhum, `None`:
    capa é conveniência, e um vídeo sem capa continua sendo um vídeo.
    """
    for quadro in _lista(_dicionario(qa_visual).get("frames")):
        item = _dicionario(quadro)
        if _texto_ou_nulo(item.get("reason")) != "hook":
            continue
        arquivo = _texto_ou_nulo(item.get("file"))
        if arquivo is None:
            continue
        caminho = Path(arquivo)
        if not caminho.is_absolute():
            caminho = raiz() / caminho
        if caminho.is_file():
            return caminho

    try:
        candidatos = sorted(artefatos.quadros.glob("f_*.jpg"))
    except OSError:
        return None
    return candidatos[0] if candidatos else None


# ---------------------------------------------------------------------------
# O BUILD OBSERVADO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildObservado:
    """Um build da fábrica externa, lido e nada além de lido.

    Os `Path` são de uso INTERNO do backend (streaming do vídeo, geração de
    poster) e por isso ficam FORA de `para_dicts()`. É a fronteira que o
    contrato do frontend descreve: o browser recebe URL assinada, nunca caminho.
    """

    slug: str
    contrato: dict[str, Any]
    ledger: list[dict[str, Any]]
    qa: dict[str, Any]
    origem: dict[str, Any]

    mp4_caminho: Path | None
    poster_caminho: Path | None

    duracao_ms: int | None
    largura: int | None
    altura: int | None
    mime: str | None
    bytes_totais: int | None
    content_hash: str | None

    #: O que o snapshot da fábrica afirma. `None` quando não há snapshot.
    hash_congelado: str | None
    #: O sha256 medido bate com o congelado? `None` = não havia o que comparar.
    #:
    #: ⚠️ Divergência NÃO é remendada. Se o arquivo em disco não for mais o que
    #: foi congelado, o campo diz `False` e o operador decide; ajustar o hash
    #: para "bater" apagaria a única prova de que o vídeo mudou depois do
    #: congelamento.
    hash_confere: bool | None

    #: Sempre `observado`. Ver o cabeçalho do módulo.
    procedencia_execucao: Literal["observado"] = PROCEDENCIA_EXECUCAO
    modo: Literal["observado"] = MODO_DE_PRODUCAO

    def para_dicts(self) -> dict[str, Any]:
        """As quatro estruturas em camelCase, prontas para JSON.

        Sem caminho, sem raiz da fábrica e sem nada que afirme autoria do VOLC
        O.S. — há teste que varre o JSON serializado atrás de `/Users/` e da
        raiz configurada.
        """
        return {
            "contrato": self.contrato,
            "ledger": list(self.ledger),
            "qa": self.qa,
            "origemExterna": self.origem,
        }


LeituraDeBuild = BuildObservado | FabricaIndisponivel


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def listar_builds() -> list[str]:
    """Os slugs observáveis, em ordem estável.

    Devolve `[]` quando a fábrica não está montada, e não levanta: um catálogo
    vazio é uma resposta legítima da tela, e quem precisa distinguir "vazio" de
    "indisponível" chama `disponivel()`.
    """
    if not disponivel():
        return []
    pasta = raiz() / "out" / "builds"
    try:
        return sorted(p.name for p in pasta.iterdir() if p.is_dir())
    except OSError:
        return []


def ler_build(slug: str) -> LeituraDeBuild:
    """Lê um build da fábrica e devolve a observação dele.

    ⚠️ A assinatura devolve união porque as duas respostas são legítimas e
    diferentes: `FabricaIndisponivel` é "não há de onde ler", `BuildNaoEncontrado`
    é "a fábrica está aqui e esse vídeo não existe nela". Colapsar as duas em
    exceção faria a rota tratar as duas igual, e a tela diria "vídeo não
    encontrado" quando o problema é que o disco não está montado.

    Nenhum `FileNotFoundError` escapa: artefato ausente vira `None` ou lista
    vazia no campo dele e a leitura segue (o `short_das` não tem QA visual nem
    snapshot e é lido inteiro assim mesmo).
    """
    if not disponivel():
        return FabricaIndisponivel()

    nome = _texto_ou_nulo(slug)
    if nome is None or nome != Path(nome).name or nome in (".", ".."):
        raise BuildNaoEncontrado(f"slug inválido: {slug!r}")

    artefatos = _artefatos(nome)
    if not artefatos.build.is_dir():
        raise BuildNaoEncontrado(f"build não observável na fábrica: {nome}")

    props = _dicionario(_ler_json(artefatos.props))
    timings = _dicionario(_ler_json(artefatos.timings))
    ledger_bruto = _dicionario(_ler_json(artefatos.ledger))
    qa_tecnico = _ler_json(artefatos.qa_tecnico)
    qa_visual = _ler_json(artefatos.qa_visual)
    freeze = _ler_json(artefatos.freeze)
    qa_tecnico = qa_tecnico if isinstance(qa_tecnico, dict) else None
    qa_visual = qa_visual if isinstance(qa_visual, dict) else None
    freeze = freeze if isinstance(freeze, dict) else None

    mapa = _mapa_do_motor()
    resolvido = _dicionario(_contrato_resolvido(nome))
    skin = (
        _texto_ou_nulo(resolvido.get("skin"))
        or _skin_da_composicao(mapa, _texto_ou_nulo(ledger_bruto.get("comp")))
    )
    config = _dicionario(_config_do_episodio(nome, mapa, skin)) or resolvido

    largura, altura = _resolucao(qa_tecnico)
    papeis = _papeis_do_arco(mapa, skin, len(_lista(props.get("scenes"))))

    contrato = {
        "tema": _tema(resolvido, ledger_bruto),
        "nicho": _texto_ou_nulo(resolvido.get("nicho")) or _nicho_da_skin(mapa, skin),
        "skin": skin,
        "titulo": _texto_ou_nulo(props.get("title") or config.get("title")),
        "badge": _texto_ou_nulo(props.get("badge") or config.get("badge")),
        "duracaoS": None,
        "fps": _numero_ou_nulo(props.get("fps")),
        "largura": largura,
        "altura": altura,
        "hook": _hook(config),
        "voz": _voz(config, mapa, skin),
        "beats": _beats(config, props, timings, papeis),
        "elementosDeRetencao": _elementos_de_retencao(props),
        "cta": _cta(config, props),
        "fatos": _fatos(config),
    }

    duracao_ms = _duracao_ms(qa_tecnico, freeze, props)
    if duracao_ms is not None:
        contrato["duracaoS"] = round(duracao_ms / 1000, 3)

    mp4 = artefatos.mp4_final if artefatos.mp4_final.is_file() else None
    content_hash = _sha256(mp4) if mp4 is not None else None
    hash_congelado = _texto_ou_nulo(_dicionario(freeze).get("sha256"))
    hash_confere = None
    if content_hash is not None and hash_congelado is not None:
        hash_confere = content_hash == hash_congelado

    origem = {
        "fabrica": FABRICA,
        "identificadorDoBuild": nome,
        "hashDoArtefato": content_hash,
        "congeladoEm": _texto_ou_nulo(_dicionario(freeze).get("frozen_at")),
        # ⚠️ SEMPRE `None`, e não por preguiça: nenhum artefato do build grava
        # versão de motor. O `contrato/motor/mapa.json` tem uma `versao`, mas ela
        # é do GRAFO e não é carimbada no build, então usá-la aqui afirmaria que
        # este vídeo saiu daquela versão sem nada que sustente a afirmação.
        "motorVersaoConhecida": None,
        "observadoEm": datetime.now(timezone.utc).isoformat(),
    }

    return BuildObservado(
        slug=nome,
        contrato=contrato,
        ledger=_ledger(ledger_bruto),
        qa=_qa(qa_tecnico, qa_visual),
        origem=origem,
        mp4_caminho=mp4,
        poster_caminho=_poster(artefatos, qa_visual),
        duracao_ms=duracao_ms,
        largura=largura,
        altura=altura,
        mime="video/mp4" if mp4 is not None else None,
        bytes_totais=_bytes_ou_nulo(mp4) if mp4 is not None else None,
        content_hash=content_hash,
        hash_congelado=hash_congelado,
        hash_confere=hash_confere,
    )
