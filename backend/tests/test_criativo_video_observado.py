"""Provas do observador de vídeo — e, principalmente, da recusa em mentir.

## O que estes testes protegem

Um leitor de patrimônio alheio erra de três formas caras, e as três são
silenciosas:

1. **Afirmar autoria.** O vídeo aparece no painel do VOLC O.S. e, dali a um
   mês, ninguém lembra que ele veio de fora. Os testes de procedência exigem
   que a única resposta possível seja `observado`, e um deles varre o FONTE do
   módulo atrás do token da procedência oposta: a garantia não é "o código não
   escreve", é "não existe código capaz de escrever".

2. **Vazar caminho de disco.** Um `previewUrl` com `/Users/...` dentro conta ao
   browser onde a fábrica mora. O teste serializa a saída inteira e procura a
   raiz configurada, o prefixo `/Users/` e qualquer string que comece em `/`.

3. **Converter ausência em valor.** `licenca: null` virando "desconhecida",
   `fatos: []` virando "sem fontes", QA que não rodou virando `PASS`. São os
   erros que fazem alguém aprovar para mídia paga uma peça cuja licença ninguém
   levantou.

## Duas famílias, de propósito

Os testes contra a **fábrica real** provam o caso que existe (o `short_odete`,
com sha256 conferido contra o snapshot) e são pulados quando a fábrica não está
montada, para não quebrarem em CI. Os testes **sintéticos** montam uma fábrica
mínima em `tmp_path` e por isso rodam em qualquer lugar: são eles que exercitam
o build incompleto, o JSON corrompido e a fábrica ausente.

⚠️ Nenhum teste daqui escreve dentro da fábrica real. Ela é patrimônio de
produção de outro dono, e este módulo inteiro é somente leitura.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

import pytest

from app.criativo import video_observado as vo

# ---------------------------------------------------------------------------
# A FÁBRICA REAL — o caso medido em 27/08/2026
# ---------------------------------------------------------------------------

SLUG_REAL = "short_odete"

#: O que `out/meta/short_odete/freeze.json` afirma sobre o MP4 final.
#: ⚠️ NÃO é o hash do `render.mp4` (a saída crua do Remotion, `447e44bf…`): são
#: dois arquivos diferentes, e ler o errado passaria neste teste só se a
#: constante estivesse errada junto.
SHA256_CONGELADO = "dc2e6cb803ecf0aaec2281b03ccac9f8891c9a75d0d4cca8d7a8180cf2123cbb"

BYTES_DO_MP4_FINAL = 40_555_197


def _raiz_real() -> Path:
    return Path(os.environ.get(vo.VARIAVEL_DE_RAIZ) or vo.RAIZ_PADRAO)


sem_fabrica = pytest.mark.skipif(
    not (_raiz_real() / "out" / "builds" / SLUG_REAL).is_dir(),
    reason=(
        "a fábrica de vídeo não está montada nesta máquina. O módulo é lido "
        "pelos testes sintéticos; este exige o build real."
    ),
)


# ---------------------------------------------------------------------------
# FÁBRICA SINTÉTICA — mínima, e com as ausências que importam
# ---------------------------------------------------------------------------

#: Arco de três papéis. Existe para provar que os papéis dos beats vêm do GRAFO
#: DO MOTOR, e não de uma lista genérica embutida no leitor: se o módulo
#: inventasse `hook/desenvolvimento/fecho`, ele não teria como acertar
#: `abertura`, `nó` e `desate`, que são nomes que só existem neste fixture.
_ARCO_INVENTADO = [
    {"papel": "abertura", "cena": "hook"},
    {"papel": "nó", "cena": "ai"},
    {"papel": "desate", "cena": "ai"},
]

_MAPA = {
    "versao": "9.9.9",
    "nichos": {"teste-de-leitura": {"skin": "provinha"}},
    "skins": {
        "provinha": {
            "comp": "Provinha",
            "config_dir": "episodios/",
            "config_driven": True,
            "voz_default": "VOZ:teste",
            "arco": _ARCO_INVENTADO,
        }
    },
    "vozes": {"VOZ:teste": {"voice": "Vozinha", "style": "Estilo declarado no grafo."}},
}


def _escrever(caminho: Path, conteudo: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (bytes, bytearray)):
        caminho.write_bytes(conteudo)
    elif isinstance(conteudo, str):
        caminho.write_text(conteudo, encoding="utf-8")
    else:
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")


def _fabrica_completa(raiz: Path, slug: str = "short_provinha") -> str:
    """Um build sintético com TODOS os artefatos, e com as ausências do real.

    As ausências são o ponto: `license` explicitamente `null` num item e
    simplesmente ausente no outro, `commercial_ok` ausente no terceiro, e
    nenhum `fatos` no episódio. É o formato do `short_odete`, reduzido.
    """
    _escrever(raiz / "contrato" / "motor" / "mapa.json", _MAPA)
    _escrever(raiz / "episodios" / "provinha.json", {
        "slug": "provinha",
        "title": "TÍTULO DO EPISÓDIO",
        "badge": "SELO",
        "voice": "Vozinha",
        "speed": 1.1,
        "omni_hook": {"line": "A primeira frase.", "seconds": 4, "setting": "um quarto"},
        "beats": ["A primeira frase.", "O meio.", "O fim."],
        "scenes": [
            {"kind": "hook"},
            {"kind": "ai", "prompt": "uma porta entreaberta"},
            {"kind": "wikimedia", "person": "Alguém Real"},
        ],
    })
    _escrever(raiz / "out" / "builds" / slug / "props.json", {
        "durationInFrames": 300,
        "fps": 30,
        "TR": 12,
        "title": "TÍTULO DO EPISÓDIO",
        "badge": "SELO",
        "scenes": [
            {"type": "video", "src": "hook_provinha.mp4", "dur": 120},
            {"type": "image", "src": "img_provinha/turn_1.png", "dur": 100},
            {"type": "image", "src": "img_provinha/real_1.jpg", "dur": 92},
        ],
        "stings": [{"t": 4.0, "text": "OLHA ISSO", "kind": "sting"}],
        "logo": None,
        "priceCards": [],
    })
    _escrever(raiz / "out" / "builds" / slug / "timings.json", {
        "cutTimes": [4.0, 7.5],
        "dur": 10.0,
    })
    _escrever(raiz / "out" / "builds" / slug / "ledger.json", {
        "video": slug,
        "comp": "Provinha",
        "caso": "o assunto do vídeo em uma frase",
        "sources": [
            # `license` explicitamente `null`: é o caso dos itens de Wikimedia
            # do `short_odete`, e o valor tem de sobreviver como ausência.
            {"scene": 2, "file": "real_1.jpg", "source": "Wikimedia Commons",
             "license": None, "credit": None, "url": None, "commercial_ok": True},
            # `license` AUSENTE (chave não existe) e `commercial_ok` ausente:
            # dois jeitos diferentes de não saber, e nenhum vira `False`.
            {"scene": 0, "file": "hook_provinha.mp4",
             "source": "Gemini Omni t2v — avatar IA FICTICIO falado (hook)",
             "disclosure": "conteudo sintetico/IA — marcar na plataforma",
             "synthid": True},
            # Licença DECLARADA: prova que o leitor preserva o valor quando ele
            # existe, e não só quando é nulo.
            {"scene": 1, "file": "turn_1.png", "source": "Banco licenciado",
             "license": "CC BY-SA 4.0", "credit": "Fulano", "commercial_ok": False},
        ],
    })
    _escrever(raiz / "out" / f"qa_{slug}.json", {
        "video": f"{slug}.mp4",
        "verdict": "PASS",
        "duration_s": 10.0,
        "checks": [
            {"check": "resolucao", "status": "PASS", "detail": "1080x1920"},
            {"check": "true_peak", "status": "WARN", "detail": "-0.7 dBTP (max -0.8)"},
        ],
    })
    _escrever(raiz / "out" / f"{slug}.qa_visual.json", {
        "video": f"{slug}.mp4",
        "verdict": "WARN",
        "frames": [
            {"t": 0.5, "reason": "hook", "file": f"out/qa_frames_{slug}/f_0.50.jpg",
             "checks": [
                 {"id": "ui_occlusion", "level": "WARN", "evidence": "legenda na zona da interface"},
                 {"id": "emoji_errado", "level": "PASS", "evidence": "emojis corretos"},
             ]},
            {"t": 5.0, "reason": "sting", "file": f"out/qa_frames_{slug}/f_5.00.jpg",
             "checks": [
                 {"id": "ui_occlusion", "level": "PASS", "evidence": "nada na zona da interface"},
                 {"id": "emoji_errado", "level": "SKIPPED", "evidence": "sem emoji esperado"},
             ]},
        ],
        "usage": {"est_cost_usd": 0.0012},
    })
    _escrever(raiz / "out" / f"qa_frames_{slug}" / "f_0.50.jpg", b"jpeg-de-mentira")
    _escrever(raiz / "out" / f"{slug}.mp4", b"mp4-de-mentira")

    import hashlib
    sha = hashlib.sha256(b"mp4-de-mentira").hexdigest()
    _escrever(raiz / "out" / "meta" / slug / "freeze.json", {
        "video": slug,
        "mp4": f"out/{slug}.mp4",
        "sha256": sha,
        "dur_s": 10.0,
        "frozen_at": "2026-07-12T12:36:12-03:00",
    })
    return slug


@pytest.fixture
def fabrica_sintetica(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, str]]:
    raiz = tmp_path / "fabrica"
    slug = _fabrica_completa(raiz)
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(raiz))
    yield raiz, slug


# ---------------------------------------------------------------------------
# UTILITÁRIOS DE PROVA
# ---------------------------------------------------------------------------


def _textos(valor: Any, caminho: str = "raiz") -> Iterator[tuple[str, str]]:
    """Todo par (endereço, string) dentro de uma estrutura JSON."""
    if isinstance(valor, dict):
        for chave, filho in valor.items():
            yield from _textos(filho, f"{caminho}.{chave}")
    elif isinstance(valor, list):
        for indice, filho in enumerate(valor):
            yield from _textos(filho, f"{caminho}[{indice}]")
    elif isinstance(valor, str):
        yield caminho, valor


def _provar_que_nao_ha_caminho(dados: dict[str, Any], raiz: Path) -> None:
    """Nenhum caminho de filesystem em nenhum campo devolvido.

    Quatro varreduras, porque cada uma pega um jeito diferente de vazar:
    a raiz configurada (o vazamento óbvio), o prefixo `/Users/` (o vazamento
    da máquina de desenvolvimento), qualquer string começando em `/` (o
    vazamento por caminho relativo à raiz do sistema) e `qa_frames`, que é a
    pasta de quadros do QA e o único caminho RELATIVO que aparece dentro dos
    artefatos lidos.
    """
    bruto = json.dumps(dados, ensure_ascii=False)
    assert str(raiz) not in bruto, "a raiz da fábrica vazou para a saída"
    assert "/Users/" not in bruto, "um caminho de máquina vazou para a saída"
    assert "qa_frames" not in bruto, "o caminho dos quadros de QA vazou para a saída"
    for endereco, texto in _textos(dados):
        assert not texto.startswith("/"), f"{endereco} parece um caminho absoluto: {texto!r}"


# ---------------------------------------------------------------------------
# 1. O BUILD REAL
# ---------------------------------------------------------------------------


@sem_fabrica
def test_short_odete_e_lido_e_o_sha256_bate_com_o_snapshot() -> None:
    """O hash medido byte a byte é o mesmo que a fábrica congelou.

    É o teste que dá sentido a `hashDoArtefato`: sem ele, "este é o vídeo que a
    fábrica aprovou" seria afirmação; com ele, qualquer pessoa reconfere.

    ⚠️ O `bytes_totais` está aqui junto por um motivo: `render.mp4` (a saída
    crua do Remotion, 41.252.563 bytes) e `out/short_odete.mp4` (o final, pós
    sound design, 40.555.197 bytes) são os dois MP4 do mesmo build. Se alguém
    trocar a fonte por engano, os dois números mudam juntos e o teste avisa.
    """
    build = vo.ler_build(SLUG_REAL)
    assert isinstance(build, vo.BuildObservado)

    assert build.content_hash == SHA256_CONGELADO
    assert build.hash_congelado == SHA256_CONGELADO
    assert build.hash_confere is True
    assert build.bytes_totais == BYTES_DO_MP4_FINAL

    assert build.origem["hashDoArtefato"] == SHA256_CONGELADO
    assert build.origem["identificadorDoBuild"] == SLUG_REAL
    assert build.origem["congeladoEm"] == "2026-07-12T12:36:12-03:00"

    # A leitura editorial chegou inteira, e não só o arquivo.
    assert build.contrato["skin"] == "gossip"
    assert build.contrato["nicho"] == "novela"
    assert build.largura == 1080 and build.altura == 1920
    assert build.duracao_ms == 43_800
    assert len(build.contrato["beats"]) == 7
    assert len(build.ledger) == 12


@sem_fabrica
def test_papeis_dos_beats_sao_os_do_arco_da_skin_e_nao_nomes_genericos() -> None:
    """Os sete papéis do `short_odete` são os do arco `gossip` do motor.

    `segredo`, `suspeitos/opções` e `payoff+cta` não são nomes que um leitor
    inventaria: eles só existem no grafo da fábrica. Se o módulo trocasse o
    arco real por uma lista genérica, este teste seria a primeira coisa a cair.
    """
    build = vo.ler_build(SLUG_REAL)
    assert isinstance(build, vo.BuildObservado)
    papeis = [beat["papel"] for beat in build.contrato["beats"]]
    assert papeis == [
        "hook", "contexto", "virada", "segredo",
        "suspeitos/opções", "revelação", "payoff+cta",
    ]


@sem_fabrica
def test_o_build_real_nao_devolve_nenhum_caminho() -> None:
    build = vo.ler_build(SLUG_REAL)
    assert isinstance(build, vo.BuildObservado)
    _provar_que_nao_ha_caminho(build.para_dicts(), _raiz_real())

    # O caminho existe, mas do lado de DENTRO: é o backend que faz streaming.
    assert build.mp4_caminho is not None and build.mp4_caminho.is_file()
    assert "mp4_caminho" not in build.para_dicts()
    assert "poster_caminho" not in build.para_dicts()


@sem_fabrica
def test_no_build_real_a_licenca_ausente_continua_ausente() -> None:
    """Os doze insumos do `short_odete` estão sem licença declarada.

    A fábrica gravou `"license": null` nos itens de Wikimedia e a nota do
    ledger explica ("licenca implicita de imprensa; CREDITAR"). Um leitor que
    preenchesse "desconhecida" ou "livre" transformaria uma pendência jurídica
    aberta em texto que tranquiliza quem vai aprovar a peça.
    """
    build = vo.ler_build(SLUG_REAL)
    assert isinstance(build, vo.BuildObservado)
    assert all(item["licenca"] is None for item in build.ledger)
    assert '"licenca": null' in json.dumps(build.para_dicts(), ensure_ascii=False)
    # E o build não registrou fatos, o que não é o mesmo que não ter fontes:
    # os doze insumos do ledger têm procedência.
    assert build.contrato["fatos"] == []
    assert len(build.ledger) == 12


# ---------------------------------------------------------------------------
# 2. NENHUM CAMINHO ABSOLUTO
# ---------------------------------------------------------------------------


def test_nenhum_caminho_absoluto_na_saida_sintetica(fabrica_sintetica) -> None:
    raiz, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    _provar_que_nao_ha_caminho(build.para_dicts(), raiz)


def test_nome_de_arquivo_sobrevive_sem_o_diretorio(fabrica_sintetica) -> None:
    """`img_provinha/turn_1.png` vira `turn_1.png`, e não some.

    Duas consequências desejadas: nada de caminho no browser, e o nome passa a
    bater com o campo `file` do ledger, que é como um beat encontra a
    procedência do insumo que ele usa.
    """
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    arquivos = [beat["assetArquivo"] for beat in build.contrato["beats"]]
    assert arquivos == ["hook_provinha.mp4", "turn_1.png", "real_1.jpg"]
    assert set(arquivos) == {item["arquivo"] for item in build.ledger}


def test_a_fabrica_e_identificada_por_simbolo_e_nao_por_caminho(fabrica_sintetica) -> None:
    raiz, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    assert build.origem["fabrica"] == "volc-factory"
    assert str(raiz) != build.origem["fabrica"]


# ---------------------------------------------------------------------------
# 3. OBSERVADO NUNCA VIRA PRODUZIDO
# ---------------------------------------------------------------------------


def test_a_procedencia_so_pode_valer_observado(fabrica_sintetica) -> None:
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)

    assert vo.PROCEDENCIA_EXECUCAO == "observado"
    assert vo.PROCEDENCIAS_ADMITIDAS == frozenset({"observado"})
    assert build.procedencia_execucao == "observado"
    assert build.modo == "observado"


def test_nenhum_campo_devolvido_afirma_autoria_do_volc_os(fabrica_sintetica) -> None:
    """A saída não tem onde guardar "quem produziu", porque ninguém produziu.

    `motor` e `motorVersao` são campos do `CreativeJob`, montados por quem
    consome esta leitura; aqui eles não existem, e a única versão mencionada
    (`motorVersaoConhecida`) é nula por não haver o que declarar.
    """
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    saida = build.para_dicts()

    bruto = json.dumps(saida, ensure_ascii=False).lower()
    for proibido in ("volc_os", "volc-os", "volc o.s", "renderizado por", "produzido por"):
        assert proibido not in bruto, f"a saída afirma autoria: {proibido!r}"

    assert set(saida) == {"contrato", "ledger", "qa", "origemExterna"}
    assert "motor" not in saida["origemExterna"]
    assert "motorVersao" not in saida["origemExterna"]


def test_o_fonte_do_modulo_nao_tem_como_escrever_a_procedencia_oposta() -> None:
    """A garantia mais forte disponível: o token não existe no arquivo.

    "O código não escreve `volc_os`" é uma afirmação sobre o comportamento de
    hoje, que um `if` novo desfaz sem ninguém notar. "O arquivo não contém o
    token" é uma afirmação sobre o arquivo, e quem quiser desfazê-la tem de
    escrevê-la, ver este teste vermelho e decidir conscientemente.
    """
    fonte = Path(vo.__file__).read_text(encoding="utf-8")
    assert "volc_os" not in fonte


def test_o_estado_de_producao_propria_nao_e_alcancavel(fabrica_sintetica) -> None:
    """Não há argumento, variável de ambiente ou dado de build que mude a
    procedência: ela é atributo de valor único do dataclass."""
    _, slug = fabrica_sintetica
    os.environ["VOLC_PROCEDENCIA"] = "volc_os"  # ignorado de propósito
    try:
        build = vo.ler_build(slug)
        assert isinstance(build, vo.BuildObservado)
        assert build.procedencia_execucao == "observado"
    finally:
        os.environ.pop("VOLC_PROCEDENCIA", None)


# ---------------------------------------------------------------------------
# 4. ARTEFATO AUSENTE NÃO DERRUBA A LEITURA
# ---------------------------------------------------------------------------


def test_build_incompleto_e_lido_com_ausencias_e_sem_excecao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um build só com props, com o ledger corrompido e sem MP4.

    É a versão extrema do `short_das`, que na fábrica real não tem QA visual
    nem snapshot congelado. Se a leitura fosse tudo ou nada, um build
    interrompido viraria erro na tela e o operador não veria nem o que existe.
    """
    raiz = tmp_path / "fabrica-pela-metade"
    slug = "short_incompleto"
    _escrever(raiz / "out" / "builds" / slug / "props.json", {
        "durationInFrames": 150,
        "fps": 30,
        "title": "SÓ O COMEÇO",
        "scenes": [{"type": "image", "src": "img/turn_1.png", "dur": 150}],
    })
    # JSON truncado: um build interrompido no meio da escrita.
    _escrever(raiz / "out" / "builds" / slug / "ledger.json", '{"video": "x", "sources": [')
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(raiz))

    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)

    # Ausência vira `None`/lista vazia, nunca zero e nunca exceção.
    assert build.ledger == []
    assert build.qa["vereditoTecnico"] is None
    assert build.qa["vereditoVisual"] is None
    assert build.qa["gatesTecnicos"] == []
    assert build.qa["gatesVisuais"] == []
    assert build.qa["custoQaUsd"] is None
    assert build.mp4_caminho is None
    assert build.poster_caminho is None
    assert build.content_hash is None
    assert build.bytes_totais is None
    assert build.mime is None
    assert build.largura is None and build.altura is None
    assert build.hash_congelado is None
    assert build.hash_confere is None
    assert build.origem["hashDoArtefato"] is None
    assert build.origem["congeladoEm"] is None

    # Mas o que EXISTE foi lido: 150 frames a 30 fps são 5 segundos.
    assert build.contrato["titulo"] == "SÓ O COMEÇO"
    assert build.duracao_ms == 5_000
    assert build.contrato["skin"] is None
    assert [b["papel"] for b in build.contrato["beats"]] == [None]

    _provar_que_nao_ha_caminho(build.para_dicts(), raiz)


def test_qa_ausente_nao_vira_pass_nem_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`vereditoVisual: None` é "não rodou"; `SKIPPED` seria "rodou e pulou".

    É o caso do `short_das` na fábrica real. Um build sem QA visual exibido
    como aprovado é exatamente o que faz alguém publicar sem revisar.
    """
    raiz = tmp_path / "fabrica-sem-visual"
    slug = "short_sem_visual"
    _escrever(raiz / "out" / "builds" / slug / "props.json", {"fps": 30, "scenes": []})
    _escrever(raiz / "out" / f"qa_{slug}.json", {
        "verdict": "WARN", "duration_s": 20.0,
        "checks": [{"check": "true_peak", "status": "WARN", "detail": "-0.7 dBTP"}],
    })
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(raiz))

    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    assert build.qa["vereditoTecnico"] == "WARN"
    assert build.qa["vereditoVisual"] is None
    assert build.qa["vereditoVisual"] != "SKIPPED"
    assert build.qa["gatesVisuais"] == []


def test_veredito_desconhecido_vira_warn_com_o_token_cru(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um veredito que a leitura não reconhece não pode virar aprovação.

    `PASS` aprovaria o que não foi lido e `SKIPPED` afirmaria que o check não
    rodou. `WARN` é o único dos quatro cujo significado é "um humano precisa
    olhar", e o token cru fica no detalhe para esse humano ver.
    """
    raiz = tmp_path / "fabrica-com-veredito-novo"
    slug = "short_esquisito"
    _escrever(raiz / "out" / "builds" / slug / "props.json", {"fps": 30, "scenes": []})
    _escrever(raiz / "out" / f"qa_{slug}.json", {
        "verdict": "INCONCLUSIVO",
        "checks": [{"check": "resolucao", "status": "TALVEZ", "detail": "1080x1920"}],
    })
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(raiz))

    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    assert build.qa["vereditoTecnico"] == "WARN"
    gates = {g["id"]: g for g in build.qa["gatesTecnicos"]}
    assert gates["resolucao"]["resultado"] == "WARN"
    assert "TALVEZ" in gates["resolucao"]["detalhe"]
    assert gates["veredito_do_build"]["resultado"] == "WARN"
    assert "INCONCLUSIVO" in gates["veredito_do_build"]["detalhe"]


