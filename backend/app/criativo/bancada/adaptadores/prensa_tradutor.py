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

#: Corpo, padding e raio do botão de CTA. São daqui, e é por isso que a altura
#: dele é CONTÁVEL em vez de medida no navegador: nada disto vem de fora.
CTA_CORPO_PX = 24
CTA_PADDING_V = 16
CTA_PADDING_H = 28
CTA_RAIO = 8
#: padding em cima e embaixo + corpo + o respiro de tinta do próprio rótulo.
ALTURA_DO_BOTAO = 2 * CTA_PADDING_V + CTA_CORPO_PX + 4
#: distância entre o botão e a base do bloco de texto.
RESPIRO_DO_BOTAO = 24

#: A sobrancelha, pelo mesmo raciocínio: corpo fixo e respiro de tinta escolhidos
#: aqui, logo altura contável. Reservar o espaço dela e NÃO descontá-lo do
#: orçamento do bloco é reservar no papel — o bloco sobe por cima assim mesmo.
ALTURA_DO_KICKER = 24 + 16
RESPIRO_DO_KICKER = 32

#: Teto do corpo da headline, em fração da LARGURA do artboard. Largura e não
#: altura porque é ela que governa quantos caracteres cabem na linha — e é a
#: linha, não a altura do quadro, que decide se a headline respira.
#:
#: ⚠️ Era constante 96 px, e o sintoma foi óbvio quando a campanha inteira saiu
#: com 95 px de headline em 1080x1080, 1080x1920 e 1200x628: três proporções
#: diferentes batendo no mesmo teto é um teto que não decidiu nada.
TETO_DA_HEADLINE = 0.11
#: `tipografia_protagonista` e `cartaz_beneficio` existem para a letra dominar o
#: quadro. Com o teto do editorial a peça sai com a headline no rodapé e dois
#: terços de campo vazio — a rota negada pela própria escala.
TETO_PROTAGONISTA = 0.165
PISO_DA_HEADLINE = 0.035

#: Rotas e registros em que a tipografia é o assunto, e não o veículo dele.
PROTAGONISTAS = frozenset({"tipografia_protagonista", "cartaz_beneficio"})

#: Acima desta fração de um eixo a zona deixa de ser "faixa reservada" e passa a
#: atravessar o quadro — e então não diz nada sobre onde o sujeito está.
FAIXA_MAXIMA = 0.6

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


def _mistura(frente: str, fundo: str, fracao: float) -> str:
    """Uma cor a `fracao` do caminho entre o fundo e a frente.

    Réguas, fios e trilhos precisam ficar ENTRE o papel e a tinta: em cima do
    papel somem, na cor da tinta competem com a letra. Derivar da própria
    família mantém a peça numa paleta só sem inventar um cinza de fora dela.
    """
    def canais(c):
        return [int(c[i:i + 2], 16) for i in (1, 3, 5)]

    f, b = canais(frente), canais(fundo)
    return "#" + "".join(f"{round(bb + (ff - bb) * fracao):02X}" for ff, bb in zip(f, b))


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
            # `tabela` pede a régua, `colunas` pede o fio, `dots` pede o par.
            # Nenhum tem default no motor: ref não resolvida vira `$...` literal
            # no CSS e a camada sai muda, sem erro nenhum.
            "linha": {"regua": _mistura(texto, superficie, 0.22),
                      "fio": _mistura(texto, superficie, 0.30),
                      "trilho": _mistura(texto, superficie, 0.18)},
            "dots": {"ativa": acento, "inativa": _mistura(texto, superficie, 0.28)},
            "ghost": acento,
        },
        # As camadas `texture` e `vinheta` referenciam estes tokens por `$`; uma
        # skin sem `efeitos` deixa a ref sem resolver e a camada sai quebrada.
        # Grão é o que costura letra de código a foto de IA: sem ele a
        # tipografia lê como adesivo colado por cima da fotografia.
        "efeitos": {
            "grao": {"opacity": 0.30, "blend": "overlay", "escala": 420,
                     "piso": -0.7, "amplitude": 3.2},
            "vinheta": {"cor": "rgba(0,0,0,0.40)", "raio": "82% 72%",
                        "centro": "50% 38%"},
            # halação: o halo que só o run ACENTUADO pinta. É o que faz a
            # âncora de desejo brilhar sem precisar de corpo maior.
            "halacao_accent": {"passes": [[12, 0.44], [34, 0.22]]},
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
            # o numeral gigante ao fundo; peso alto e entrelinha 1 porque ele é
            # mancha, não leitura.
            "ghost": {"family": "Inter", "weight": 900, "line_height": 1,
                      "tracking": "-0.04em"},
            # ⚠️ respiro MAIOR que o do display, e por conta e não por gosto: o
            # déficit de meia-entrelinha é (1,21 − line_height)/2, e com
            # line_height 1 ele vai a 0,105em contra os 0,075em do display.
            # Copiar o número do display reprovou as 21 peças da campanha com a
            # tinta 2 px acima do limite.
            "kicker": {"family": "Inter", "weight": 700, "tracking": "0.22em",
                       "transform": "uppercase", "line_height": 1,
                       "ink_padding": "0.16em 0.04em 0.16em 0.04em"},
            "label": {
                "family": "Inter",
                "weight": 700,
                "tracking": "0.08em",
                "transform": "uppercase",
                "line_height": 1,
                "ink_padding": "0.16em 0.04em 0.16em 0.04em",
            },
        },
    }


