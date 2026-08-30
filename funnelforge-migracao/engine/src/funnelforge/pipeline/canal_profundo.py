"""Domínio-raiz → a PÁGINA que o leitor precisa abrir.

## O defeito que este módulo existe para consertar

Medido em 19/08/2026 no funil FGTS publicado: **22 de 23 links externos eram
domínio-raiz.** "página de download na Google Play Store" apontava para
`play.google.com`. "tabela de limites da Caixa" apontava para `caixa.gov.br`.
O leitor que clica cai na home de uma instituição e tem de procurar sozinho —
que é exatamente o trabalho que o artigo prometeu poupar.

A causa NÃO era o `build_official_links` escolhendo mal. Era mais acima: a
pesquisa devolveu só raízes. Nas três páginas de solução, `fonte_primaria` e
`fontes` continham apenas `https://www.caixa.gov.br`, `https://www.fgts.gov.br`,
`https://play.google.com`, `https://apps.apple.com`.

E o prompt da pesquisa JÁ pedia o contrário, com todas as letras e com exemplo:
"URL EXATA (nunca o portal generico)". O modelo ignorou nas três. É a mesma
lição do `&` proibido no widget — instrução sozinha não sustenta invariante.

## Como isto resolve

Mecanicamente: abre a raiz num navegador de verdade, lê os links internos, e
escolhe o que melhor casa com os termos do tema da página. Foi o método que
achou, à mão, `…/fgts/saque-FGTS/Paginas/default.aspx#saque-aniversario` —
enquanto a URL que eu havia SUPOSTO para a mesma coisa devolvia 404.

⚠️ E é por isso que a descoberta tem de ser mecânica em vez de adivinhada: uma
URL plausível e morta é pior que a raiz viva. A raiz pelo menos abre.

## O contrato

`escolher_profundo` é PURO — recebe os links já coletados e devolve o melhor.
É onde mora a decisão, e é o que os testes exercitam sem rede. Quem busca os
links é `colher_links`, isolado e substituível.

Fail-safe em toda parte: qualquer problema devolve a raiz que entrou. Um canal
oficial pior nunca vale uma página perdida.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

#: Palavras que não distinguem nada num site institucional brasileiro. Sem esta
#: poda, "saque" casa com "Fale conosco > Saque" e com o menu inteiro.
_VAZIAS = frozenset({
    "de", "da", "do", "das", "dos", "e", "o", "a", "os", "as", "em", "no", "na",
    "para", "por", "com", "um", "uma", "que", "se", "ao", "aos", "sobre", "como",
    "qual", "quais", "seu", "sua", "meu", "minha", "voce", "mais", "pelo", "pela",
    "site", "portal", "pagina", "oficial", "brasil", "gov", "www", "http", "https",
})

#: Trechos que denunciam página de serviço institucional em vez de navegação.
#: Não são obrigatórios — só ganham pontos.
_SINAIS_DE_SERVICO = ("saque", "consulta", "solicit", "simul", "aplicativo", "app",
                      "beneficio", "servico", "download", "baixe", "extrato")

#: Caminhos que nunca são o destino de um leitor com uma dúvida concreta.
_LIXO = ("/busca", "/search", "/mapa-do-site", "/sitemap", "/acessibilidade",
         "/privacidade", "/termos", "/cookie", "/login", "/webmail", "/rss",
         "/feed", "/contato", "/fale-conosco", "/ouvidoria", "/imprensa",
         "/carreiras", "/trabalhe", "javascript:", "mailto:", "tel:")


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def termos_uteis(*textos: str) -> set[str]:
    """As palavras do tema que servem para casar — sem acento, sem as vazias.

    Palavras de 3 letras ou menos saem junto: "app" seria útil, mas "faz",
    "ver" e "sim" produzem casamento com qualquer menu.
    """
    junto = _sem_acento(" ".join(t or "" for t in textos))
    palavras = re.split(r"[^a-z0-9]+", junto)
    return {p for p in palavras if len(p) > 3 and p not in _VAZIAS}


def _profundidade(url: str) -> int:
    """Quantos segmentos de caminho a URL tem. Raiz = 0."""
    try:
        return len([s for s in urlparse(url).path.split("/") if s])
    except Exception:  # noqa: BLE001
        return 0


def e_raiz(url: str) -> bool:
    """`https://www.caixa.gov.br` e `https://www.caixa.gov.br/` são raiz.

    É a marca da instituição, não a resposta a uma pergunta. Uma âncora que
    promete "a tabela de limites" e entrega isto quebra a promessa do texto.
    """
    try:
        p = urlparse(url)
        return not p.path.strip("/") and not p.query and not p.fragment
    except Exception:  # noqa: BLE001
        return False


def _mesmo_host(a: str, b: str) -> bool:
    try:
        ha = urlparse(a).netloc.lower().removeprefix("www.")
        hb = urlparse(b).netloc.lower().removeprefix("www.")
        return bool(ha) and ha == hb
    except Exception:  # noqa: BLE001
        return False


def pontuar(texto_da_ancora: str, url: str, termos: set[str],
            *, minimo_de_termos: int = 2) -> int:
    """Quanto este link responde ao tema. Maior é melhor; 0 ou menos, descarta.

    O TEXTO da âncora pesa o dobro do caminho: "Saque-aniversário" escrito por
    quem fez o site é evidência mais forte que a palavra aparecer numa pasta.
    """
    if not url or url.startswith(("javascript:", "mailto:", "tel:")):
        return -1
    caminho = _sem_acento(urlparse(url).path + " " + (urlparse(url).fragment or ""))
    if any(x in caminho for x in _LIXO):
        return -1

    do_texto = termos_uteis(texto_da_ancora)
    do_caminho = termos_uteis(caminho)

    # ⚠️ DOIS TERMOS DISTINTOS, ANTES DE QUALQUER BÔNUS.
    #
    # Medido em 19/08/2026 contra o site ao vivo: com o tema "antecipação do
    # saque-aniversário", a página `habilitacao-saque-calamidade-fgts` casava
    # UM termo — `saque` — e mesmo assim vencia, porque o bônus de
    # profundidade (+3) e o de página-de-serviço (+1) somavam mais que o
    # casamento real. Saque de CALAMIDADE num artigo sobre antecipação.
    #
    # Link específico ERRADO é pior que a raiz: a raiz é honesta sobre ser a
    # instituição; o link errado promete a resposta e entrega outra. Por isso
    # os bônus só entram depois de o casamento já estar de pé.
    # ⚠️ `minimo_de_termos` separa DUAS perguntas diferentes.
    #
    # Escolher o destino final exige 2 termos (o padrão): é o que impede
    # saque-calamidade de vencer um artigo sobre antecipação.
    #
    # Mas EXPLORAR onde procurar é outra coisa. A seção
    # `/beneficios-trabalhador/fgts/` casa só `fgts` — um termo — e é
    # justamente por dentro dela que se chega ao saque-aniversário. Aplicar o
    # rigor da escolha à exploração fazia o segundo salto morrer antes de
    # começar, e a busca voltava a errar como se tivesse um salto só.
    #
    # Permissivo sobre onde olhar; rigoroso sobre o que escolher.
    casados = termos & (do_texto | do_caminho)
    if len(casados) < minimo_de_termos:
        return 0

    pontos = 2 * len(termos & do_texto) + len(termos & do_caminho)
    # Um sinal de página de serviço desempata a favor de quem resolve.
    if any(s in caminho for s in _SINAIS_DE_SERVICO):
        pontos += 1
    # Profundidade é sinal fraco e com teto: `/a/b/c/d/e` não é melhor que
    # `/a/b` só por ser mais fundo — muitas vezes é uma notícia velha.
    pontos += min(_profundidade(url), 3)
    return pontos


def escolher_profundo(raiz: str, links: list[tuple[str, str]],
                      termos: set[str]) -> str | None:
    """O melhor link interno para o tema, ou `None` se nenhum servir.

    PURO: não abre rede. `links` é `[(texto da âncora, href absoluto)]`.
    """
    if not termos:
        return None
    melhor, melhor_pontos = None, 0
    for texto, href in links:
        if not href or not _mesmo_host(raiz, href) or e_raiz(href):
            continue
        p = pontuar(texto, href, termos)
        if p > melhor_pontos:
            melhor, melhor_pontos = href, p
    # Dois termos casados é o piso: um só casa com o menu de qualquer site.
    return melhor if melhor_pontos >= 3 else None


def colher_links(url: str, *, timeout_ms: int = 30000) -> list[tuple[str, str]]:
    """Os links internos de uma página, lidos com navegador de verdade.

    ⚠️ Navegador e não `httpx`: medido em 19/08/2026, `caixa.gov.br` devolve 302
    para uma tela de verificação anti-robô (ShieldSquare) a qualquer cliente que
    não execute JavaScript — a mesma proteção que já tinha sujado as `fontes` da
    pesquisa com uma URL de CAPTCHA.

    Devolve lista vazia em qualquer falha: sem links, quem chama fica com a raiz.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001 - sem playwright, modo degradado
        return []
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            try:
                pg = b.new_page(user_agent=ua)
                pg.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                pg.wait_for_timeout(1500)
                brutos = pg.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => [e.textContent.trim().slice(0,80), e.href])")
                return [(t, h) for t, h in brutos if h]
            finally:
                b.close()
    except Exception:  # noqa: BLE001 - descoberta é best-effort, nunca fatal
        return []


