"""A peça do meio: `CreativeSpec` → `post.spec/1.0.0`, a spec que a PRENSA lê.

## Onde isto entra

O Estúdio produz `CreativeSpec` (`studio/spec_visual.py`) e `prensa_http.py`
já sabe falar com o serviço. Faltava o tradutor. Ele é uma função pura: não
abre socket, não lê disco, não chama modelo — recebe a decisão criativa já
aprovada e devolve o JSON que `motor/resolve.py` aceita.

## `variants` NÃO existe, e é por isso que multi-formato é N specs

Medido em 10/09/2026 dentro do container: uma spec declarando três `variants`
(4:5, 9:16, 1:1, cada uma com sua `safe_area`, exatamente como o
`PRENSA-SPEC.md` §3 promete) produziu **um** PNG de 1088x1360, com sha256 byte
a byte idêntico ao da mesma spec sem `variants` nenhum. `grep -rn variants
services/prensa/motor/*.py` não devolve nada: o campo atravessa `resolve.py`,
entra no `.resolvido.json` e no `hash_canonico`, e `render.py` nunca o lê. O
`PRENSA-SPEC.md` é datado 15/08/2026, se declara "Fase 0 executada", e agenda
`variants` para a Fase 1 — é projeto, não inventário.

O eixo de multiplicidade do motor é `slides` (lâmina de carrossel), um artboard
por spec (`render.py:879`). Então `traduzir_lote` emite uma spec por formato.

⚠️ Isso não é contorno de limitação: é a MESMA doutrina que
`test_criativo_ancora_e_multiformato` já sela — cada formato é uma geração
própria, nunca um recorte do 4x5, porque texto vive exatamente nas bordas que a
tesoura corta. O motor e a doutrina concordam; o documento é que estava adiante.

## Por que a família cromática vira SKIN e não instrução

Porque instrução em prosa não segurou cor: um lote inteiro voltou azul-marinho
nas quatro peças com o prompt mandando o contrário. Aqui a família vira
`tokens_*.json` — `color.surface.base` e `color.accent.text` saem de cores
DIFERENTES da família declarada, e o motor pinta o que o token diz. Cor deixa
de ser pedido e vira dado.

## Por que o acento cai na âncora

`accent` é a cor mais forte da peça. `assunto_principal` é o mecanismo (o app);
`ancora_de_desejo` é o que para o polegar (o dinheiro). Pintar de ouro o
mecanismo desfaria no pixel a separação que a blindagem da v1 comprou. E o
budget de 2 palavras não é gosto: `resolve.py:100` reprova acima disso.
"""
from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - só para o tipo, sem custo em runtime
    from app.criativo.studio.spec_visual import CreativeSpec


class FamiliaCromaticaInsuficiente(ValueError):
    """Uma cor só não é família: não há como pôr duas em superfície grande."""


class CorDesconhecida(ValueError):
    """Nome de cor sem hex declarado e fora do léxico.

    Falha em vez de cair num cinza padrão porque um default silencioso é
    exatamente como um lote volta monocromático sem ninguém perceber.
    """


#: O piso da família. Abaixo disto não existe "duas cores em superfície grande".
MINIMO_DA_FAMILIA = 2

#: `resolve.py:100` — accent budget. Acima disto a peça é recusada antes do custo.
ACCENT_MAX_PALAVRAS = 2

#: Cores que aparecem em briefing brasileiro de programa público e social. É um
#: atalho, não uma autoridade: o operador pode sempre declarar o hex junto do
#: nome ("azul royal #1D3FBB") e é o hex declarado que vence.
LEXICO_DE_CORES: dict[str, str] = {
    "azul royal": "#1D3FBB",
    "azul marinho": "#12224F",
    "azul cobalto": "#1B3FCC",
    "azul claro": "#7FB2F0",
    "amarelo ouro": "#F2B705",
    "amarelo": "#F5C518",
    "verde bandeira": "#0E7A3C",
    "verde": "#16874A",
    "branco": "#F7F7F5",
    "preto": "#0B0B0F",
    "cinza": "#8A8A93",
    "vermelho": "#C42B1C",
    "laranja": "#E2600F",
    "roxo": "#5B2A86",
    "rosa": "#D2478A",
    "bege": "#E8DCC8",
    "grafite": "#22242A",
}