def test_slug_inexistente_levanta_erro_de_dominio(fabrica_sintetica) -> None:
    """`BuildNaoEncontrado`, nunca `FileNotFoundError`.

    Um `FileNotFoundError` vazando pela rota entrega o caminho do disco dentro
    da mensagem de erro, que é o que este módulo passa o tempo todo evitando.
    """
    with pytest.raises(vo.BuildNaoEncontrado) as erro:
        vo.ler_build("short_que_nunca_existiu")
    assert "/" not in str(erro.value)

    # E travessia de diretório é recusada antes de tocar o disco.
    for maldoso in ("../../etc", "..", "out/builds/x"):
        with pytest.raises(vo.BuildNaoEncontrado):
            vo.ler_build(maldoso)


def test_fabrica_ausente_devolve_indisponibilidade_tipada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raiz que não existe: objeto tipado, não exceção e não dado inventado.

    Caminho absoluto não pode virar contrato de produção (ADR-002), então a
    ausência da fábrica tem de ser um estado que a interface sabe mostrar, e
    não um erro que ela precisa interpretar.
    """
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(tmp_path / "nao-existe"))

    assert vo.disponivel() is False
    assert vo.listar_builds() == []

    leitura = vo.ler_build("short_odete")
    assert isinstance(leitura, vo.FabricaIndisponivel)
    assert leitura.codigo == "raiz_ausente"
    assert "/" not in leitura.motivo

    vazio = leitura.para_dicts()
    assert vazio["contrato"] is None
    assert vazio["ledger"] == []
    assert vazio["qa"] is None
    assert vazio["origemExterna"] is None
    _provar_que_nao_ha_caminho(vazio, tmp_path)


# ---------------------------------------------------------------------------
# 5. AUSÊNCIA PRESERVADA COMO AUSÊNCIA
# ---------------------------------------------------------------------------


def test_licenca_nula_e_fatos_vazios_sobrevivem_a_leitura(fabrica_sintetica) -> None:
    """Três formas de não saber, e nenhuma vira valor.

    - `"license": null` explícito continua `None`.
    - `license` ausente continua `None` (e não "desconhecida").
    - `commercial_ok` ausente continua `None` (e não `False`).

    A terceira é a mais perigosa das três: `False` significa "a fábrica disse
    que NÃO pode usar comercialmente", que é uma afirmação jurídica que ninguém
    fez.
    """
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    por_arquivo = {item["arquivo"]: item for item in build.ledger}

    assert por_arquivo["real_1.jpg"]["licenca"] is None          # null explícito
    assert por_arquivo["hook_provinha.mp4"]["licenca"] is None   # chave ausente
    assert por_arquivo["hook_provinha.mp4"]["usoComercialOk"] is None
    assert por_arquivo["hook_provinha.mp4"]["usoComercialOk"] is not False

    # E o valor DECLARADO sobrevive igual: a regra é preservar, não anular.
    assert por_arquivo["turn_1.png"]["licenca"] == "CC BY-SA 4.0"
    assert por_arquivo["turn_1.png"]["credito"] == "Fulano"
    assert por_arquivo["turn_1.png"]["usoComercialOk"] is False

    # `fatos: []` é "o build não registrou fatos", e o ledger prova que isso não
    # é o mesmo que "não há fontes": três insumos com procedência declarada.
    assert build.contrato["fatos"] == []
    assert len(build.ledger) == 3


def test_sintetico_vem_do_synthid_ou_da_descricao_da_fonte(fabrica_sintetica) -> None:
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    por_arquivo = {item["arquivo"]: item for item in build.ledger}

    assert por_arquivo["hook_provinha.mp4"]["sintetico"] is True
    assert por_arquivo["hook_provinha.mp4"]["disclosure"] is not None
    assert por_arquivo["real_1.jpg"]["sintetico"] is False
    assert por_arquivo["real_1.jpg"]["disclosure"] is None


def test_elementos_de_retencao_sao_os_usados_e_nao_o_catalogo_da_skin(
    fabrica_sintetica,
) -> None:
    """`logo: null` e `priceCards: []` não entram: o vídeo não os tem."""
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    assert build.contrato["elementosDeRetencao"] == ["stings"]


def test_cta_ausente_nao_e_derivado_do_ultimo_beat(fabrica_sintetica) -> None:
    """O episódio sintético não declara CTA, e a leitura não inventa um.

    É o caso do `short_odete`: o beat final termina em "Segue pra mais
    mistérios de novela!", que qualquer heurística chamaria de CTA. Heurística
    não é registro.
    """
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    assert build.contrato["cta"] is None


def test_papeis_saem_nulos_quando_o_arco_nao_cabe_nos_beats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cinco beats contra três papéis: nenhum papel, e não três mais dois nulos.

    É o caso do `short_das` (cinco beats, arco `holerite` de sete papéis).
    Alinhar por posição colocaria o rótulo errado em cada cena, e papel errado
    é pior que papel ausente: `None` faz a interface calar, o rótulo errado a
    faz mentir com confiança.
    """
    raiz = tmp_path / "fabrica-desalinhada"
    slug = "short_desalinhado"
    _escrever(raiz / "contrato" / "motor" / "mapa.json", _MAPA)
    _escrever(raiz / "out" / "builds" / slug / "ledger.json",
              {"video": slug, "comp": "Provinha", "sources": []})
    _escrever(raiz / "out" / "builds" / slug / "props.json", {
        "fps": 30,
        "scenes": [{"type": "image", "src": f"c{i}.png", "dur": 60} for i in range(5)],
    })
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(raiz))

    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    assert build.contrato["skin"] == "provinha"
    assert [b["papel"] for b in build.contrato["beats"]] == [None] * 5
    # E o copy também não é costurado quando a contagem não bate.
    assert all(b["copy"] is None for b in build.contrato["beats"])