def melhores(raiz: str, links: list[tuple[str, str]], termos: set[str],
             *, quantos: int = 3) -> list[str]:
    """Os `quantos` links internos mais promissores, do melhor para o pior.

    Serve ao segundo salto: a página certa quase nunca está pendurada na home,
    mas a SEÇÃO dela está.
    """
    pontuados: list[tuple[int, str]] = []
    vistos: set[str] = set()
    for texto, href in links:
        if not href or not _mesmo_host(raiz, href) or e_raiz(href) or href in vistos:
            continue
        p = pontuar(texto, href, termos, minimo_de_termos=1)
        if p > 0:
            vistos.add(href)
            pontuados.append((p, href))
    pontuados.sort(key=lambda x: -x[0])
    return [u for _, u in pontuados[:quantos]]


def aprofundar(raiz: str, termos: set[str], *, verificar=None,
               colher=colher_links, saltos: int = 2) -> str:
    """A porta de entrada: devolve a página profunda, ou a própria raiz.

    ⚠️ DOIS SALTOS, E O SEGUNDO É O QUE IMPORTA.

    Medido em 19/08/2026 contra o site ao vivo: partindo da HOME da Caixa com o
    tema "saque-aniversário do FGTS", um salto só escolhia
    `.../habilitacao-saque-calamidade-fgts/...` — saque de CALAMIDADE. Ele casa
    "saque" e "fgts" e está pendurado na home; a página do saque-aniversário
    não está.

    Quando achei essa mesma página à mão, eu tinha partido da SEÇÃO
    `/beneficios-trabalhador/fgts/`, não da home. É esse o caminho que o
    leitor faz e é o que o resolvedor precisa fazer: escolher as seções mais
    promissoras e olhar dentro delas antes de decidir.

    Nunca levanta e nunca devolve vazio — o pior caso é continuar com o que
    entrou, que é exatamente o comportamento de antes deste módulo.
    """
    if not raiz or not e_raiz(raiz):
        return raiz                      # já é específica; não mexe
    try:
        primeiro_nivel = colher(raiz)
        candidatos = list(primeiro_nivel)
        if saltos > 1:
            for secao in melhores(raiz, primeiro_nivel, termos):
                candidatos += colher(secao)
        escolhido = escolher_profundo(raiz, candidatos, termos)
    except Exception:  # noqa: BLE001
        return raiz
    if not escolhido:
        return raiz
    if verificar is not None:
        try:
            if not verificar(escolhido):
                return raiz              # fail-closed: link morto não sobe
        except Exception:  # noqa: BLE001
            return raiz
    return escolhido