#: As fontes que a PRENSA empacota, com o sha256 que `resolve.py:valida_fontes`
#: CONFERE antes de abrir o navegador. O hash é fixado aqui de propósito: o
#: tradutor é função pura e não lê disco, e uma divergência precisa sair como
#: "fonte adulterada = recusa pré-custo" — o motor já diz isso com o nome certo —
#: em vez de virar tipografia trocada em silêncio no meio de um lote.
FONTES_DA_PRENSA: tuple[dict, ...] = (
    {
        "role": "display",
        "family": "Inter",
        "weight": 800,
        "weight_range": "100 900",
        "file": "fonts/Inter-Variable.ttf",
        "sha256": "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031",
    },
    {
        "role": "support",
        "family": "Inter",
        "weight": 500,
        "weight_range": "100 900",
        "file": "fonts/Inter-Variable.ttf",
        "sha256": "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031",
    },
)

_HEX = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _chave(nome: str) -> str:
    limpo = _HEX.sub("", nome)
    limpo = _sem_acento(limpo).lower()
    limpo = re.sub(r"[^a-z ]+", " ", limpo)
    return " ".join(limpo.split())


def hex_da_cor(declarada: str) -> str:
    """O hex de uma cor da família: o declarado vence, o léxico socorre."""
    achado = _HEX.search(declarada)
    if achado:
        digitos = achado.group(1)
        if len(digitos) == 3:
            digitos = "".join(c * 2 for c in digitos)
        return f"#{digitos.upper()}"

    chave = _chave(declarada)
    if chave in LEXICO_DE_CORES:
        return LEXICO_DE_CORES[chave]
    # "azul royal saturado" ainda é azul royal: o núcleo são as duas primeiras
    # palavras, mesma regra que `agente/validacao.py:_nucleo_da_cor` já usa.
    nucleo = " ".join(chave.split()[:2])
    if nucleo in LEXICO_DE_CORES:
        return LEXICO_DE_CORES[nucleo]
    primeira = chave.split()[0] if chave else ""
    if primeira in LEXICO_DE_CORES:
        return LEXICO_DE_CORES[primeira]
    raise CorDesconhecida(
        f"cor fora do léxico e sem hex declarado: {declarada!r}. "
        "Declare o hex junto do nome (ex.: 'azul royal #1D3FBB')."
    )