#: Tratamento tipográfico do run acentuado, por REGISTRO. O registro é decisão
#: criativa já aprovada; qual bisturi ele usa é consequência mecânica dela — a
#: mesma lógica que faz a rota decidir quem compõe a letra (`planos.py`).
TRATAMENTO_POR_REGISTRO: dict[str, dict] = {
    # vernáculo de anúncio de programa: chapa de cor e letra vazada.
    "cartaz_beneficio": {"tipo": "knockout", "cor": "$color.accent.text",
                         "cor_texto": "auto", "padding": "0.02em 0.12em 0.07em"},
    # grifo de marca-texto, para quando a peça é gráfica e a cor já trabalha.
    "grafico": {"tipo": "marcador", "cor": "$color.accent.text", "blend": "normal",
                "cor_texto": "auto", "padding": "0.03em 0.14em 0.09em",
                "radius": "0.05em"},
}


def _runs_com_ancora(headline: str, ancoras: list[str],
                     registro: str = "") -> list[dict]:
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
    destacado = {"text": headline[i:j], "accent": True}
    tratamento = TRATAMENTO_POR_REGISTRO.get(registro)
    if tratamento:
        destacado["tratamento"] = dict(tratamento)
    runs = []
    if headline[:i]:
        runs.append({"text": headline[:i]})
    runs.append(destacado)
    if headline[j:]:
        runs.append({"text": headline[j:]})
    return runs


def ancora_do_corte(zona: list | None) -> str:
    """Onde firmar o corte da foto, deduzido de onde o texto vai ficar.

    `object-fit:cover` é fixo no motor, então servir N artboards com uma imagem
    só é sempre um corte — e a única coisa que a spec controla é POR ONDE ele
    corta. Medido: uma foto 4:5 num 1.91:1 com corte centrado decapita o
    sujeito, sobrando barba e ombro.

    O plano já sabe a resposta sem que ninguém a declare: ele reservou uma faixa
    para o texto justamente porque o sujeito está do lado contrário.

    Só se inclina o eixo em que o plano de fato reserva uma FAIXA.
    `coluna_direita` ocupa 47% da largura — é faixa — e 72% da altura, que não
    é: inclinar o vertical ali seria ler intenção onde o plano não declarou
    nenhuma. Daí o piso de `FAIXA_MAXIMA`: acima disso a zona atravessa o quadro
    e aquele eixo fica centrado.
    """
    if not zona:
        return "center center"
    x0, y0, x1, y1 = zona

    def eixo(ini: float, fim: float, antes: str, depois: str) -> str:
        if (fim - ini) > FAIXA_MAXIMA:
            return "center"
        return antes if (ini + fim) / 2 < 0.5 else depois

    return f"{eixo(x0, x1, 'right', 'left')} {eixo(y0, y1, 'bottom', 'top')}"