# ---------------------------------------------------------------------------
# 6. VERSÃO DO MOTOR: AUSENTE, E DECLARADA COMO AUSENTE
# ---------------------------------------------------------------------------


def test_motor_versao_conhecida_e_sempre_nula(fabrica_sintetica) -> None:
    """A fábrica não carimba versão de motor dentro do build.

    ⚠️ O fixture põe `"versao": "9.9.9"` no grafo do motor de propósito. Ela
    existe, é legível, e mesmo assim NÃO pode aparecer aqui: é a versão do
    GRAFO no momento da leitura, não a que renderizou este vídeo. Usá-la
    afirmaria uma procedência que nenhum artefato do build sustenta, e a
    afirmação seria plausível o bastante para ninguém conferir.
    """
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)

    assert build.origem["motorVersaoConhecida"] is None
    assert "9.9.9" not in json.dumps(build.para_dicts(), ensure_ascii=False)


@sem_fabrica
def test_motor_versao_conhecida_e_nula_tambem_no_build_real() -> None:
    build = vo.ler_build(SLUG_REAL)
    assert isinstance(build, vo.BuildObservado)
    assert build.origem["motorVersaoConhecida"] is None


def test_provider_de_voz_e_nulo_pelo_mesmo_motivo(fabrica_sintetica) -> None:
    """O provedor de TTS é escolhido em tempo de execução e não é gravado.

    Herdá-lo do runtime da fábrica daria um campo preenchido que nenhuma
    evidência do build sustenta, que é a mesma falha de `motorVersaoConhecida`
    por outra porta. O `id` e a `velocidade`, esses sim, estão no input.
    """
    _, slug = fabrica_sintetica
    build = vo.ler_build(slug)
    assert isinstance(build, vo.BuildObservado)
    voz = build.contrato["voz"]
    assert voz is not None
    assert voz["provider"] is None
    assert voz["id"] == "Vozinha"
    assert voz["velocidade"] == 1.1
    assert voz["estilo"] == "Estilo declarado no grafo."