def _luminancia(cor_hex: str) -> float:
    """Luminância relativa WCAG — mesma linearização do `resolve.py:76`."""
    r, g, b = (int(cor_hex[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def _croma(cor_hex: str) -> float:
    r, g, b = (int(cor_hex[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b)


def contraste(a: str, b: str) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def skin_da_familia(familia: list[str], *, identificador: str = "VOS:familia") -> dict:
    """A família cromática declarada vira um `tokens_*.json` da PRENSA.

    Os papéis são atribuídos por MEDIÇÃO, não por ordem de declaração: a cor
    mais escura sustenta a superfície grande, a de maior croma entre as
    restantes vira o acento, e o texto recebe a cor da família que mais
    contrasta com a superfície. Ordem de declaração seria arbitrária e faria a
    mesma família render diferente conforme quem digitou primeiro.
    """
    if len(familia) < MINIMO_DA_FAMILIA:
        raise FamiliaCromaticaInsuficiente(
            f"família com {len(familia)} cor(es); o mínimo é {MINIMO_DA_FAMILIA} "
            "para sustentar duas em superfície grande"
        )

    resolvida = {nome: hex_da_cor(nome) for nome in familia}
    cores = list(resolvida.values())

    superficie = min(cores, key=_luminancia)
    restantes = [c for c in cores if c != superficie]
    acento = max(restantes, key=_croma)
    texto = max(cores, key=lambda c: contraste(c, superficie))
    # o texto nunca pode ser a própria superfície, mesmo em família de duas
    if texto == superficie:
        texto = "#FFFFFF" if _luminancia(superficie) < 0.4 else "#0B0B0F"

    return {
        "$schema": "prensa-tokens/0.1",
        "skin": identificador,
        "versao": "1.0.0",
        "familia_resolvida": resolvida,
        "fonts": [dict(f) for f in FONTES_DA_PRENSA],
        "color": {
            "surface": {"base": superficie, "container": superficie},
            "text": {
                "primary": texto,
                "secondary": texto,
                "muted": texto,
                "nota": texto,
                "on_accent": superficie,
            },
            "accent": {"text": acento, "graphic": acento, "dim": acento},
        },
        "type": {
            # ⚠️ `ink_padding` não é enfeite: `render.py:611` mede a TINTA, não a
            # caixa, e o glifo pinta fora do layout box. Toda skin do acervo
            # declara o respiro; uma gerada sem ele encosta a letra na borda da
            # área segura e a peça é recusada DEPOIS de renderizada
            # (`render.py:265` aplica o valor como padding CSS).
            #
            # O número vem de conta, não de gosto. A área de conteúdo do Inter é
            # ~1,21em (ascendente 0,969 + descendente 0,241); com `line_height`
            # 1,06 a meia-entrelinha fica NEGATIVA em (1,21 - 1,06)/2 = 0,075em,
            # e é exatamente por isso que a tinta sobe acima da caixa. 0,12em
            # cobre esse déficit com folga e escala junto com o corpo escolhido
            # pelo fitter — que é a razão de o motor exprimir isto em em e não
            # em px. Medido antes: as peças cujo frame encostava na borda
            # superior reprovavam com a tinta 3 px acima do limite.
            "display": {
                "family": "Inter",
                "weight": 800,
                "line_height": 1.06,
                "wrap": "balance",
                "tracking": "-0.02em",
                "ink_padding": "0.12em 0.05em 0.12em 0.05em",
            },
            "body": {
                "family": "Inter",
                "weight": 450,
                "line_height": 1.4,
                "ink_padding": "0.05em 0.04em 0.05em 0.04em",
            },
            "label": {
                "family": "Inter",
                "weight": 700,
                "tracking": "0.08em",
                "transform": "uppercase",
                "line_height": 1,
                "ink_padding": "0.06em 0.04em 0.06em 0.04em",
            },
        },
    }


def _runs_com_ancora(headline: str, ancoras: list[str]) -> list[dict]:
    """Parte a headline em runs, acentuando a âncora — no máximo 2 palavras.

    Casamento literal e sem diacrítico, para que "Pé-de-Meia" case com
    "pe-de-meia". As âncoras são tentadas na ordem: a canônica primeiro, depois
    os sinônimos que o OPERADOR aprovou — nunca sinônimo proposto pelo modelo,
    que tornaria a contraprova circular (`agente/contrato.py:115`).

    Âncora que não aparece na headline não inventa acento: o acento é bisturi, e
    bisturi que corta no lugar errado é pior que nenhum.
    """
    achado = alvo = None
    for candidata in ancoras:
        # o budget corta a âncora ANTES da busca: "poupança do ensino médio"
        # vira "poupança do", que é o que cabe em `resolve.py:100`.
        alvo = " ".join(str(candidata).split()[:ACCENT_MAX_PALAVRAS])
        if not alvo:
            continue
        achado = re.search(re.escape(_sem_acento(alvo)), _sem_acento(headline), re.IGNORECASE)
        if achado:
            break
    if not achado:
        return [{"text": headline}]

    i, j = achado.span()
    runs = []
    if headline[:i]:
        runs.append({"text": headline[:i]})
    runs.append({"text": headline[i:j], "accent": True})
    if headline[j:]:
        runs.append({"text": headline[j:]})
    return runs


def _nome_do_formato(largura: int, altura: int) -> str:
    razao = largura / altura
    if abs(razao - 0.8) < 0.02:
        return "feed_4x5"
    if abs(razao - 0.5625) < 0.02:
        return "story_9x16"
    if abs(razao - 1.0) < 0.02:
        return "square_1x1"
    if abs(razao - 1.91) < 0.05:
        return "wide_1_91x1"
    return f"custom_{largura}x{altura}"


def traduzir(
    spec: CreativeSpec,
    *,
    artboard: tuple[int, int],
    ancora: str | None = None,
    ancoras_aceitas: list[str] | None = None,
    asset: dict | None = None,
    tokens_file: str = "",
) -> dict:
    """Uma `CreativeSpec` e um artboard viram uma `post.spec/1.0.0`.

    `asset`, quando dado, é `{"id":…, "file":…}` de uma cena já gerada sem
    texto; sem ele a peça é campo cromático puro, que é o caso em que a PRENSA
    não depende de imagem nenhuma para existir.
    """
    largura, altura = artboard
    textos = {papel: t for papel, t in spec.texto_exato.items() if str(t).strip()}
    margem = spec.margem_segura
    plano = spec.plano_de_composicao or {}
    zona = plano.get("zona")

    if zona and asset:
        # `planos.PLANOS[*]["zona"]` é (x0,y0,x1,y1) em FRAÇÃO do canvas, e é
        # essa escolha de unidade que faz multi-formato custar uma multiplicação
        # em vez de um recorte: a mesma faixa reproporciona sozinha.
        #
        # ⚠️ Só vale HAVENDO CENA. O plano existe para desviar da foto; sem foto
        # não há o que desviar, e obedecê-lo empurra o texto para um terço e
        # deixa o resto do campo cromático vazio — foi o que o primeiro lote
        # mostrou, com 65% de azul liso embaixo das quatro peças.
        #
        # ⚠️ E a zona é RECORTADA pela área segura. As duas geometrias vêm de
        # sistemas diferentes e discordam: `faixa_superior` começa em 0.05 (54 px
        # em 1080) e `especificar` calcula margem de 7% (76 px). Medido: sem o
        # recorte o lote inteiro — 16 de 16 — reprova com "tinta fora da safe
        # area (l:54 …)", DEPOIS de renderizado. A zona é hipótese sobre onde a
        # foto está calma; a área segura é contrato com a plataforma. Cede a
        # hipótese.
        ancora_do_frame = "top_left"
        x = max(round(zona[0] * largura), margem["esquerda"])
        y = max(round(zona[1] * altura), margem["topo"])
        direita = min(round(zona[2] * largura), largura - margem["direita"])
        base = min(round(zona[3] * altura), altura - margem["base"])
        largura_da_zona = max(1, direita - x)
        altura_da_zona = max(1, base - y)
    else:
        # Tipografia pura: o bloco ancora no RODAPÉ da área segura, que é a
        # convenção das skins do acervo (kintsugi, volcnews) e o que dá peso
        # editorial — texto pendurado no topo com o resto vazio lê como erro.
        ancora_do_frame = "bottom_left"
        x = margem["esquerda"]
        y = margem["base"]
        largura_da_zona = largura - margem["esquerda"] - margem["direita"]
        altura_da_zona = altura - margem["topo"] - margem["base"]

    filhos: list[dict] = []
    if "headline" in textos:
        filhos.append({
            "id": "headline",
            "type": "text",
            "slot": "headline",
            "runs": _runs_com_ancora(
                textos["headline"],
                [a for a in [ancora, *(ancoras_aceitas or [])] if a],
            ),
            "style": {
                "font": "$type.display",
                "color": "$color.text.primary",
                "accent_color": "$color.accent.text",
            },
            # ⚠️ `auto` EXIGE overflow=fail (`resolve.py:97`): o motor prefere
            # recusar a peça a entregar headline cortada.
            "fit": {"mode": "auto", "min": 34, "max": 96,
                    "max_lines": 5, "hyphenate": False, "overflow": "fail"},
        })
    if "complemento" in textos:
        filhos.append({
            "id": "complemento",
            "type": "text",
            "slot": "body",
            "runs": [{"text": textos["complemento"]}],
            "style": {"font": "$type.body", "color": "$color.text.secondary"},
            "fit": {"mode": "auto", "min": 20, "max": 38,
                    "max_lines": 4, "overflow": "fail"},
        })
    if "cta" in textos:
        filhos.append({
            "id": "cta",
            "type": "text",
            "slot": "label",
            "runs": [{"text": textos["cta"]}],
            "style": {"font": "$type.label", "color": "$color.accent.text"},
            "fit": {"mode": "fixed", "size": 24, "max_lines": 1, "overflow": "fail"},
        })

    camadas: list[dict] = []
    if asset:
        camadas.append({
            "id": "cena",
            "type": "image",
            "asset": asset["id"],
            "box": {"x": 0, "y": 0, "w": "100%", "h": "100%"},
            "object_fit": "cover",
            "object_position": "center center",
        })
    camadas.append({
        "id": "conteudo",
        "type": "frame",
        # `_pos_css` (`render.py:69`) lê left/right e top/bottom do nome da
        # âncora, então `bottom_left` mede y a partir da base do canvas.
        "pos": {"anchor": ancora_do_frame, "x": x, "y": y},
        "max_width": largura_da_zona,
        # ⚠️ Orçamento de ALTURA do bloco, e não é opcional. `fit` por elemento
        # garante largura e nº de linhas; a altura da pilha inteira é outra
        # restrição, e sem ela o bloco cresce para baixo e a tinta sai da área
        # segura — medido no lote real: CTA em b=1286 num canvas de 1350 com
        # limite 1274. `render.py:571` encolhe os filhos `auto` até caber.
        "zona_h": altura_da_zona,
        "layout": {"mode": "vertical", "gap": 22},
        "children": filhos,
    })

    post: dict = {
        "schema_version": "post.spec/1.0.0",
        "spec_id": f"{spec.creative_ref}_{largura}x{altura}",
        "seed": 11,
        "skin": {
            "id": "VOS:familia",
            "versao": "1.0.0",
            "tokens_file": tokens_file or "tokens_familia.json",
        },
        "brand": {"cliente": "volc", "handle": ""},
        "pauta": {"tema": spec.angulo, "nicho": "", "idioma": "pt-BR"},
        "artboard": {
            "base": {
                "w": largura,
                "h": altura,
                "formato": _nome_do_formato(largura, altura),
                "color_profile": "srgb",
            },
            "safe_area": {
                "top": spec.margem_segura["topo"],
                "bottom": spec.margem_segura["base"],
                "left": spec.margem_segura["esquerda"],
                "right": spec.margem_segura["direita"],
            },
        },
        "gates": {
            "accent_budget": {"max_palavras": ACCENT_MAX_PALAVRAS},
            "contrast_min": 4.5,
            "contrast_min_large": 3.0,
            "clearance_decorativo_px": 16,
        },
        "slides": [{
            "id": "unico",
            "background": "$color.surface.base",
            "layers": camadas,
        }],
    }
    if asset:
        post["assets"] = [{
            "id": asset["id"],
            "kind": asset.get("kind", "photo_ia"),
            "file": asset["file"],
            "ia_gerada": asset.get("ia_gerada", True),
        }]
        # colocação auto: o motor MEDE a foto e escolhe a zona, em vez de
        # confiar que o modelo obedeceu ao plano. `resolve.py` sobrescreve a
        # `pos` do frame com a medida — a zona acima é a hipótese, não a lei.
        post["colocacao"] = {
            "modo": "auto",
            "asset": asset["id"],
            "frame": "conteudo",
            "alvo_contraste": 4.5,
        }
    return post


def traduzir_lote(
    spec: CreativeSpec,
    formatos: list[tuple[int, int]],
    *,
    ancora: str | None = None,
    ancoras_aceitas: list[str] | None = None,
    asset_por_formato: dict[tuple[int, int], dict] | None = None,
    tokens_file: str = "",
) -> list[dict]:
    """Uma decisão criativa, N artboards, N specs inteiras.

    ⚠️ Não existe caminho de um render só: ver o cabeçalho deste módulo. Cada
    formato paga um resolve e um render, e recebe em troca composição nativa —
    a alternativa medida (recortar o 4x5) preserva 42% da imagem e decapita
    headline e CTA, porque texto vive nas bordas que a tesoura corta.
    """
    assets = asset_por_formato or {}
    return [
        traduzir(spec, artboard=formato, ancora=ancora,
                 ancoras_aceitas=ancoras_aceitas,
                 asset=assets.get(formato), tokens_file=tokens_file)
        for formato in formatos
    ]


# ── leitores da spec traduzida ───────────────────────────────────────────────
# Existem para que o teste (e quem depurar um lote) leiam a spec pelo mesmo
# caminho, em vez de cada um decorar o aninhamento de `slides[0].layers`.

def frame_de(post: dict) -> dict:
    return next(c for c in post["slides"][0]["layers"] if c["id"] == "conteudo")


#: alias interno, para os leitores abaixo lerem melhor
_frame = frame_de


def camadas_de_texto(post: dict) -> list[dict]:
    return [c for c in _frame(post)["children"] if c["type"] == "text"]


def runs_da_headline(post: dict) -> list[dict]:
    return next(c["runs"] for c in camadas_de_texto(post) if c["id"] == "headline")


def headline_de(post: dict) -> str:
    return "".join(run["text"] for run in runs_da_headline(post))


def textos_de(post: dict) -> dict[str, str]:
    papeis = {"headline": "headline", "complemento": "complemento", "cta": "cta"}
    return {
        papeis[c["id"]]: "".join(r["text"] for r in c["runs"])
        for c in camadas_de_texto(post)
        if c["id"] in papeis
    }


def zona_em_pixels(post: dict) -> dict[str, int]:
    frame = _frame(post)
    return {"x": frame["pos"]["x"], "y": frame["pos"]["y"], "w": frame["max_width"]}
