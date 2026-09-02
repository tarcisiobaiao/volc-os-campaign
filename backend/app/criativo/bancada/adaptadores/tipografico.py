"""Motor tipografico local: pixel real, sem rede, sem credencial, deterministico.

## Por que este motor existe

A fatia de aceite exige um artefato REAL produzido por um adaptador que roda aqui.
Todo motor de imagem do parque hoje precisa de credencial externa
(`gemini-imagem`) ou de um pipeline que nao esta portado (`prensa`). Sem um motor
local, "provar o executor" viraria "provar o executor com um dublê", que nao
prova executor nenhum.

## Por que NAO e a PRENSA

Copiar a PRENSA foi proibido explicitamente numa rodada anterior, e a razao
continua boa: um vendor parcial diverge da fonte em silencio. Este motor nao imita
a PRENSA nem tenta substitui-la. Ele faz uma coisa so, bem: compor tipografia
sobre fundo solido, com fonte de arquivo real, de forma reproduzivel. A PRENSA
faz grid, variantes, gates de DOM e promocao transacional; nada disso esta aqui.

## Determinismo

Mesma encomenda -> mesmos bytes. Isso exige cuidado que nao e obvio:

- nenhuma leitura de relogio entra no pixel;
- `Image.save` do PNG grava tempo em `tIME` se pedirem; nao pedimos;
- a escolha de cor vem de `random.Random(seed)`, semeado por encomenda e nunca
  do modulo `random` global, que outro job poderia ter mexido;
- a fonte entra no recibo por sha256, porque trocar o arquivo da fonte muda o
  pixel e um recibo que nao registrasse isso mentiria sobre reprodutibilidade.

## Caminho absoluto

⚠️ **Correcao de 28/08/2026, noite.** A versao anterior desta secao dizia "nao ha
nenhum embutido" e a lista `_PISTAS_DE_FONTE` comecava com
`/Users/mac/Desktop/Volc Midia Global/...` — o caminho pessoal de uma maquina, e
justamente o que vence a busca aqui. A afirmacao era falsa.

E a consequencia nao e estetica: `versoes.fonte_sha256` entra na
`assinatura_determinista`, entao o mesmo pedido nesta maquina e num servidor
produz assinaturas DIFERENTES por causa de um caminho pessoal.

O que e verdade: `CRIATIVO_FONTES_DIR` tem precedencia sobre tudo, as pistas sao
tentativas de conveniencia declaradas como tais, e sem fonte o motor FALHA COM
MOTIVO. Nao existe fallback para a fonte bitmap embutida do PIL: ela produziria
uma imagem que parece tipografia e nao e, e a tela diria "produziu" sobre uma
peca que ninguem usaria.
"""

from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path
from typing import Any

from volc_ads.criativo.contrato import NaturezaDaProcedencia

from ..contrato import Artefato, Encomenda, FalhaDoMotor

VERSAO_DO_ADAPTADOR = "1.0.0"

#: A fonte que viaja com o codigo. Ver `fontes/PROCEDENCIA.md` para licenca.
#:
#: ⚠️ Nao ha mais lista de "pistas" com caminho de maquina. A versao anterior
#: comecava por `/Users/mac/Desktop/...` e a docstring afirmava "nao ha caminho
#: absoluto embutido" — as duas coisas ao mesmo tempo. E a consequencia nao era
#: estetica: `fonte_sha256` entra na assinatura determinista, entao o mesmo
#: pedido em duas maquinas dava assinaturas diferentes.
#:
#: Tambem nao ha fallback para fonte de SISTEMA. Uma Helvetica achada por acaso
#: mudaria o pixel sem mudar nada do pedido, e o recibo diria "mesmas versoes".
FONTES_EMPACOTADAS: Path = Path(__file__).resolve().parent.parent / "fontes"

_PREFERIDAS: tuple[str, ...] = ("Inter-Variable.ttf",)


def _escolher_em(d: Path) -> Path | None:
    for nome in _PREFERIDAS:
        c = d / nome
        if c.is_file():
            return c
    # Ordem alfabetica: a escolha precisa ser a mesma em qualquer maquina com o
    # mesmo diretorio.
    achadas = sorted(
        p for p in d.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".ttc")
    )
    return achadas[0] if achadas else None