def faixa_na_foto(
    faixa: list, artboard: tuple[int, int], foto: tuple[int, int],
    object_position: str,
) -> list:
    """Converte uma faixa em fração do QUADRO para fração da FOTO.

    Existe porque `resolve.scrim_auto` mede o arquivo de origem fatiado pela
    fração da altura dele — recebe a spec e nunca a usa, então não sabe do
    artboard nem do corte. Enquanto a foto e o quadro têm a mesma proporção isso
    é indistinguível; fora dali o engine mede pixels que ninguém vê. Numa
    entrega 1.91:1 com corte no topo, a faixa 0.58→0.73 do quadro cai em
    0.24→0.31 da foto: o rosto claro, e não o fundo escuro. O selo sairia
    otimista, que é o pior erro possível num portão de contraste.

    A conta é a do `object-fit: cover`: escala pelo maior fator, e o resto do
    lado que sobra é cortado conforme o `object-position`.
    """
    largura_q, altura_q = artboard
    largura_f, altura_f = foto
    if not (largura_f and altura_f):
        return faixa
    escala = max(largura_q / largura_f, altura_q / altura_f)
    janela = altura_q / escala          # altura da foto que cabe no quadro, em px da foto
    sobra = max(0.0, altura_f - janela)
    vertical = object_position.split()[-1] if object_position else "center"
    topo = {"top": 0.0, "bottom": sobra}.get(vertical, sobra / 2)
    return [round((topo + f * janela) / altura_f, 4) for f in faixa]