# ---------------------------------------------------------------------------
# 7. A LIMITAÇÃO DECLARADA
# ---------------------------------------------------------------------------


def test_limitacao_declarada_e_texto_de_operador() -> None:
    """O texto que a interface mostra no lugar de "Criar vídeo".

    Ele existe para a interface não inventar a limitação nem escondê-la, e por
    isso as regras de forma são testadas: sem travessão (PRODUCT.md), sem
    caminho, e sem nome de arquivo interno da fábrica. Um operador que lê
    `pipeline/buildspace.py` numa tela de produto não aprende nada; ele aprende
    que dois vídeos ao mesmo tempo se corrompem.
    """
    texto = vo.limitacao_declarada()
    assert texto == vo.LIMITACAO_DECLARADA
    assert len(texto) > 200

    assert "—" not in texto, "travessão não vai para a interface"
    assert "/" not in texto, "nada que pareça caminho vai para a interface"
    for interno in (".py", ".json", "props", "buildspace", "runner", "remotion"):
        assert interno not in texto.lower(), f"nome interno da fábrica no texto: {interno}"

    # Os três impedimentos medidos precisam estar lá: é o conteúdo, não a forma.
    assert "ao mesmo tempo" in texto
    assert "teste" in texto.lower()
    assert "leitura, não produção" in texto


# ---------------------------------------------------------------------------
# 8. O CATÁLOGO
# ---------------------------------------------------------------------------


def test_listar_builds_devolve_slugs_em_ordem_estavel(fabrica_sintetica) -> None:
    raiz, slug = fabrica_sintetica
    (raiz / "out" / "builds" / "short_outro").mkdir(parents=True)
    assert vo.listar_builds() == sorted(["short_outro", slug])


@sem_fabrica
def test_o_catalogo_real_inclui_o_short_odete() -> None:
    assert vo.disponivel() is True
    assert SLUG_REAL in vo.listar_builds()


def test_a_raiz_e_relida_do_ambiente_a_cada_chamada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem cache de import.

    Uma constante montada no import congela o valor no primeiro import do
    processo, e um teste que aponta a raiz para outro lugar passaria a depender
    da ordem em que os módulos foram carregados.
    """
    primeira = tmp_path / "uma"
    segunda = tmp_path / "outra"
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(primeira))
    assert vo.raiz() == primeira
    monkeypatch.setenv(vo.VARIAVEL_DE_RAIZ, str(segunda))
    assert vo.raiz() == segunda