def _escolher_fonte() -> Path:
    """1. empacotada · 2. `CRIATIVO_FONTES_DIR` · 3. falha com motivo."""
    if FONTES_EMPACOTADAS.is_dir() and (f := _escolher_em(FONTES_EMPACOTADAS)):
        return f

    do_ambiente = os.environ.get("CRIATIVO_FONTES_DIR")
    if do_ambiente:
        d = Path(do_ambiente)
        if not d.is_dir():
            raise FalhaDoMotor(
                "CRIATIVO_FONTES_DIR aponta para um diretorio que nao existe",
                permanente=True,
            )
        if f := _escolher_em(d):
            return f
        raise FalhaDoMotor(
            "CRIATIVO_FONTES_DIR nao tem nenhuma fonte .ttf/.otf/.ttc",
            permanente=True,
        )

    raise FalhaDoMotor(
        "nenhuma fonte empacotada e CRIATIVO_FONTES_DIR nao definida",
        permanente=True,
    )


def _sha256_do_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def _luminancia_relativa(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.x. Formula publica, nao codigo de terceiro."""

    def canal(v: int) -> float:
        c = v / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razao_de_contraste(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Razao WCAG entre duas cores. 4.5 e o piso de texto normal em AA."""
    la, lb = _luminancia_relativa(a), _luminancia_relativa(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


#: Piso de contraste para texto normal em WCAG 2.2 nivel AA.
PISO_AA = 4.5

#: Paletas do motor. Nao ha sorteio livre de cor: sortear RGB e a forma mais
#: rapida de produzir texto ilegivel com aparencia de variedade.
#:
#: ⚠️ A primeira versao desta tabela vinha com o comentario "contraste ja
#: conferido contra o piso AA" e continha `#168B68` (o `success` do DESIGN.md)
#: sobre quase-branco: razao 4.114, ABAIXO do piso. O comentario afirmava uma
#: conferencia que ninguem tinha feito, e o proprio gate deste motor reprovou a
#: peca — foi assim que o defeito apareceu. O verde agora e uma variante mais
#: escura da mesma familia, e a guarda logo abaixo impede o comentario de voltar
#: a mentir.
_PALETAS: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = (
    ((243, 245, 247), (26, 28, 30)),    # 15.64
    ((12, 17, 27), (243, 246, 250)),    # 17.43
    ((13, 71, 161), (248, 250, 252)),   #  8.25  primary do DESIGN.md
    ((17, 105, 79), (250, 251, 252)),   #  6.42  success escurecido para caber em AA
    ((26, 28, 30), (255, 214, 10)),     # 12.11
)


def _conferir_paletas() -> None:
    """Roda no import. Uma paleta que nao passa no proprio gate do motor nao pode
    existir na tabela: ela produziria uma peca reprovada DEPOIS de renderizada,
    gastando tempo para descobrir o que dava para saber antes."""
    for fundo, tinta in _PALETAS:
        r = razao_de_contraste(fundo, tinta)
        if r < PISO_AA:
            raise AssertionError(
                f"paleta {fundo}/{tinta} tem contraste {r:.3f}, abaixo do piso "
                f"AA de {PISO_AA}"
            )


_conferir_paletas()


class MotorTipografico:
    """Compoe uma peca com fundo solido e texto real, medindo o que produziu."""

    slug = "tipografico-local"
    versao = VERSAO_DO_ADAPTADOR
    #: ⚠️ ACHADO DESTA RODADA. Sem este atributo, `servico.natureza_do_motor`
    #: devolvia `NAO_DECLARADA` — resposta CORRETA da funcao e ERRADA para este
    #: motor, que e tao local quanto o `png-local`. E o custo aparecia no portao:
    #: `NATUREZAS_ACEITAS[Destino.PRODUCAO]` aceita `NAO_DECLARADA` como divida
    #: declarada, entao a peca de um motor 100% local PASSAVA em producao com
    #: aviso, enquanto a do `png-local` — que declara corretamente — recebia
    #: recusa. O incentivo estava invertido: nao declarar valia mais que declarar.
    natureza = NaturezaDaProcedencia.LOCAL
    #: O que este motor produz. O catalogo pergunta; ele nao chuta.
    midias = ("imagem",)

    def __init__(self) -> None:
        self._fonte = _escolher_fonte()

    def versoes_congeladas(self) -> dict[str, str]:
        from PIL import Image as _I

        return {
            "adaptador": VERSAO_DO_ADAPTADOR,
            "pillow": getattr(_I, "__version__", "desconhecida"),
            "fonte_arquivo": self._fonte.name,
            "fonte_sha256": _sha256_do_arquivo(self._fonte),
        }

    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        from PIL import Image, ImageDraw, ImageFont

        destino = Path(dir_trabalho)
        if not destino.is_dir():
            raise FalhaDoMotor(f"diretorio de trabalho inexistente: {destino}",
                               permanente=True)

        titulo = str(encomenda.parametros.get("titulo") or "").strip()
        if not titulo:
            raise FalhaDoMotor("sem titulo: nao ha o que compor", permanente=True)
        apoio = str(encomenda.parametros.get("apoio") or "").strip()

        # ⚠️ `random.Random(seed)`, nunca o `random` do modulo. O global e estado
        # compartilhado entre jobs, e dois trabalhos simultaneos se contaminariam
        # exatamente como os 21 geradores da fabrica se contaminam hoje.
        sorteio = random.Random(encomenda.seed)
        fundo, tinta = _PALETAS[sorteio.randrange(len(_PALETAS))]

        artefatos: list[Artefato] = []
        for saida in encomenda.saidas:
            if saida.midia != "imagem":
                raise FalhaDoMotor(
                    f"este motor produz imagem; pediram {saida.midia}", permanente=True
                )
            img = Image.new("RGB", (saida.largura, saida.altura), fundo)
            desenho = ImageDraw.Draw(img)

            margem = max(48, saida.largura // 12)
            largura_util = saida.largura - 2 * margem
            corpo = max(28, saida.largura // 14)

            fonte_titulo = ImageFont.truetype(str(self._fonte), corpo)
            linhas = _quebrar(desenho, titulo, fonte_titulo, largura_util)
            altura_linha = int(corpo * 1.22)
            bloco = altura_linha * len(linhas)

            fonte_apoio = ImageFont.truetype(str(self._fonte), max(18, corpo // 2))
            linhas_apoio = _quebrar(desenho, apoio, fonte_apoio, largura_util) if apoio else []
            altura_apoio = int(corpo * 0.7) * len(linhas_apoio)

            y = (saida.altura - bloco - altura_apoio) // 2
            for linha in linhas:
                desenho.text((margem, y), linha, font=fonte_titulo, fill=tinta)
                y += altura_linha
            if linhas_apoio:
                y += int(corpo * 0.4)
                for linha in linhas_apoio:
                    desenho.text((margem, y), linha, font=fonte_apoio, fill=tinta)
                    y += int(corpo * 0.7)

            caminho = destino / f"{saida.slot}.png"
            # `optimize=False` e nenhum parametro de tempo: o PNG precisa sair
            # byte a byte igual entre execucoes.
            img.save(caminho, format="PNG", optimize=False, compress_level=6)

            dados = caminho.read_bytes()
            artefatos.append(
                Artefato(
                    slot=saida.slot,
                    caminho=str(caminho),
                    mime="image/png",
                    bytes_=len(dados),
                    sha256=hashlib.sha256(dados).hexdigest(),
                    largura=saida.largura,
                    altura=saida.altura,
                    duracao_s=None,
                )
            )
        return tuple(artefatos)

    def medir_contraste(self, encomenda: Encomenda) -> dict[str, Any]:
        """O contraste que ESTA peca usou, com o numero, nao so com o veredito."""
        sorteio = random.Random(encomenda.seed)
        fundo, tinta = _PALETAS[sorteio.randrange(len(_PALETAS))]
        razao = razao_de_contraste(fundo, tinta)
        return {
            "razao": round(razao, 3),
            "piso_aa": PISO_AA,
            "fundo": list(fundo),
            "tinta": list(tinta),
            "fonte": "WCAG 2.2, luminancia relativa",
        }


def _quebrar(desenho: Any, texto: str, fonte: Any, largura: int) -> list[str]:
    if not texto:
        return []
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        tentativa = f"{atual} {p}".strip()
        if desenho.textlength(tentativa, font=fonte) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas
