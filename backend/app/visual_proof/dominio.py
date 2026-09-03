"""As regras da prova visual, sem framework, sem rede e sem processo filho.

Só `stdlib`. É condição, não estilo: este módulo é a única dependência VOLC que
o broker (`tools/adspower-broker/`) carrega para o host isolado, e ele precisa
rodar lá sem instalar FastAPI, httpx ou o resto do backend.

## As três decisões que este arquivo existe para segurar

**1. Aprovar é ato humano.** `avaliar_captura` nunca devolve `approved`. O
melhor veredito automático é `eligible_for_human_review`. A diferença não é
formal: "a captura não encontrou problema" e "a página está certa" são
afirmações distintas, e só a segunda autoriza continuar publicando. Um motor
que colapsa as duas ensina a operação a confiar num carimbo que ninguém deu.

**2. Falha do AdsPower não reprova a página.** Timeout, autenticação recusada,
endpoint fora da fronteira e perfil indisponível produzem `indeterminate` —
nunca `needs_correction`. É o guarda escrito no ADR de distribuição orgânica
("Falha do AdsPower não transforma a página em reprovada"), e sem ele o QA
visual vira um gerador de correções falsas toda vez que o executor cai.

**3. Ausência falha FECHADA.** Host que não resolve não é "público por
enquanto"; artefato de zero byte não é "página vazia"; DNS com um endereço
público e outro privado não é "público o suficiente". Cada um desses vira
recusa ou `indeterminate`, e nenhum vira sucesso silencioso.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Literal, Optional, Sequence
from urllib.parse import parse_qsl, urlparse, urlunparse


# ─────────────────────────────────────────────────────────────────────────────
# Recusas
# ─────────────────────────────────────────────────────────────────────────────


class PayloadRecusado(ValueError):
    """O pedido não pode virar operação. A mensagem é para quem opera."""


class UrlRecusada(PayloadRecusado):
    """O endereço não pode ser aberto por um perfil autenticado."""


class EndpointRecusado(PayloadRecusado):
    """O endpoint do AdsPower está fora da fronteira permitida."""


class TransicaoInvalida(PayloadRecusado):
    """O job não pode ir deste estado para aquele."""


class VazamentoDetectado(RuntimeError):
    """Um valor sentinela apareceu onde nunca pode aparecer.

    Não é `ValueError` de propósito: isto não é "payload inválido", é falha de
    contenção. Quem captura `PayloadRecusado` genericamente não deve engolir
    esta.
    """


class NomeNaoResolvido(LookupError):
    """O resolvedor não conhece este host. Ver `exigir_url_de_superficie`."""


# ─────────────────────────────────────────────────────────────────────────────
# Política de URL da superfície publicada
# ─────────────────────────────────────────────────────────────────────────────

#: Endereços de serviço de metadados de nuvem. Todos já caem em `is_global`
#: falso, e a lista existe para que a recusa cite o motivo certo no recibo —
#: "metadados de nuvem" é diagnóstico, "endereço não público" é sintoma.
ENDERECOS_DE_METADADOS: frozenset[str] = frozenset({
    "169.254.169.254",   # AWS / Azure / GCP / DigitalOcean
    "192.0.0.192",       # Oracle Cloud
    "100.100.100.200",   # Alibaba Cloud
    "fd00:ec2::254",     # AWS IMDS sobre IPv6
})

#: Sufixos que só existem dentro de uma rede. Recusados ANTES de resolver: um
#: `.internal` que resolve para IP público continua sendo um nome de rede
#: interna, e abrir um deles com sessão autenticada é o pedido errado.
SUFIXOS_INTERNOS: tuple[str, ...] = (
    ".internal", ".local", ".localdomain", ".home.arpa", ".lan",
    ".intranet", ".corp", ".private", ".test", ".invalid", ".localhost",
)

HOSTS_INTERNOS: frozenset[str] = frozenset({
    "localhost", "metadata", "metadata.goog", "instance-data",
})

#: Só 443. Uma porta alternativa em HTTPS não é ilegal — é sinal de superfície
#: que não é a página publicada, e o QA visual confere a página publicada.
PORTA_HTTPS_PADRAO = 443


def _resolver_padrao(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise NomeNaoResolvido(host) from exc
    if not infos:
        raise NomeNaoResolvido(host)
    return [info[4][0] for info in infos]


def _endereco_e_publico(bruto: str) -> bool:
    try:
        ip = ipaddress.ip_address(bruto.split("%", 1)[0])
    except ValueError:
        return False
    if str(ip) in ENDERECOS_DE_METADADOS:
        return False
    return bool(
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
        and not ip.is_loopback
        and not ip.is_link_local
    )


def dominio_casa(host: str, dominio_esperado: str) -> bool:
    """`blog.exemplo.com.br` pertence a `exemplo.com.br`; `malexemplo` não.

    A comparação é por RÓTULO, não por sufixo de string: `endswith` puro
    aceitaria `malexemplo.com.br` dentro de `exemplo.com.br`, que é o truque
    mais barato para levar um QA autenticado a um domínio de terceiro.
    """
    h = (host or "").strip(".").lower()
    d = (dominio_esperado or "").strip(".").lower()
    if not h or not d:
        return False
    return h == d or h.endswith("." + d)


def exigir_url_de_superficie(
    url: str,
    *,
    dominio_esperado: Optional[str] = None,
    resolver: Optional[Callable[[str], Sequence[str]]] = None,
) -> str:
    """Valida o endereço que um perfil AUTENTICADO vai abrir. Não busca nada.

    ## Por que esta função não reusa `publisher_quality.fetch`

    Aquele módulo resolve um problema vizinho e apaga query e fragmento, porque
    persiste artefato de leitura pública e não quer guardar id de campanha. Aqui
    a query é PARTE do endereço a conferir — `?p=123` do WordPress e
    `?story_fbid=` do Facebook mudam a página. Apagá-la faria o QA visual
    conferir uma página diferente da publicada, e chamar de aprovada a errada.

    O sigilo volta um passo depois, em `sanitizar_url_para_recibo`, que redige
    os VALORES da query antes de o endereço virar recibo. Separar as duas
    responsabilidades é o que permite conferir a página certa e guardar um
    registro que não carrega token de sessão colado na URL.

    O fragmento é descartado: ele nunca chega ao servidor, então não faz parte
    da identidade da página.
    """
    bruto = (url or "").strip()
    if not bruto:
        raise UrlRecusada("endereço ausente: o QA visual precisa saber qual página abrir.")
    if len(bruto) > 2000:
        raise UrlRecusada("endereço longo demais para ser uma superfície publicada.")

    partes = urlparse(bruto)
    if partes.scheme != "https":
        raise UrlRecusada(
            "o QA visual só abre HTTPS: um perfil autenticado em texto claro entrega a "
            "sessão a quem estiver no caminho.")
    if partes.username or partes.password:
        raise UrlRecusada("o endereço não pode carregar credencial embutida (user:senha@).")

    host = (partes.hostname or "").strip(".").lower()
    if not host:
        raise UrlRecusada("o endereço não tem host.")
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        raise UrlRecusada(
            "host com caractere não-ASCII: envie a forma punycode (xn--…). Nomes "
            "parecidos em alfabetos diferentes são o jeito mais barato de trocar o "
            "destino sem que a diferença apareça na tela.") from None

    try:
        porta = partes.port
    except ValueError:
        raise UrlRecusada("porta inválida no endereço.") from None
    if porta not in (None, PORTA_HTTPS_PADRAO):
        raise UrlRecusada(
            f"porta {porta} não é a de uma superfície publicada: só 443 é aceita.")

    if host in HOSTS_INTERNOS or host.endswith(SUFIXOS_INTERNOS):
        raise UrlRecusada("o host pertence a uma rede interna e não é superfície publicada.")

    if dominio_esperado and not dominio_casa(host, dominio_esperado):
        raise UrlRecusada(
            "o endereço está fora do domínio esperado deste ativo. O QA visual não "
            "navega para fora do que foi autorizado.")

    # ── resolução: TODOS os endereços precisam ser públicos ──────────────────
    #
    # "pelo menos um público" deixaria o navegador escolher o privado — é o
    # formato clássico do DNS rebinding, e custa um registro A a mais.
    resolve = resolver or _resolver_padrao
    try:
        ip_literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip_literal = None
    enderecos = [str(ip_literal)] if ip_literal is not None else None
    if enderecos is None:
        try:
            enderecos = list(resolve(host))
        except NomeNaoResolvido:
            raise UrlRecusada(
                "o host não resolve. Um nome desconhecido não é público por enquanto: "
                "é desconhecido, e desconhecido não passa.") from None
    if not enderecos:
        raise UrlRecusada("o host não resolveu para endereço nenhum.")
    for endereco in enderecos:
        if str(endereco) in ENDERECOS_DE_METADADOS:
            raise UrlRecusada(
                "o host resolve para o serviço de metadados da nuvem. Abrir esse "
                "endereço com um perfil autenticado é o caminho curto para vazar "
                "credencial de instância.")
        if not _endereco_e_publico(str(endereco)):
            raise UrlRecusada(
                "o host resolve para endereço privado, de loopback ou reservado. "
                "Superfície publicada é pública, por definição.")

    caminho = partes.path or "/"
    return urlunparse(("https", host, caminho, "", partes.query, ""))


def exigir_endpoint_do_adspower(
    base: str, *, portas_permitidas: Iterable[int] = (50325,)
) -> str:
    """A Local API só pode ser falada em loopback, numa porta declarada.

    ## Por que só literal de IP, e nunca `localhost` ou `local.adspower.net`

    A documentação oficial oferece `http://local.adspower.net:50325/` como
    endereço equivalente ao loopback. Um NOME depende de `/etc/hosts` e do
    resolvedor: quem editar qualquer um dos dois muda para onde a chave da API
    é enviada, sem tocar em nenhuma configuração do VOLC. Um literal `127.0.0.1`
    não tem essa junta.

    Consultado em 02/09/2026: https://localapi-doc-en.adspower.com/docs/Rdw7Iu
    """
    bruto = (base or "").strip().rstrip("/")
    if not bruto:
        raise EndpointRecusado("endpoint do AdsPower ausente: o broker não adivinha porta.")
    partes = urlparse(bruto)
    if partes.scheme not in ("http", "https"):
        raise EndpointRecusado("o endpoint do AdsPower precisa ser http(s).")
    if partes.username or partes.password:
        raise EndpointRecusado("o endpoint do AdsPower não pode carregar credencial embutida.")
    if partes.path or partes.query or partes.fragment:
        raise EndpointRecusado(
            "informe só a base (esquema://host:porta) — o caminho é do broker, não da "
            "configuração.")
    host = (partes.hostname or "").strip("[]")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise EndpointRecusado(
            "o endpoint do AdsPower precisa ser um literal de IP de loopback "
            "(127.0.0.1 ou ::1). Um nome pode ser reapontado sem tocar nesta "
            "configuração — e a chave da API iria junto.") from None
    if not ip.is_loopback:
        raise EndpointRecusado(
            "o AdsPower só é falado em loopback. Um endpoint remoto significa que a "
            "chave da Local API viaja pela rede.")
    try:
        porta = partes.port
    except ValueError:
        raise EndpointRecusado("porta inválida no endpoint do AdsPower.") from None
    permitidas = tuple(portas_permitidas)
    if porta is None or porta not in permitidas:
        raise EndpointRecusado(
            f"porta {porta} fora da allowlist do broker {permitidas}.")
    return f"{partes.scheme}://{host}:{porta}"


# ─────────────────────────────────────────────────────────────────────────────
# Estados
# ─────────────────────────────────────────────────────────────────────────────

ESTADOS_DO_JOB: tuple[str, ...] = (
    "requested", "authorized", "running", "captured", "approved",
    "needs_correction", "indeterminate", "failed", "cancelled", "expired",
)

#: Terminais: nada sai deles. Um job aprovado que volta a `running` é um recibo
#: que deixou de valer sem ninguém revogá-lo.
ESTADOS_TERMINAIS: frozenset[str] = frozenset({
    "approved", "needs_correction", "indeterminate", "failed", "cancelled", "expired",
})

_SAIDAS_COMUNS = ("failed", "cancelled", "expired")

TRANSICOES: dict[str, frozenset[str]] = {
    "requested": frozenset(("authorized", *_SAIDAS_COMUNS)),
    "authorized": frozenset(("running", *_SAIDAS_COMUNS)),
    "running": frozenset(("captured", "needs_correction", "indeterminate", *_SAIDAS_COMUNS)),
    # `approved` só sai daqui, e só por ato humano. Ver `VisualProofJob.aprovar`.
    "captured": frozenset(("approved", "needs_correction", "indeterminate", *_SAIDAS_COMUNS)),
    **{terminal: frozenset() for terminal in ESTADOS_TERMINAIS},
}


def transicao_permitida(de: str, para: str) -> bool:
    return para in TRANSICOES.get(de, frozenset())


def exigir_transicao(de: str, para: str) -> None:
    if not transicao_permitida(de, para):
        raise TransicaoInvalida(
            f"um job de prova visual não vai de {de} para {para}.")


# ─────────────────────────────────────────────────────────────────────────────
# Veredito
# ─────────────────────────────────────────────────────────────────────────────

#: O que a AVALIAÇÃO AUTOMÁTICA pode produzir. `approved` está fora, e a
#: ausência é o contrato: ver o docstring do módulo.
VEREDITOS_AUTOMATICOS: tuple[str, ...] = (
    "eligible_for_human_review", "needs_correction", "indeterminate",
)

#: O que um JOB pode terminar carregando, incluindo o carimbo humano.
VEREDITOS_DO_JOB: tuple[str, ...] = ("approved", *VEREDITOS_AUTOMATICOS)

ResultadoAutomatico = Literal["eligible_for_human_review", "needs_correction", "indeterminate"]

#: Acima disso, a leitura deixou de ser "página com ruído" e virou "não dá para
#: afirmar o que foi visto". Os dois limiares são declarados, não descobertos:
#: nenhuma medição real existe ainda para calibrá-los, e fingir calibração seria
#: pior do que assumir o arbítrio.
LIMITE_CONSOLE_INDETERMINADO = 10
LIMITE_REDE_INDETERMINADO = 5


@dataclass(frozen=True)
class LeituraDaSuperficie:
    """O que voltou da captura, já sanitizado, pronto para virar veredito."""

    url_final: str
    url_esperada: str
    dominio_esperado: Optional[str]
    status_http: Optional[int]
    console_erros: int
    rede_falhas: int
    redirecionamentos: int
    artefato_bytes: int
    conteudo_sha256: Optional[str] = None
    conteudo_sha256_esperado: Optional[str] = None


@dataclass(frozen=True)
class VisualProofVerdict:
    resultado: str
    justificativas: tuple[str, ...] = ()
    checagens: tuple[dict[str, Any], ...] = ()

    def para_dicionario(self) -> dict[str, Any]:
        return {
            "resultado": self.resultado,
            "justificativas": list(self.justificativas),
            "checagens": [dict(c) for c in self.checagens],
        }


def _checagem(nome: str, ok: bool, detalhe: str) -> dict[str, Any]:
    return {"nome": nome, "resultado": "ok" if ok else "falhou", "detalhe": detalhe}


def avaliar_captura(leitura: LeituraDaSuperficie) -> VisualProofVerdict:
    """Transforma leitura em veredito — e nunca em `approved`.

    A ordem das regras é deliberada. Primeiro os fatos que a resposta AFIRMA
    (endereço final, domínio, status, hash de conteúdo): eles valem mesmo que a
    imagem não tenha saído. Depois a ausência de imagem, que é impossibilidade
    de ver e não prova de erro. Por último o ruído (console e rede), que sozinho
    nunca reprova.
    """
    justificativas: list[str] = []
    checagens: list[dict[str, Any]] = []

    url_bate = leitura.url_final == leitura.url_esperada
    checagens.append(_checagem("url_final", url_bate, "endereço final igual ao esperado"))
    if not url_bate:
        justificativas.append(
            "o endereço final aberto não é o esperado para este ativo")

    dominio_bate = True
    if leitura.dominio_esperado:
        host = (urlparse(leitura.url_final).hostname or "")
        dominio_bate = dominio_casa(host, leitura.dominio_esperado)
        checagens.append(_checagem("dominio_final", dominio_bate, "domínio final dentro do esperado"))
        if not dominio_bate:
            justificativas.append("a página final está fora do domínio esperado")

    status_ok = leitura.status_http is None or 200 <= leitura.status_http < 400
    checagens.append(_checagem("status_http", status_ok, "resposta HTTP de sucesso"))
    if not status_ok:
        justificativas.append(f"a página respondeu HTTP {leitura.status_http}")

    hash_ok = True
    if leitura.conteudo_sha256_esperado:
        hash_ok = leitura.conteudo_sha256 == leitura.conteudo_sha256_esperado
        checagens.append(_checagem("conteudo_sha256", hash_ok, "conteúdo igual ao aprovado"))
        if not hash_ok:
            justificativas.append(
                "o conteúdo publicado difere da versão aprovada (hash divergente)")

    if not (url_bate and dominio_bate and status_ok and hash_ok):
        return VisualProofVerdict("needs_correction", tuple(justificativas), tuple(checagens))

    tem_imagem = leitura.artefato_bytes > 0
    checagens.append(_checagem("artefato", tem_imagem, "captura produziu imagem"))
    if not tem_imagem:
        justificativas.append(
            "a captura não produziu imagem: não dá para afirmar o que a página mostrou")
        return VisualProofVerdict("indeterminate", tuple(justificativas), tuple(checagens))

    if leitura.redirecionamentos:
        justificativas.append(
            f"a navegação passou por {leitura.redirecionamentos} redirecionamento(s)")

    if leitura.rede_falhas:
        justificativas.append(f"{leitura.rede_falhas} requisição(ões) de rede falharam")
    if leitura.console_erros:
        justificativas.append(f"{leitura.console_erros} erro(s) no console do navegador")

    ruido_alto = (
        leitura.console_erros >= LIMITE_CONSOLE_INDETERMINADO
        or leitura.rede_falhas >= LIMITE_REDE_INDETERMINADO
    )
    checagens.append(_checagem("ruido", not ruido_alto, "console e rede dentro do tolerado"))
    if ruido_alto:
        justificativas.append(
            "ruído alto demais para afirmar o que foi visto — a leitura fica indeterminada, "
            "e não reprovada")
        return VisualProofVerdict("indeterminate", tuple(justificativas), tuple(checagens))

    justificativas.append(
        "nenhuma checagem automática falhou; a aprovação depende de revisão humana")
    return VisualProofVerdict(
        "eligible_for_human_review", tuple(justificativas), tuple(checagens))


#: Motivos técnicos conhecidos. Todos viram `indeterminate` — ver o guarda 2 no
#: docstring do módulo.
MOTIVOS_TECNICOS: tuple[str, ...] = (
    "timeout", "endpoint_recusado", "autenticacao_recusada", "perfil_indisponivel",
    "broker_indisponivel", "resolucao_de_segredo_falhou", "captura_falhou",
)


def veredito_de_falha_tecnica(motivo: str) -> VisualProofVerdict:
    return VisualProofVerdict(
        "indeterminate",
        (
            f"falha técnica do executor ({motivo}): a página não foi avaliada",
            "falha do AdsPower não reprova a página — o resultado é indeterminado",
        ),
        (_checagem("execucao", False, motivo),),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sanitização
# ─────────────────────────────────────────────────────────────────────────────

REDIGIDO = "«redigido»"

#: Cada padrão cobre uma forma que, se aparecer num recibo, num log ou numa
#: exceção, publica o que o sistema existe para não publicar.
#:
#: ⚠️ `op://` é redigido até o FIM DA LINHA, de propósito. A gramática do
#: 1Password aceita espaço dentro do nome do item (`op://VOLC/Pagina Piloto/…`),
#: então parar no primeiro espaço deixaria `Piloto/credential` na frase. Redigir
#: demais num recibo é barato; redigir de menos não tem volta.
_PADROES_SENSIVEIS: tuple[re.Pattern[str], ...] = (
    re.compile(r"op://[^\n\r]*"),
    re.compile(r"\bBearer\s+[^\s\"']+", re.IGNORECASE),
    re.compile(r"\b(?:Set-)?Cookie\s*:\s*[^\n\r]*", re.IGNORECASE),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"-----BEGIN[^\n\r]*"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?"),
    re.compile(r"\b(?:sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{16,}"),
    re.compile(r"\b(?:api[_-]?key|apikey|token|senha|password)\s*[:=]\s*[^\s,;\"']{6,}",
               re.IGNORECASE),
)

_CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sanitizar_texto(texto: Optional[str], limite: int = 600) -> str:
    """Reduz um texto a algo que pode ser guardado e mostrado.

    Não tenta "detectar segredo por entropia": isso cria confiança falsa. Ela
    remove FORMATOS reconhecíveis, e a defesa real continua sendo não deixar o
    valor chegar aqui.
    """
    if not texto:
        return ""
    limpo = _CONTROLE.sub(" ", str(texto))
    for padrao in _PADROES_SENSIVEIS:
        limpo = padrao.sub(REDIGIDO, limpo)
    # A substituição do userinfo come o `@`; devolvê-lo mantém a frase legível.
    limpo = limpo.replace(f"://{REDIGIDO}", f"://{REDIGIDO}@") if "://" + REDIGIDO in limpo else limpo
    limpo = " ".join(limpo.split())
    return limpo[:limite] + ("…" if len(limpo) > limite else "")


def sanitizar_url_para_recibo(url: Optional[str]) -> str:
    """Mantém esquema, host e caminho; redige os VALORES da query.

    As CHAVES ficam: `?token=` conta uma história que `?` sozinho apaga — quem
    lê o recibo precisa saber que havia um token na URL para decidir se aquela
    URL podia ter sido registrada em algum lugar.
    """
    if not url:
        return ""
    partes = urlparse(str(url).strip())
    if not partes.scheme or not partes.hostname:
        return sanitizar_texto(url)
    host = partes.hostname.lower()
    if partes.port and partes.port not in (80, 443):
        host = f"{host}:{partes.port}"
    base = f"{partes.scheme}://{host}{partes.path or '/'}"
    if not partes.query:
        return base
    chaves = [chave for chave, _ in parse_qsl(partes.query, keep_blank_values=True)]
    return base + "?" + "&".join(f"{chave}={REDIGIDO}" for chave in chaves)


#: Uma sentinela precisa ser longa o bastante para não casar por acaso. Oito
#: caracteres já distinguem; abaixo disso a varredura vira gerador de falso
#: alarme, e um alarme que sempre toca é um alarme que ninguém lê.
TAMANHO_MINIMO_DE_SENTINELA = 8


def recusar_valor_sensivel(documento: Any, *, sentinelas: Sequence[str]) -> None:
    """Percorre o documento inteiro e falha se um valor sentinela aparecer.

    Levanta citando o CAMINHO, nunca o valor — repetir a sentinela na mensagem
    publicaria no log de quem a recusou exatamente o que a recusa protege. É o
    mesmo cuidado de `asset_vault.dominio.recusar_chave_sensivel`.
    """
    agulhas = [s for s in sentinelas if s]
    for agulha in agulhas:
        if len(agulha) < TAMANHO_MINIMO_DE_SENTINELA:
            raise ValueError(
                f"sentinela curta demais ({len(agulha)} caracteres): use ao menos "
                f"{TAMANHO_MINIMO_DE_SENTINELA}, senão a varredura casa por acaso.")
    if not agulhas:
        return

    def caminhar(valor: Any, caminho: str) -> None:
        if isinstance(valor, dict):
            for chave, aninhado in valor.items():
                sufixo = f"{caminho}.{chave}" if caminho else str(chave)
                caminhar(aninhado, sufixo)
            return
        if isinstance(valor, (list, tuple)):
            for indice, item in enumerate(valor):
                caminhar(item, f"{caminho}[{indice}]")
            return
        if isinstance(valor, (str, bytes)):
            texto = valor.decode("utf-8", "replace") if isinstance(valor, bytes) else valor
            for agulha in agulhas:
                if agulha in texto:
                    raise VazamentoDetectado(
                        f"valor sentinela encontrado em {caminho or '(raiz)'} — "
                        "o valor não é repetido aqui de propósito")

    caminhar(documento, "")


# ─────────────────────────────────────────────────────────────────────────────
# Impressão digital do pedido
# ─────────────────────────────────────────────────────────────────────────────


def impressao_do_pedido(payload: Any) -> str:
    """SHA-256 do JSON canônico. É o que decide replay de conflito.

    `sort_keys` porque a MESMA intenção escrita em ordem diferente é a mesma
    intenção — um retry que muda a ordem das chaves não pode virar publicação
    duplicada. Conteúdo não serializável levanta `TypeError` em vez de virar
    `str(obj)`: o `repr` de um objeto carrega o endereço de memória, e a
    impressão deixaria de ser estável entre processos.
    """
    texto = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sha256_de_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Contratos
# ─────────────────────────────────────────────────────────────────────────────
#
# Os nomes das CLASSES são os do contrato canônico da missão, em inglês, para
# que "BrowserProfileReference" seja greppável entre o documento e o código. Os
# CAMPOS seguem o português do resto do repositório (`ativo_id`,
# `chave_idempotencia`, `nome_logico`), porque é com o Cofre que eles conversam.

#: Mesma gramática de `asset_vault.dominio.NOME_LOGICO`. A concordância entre os
#: dois é PROVADA por teste, não prometida aqui — os módulos não se importam de
#: propósito (ver o `__init__` deste pacote).
NOME_LOGICO = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")

#: Mesma gramática de `asset_vault.dominio.CHAVE_DE_IDEMPOTENCIA`, pelo mesmo
#: motivo: a chave do QA visual costuma DERIVAR da chave da publicação, e duas
#: gramáticas diferentes fariam uma chave válida de um lado ser recusada do
#: outro no meio do fluxo.
CHAVE_DE_IDEMPOTENCIA = re.compile(r"^[A-Za-z0-9._:#-]{8,120}$")


def exigir_chave_de_idempotencia_visual(valor: str) -> str:
    if not CHAVE_DE_IDEMPOTENCIA.match(valor or ""):
        raise PayloadRecusado(
            "chave de idempotência inválida: 8 a 120 caracteres entre letras, dígitos, "
            "'.', '_', ':', '#' e '-'. Ela não pode ser sorteada — um retry com chave "
            "nova executa de novo.")
    return valor


def exigir_perfil_logico(valor: str) -> str:
    if not NOME_LOGICO.match(valor or ""):
        raise PayloadRecusado(
            "nome lógico de perfil inválido: MAIÚSCULAS, dígitos e '_', de 2 a 64 "
            "caracteres (ex.: PERFIL_PILOTO_01). O valor recebido não é repetido aqui.")
    return valor


@dataclass(frozen=True)
class BrowserProfileReference:
    """O perfil como o VOLC o conhece: um NOME LÓGICO, nunca o `user_id`.

    ## Por que o `user_id` do AdsPower não mora aqui

    O `user_id` é o identificador que a Local API aceita para abrir o perfil.
    Quem o tem, e alcança a porta 50325, abre o navegador com a sessão já
    autenticada da página. Ele não é "segredo" no sentido de senha, e é
    exatamente por isso que costuma vazar: entra em log, em recibo, em issue.

    A tradução `PERFIL_PILOTO_01 -> user_id` mora só na allowlist do broker, no
    host isolado. O VOLC, o Supabase, o grafo e a tela falam o nome lógico.
    """

    ativo_id: str
    perfil_logico: str
    owner_sub: str
    provider: str
    credencial_nome_logico: str

    def __post_init__(self) -> None:
        exigir_perfil_logico(self.perfil_logico)
        if not NOME_LOGICO.match(self.credencial_nome_logico or ""):
            raise PayloadRecusado(
                "nome lógico de credencial inválido (ex.: ADSPOWER_API_KEY).")
        if not (self.ativo_id or "").strip():
            raise PayloadRecusado("o perfil precisa apontar para um ativo do Cofre.")
        if not (self.owner_sub or "").strip():
            raise PayloadRecusado("o perfil precisa ter dono.")
        if self.provider not in ("1password", "bitwarden", "vaultwarden", "passbolt", "infisical"):
            raise PayloadRecusado(f"provider de cofre desconhecido: {self.provider}")

    def para_dicionario(self) -> dict[str, Any]:
        return {
            "ativo_id": self.ativo_id,
            "perfil_logico": self.perfil_logico,
            "owner_sub": self.owner_sub,
            "provider": self.provider,
            "credencial_nome_logico": self.credencial_nome_logico,
        }


#: As quatro operações que o broker aceita. Não existe "executar comando".
#: A ausência é o contrato: uma porta genérica com allowlist vazia é uma porta
#: aberta esperando alguém preencher a lista.
OPERACOES_DO_BROKER: tuple[str, ...] = (
    "estado_do_perfil", "abrir_perfil", "capturar_superficie", "fechar_perfil",
)


@dataclass(frozen=True)
class Viewport:
    largura: int
    altura: int

    def __post_init__(self) -> None:
        if not (320 <= self.largura <= 3840 and 320 <= self.altura <= 3840):
            raise PayloadRecusado("viewport fora da faixa aceitável (320–3840).")

    def para_dicionario(self) -> dict[str, int]:
        return {"largura": self.largura, "altura": self.altura}


@dataclass(frozen=True)
class AdsPowerBrokerRequest:
    """O que o VOLC pede ao broker. Referências lógicas, nunca segredo."""

    pedido_id: str
    chave_idempotencia: str
    operacao: str
    perfil: BrowserProfileReference
    owner_sub: str
    ativo_id: str
    timeout_s: int = 45
    url_alvo: Optional[str] = None
    dominio_esperado: Optional[str] = None
    viewport: Optional[Viewport] = None
    timezone: Optional[str] = None

    def __post_init__(self) -> None:
        if self.operacao not in OPERACOES_DO_BROKER:
            raise PayloadRecusado(
                f"operação fora da allowlist do broker: {self.operacao}")
        if not (1 <= self.timeout_s <= 300):
            raise PayloadRecusado("timeout fora da faixa aceitável (1–300 s).")
        if self.operacao == "capturar_superficie" and not self.url_alvo:
            raise PayloadRecusado("capturar_superficie exige url_alvo.")
        if self.owner_sub != self.perfil.owner_sub:
            raise PayloadRecusado(
                "o dono do pedido não é o dono do perfil: o broker não empresta perfil.")

    def para_dicionario(self) -> dict[str, Any]:
        return {
            "pedido_id": self.pedido_id,
            "chave_idempotencia": self.chave_idempotencia,
            "operacao": self.operacao,
            "perfil": self.perfil.para_dicionario(),
            "owner_sub": self.owner_sub,
            "ativo_id": self.ativo_id,
            "timeout_s": self.timeout_s,
            "url_alvo": self.url_alvo,
            "dominio_esperado": self.dominio_esperado,
            "viewport": self.viewport.para_dicionario() if self.viewport else None,
            "timezone": self.timezone,
        }

    def impressao(self) -> str:
        """O que define "o mesmo pedido" para fins de idempotência.

        `pedido_id` fica de FORA: ele muda a cada retry, e incluí-lo faria toda
        repetição parecer um pedido novo — que é justamente o defeito que a
        chave de idempotência existe para evitar.
        """
        corpo = self.para_dicionario()
        corpo.pop("pedido_id", None)
        return impressao_do_pedido(corpo)


@dataclass(frozen=True)
class AdsPowerBrokerReceipt:
    """O que o broker devolve. Sem valor de segredo, sem cookie, sem `user_id`."""

    recibo_id: str
    pedido_id: str
    chave_idempotencia: str
    operacao: str
    perfil_logico: str
    owner_sub: str
    ativo_id: str
    estado: str  # executado | recusado | falhou | replay
    motivo_codigo: str
    motivo: str
    iniciado_em: str
    concluido_em: str
    duracao_ms: int
    adspower_code: Optional[int] = None
    url_final: Optional[str] = None
    status_http: Optional[int] = None
    redirecionamentos: tuple[str, ...] = ()
    artefato: Optional["VisualProofArtifact"] = None
    console_resumo: dict[str, Any] = field(default_factory=dict)
    rede_resumo: dict[str, Any] = field(default_factory=dict)

    def para_dicionario(self) -> dict[str, Any]:
        return {
            "recibo_id": self.recibo_id,
            "pedido_id": self.pedido_id,
            "chave_idempotencia": self.chave_idempotencia,
            "operacao": self.operacao,
            "perfil_logico": self.perfil_logico,
            "owner_sub": self.owner_sub,
            "ativo_id": self.ativo_id,
            "estado": self.estado,
            "motivo_codigo": self.motivo_codigo,
            "motivo": sanitizar_texto(self.motivo),
            "iniciado_em": self.iniciado_em,
            "concluido_em": self.concluido_em,
            "duracao_ms": self.duracao_ms,
            "adspower_code": self.adspower_code,
            "url_final": sanitizar_url_para_recibo(self.url_final) or None,
            "status_http": self.status_http,
            "redirecionamentos": [sanitizar_url_para_recibo(u) for u in self.redirecionamentos],
            "artefato": self.artefato.para_dicionario() if self.artefato else None,
            "console_resumo": dict(self.console_resumo),
            "rede_resumo": dict(self.rede_resumo),
        }


@dataclass(frozen=True)
class VisualProofArtifact:
    """A imagem por REFERÊNCIA e HASH. Os bytes nunca entram em JSON.

    Um screenshot de 1366×768 em PNG passa de 300 KB. Guardá-lo em base64
    dentro do recibo, do Roadmap ou do grafo transformaria cada prova visual
    num arquivo que ninguém consegue revisar, versionar ou apagar — e um deles
    já basta para carregar dado pessoal de quem aparecer na tela.
    """

    referencia: str
    sha256: str
    bytes_: int
    mime: str
    criado_em: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256 or ""):
            raise PayloadRecusado("sha256 do artefato inválido.")
        if self.bytes_ < 0:
            raise PayloadRecusado("tamanho de artefato negativo.")

    def para_dicionario(self) -> dict[str, Any]:
        return {
            "referencia": self.referencia,
            "sha256": self.sha256,
            "bytes": self.bytes_,
            "mime": self.mime,
            "criado_em": self.criado_em,
        }


@dataclass
class VisualProofJob:
    """O job de QA visual, do pedido ao veredito.

    Mutável de propósito: o job é a linha do tempo de UMA intenção, e cada
    transição é um fato novo sobre a mesma coisa. Copiá-lo a cada passo faria
    "qual é o estado atual" virar uma pergunta com várias respostas.
    """

    job_id: str
    owner_sub: str
    ativo_id: str
    perfil: BrowserProfileReference
    url_esperada: str
    dominio_esperado: Optional[str]
    viewport: Viewport
    timezone: str
    classe_de_agente: str
    chave_idempotencia: str
    criado_em: str
    timeout_s: int
    conteudo_sha256_esperado: Optional[str] = None

    estado: str = "requested"
    tentativas: int = 0
    url_final: Optional[str] = None
    recibo_id: Optional[str] = None
    artefato: Optional[VisualProofArtifact] = None
    console_resumo: dict[str, Any] = field(default_factory=dict)
    rede_resumo: dict[str, Any] = field(default_factory=dict)
    redirecionamentos: list[str] = field(default_factory=list)
    checagens: list[dict[str, Any]] = field(default_factory=list)
    veredito: Optional[str] = None
    justificativas: list[str] = field(default_factory=list)
    revisao_humana: Optional[dict[str, Any]] = None
    historico: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def novo(cls, **kwargs: Any) -> "VisualProofJob":
        job = cls(**kwargs)
        job.historico.append({"estado": "requested", "em": job.criado_em})
        return job

    # ── transições ───────────────────────────────────────────────────────────

    def _ir_para(self, destino: str, em: Optional[str] = None) -> None:
        exigir_transicao(self.estado, destino)
        self.estado = destino
        self.historico.append({"estado": destino, "em": em or ""})

    def autorizar(self, em: Optional[str] = None) -> None:
        self._ir_para("authorized", em)

    def iniciar(self, *, recibo_id: str, em: Optional[str] = None) -> None:
        self._ir_para("running", em)
        self.recibo_id = recibo_id
        self.tentativas += 1

    def registrar_captura(
        self, *, url_final: str, artefato: Optional[VisualProofArtifact],
        console_resumo: dict[str, Any], rede_resumo: dict[str, Any],
        redirecionamentos: Sequence[str], checagens: Sequence[dict[str, Any]],
        veredito: VisualProofVerdict, em: Optional[str] = None,
    ) -> None:
        """Guarda a leitura e move o job para o estado que o veredito exige.

        `eligible_for_human_review` NÃO é um estado do job: ele para em
        `captured`, esperando gente. Colapsar os dois faria a fila de revisão
        desaparecer da tela.
        """
        destino = {
            "eligible_for_human_review": "captured",
            "needs_correction": "needs_correction",
            "indeterminate": "indeterminate",
        }.get(veredito.resultado)
        if destino is None:
            raise TransicaoInvalida(
                f"veredito automático desconhecido: {veredito.resultado}")
        self._ir_para(destino, em)
        self.url_final = url_final
        self.artefato = artefato
        self.console_resumo = dict(console_resumo)
        self.rede_resumo = dict(rede_resumo)
        self.redirecionamentos = list(redirecionamentos)
        self.checagens = [dict(c) for c in checagens]
        self.veredito = veredito.resultado
        self.justificativas = list(veredito.justificativas)

    def aprovar(self, *, revisor: str, nota: str, em: Optional[str] = None) -> None:
        """O único caminho até `approved`, e ele exige uma pessoa nomeada."""
        if not (revisor or "").strip():
            raise TransicaoInvalida(
                "aprovar é ato humano: informe quem revisou. Nenhuma avaliação "
                "automática produz `approved`.")
        self._ir_para("approved", em)
        self.veredito = "approved"
        self.revisao_humana = {"revisor": revisor, "nota": sanitizar_texto(nota), "em": em or ""}

    def pedir_correcao_humana(self, *, revisor: str, nota: str,
                              em: Optional[str] = None) -> None:
        """O contraponto de `aprovar`: a pessoa viu e reprovou.

        Existe como método próprio para que o plano de controle não precise
        mexer em `_ir_para` — uma camada de aplicação que chama método privado
        do domínio é uma camada que vai acabar pulando a validação.
        """
        if not (revisor or "").strip():
            raise TransicaoInvalida("reprovar também é ato humano: informe quem revisou.")
        self._ir_para("needs_correction", em)
        self.veredito = "needs_correction"
        self.revisao_humana = {"revisor": revisor, "nota": sanitizar_texto(nota), "em": em or ""}

    def marcar_indeterminado(self, veredito: VisualProofVerdict, em: Optional[str] = None) -> None:
        self._ir_para("indeterminate", em)
        self.veredito = veredito.resultado
        self.justificativas = list(veredito.justificativas)
        self.checagens = [dict(c) for c in veredito.checagens]

    def falhar(self, motivo: str, em: Optional[str] = None) -> None:
        self._ir_para("failed", em)
        self.justificativas = [sanitizar_texto(motivo)]

    def cancelar(self, motivo: str, em: Optional[str] = None) -> None:
        self._ir_para("cancelled", em)
        self.justificativas = [sanitizar_texto(motivo)]

    def expirar(self, em: Optional[str] = None) -> None:
        self._ir_para("expired", em)
        self.justificativas = ["o job passou do prazo sem ser executado"]

    # ── projeção ─────────────────────────────────────────────────────────────

    def para_dicionario(self) -> dict[str, Any]:
        """A projeção que pode sair desta máquina.

        Nenhum `user_agent` e nenhum `fingerprint`: `classe_de_agente`
        ("desktop-chromium") diz o que o revisor precisa saber para julgar o
        enquadramento, e uma impressão digital de navegador diria a um terceiro
        como reconhecer o perfil em outro lugar.
        """
        return {
            "job_id": self.job_id,
            "owner_sub": self.owner_sub,
            "ativo_id": self.ativo_id,
            "perfil": self.perfil.para_dicionario(),
            "url_esperada": sanitizar_url_para_recibo(self.url_esperada),
            "url_final": sanitizar_url_para_recibo(self.url_final) or None,
            "dominio_esperado": self.dominio_esperado,
            "viewport": self.viewport.para_dicionario(),
            "timezone": self.timezone,
            "classe_de_agente": self.classe_de_agente,
            "criado_em": self.criado_em,
            "timeout_s": self.timeout_s,
            "tentativas": self.tentativas,
            "chave_idempotencia": self.chave_idempotencia,
            "conteudo_sha256_esperado": self.conteudo_sha256_esperado,
            "artefato": self.artefato.para_dicionario() if self.artefato else None,
            "console_resumo": dict(self.console_resumo),
            "rede_resumo": dict(self.rede_resumo),
            "redirecionamentos": [sanitizar_url_para_recibo(u) for u in self.redirecionamentos],
            "checagens": [dict(c) for c in self.checagens],
            "recibo_id": self.recibo_id,
            "veredito": self.veredito,
            "justificativas": list(self.justificativas),
            "revisao_humana": dict(self.revisao_humana) if self.revisao_humana else None,
            "estado": self.estado,
            "historico": [dict(h) for h in self.historico],
        }
