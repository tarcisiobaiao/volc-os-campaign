"""O contrato do widget: o que a LLM entrega, e o que é recusado antes de renderizar.

## Por que este módulo existe

Até 19/08/2026 a LLM escrevia o widget INTEIRO — HTML, CSS e JavaScript. Medido
na run 9 (`fgts-saque-aniversario-20260819-135623`):

- 3 widgets tentados, **1 entregue** (p5). p3 caiu por `ungrounded_legal_claim`,
  p4 nem chegou a rodar (teto de custo estourado em US$ 1,2022 de US$ 1,2000).
- US$ 0,6994 gastos em widget de um total de US$ 3,5067 na run — **20%**.
- As duas falhas não pararam no widget: `content_gate` exige o widget na página
  que o comporta, então cada falha derrubou um ARTIGO COMPLETO, já pesquisado,
  escrito, julgado, com SEO, imagem e build prontos.
- O único que passou trazia 4.098 caracteres de CSS inventado do zero, 19 cores
  arbitrárias, **1** atributo `aria-`, **zero** `role=` e nenhum
  `prefers-reduced-motion`.

Nenhum desses quatro problemas se resolve com prompt melhor. Eles são
consequência de pedir código a um gerador de texto e torcer.

## A inversão

A LLM não escreve mais código. Ela escreve **conteúdo** — este JSON. O motor
renderiza com gabarito determinístico (`render.py`) sobre um sistema de design
único (`estilo.py`). O que era sorte vira invariante:

| antes (sorte por página)          | agora (construção)                     |
|-----------------------------------|----------------------------------------|
| allowlist de tags/atributos       | o markup é nosso e constante           |
| `grid-area` presente              | o gabarito sempre empilha em grid      |
| sem `&` no script                 | o script é nosso, escrito uma vez      |
| `visibility`, nunca `display`     | idem                                   |
| a11y ao acaso                     | rótulo, foco e `aria-live` no gabarito |
| CSS reinventado a cada página     | um CSS, quatro arquétipos              |

## O que ESTE arquivo garante

Que o conteúdo tem substância. O gabarito impede widget quebrado; só o contrato
impede widget VAZIO — e vazio foi um modo de falha real: `widget_p5` marcou
`OK` num bloco de 354 caracteres que era uma lista de dois itens. O sanitizador
não reclamou porque ele só sabe dizer o que é proibido, nunca o que é exigido.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

# ── os arquétipos que EXISTEM ────────────────────────────────────────────────
#
# ⚠️ Quatro, não nove. `ENGAJAMENTO_PARA_ARQUETIPO` em `pipeline/steps.py` é a
# única porta de entrada, e ela mapeia quatro rótulos de engajamento. O prompt
# antigo descrevia NOVE arquétipos em 116 linhas: cinco catálogos completos
# viajavam em cada chamada sem poder ser escolhidos — token pago por opção
# inalcançável, e ruído para o modelo escolher dentro.
#
# Se um dia o motor de pautas passar a emitir um quinto engajamento, o mapa lá
# e este dicionário aqui têm de crescer juntos — a prova
# `test_arquetipos_batem_com_o_mapa_do_pipeline` falha se divergirem.

#: `chave` → (nome de exibição, rótulo do controle, quantos controles aceita)
ARQUETIPOS: dict[str, dict[str, object]] = {
    "roteador": {
        "nome": "Roteador de Elegibilidade",
        "eyebrow": "responda e veja o seu caminho",
        # Duas perguntas categóricas classificam sem virar formulário. Três já
        # produzem 27 combinações e o leitor abandona antes do resultado.
        "min_controles": 1, "max_controles": 2,
        "forma": "select",
    },
    "navegador": {
        "nome": "Navegador de Jornada",
        "eyebrow": "em que etapa você está",
        "min_controles": 1, "max_controles": 1,
        "forma": "select",
    },
    "comparador": {
        "nome": "Comparador de Rotas",
        "eyebrow": "compare os caminhos",
        # Botões: as rotas são poucas e nomeadas, e ver os nomes lado a lado É
        # a comparação. Escondê-las dentro de um `select` mata a peça.
        "min_controles": 1, "max_controles": 1,
        "forma": "botoes",
    },
    "diagnostico": {
        "nome": "Diagnóstico de Recusa",
        "eyebrow": "o que aconteceu com você",
        "min_controles": 1, "max_controles": 1,
        "forma": "select",
    },
}

#: Tons semânticos. O tom NUNCA é o único portador de sentido — o gabarito
#: sempre imprime o rótulo do chip em texto ao lado da cor (regra WCAG
#: `color-not-only`), e é por isso que `chip` é obrigatório em todo cenário.
TONS = frozenset({"neutro", "ok", "atencao", "risco"})

#: Tetos de conteúdo. Não são estética: o widget divide a tela com anúncio, e
#: um cenário de 900 caracteres empurra a dobra e come viewability.
MAX_TITULO = 90
MAX_SUBTITULO = 160
MAX_CHIP = 28
MAX_CORPO = 420
MAX_PASSO = 140
MAX_ITEM = 120
MAX_OPCAO = 60
MAX_RODAPE = 240


def chave_por_nome(nome: str) -> str | None:
    """`"Diagnóstico de Recusa"` → `"diagnostico"`.

    `ENGAJAMENTO_PARA_ARQUETIPO` no pipeline fala por NOME de exibição — é o
    vocabulário do motor de pautas e de todas as runs já gravadas. O motor de
    widgets fala por chave. Esta função é a única ponte entre os dois, e
    `test_arquetipos_batem_com_o_mapa_do_pipeline` garante que ela nunca fique
    sem resposta.
    """
    for chave, spec in ARQUETIPOS.items():
        if spec["nome"] == nome:
            return chave
    return None


class WidgetInvalido(ValueError):
    """O JSON não descreve um widget publicável.

    Carrega os motivos em `motivos` — cada um é uma frase acionável, porque ela
    volta para o modelo na retentativa. "Inválido" sozinho não conserta nada.
    """

    def __init__(self, *motivos: str):
        self.motivos = list(motivos)
        super().__init__(" · ".join(motivos))


@dataclass(frozen=True)
class Opcao:
    """Uma escolha possível dentro de um controle."""
    valor: str
    texto: str


@dataclass(frozen=True)
class Controle:
    """A pergunta que o leitor responde."""
    id: str
    rotulo: str
    opcoes: list[Opcao]


@dataclass(frozen=True)
class Lista:
    """Um agrupamento nomeado dentro do cenário — prós, contras, cuidados."""
    rotulo: str
    itens: list[str]


#: Quanto um cenário pode ser MAIOR que o menor irmão, em peso de conteúdo.
#:
#: ⚠️ ISTO NÃO É ESTÉTICA — É O BURACO BRANCO.
#:
#: Todos os cenários ocupam a MESMA célula do grid (é o que dá CLS zero), então
#: o container tem sempre a altura do MAIOR. Quando o leitor escolhe um cenário
#: curto, a diferença vira área vazia; e a altura reservada empurra o anúncio de
#: baixo o tempo todo, não só na troca.
#:
#: Medido em 19/08/2026 na p4 publicada: os cenários iam de 207px a 864px —
#: 4,2×. Escolher "saldo insuficiente" deixava 657px de branco no meio do
#: artigo. Na p3, que ficou entre 368 e 413px (1,1×), o efeito não existe.
#:
#: 2,0 é folgado de propósito: aperta o caso patológico sem obrigar o modelo a
#: escrever cenários artificialmente iguais.
RAZAO_MAXIMA_DE_PESO = 2.0


@dataclass(frozen=True)
class Cenario:
    """Um resultado PRÉ-RENDERIZADO.

    `quando` mapeia id-do-controle → valor. Todos os cenários são impressos no
    HTML e empilhados na mesma célula de grid; o JavaScript só troca qual está
    visível. É daí que sai o CLS zero — não há para onde o anúncio se mover.

    `padrao=True` marca o cenário coringa: ele responde por qualquer combinação
    que os outros não cobrirem. Sem ele, uma combinação esquecida deixaria o
    leitor olhando para um vazio depois de responder.
    """
    chip: str
    tom: str
    titulo: str
    corpo: str
    quando: dict[str, str] = field(default_factory=dict)
    passos: list[str] = field(default_factory=list)
    listas: list[Lista] = field(default_factory=list)
    padrao: bool = False

    @property
    def peso(self) -> int:
        """Aproximação da ALTURA que este cenário vai ocupar, em caracteres.

        Não é medida de pixel — é a única coisa que dá para saber sem navegador.
        Os multiplicadores saem da geometria do gabarito: cada passo é uma linha
        com marcador (~90 caracteres de altura equivalente), cada item de lista
        pesa menos (~70), e cada lista traz um rótulo próprio (~60).

        Calibrado contra as alturas medidas em 19/08/2026 na p4 publicada, onde
        207px e 864px de conteúdo real produziram razão 4,2× — a mesma ordem de
        grandeza que este peso devolve para aqueles cenários.
        """
        return (len(self.corpo)
                + 90 * len(self.passos)
                + 60 * len(self.listas)
                + 70 * sum(len(l.itens) for l in self.listas))

    @property
    def forma_do_conteudo(self) -> tuple[bool, bool]:
        """(tem passos, tem listas) — a SILHUETA do cenário.

        Dois cenários com silhuetas diferentes têm alturas muito diferentes por
        construção, e é isso que produz o buraco branco. Exigir a mesma silhueta
        é mais fácil de o modelo obedecer do que "escreva textos do mesmo
        tamanho", e resolve a maior parte da variação.
        """
        return (bool(self.passos), bool(self.listas))


@dataclass(frozen=True)
class Widget:
    """O widget inteiro, já validado. `render.py` só sabe imprimir isto."""
    arquetipo: str
    titulo: str
    subtitulo: str
    controles: list[Controle]
    cenarios: list[Cenario]
    rodape: str = ""

    @property
    def nome_do_arquetipo(self) -> str:
        return str(ARQUETIPOS[self.arquetipo]["nome"])

    @property
    def forma(self) -> str:
        return str(ARQUETIPOS[self.arquetipo]["forma"])


# ── leitura tolerante do que o modelo devolveu ───────────────────────────────

_CERCA_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def _texto(v: object) -> str:
    """Normaliza qualquer coisa vinda do JSON para um texto limpo de uma linha.

    Colapsa espaço e remove controles: o gabarito imprime dentro de HTML, e uma
    quebra de linha crua no meio de um `<span>` não quebra nada, mas suja o
    diff e o teste de comprimento.
    """
    if v is None:
        return ""
    s = str(v)
    s = "".join(c for c in s if unicodedata.category(c)[0] != "C" or c in "\t\n")
    return re.sub(r"\s+", " ", s).strip()


def _lista_de_textos(v: object, limite: int) -> list[str]:
    if not isinstance(v, list):
        return []
    saida = []
    for item in v:
        t = _texto(item)
        if t:
            saida.append(t[:limite])
    return saida


def ler(bruto: str) -> Widget:
    """Lê o JSON do modelo e devolve um `Widget` válido — ou levanta.

    Tolerante na FORMA (cerca de markdown, texto em volta, campo faltando que
    tenha padrão sensato) e rígida na SUBSTÂNCIA (quantos cenários, quanto
    conteúdo, cobertura das combinações). É essa assimetria que evita as duas
    falhas conhecidas: rejeitar por uma crase, e aceitar uma lista de dois itens.
    """
    texto = _CERCA_RE.sub("", (bruto or "").strip())
    # O modelo às vezes prefacia ("Aqui está o widget:"). Pega do primeiro `{`
    # ao último `}` em vez de recusar — recusar aqui custa uma retentativa
    # inteira por um problema que não é de conteúdo.
    i, j = texto.find("{"), texto.rfind("}")
    if i == -1 or j <= i:
        raise WidgetInvalido("A resposta não contém um objeto JSON.")
    try:
        dados = json.loads(texto[i:j + 1])
    except json.JSONDecodeError as exc:
        raise WidgetInvalido(f"JSON malformado: {exc.msg} (linha {exc.lineno}).") from exc
    if not isinstance(dados, dict):
        raise WidgetInvalido("O JSON não é um objeto.")
    return _montar(dados)


def _montar(d: dict) -> Widget:
    motivos: list[str] = []

    arquetipo = _texto(d.get("arquetipo")).lower()
    if arquetipo not in ARQUETIPOS:
        raise WidgetInvalido(
            f"`arquetipo` deve ser um de {sorted(ARQUETIPOS)} — veio {arquetipo!r}.")
    spec = ARQUETIPOS[arquetipo]

    titulo = _texto(d.get("titulo"))[:MAX_TITULO]
    if not titulo:
        motivos.append("`titulo` está vazio.")
    subtitulo = _texto(d.get("subtitulo"))[:MAX_SUBTITULO]

    # ── controles ────────────────────────────────────────────────────────────
    controles: list[Controle] = []
    vistos: set[str] = set()
    for i, c in enumerate(d.get("controles") or []):
        if not isinstance(c, dict):
            continue
        cid = _identificador(_texto(c.get("id")) or f"c{i + 1}")
        if cid in vistos:
            cid = f"{cid}{i + 1}"
        vistos.add(cid)
        rotulo = _texto(c.get("rotulo"))
        opcoes: list[Opcao] = []
        valores: set[str] = set()
        for k, o in enumerate(c.get("opcoes") or []):
            if isinstance(o, dict):
                valor, txt = _texto(o.get("valor")), _texto(o.get("texto"))
            else:
                valor, txt = "", _texto(o)
            valor = _identificador(valor or txt or f"o{k + 1}")
            if valor in valores:
                continue
            valores.add(valor)
            if txt:
                opcoes.append(Opcao(valor=valor, texto=txt[:MAX_OPCAO]))
        if not rotulo:
            motivos.append(f"O controle {cid} está sem `rotulo` — o leitor não "
                           "saberia o que está respondendo.")
        # Uma opção só não é escolha; é uma afirmação com cara de pergunta.
        if len(opcoes) < 2:
            motivos.append(f"O controle {cid} tem {len(opcoes)} opção(ões); o "
                           "mínimo é 2, senão não há o que escolher.")
        controles.append(Controle(id=cid, rotulo=rotulo[:MAX_OPCAO * 2], opcoes=opcoes))

    minc, maxc = int(spec["min_controles"]), int(spec["max_controles"])  # type: ignore[call-overload]
    if not (minc <= len(controles) <= maxc):
        motivos.append(f"O arquétipo {spec['nome']} aceita de {minc} a {maxc} "
                       f"controle(s); vieram {len(controles)}.")

    # ── cenários ─────────────────────────────────────────────────────────────
    cenarios: list[Cenario] = []
    for i, s in enumerate(d.get("cenarios") or []):
        if not isinstance(s, dict):
            continue
        chip = _texto(s.get("chip"))[:MAX_CHIP]
        tom = _texto(s.get("tom")).lower() or "neutro"
        if tom not in TONS:
            tom = "neutro"
        c_titulo = _texto(s.get("titulo"))[:MAX_TITULO]
        corpo = _texto(s.get("corpo"))[:MAX_CORPO]
        passos = _lista_de_textos(s.get("passos"), MAX_PASSO)[:5]
        listas: list[Lista] = []
        for lst in (s.get("listas") or []):
            if not isinstance(lst, dict):
                continue
            r, itens = _texto(lst.get("rotulo")), _lista_de_textos(lst.get("itens"), MAX_ITEM)[:5]
            if r and itens:
                listas.append(Lista(rotulo=r[:MAX_CHIP], itens=itens))
        quando = {}
        for k, v in (s.get("quando") or {}).items():
            quando[_identificador(_texto(k))] = _identificador(_texto(v))

        # ⚠️ O portão contra o widget-fantasma. `widget_p5` marcou OK num bloco
        # de 354 caracteres — uma `<ul>` com dois itens. Um cenário sem chip,
        # sem título e sem corpo é exatamente isso, e ele NÃO entra.
        if not chip or not c_titulo:
            motivos.append(f"O cenário {i + 1} está sem `chip` ou sem `titulo`.")
            continue
        if not corpo and not passos and not listas:
            motivos.append(f"O cenário {i + 1} ({chip}) não tem `corpo`, `passos` "
                           "nem `listas` — seria um resultado em branco.")
            continue
        cenarios.append(Cenario(chip=chip, tom=tom, titulo=c_titulo, corpo=corpo,
                                quando=quando, passos=passos, listas=listas,
                                padrao=bool(s.get("padrao"))))

    if len(cenarios) < 2:
        motivos.append(f"Vieram {len(cenarios)} cenário(s) válido(s); o mínimo é 2 "
                       "— com um só, a interação não muda nada na tela.")

    motivos += _equilibrio(cenarios)
    motivos += _sem_urls(cenarios, _texto(d.get("rodape")))

    motivos += _cobertura(controles, cenarios)

    if motivos:
        raise WidgetInvalido(*motivos)

    return Widget(arquetipo=arquetipo, titulo=titulo, subtitulo=subtitulo,
                  controles=controles, cenarios=cenarios,
                  rodape=_texto(d.get("rodape"))[:MAX_RODAPE])


_URL_RE = re.compile(r"https?://|www\.", re.I)
_CITACAO_RE = re.compile(r"\[[^\]]{2,60}\]\s*\(")


def _sem_urls(cenarios: list[Cenario], rodape: str) -> list[str]:
    """O widget não é lugar de URL. Nenhuma.

    ⚠️ Visto na regeração de 19/08/2026: o modelo escreveu
    `[Caixa Econômica Federal] (https://www.caixa.gov.br)` dentro do corpo de um
    cenário. O gabarito escapa tudo que recebe — corretamente, senão o modelo
    poderia injetar markup —, então aquilo apareceu ao leitor como texto cru,
    colchetes e parênteses inclusive.

    A tentação é converter em `<a>`. Seria errado por dois motivos: a allowlist
    do sanitizador não tem `<a>` (link em bloco raw é vetor de vazamento do
    clique comprado), e a citação da fonte é trabalho do ARTIGO, que já a faz em
    prosa com o canal que a pesquisa verificou. Duplicar a fonte dentro do
    widget não acrescenta procedência; acrescenta ruído.

    Então a regra é simples e absoluta: nenhuma URL, nenhuma citação em
    colchetes. Diga "segundo a Caixa" e pronto.
    """
    sujos: list[str] = []
    for c in cenarios:
        alvo = " ".join([c.titulo, c.corpo, *c.passos,
                         *(i for l in c.listas for i in l.itens)])
        if _URL_RE.search(alvo) or _CITACAO_RE.search(alvo):
            sujos.append(c.chip)
    if _URL_RE.search(rodape) or _CITACAO_RE.search(rodape):
        sujos.append("rodapé")
    if not sujos:
        return []
    return [f"Há URL ou citação entre colchetes em: {', '.join(sujos[:5])}. O "
            f"widget não pode conter endereço de site nem `[texto](link)` — isso "
            f"aparece como texto cru para o leitor. Escreva \"segundo a Caixa\" "
            f"em vez de \"[Caixa] (https://...)\"; a citação da fonte é trabalho "
            f"do artigo, não do widget."]


def _equilibrio(cenarios: list[Cenario]) -> list[str]:
    """Cenários de tamanhos muito diferentes produzem o BURACO BRANCO.

    Todos ocupam a mesma célula do grid — é daí que vem o CLS zero —, então o
    container tem sempre a altura do maior. Um cenário curto escolhido pelo
    leitor deixa a diferença em branco no meio do artigo, e a altura reservada
    empurra o anúncio de baixo o tempo todo.

    Medido em 19/08/2026 na p4 publicada: de 207px a 864px, 4,2×. A p3, entre
    368 e 413px, não tinha o problema.

    As duas regras abaixo atacam causas diferentes. A SILHUETA (um cenário tem
    passos, o irmão não) é a que produz as diferenças grandes e é trivial de
    corrigir. O PESO pega o resto — texto muito mais longo num cenário só.
    """
    reais = [c for c in cenarios if c.peso > 0]
    if len(reais) < 2:
        return []

    motivos: list[str] = []

    formas = {c.forma_do_conteudo for c in reais}
    if len(formas) > 1:
        com_passos = [c.chip for c in reais if c.passos]
        sem_passos = [c.chip for c in reais if not c.passos]
        com_listas = [c.chip for c in reais if c.listas]
        detalhe = []
        if com_passos and sem_passos:
            detalhe.append(f"com `passos`: {', '.join(com_passos[:4])}; "
                           f"sem: {', '.join(sem_passos[:4])}")
        if com_listas and len(com_listas) != len(reais):
            detalhe.append(f"só {', '.join(com_listas[:4])} tem `listas`")
        motivos.append(
            "Os cenários não têm a mesma forma — " + " · ".join(detalhe) + ". "
            "Todos precisam da MESMA combinação de `corpo`/`passos`/`listas`, "
            "senão uns ficam muito mais altos que os outros e sobra área em "
            "branco na página.")

    magro, gordo = min(reais, key=lambda c: c.peso), max(reais, key=lambda c: c.peso)
    razao = gordo.peso / max(magro.peso, 1)
    if razao > RAZAO_MAXIMA_DE_PESO:
        motivos.append(
            f"O cenário \"{gordo.chip}\" é {razao:.1f}× maior que \"{magro.chip}\" "
            f"({gordo.peso} contra {magro.peso}). Deixe todos com volume "
            f"parecido — o limite é {RAZAO_MAXIMA_DE_PESO:.0f}×. Encurte o maior "
            f"ou desenvolva o menor.")

    return motivos


def _cobertura(controles: list[Controle], cenarios: list[Cenario]) -> list[str]:
    """Toda combinação de respostas tem de levar a ALGUM cenário.

    Um leitor que responde e não vê nada é pior que um artigo sem widget: ele
    conclui que a página está quebrada. Um cenário `padrao` resolve tudo de uma
    vez; sem ele, exigimos o produto cartesiano completo e dizemos QUAIS
    combinações faltam — a retentativa precisa da lista, não do veredito.
    """
    if any(c.padrao for c in cenarios):
        return []
    if not controles or any(not c.opcoes for c in controles):
        return []

    cobertas = set()
    for s in cenarios:
        chave = tuple(s.quando.get(c.id, "") for c in controles)
        cobertas.add(chave)

    faltando = []
    for combo in _produto([[o.valor for o in c.opcoes] for c in controles]):
        if tuple(combo) not in cobertas:
            faltando.append(" + ".join(f"{c.id}={v}" for c, v in zip(controles, combo)))

    if not faltando:
        return []
    amostra = ", ".join(faltando[:6]) + ("…" if len(faltando) > 6 else "")
    return [f"{len(faltando)} combinação(ões) de respostas não levam a nenhum "
            f"cenário: {amostra}. Cubra todas, ou marque UM cenário com "
            '`"padrao": true` para responder pelas que sobrarem.']


def _produto(listas: list[list[str]]) -> list[list[str]]:
    saida: list[list[str]] = [[]]
    for l in listas:
        saida = [acc + [v] for acc in saida for v in l]
    return saida


_NAO_IDENT_RE = re.compile(r"[^a-z0-9]+")


def _identificador(bruto: str) -> str:
    """Texto livre → chave estável para `data-*` e para o JavaScript.

    Sem acento, sem espaço, sem aspas. O valor vai parar dentro de um atributo
    HTML e de uma comparação de string no script; qualquer um dos três quebraria
    o widget de um jeito que só apareceria no navegador do leitor.
    """
    s = unicodedata.normalize("NFKD", (bruto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _NAO_IDENT_RE.sub("-", s).strip("-")
    return s[:40] or "x"