def _tem_chapa(runs: list[dict]) -> bool:
    """Algum run já está vazado ou grifado sobre uma superfície de cor?"""
    return any((r.get("tratamento") or {}).get("tipo") in {"knockout", "marcador"}
               for r in runs)


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
    botao: bool = False,
    kicker: str | None = None,
    ghost: str | None = None,
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
    tem_botao = botao and bool(str(spec.texto_exato.get("cta") or "").strip())
    protagonista = PROTAGONISTAS & {
        str(spec.direcao_de_arte.get("rota_de_texto") or ""),
        str(spec.direcao_de_arte.get("registro") or ""),
    }
    teto = TETO_PROTAGONISTA if protagonista else TETO_DA_HEADLINE
    reserva_de_rodape = (ALTURA_DO_BOTAO + RESPIRO_DO_BOTAO) if tem_botao else 0
    reserva_de_topo = (ALTURA_DO_KICKER + RESPIRO_DO_KICKER) if kicker else 0

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
        y = max(round(zona[1] * altura), margem["topo"] + reserva_de_topo)
        direita = min(round(zona[2] * largura), largura - margem["direita"])
        base = min(round(zona[3] * altura), altura - margem["base"] - reserva_de_rodape)
        largura_da_zona = max(1, direita - x)
        altura_da_zona = max(1, base - y)
    else:
        # Tipografia pura: o bloco ancora no RODAPÉ da área segura, que é a
        # convenção das skins do acervo (kintsugi, volcnews) e o que dá peso
        # editorial — texto pendurado no topo com o resto vazio lê como erro.
        ancora_do_frame = "bottom_left"
        x = margem["esquerda"]
        y = margem["base"] + reserva_de_rodape
        largura_da_zona = largura - margem["esquerda"] - margem["direita"]
        altura_da_zona = (altura - margem["topo"] - margem["base"]
                          - reserva_de_rodape - reserva_de_topo)

    # A faixa onde a letra realmente vive, em fração da altura — é ela que o
    # scrim vai medir. Com âncora inferior o bloco cresce para cima a partir da
    # base, então a faixa é o trecho de baixo do canvas.
    if ancora_do_frame == "bottom_left":
        faixa_texto = [round(1 - (y + altura_da_zona) / altura, 4),
                       round(1 - y / altura, 4)]
    else:
        faixa_texto = [round(y / altura, 4), round((y + altura_da_zona) / altura, 4)]

    runs_da_headline = _runs_com_ancora(
        str(textos.get("headline", "")),
        [a for a in [ancora, *(ancoras_aceitas or [])] if a],
        registro=str(spec.direcao_de_arte.get("registro") or ""),
    )

    filhos: list[dict] = []
    if "headline" in textos:
        filhos.append({
            "id": "headline",
            "type": "text",
            "slot": "headline",
            "runs": runs_da_headline,
            "style": {
                "font": "$type.display",
                "color": "$color.text.primary",
                "accent_color": "$color.accent.text",
            },
            # ⚠️ Só quando o acento é letra SOLTA. `halacao` sopra a cor do
            # acento para fora do glifo; com o acento já vazado de uma chapa
            # (`knockout`) ou grifado (`marcador`), o sopro cai DENTRO da chapa
            # e embarra a letra em vez de destacá-la — visto em `quem fica de
            # fora`, que saiu com fumaça marrom por cima do ouro. Só um dos dois
            # pode ganhar aquele pixel.
            **({} if _tem_chapa(runs_da_headline) else
               {"efeitos": {"halacao": "$efeitos.halacao_accent"}}),
            # ⚠️ `auto` EXIGE overflow=fail (`resolve.py:97`): o motor prefere
            # recusar a peça a entregar headline cortada.
            "fit": {"mode": "auto",
                    "min": round(largura * PISO_DA_HEADLINE),
                    "max": round(largura * teto),
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
    if "cta" in textos and botao:
        pass  # o botão é camada de TOPO — montado abaixo, fora do bloco
    if "cta" in textos and not botao:
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
        corte = asset.get("object_position") or ancora_do_corte(zona)
        # ⚠️ `object_fit`/`box` do spec são IGNORADOS — `render.py` fixa
        # `object-fit:cover` e `inset:0`. Uma foto 4:5 num artboard 9:16 é
        # CORTADA pelo motor, e é por isso que servir N formatos com uma
        # imagem só é economia real na letra e aposta no enquadramento.
        camadas.append({
            "id": asset["id"] + "_bg",
            "type": "image",
            "asset": asset["id"],
            # derivada do plano; o operador ainda pode dirigir a foto que foge à regra
            "object_position": corte,
        })
        # O SELO. `resolve.scrim_auto` mede a luminância da foto dentro de
        # `faixa_texto` (p95 Rec.709) e devolve o alpha MÍNIMO que garante o
        # contraste alvo. É a doutrina inteira num campo: a IA compõe a luz, o
        # engine sela o contraste. Gradiente cozido no prompt varia a cada run e
        # não re-resolve para outro formato; este re-mede em cada artboard.
        camadas.append({
            "id": "selo",
            "type": "scrim",
            "asset_ref": asset["id"],
            "style": {"gradient": {
                "auto": True,
                "direcao": "to top" if faixa_texto[0] > 0.4 else "to bottom",
                # derivada da zona do texto, nunca digitada solta: faixa e zona
                # divergiriam na primeira troca de plano e o engine passaria a
                # selar contraste onde não há letra. E convertida para o espaço
                # da FOTO, que é o que o `scrim_auto` de fato fatia — sem a foto
                # declarar seu tamanho, não há conversão possível e a faixa
                # passa crua, que é como o motor sempre a recebeu.
                "faixa_texto": faixa_na_foto(
                    faixa_texto, (largura, altura),
                    (asset.get("w", 0), asset.get("h", 0)), corte),
                # guardada para o recibo: é a faixa onde a letra vive NO QUADRO,
                # e a diferença entre as duas é o tamanho do corte.
                "faixa_no_quadro": faixa_texto,
                "contraste_alvo": 7.0,
                "curva": [[0, 1.0], [38, 0.95], [55, 0.45], [70, 0.0]],
            }},
        })
        camadas.append({
            "id": "vinheta",
            "type": "vinheta",
            "cor": "$efeitos.vinheta.cor",
            "raio": "$efeitos.vinheta.raio",
            "centro": "$efeitos.vinheta.centro",
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

    itens = [str(i) for i in (spec.direcao_de_arte.get("checklist") or []) if str(i).strip()]
    if itens:
        # `direcao_de_arte.checklist` já existe e já é lista — vira layout de
        # verdade. Despejado dentro do complemento viraria prosa corrida, e um
        # checklist existe justamente para ser lido item a item em meio segundo.
        camadas.append({
            "id": "checklist",
            "type": "colunas",
            "pos": {"anchor": "top_left", "x": margem["esquerda"],
                    "y": margem["topo"] + (92 if kicker else 0)},
            "w": largura - margem["esquerda"] - margem["direita"],
            "gap": 34,
            "tam_titulo": 22,
            "tam_corpo": 25,
            "style": {"font_titulo": "$type.kicker", "font_corpo": "$type.body",
                      "cor_titulo": "$color.accent.text",
                      "cor_corpo": "$color.text.secondary",
                      "cor_fio": "$color.linha.fio"},
            "colunas": [{"titulo": f"{n:02d}", "texto": item}
                        for n, item in enumerate(itens, 1)],
        })

    if kicker:
        # A sobrancelha editorial: filete de acento + rótulo em caixa alta. É a
        # mesma construção das quatro skins do acervo, e é o que dá à peça
        # registro de publicação em vez de post avulso.
        camadas.append({
            "id": "kicker_row",
            "type": "frame",
            "pos": {"anchor": "top_left", "x": margem["esquerda"],
                    "y": margem["topo"]},
            "layout": {"mode": "horizontal", "gap": 18, "align": "center"},
            "children": [
                {"id": "kicker_rule", "type": "rect", "w": 48, "h": 6,
                 "fill": "$color.accent.graphic", "radius": 0},
                {"id": "kicker", "type": "text", "slot": "kicker",
                 "runs": [{"text": kicker}],
                 "style": {"font": "$type.kicker", "color": "$color.accent.text"},
                 "fit": {"mode": "fixed", "size": 24, "max_lines": 1,
                         "overflow": "fail"}},
            ],
        })

    if ghost:
        # ⚠️ `decorative` é o que vira `data-mask` no motor. Sem a marca, o gate
        # de colisão lê o numeral como texto e reprova toda peça que tem um
        # algarismo de 400 px atrás da headline — ele é mancha, não leitura.
        camadas.append({
            "id": "ghost",
            "type": "text",
            "decorative": True,
                        # abaixo da sobrancelha quando ela existe: `clearance_decorativo_px`
            # reprova decorativo encostado em texto, e no carrossel o numeral
            # invadiu o kicker por 13 px. Quem cede é a mancha.
            "pos": {"anchor": "top_right", "x": -16,
                    "y": margem["topo"] + (96 if kicker else 0)},
            "runs": [{"text": ghost}],
            "style": {"font": "$type.ghost", "color": "$color.ghost",
                      "opacity": 0.09},
            "fit": {"mode": "fixed", "size": round(altura * 0.30), "max_lines": 1},
        })

    if tem_botao:
        # ⚠️ CAMADA DE TOPO, com `pos` próprio. `_pos_css` (`render.py:65`) emite
        # `position:absolute` para todo frame, então um frame ANINHADO sem `pos`
        # cai em `left:0;top:0` e escapa do fluxo do pai. Medido: o botão como
        # filho do bloco saltou para a origem do canvas e reprovou as quatro
        # peças com `colisão de texto: headline × cta`. Nenhuma spec do acervo
        # aninha frame em frame.
        #
        # `style.fill` é o que dá `data-mask` ao frame — é assim que o gate de
        # clearance o julga como vizinho declarado e não como tinta vazando.
        camadas.append({
            "id": "botao",
            "type": "frame",
            "pos": {"anchor": "bottom_left", "x": margem["esquerda"],
                    "y": margem["base"]},
            "style": {"fill": "$color.accent.text", "radius": CTA_RAIO,
                      "padding": f"{CTA_PADDING_V}px {CTA_PADDING_H}px"},
            "layout": {"mode": "horizontal", "gap": 0, "align": "center"},
            "children": [{
                "id": "cta",
                "type": "text",
                "slot": "label",
                "runs": [{"text": textos["cta"]}],
                "style": {"font": "$type.label", "color": "$color.text.on_accent"},
                "fit": {"mode": "fixed", "size": CTA_CORPO_PX,
                        "max_lines": 1, "overflow": "fail"},
            }],
        })

    if asset:
        # Por CIMA de tudo, inclusive da letra: é o grão que costura tipografia
        # de código a fotografia de IA. Embaixo do texto ele granula só a foto e
        # a letra continua lendo como adesivo.
        camadas.append({
            "id": "grao",
            "type": "texture",
            "opacity": "$efeitos.grao.opacity",
            "blend": "$efeitos.grao.blend",
            "escala": "$efeitos.grao.escala",
            "piso": "$efeitos.grao.piso",
            "amplitude": "$efeitos.grao.amplitude",
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
    }
    if asset:
        # ⚠️ CAMADAS DE TOPO, e não `slides`, e a escolha não é estilística.
        # `resolve.py` mede o scrim varrendo `resolvido.get("layers")` e resolve
        # a colocação automática varrendo `resolvido.get("slides")`. Os dois
        # caminhos NUNCA se encontram: uma spec com `slides` jamais tem o scrim
        # medido. Havendo cena, o scrim vence — ele SELA o contraste do texto
        # sobre a foto, enquanto a colocação apenas o desvia. `render.py:774`
        # trata `layers` de topo como lâmina única.
        post["background"] = "$color.surface.base"
        post["layers"] = camadas
        post["assets"] = [{
            "id": asset["id"],
            "kind": asset.get("kind", "photo_ia"),
            "file": asset["file"],
            "ia_gerada": asset.get("ia_gerada", True),
            "regras": ["REGRA:sem-texto-em-imagem-ia", "REGRA:scrim-e-do-engine"],
        }]
    else:
        post["slides"] = [{
            "id": "unico",
            "background": "$color.surface.base",
            "layers": camadas,
        }]
    return post


def traduzir_carrossel(
    laminas: list,
    *,
    artboard: tuple[int, int],
    ancora: str | None = None,
    ancoras_aceitas: list[str] | None = None,
    kicker: str | None = None,
    tokens_file: str = "",
) -> dict:
    """N `CreativeSpec` viram UMA spec com N lâminas — e N PNGs.

    ⚠️ Não confundir com `traduzir_lote`. Carrossel é o eixo `slides`, que o
    motor de fato tem: uma spec, um artboard, N arquivos `_sNN`
    (`render.py:879`). Multi-formato é o oposto — N specs, um PNG cada. Foi
    justamente essa confusão que o campo `variants` induziu: ele parecia dizer
    que o motor multiplicava por PROPORÇÃO, quando o que ele multiplica é
    LÂMINA.

    A paginação é contada aqui, não declarada: `dots.total` é o tamanho da
    lista e `atual` é o índice. Pedir esses dois números a quem escreve a spec
    é pedir um fato que o código já tem.
    """
    if not laminas:
        raise ValueError("carrossel sem lâmina")

    slides = []
    for indice, lamina in enumerate(laminas):
        parcial = traduzir(lamina, artboard=artboard, ancora=ancora,
                           ancoras_aceitas=ancoras_aceitas,
                           kicker=kicker if indice == 0 else None,
                           ghost=f"{indice + 1:02d}",
                           tokens_file=tokens_file)
        camadas = parcial["slides"][0]["layers"]
        camadas.append({
            "id": "dots",
            "type": "dots",
            "total": len(laminas),
            "atual": indice,
            "size": 10,
            "gap": 10,
            "cor_ativa": "$color.dots.ativa",
            "cor_inativa": "$color.dots.inativa",
            "pos": {"anchor": "bottom_right",
                    "x": parcial["artboard"]["safe_area"]["right"],
                    "y": parcial["artboard"]["safe_area"]["bottom"]},
        })
        slides.append({"id": f"s{indice + 1:02d}",
                       "background": "$color.surface.base",
                       "layers": camadas})

    post = traduzir(laminas[0], artboard=artboard, ancora=ancora,
                    ancoras_aceitas=ancoras_aceitas, tokens_file=tokens_file)
    post["spec_id"] = f"{laminas[0].creative_ref}_carrossel"
    post["slides"] = slides
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

def camadas_de(post: dict) -> list[dict]:
    """As camadas da lâmina, venha ela em `layers` de topo ou em `slides`."""
    if "layers" in post:
        return post["layers"]
    return post["slides"][0]["layers"]


def frame_de(post: dict) -> dict:
    return next(c for c in camadas_de(post) if c["id"] == "conteudo")


def botao_de(post: dict) -> dict | None:
    return next((c for c in camadas_de(post) if c["id"] == "botao"), None)


#: alias interno, para os leitores abaixo lerem melhor
_frame = frame_de


def camadas_de_texto(post: dict) -> list[dict]:
    """Os nós de texto da peça: os do bloco e o rótulo do botão, se houver."""
    achadas = [c for c in _frame(post)["children"] if c["type"] == "text"]
    alvo = botao_de(post)
    if alvo:
        achadas += [f for f in alvo["children"] if f["type"] == "text"]
    return achadas


def runs_e_fit(post: dict) -> dict:
    return next(c["fit"] for c in camadas_de_texto(post) if c["id"] == "headline")


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
