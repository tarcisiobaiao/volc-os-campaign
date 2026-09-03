"""As regras do broker, sem framework, sem rede e sem I/O.

Tudo o que este arquivo faz e RECUSAR. Ele nao abre socket, nao le variavel de
ambiente e nao conhece o AdsPower; ele conhece a forma de um pedido legitimo e
diz nao para todo o resto, ANTES de o pedido sair da maquina.

## As cinco recusas, e por que cada uma existe

1. **Endereco.** So loopback literal. Um broker que aceita `local.adspower.net`
   depende de DNS para saber se esta falando com a propria maquina, e DNS e
   reconfiguravel por quem controla a rede. `127.0.0.1` nao e.
2. **Verificacao.** O guia de MCP do AdsPower ensina um modo com a verificacao
   da API desligada. O ADR de 28/08 recusa esse modo como configuracao VOLC.
   Aqui ele falha no preflight, com nome proprio.
3. **Acao.** Allowlist por NOME, com `muta` declarado por acao — nao inferido do
   verbo HTTP. No AdsPower `browser/start` e um GET, e ele abre um navegador.
4. **Perfil.** Allowlist explicita. Um broker que aceita qualquer `user_id` e um
   broker que qualquer processo local pode usar para tocar qualquer perfil.
5. **Resposta.** Projecao por allowlist, nunca filtro por blocklist. O
   `user/list` do AdsPower devolve o perfil INTEIRO — e o perfil guarda usuario,
   senha, cookie e chave de 2FA da conta que ele autentica. Um recibo montado
   por remocao de campos conhecidos copia todo campo que alguem adicionar
   depois; um recibo montado por projecao copia so o que foi nomeado aqui.

## O segredo

`Segredo` existe porque um `str` nao se defende. Ele aparece em `repr()` de
qualquer dataclass que o contenha, em `json.dumps` de qualquer recibo, no
traceback de qualquer excecao que o receba como argumento e no log de qualquer
`logging.debug("%s", pedido)`. `Segredo` recusa os quatro caminhos e obriga
quem precisa do valor a escrever `.revelar()` — que e uma linha auditavel.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
# `Mapping` vem de `collections.abc` e nao de `typing`: ele e usado em
# `isinstance`, e o alias de `typing` esta depreciado para esse uso desde 3.9.
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.asset_vault import dominio as cofre

# ── Estados tipados, com exit code proprio ──────────────────────────────────
#
# Mesmo contrato de `tools/onepassword-smoke/run.py`: um runner externo precisa
# distinguir "nao deu para tentar" de "tentou e vazou" sem parsear texto. Os
# codigos 10-19 sao bloqueio (nao e culpa do broker), 20-29 sao falha de
# seguranca, 30-39 sao recusa de contrato, 40+ e defeito interno.

ESTADOS: dict[str, int] = {
    "ok": 0,
    "blocked/segredo_ausente": 10,
    "blocked/segredo_nao_resolvido": 11,
    "blocked/cofre_trancado": 12,
    "blocked/local_api_ausente": 13,
    "blocked/exige_checkpoint": 14,
    "falha/vazamento": 20,
    "falha/resposta_ilegivel": 21,
    "falha/preflight": 30,
    "falha/conflito_de_idempotencia": 31,
    "falha/tempo_esgotado": 32,
    "falha/interna": 40,
}


class BrokerRecusado(ValueError):
    """O pedido nao pode virar chamada. A mensagem e para quem opera."""

    def __init__(self, mensagem: str, estado: str = "falha/preflight"):
        super().__init__(mensagem)
        self.estado = estado


class AcessoIndisponivel(RuntimeError):
    """O broker nao pode agir, e isso NAO vira resposta vazia.

    Mesma disciplina de `aplicacao.CofreIndisponivel`: um broker que responde
    "nenhum perfil" porque o segredo sumiu afirma um inventario vazio com a
    mesma cara com que afirmaria trinta perfis.
    """

    def __init__(self, mensagem: str, estado: str = "blocked/local_api_ausente"):
        super().__init__(mensagem)
        self.estado = estado


# ── O segredo que nao se deixa imprimir ─────────────────────────────────────


class Segredo:
    """Um valor que so sai por `.revelar()`, e nunca por acidente.

    ⚠️ O que esta classe NAO promete: apagar o valor da memoria. `str` em
    CPython e imutavel e interned; nao ha como zerar o buffer. A defesa e de
    superficie (log, recibo, traceback, serializacao), nao de memoria — e dizer
    isso aqui e melhor do que deixar alguem supor o contrario.
    """

    __slots__ = ("_valor",)

    def __init__(self, valor: str) -> None:
        self._valor = valor

    def revelar(self) -> str:
        """A UNICA porta de saida. Procure por `.revelar(` para auditar o uso."""
        return self._valor

    def __bool__(self) -> bool:
        return bool(self._valor)

    def __len__(self) -> int:
        # Comprimento vaza entropia (estreita o espaco de busca de quem procura
        # a chave). A mesma recusa que `tools/onepassword-smoke` ja faz.
        raise TypeError("o comprimento de um Segredo nao e observavel")

    def __repr__(self) -> str:
        return "<segredo omitido>"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return "<segredo omitido>"

    def __reduce__(self):
        raise TypeError("um Segredo nao pode ser serializado")

    # `__reduce__` sozinho fecharia pickle, e o `copy` chega nele por
    # `__reduce_ex__` — mas por um caminho que depende de detalhe do CPython.
    # Fechar os tres explicitamente nao depende de nada.
    def __copy__(self):
        raise TypeError("um Segredo nao pode ser copiado")

    def __deepcopy__(self, _memo):
        raise TypeError("um Segredo nao pode ser copiado")

    def __eq__(self, outro: object) -> bool:
        # Comparar com `str` responderia "achei" para quem esta adivinhando.
        # Comparar dois `Segredo` e legitimo e nao revela nada a terceiros.
        if isinstance(outro, Segredo):
            return self._valor == outro._valor
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]


#: Valores que sao evidentemente placeholder, e nao chave. Recusa-los aqui evita
#: o modo de falha mais chato de diagnosticar: o broker "funciona", o AdsPower
#: responde 401, e o operador procura o defeito na rede.
#: O vazio NAO esta nesta lista: ele ja e recusado antes, como ausencia, e com
#: outro estado (`blocked/segredo_ausente`). Repeti-lo aqui seria uma linha que
#: nunca executa.
_BEARER_PLACEHOLDER = frozenset({
    "changeme", "trocar", "preencher", "your-api-key", "api-key", "apikey",
    "none", "null", "undefined", "xxx", "todo",
})


def exigir_bearer(valor: str | None, *, nome_da_variavel: str) -> Segredo:
    """Fail closed: sem chave ativa nao existe modo degradado.

    O ramo do `op://` nao e teorico. `op run -- broker` com o cofre TRANCADO
    nao injeta: a variavel chega com a REFERENCIA literal, nao com o valor. Um
    broker que a mandasse como Bearer publicaria o endereco do item no log de
    acesso do AdsPower — o unico lugar onde ele nunca deveria estar.
    """
    if valor is None or not valor.strip():
        raise AcessoIndisponivel(
            f"a variavel {nome_da_variavel} nao chegou preenchida. Rode o broker sob "
            "`op run -- ...` com o 1Password destrancado; sem chave ativa nao ha modo "
            "degradado.",
            estado="blocked/segredo_ausente",
        )
    limpo = valor.strip()
    if limpo.startswith("op://"):
        raise AcessoIndisponivel(
            f"a variavel {nome_da_variavel} ainda contem a REFERENCIA, nao o valor: o "
            "1Password nao resolveu a injecao (cofre trancado ou aprovacao negada). "
            "O broker para aqui em vez de usar o endereco como se fosse a chave.",
            estado="blocked/segredo_nao_resolvido",
        )
    if limpo.lower() in _BEARER_PLACEHOLDER:
        raise BrokerRecusado(
            f"a variavel {nome_da_variavel} tem um valor de exemplo, nao uma chave.")
    return Segredo(limpo)


# ── Endereco: loopback literal, e nada mais ─────────────────────────────────

PORTA_PADRAO_ADSPOWER = 50325


def exigir_endereco_de_loopback(endereco: str) -> str:
    """So `http://<ip-de-loopback>:<porta>`. Devolve a forma canonica.

    Cada recusa tem motivo proprio:

    * **nome em vez de IP** — `local.adspower.net` e o endereco que a
      documentacao sugere, e ele resolve para 127.0.0.1 hoje. "Hoje" e a
      palavra: quem controla o resolvedor controla para onde o Bearer vai. Um
      literal nao depende de ninguem.
    * **`https`** — TLS num socket que nunca sai da maquina nao acrescenta
      fronteira, mas acrescenta um certificado para gerenciar; e certificado
      chato de gerenciar e como `verify=False` entra no codigo. O ADR recusa
      modo sem verificacao, e esta e a porta por onde ele voltaria.
    * **userinfo** — `http://usuario:senha@127.0.0.1` poe credencial na URL, e
      URL vai para log de proxy, historico e traceback.
    * **porta implicita** — silencio sobre a porta e como um broker acaba na 80.
    """
    bruto = (endereco or "").strip()
    if not bruto:
        raise BrokerRecusado("informe o endereco da Local API (ex.: http://127.0.0.1:50325).")
    partes = urlsplit(bruto)
    if partes.scheme != "http":
        raise BrokerRecusado(
            "o endereco da Local API precisa usar http em loopback. "
            "https aqui nao acrescenta fronteira e abre caminho para desligar a "
            "verificacao de certificado, que o ADR recusa.")
    if partes.username or partes.password:
        raise BrokerRecusado(
            "o endereco nao pode carregar usuario ou senha: URL vai para log, "
            "historico e traceback. A chave viaja no cabecalho Authorization.")
    if partes.path not in ("", "/") or partes.query or partes.fragment:
        raise BrokerRecusado(
            "o endereco da Local API e so esquema, host e porta — o caminho vem do "
            "catalogo de acoes, nao do operador.")
    try:
        # ⚠️ `.port` LEVANTA `ValueError` numa porta nao numerica, e o `ValueError`
        # cru nao e `BrokerRecusado`: ele escaparia do `except` do CLI e viraria
        # traceback em vez de recibo.
        porta = partes.port
    except ValueError:
        raise BrokerRecusado("a porta do endereco nao e um numero.") from None
    if porta is None:
        raise BrokerRecusado(
            f"informe a porta explicitamente (a padrao do AdsPower e {PORTA_PADRAO_ADSPOWER}).")
    hospedeiro = (partes.hostname or "").strip("[]")
    try:
        ip = ipaddress.ip_address(hospedeiro)
    except ValueError:
        raise BrokerRecusado(
            f"o host {hospedeiro!r} nao e um IP de loopback literal. Use 127.0.0.1: um "
            "nome depende de DNS para provar que a chamada nao sai da maquina, e DNS "
            "e reconfiguravel por quem controla a rede."
        ) from None
    if not ip.is_loopback:
        raise BrokerRecusado(
            "o broker so fala com loopback. Um sidecar alcancavel de fora da maquina "
            "transforma a Local API do AdsPower numa API publica autenticada por uma "
            "unica chave.")
    # IPv6 volta COM colchetes: `http://::1:50325` nao e URL, e uma forma
    # canonica que nenhum cliente HTTP aceita nao e canonica.
    literal = f"[{hospedeiro}]" if ip.version == 6 else hospedeiro
    return f"http://{literal}:{porta}"


#: Flags e variaveis que desligam a verificacao. O guia de MCP do AdsPower
#: ensina esse modo; o ADR de 28/08 o recusa como configuracao VOLC. A recusa
#: acontece no preflight porque depois de a chamada sair nao ha o que desfazer.
_MARCAS_DE_SEM_VERIFICACAO = (
    "--sem-verificacao", "--no-verify", "--insecure", "--disable-auth",
    "--no-auth", "--skip-verify", "--no-check-certificate", "--no-masking",
)
_ENV_DE_SEM_VERIFICACAO = (
    "ADSPOWER_SEM_VERIFICACAO", "ADSPOWER_NO_AUTH", "ADSPOWER_DISABLE_AUTH",
    "ADSPOWER_INSECURE", "VOLC_BROKER_SEM_VERIFICACAO",
)


def exigir_verificacao_ligada(argv: Iterable[str], ambiente: Mapping[str, str]) -> None:
    erros: list[str] = []
    for arg in argv:
        texto = str(arg)
        for marca in _MARCAS_DE_SEM_VERIFICACAO:
            if texto == marca or texto.startswith(marca + "="):
                erros.append(
                    f"flag proibida: {marca}. O ADR de 28/08/2026 recusa o modo com "
                    "verificacao desligada como configuracao de producao VOLC.")
    for chave in _ENV_DE_SEM_VERIFICACAO:
        valor = str(ambiente.get(chave, "")).strip().lower()
        if valor and valor not in ("0", "false", "nao", "no"):
            erros.append(
                f"variavel proibida: {chave}. Desligar a verificacao da Local API deixa "
                "qualquer processo da maquina tocar qualquer perfil.")
    if erros:
        raise BrokerRecusado(" | ".join(erros))


# ── Catalogo de acoes: allowlist com `muta` DECLARADO ───────────────────────


@dataclass(frozen=True)
class Acao:
    nome: str
    metodo: str
    caminho: str
    #: Declarado, nunca inferido do verbo. No AdsPower `browser/start` e um GET
    #: e abre um navegador; `user/delete` e um POST e apaga um perfil. O verbo
    #: HTTP descreve o transporte, nao o efeito.
    muta: bool
    exige_perfil: bool
    parametros: tuple[str, ...]
    descricao: str


#: As acoes LIBERADAS nesta versao: leitura, inventario e estado. Nenhuma abre
#: navegador, cria, altera ou apaga coisa alguma.
#:
#: ⚠️ PROCEDENCIA. Os caminhos vem da documentacao publica da Local API
#: (https://help.adspower.com/docs/api) citada no ADR de 28/08/2026. Eles NAO
#: foram exercitados contra um cliente AdsPower real nesta sessao — nao ha
#: instancia AdsPower nesta maquina. Se a versao do cliente mudar o caminho, a
#: falha e um 404 sanitizado, e nao um efeito inesperado: toda acao daqui e
#: nao-mutante por construcao.
ACOES: dict[str, Acao] = {
    "status": Acao(
        nome="status", metodo="GET", caminho="/status", muta=False,
        exige_perfil=False, parametros=(),
        descricao="A Local API esta no ar nesta maquina?"),
    "inventario_perfis": Acao(
        nome="inventario_perfis", metodo="GET", caminho="/api/v1/user/list", muta=False,
        exige_perfil=False, parametros=("page", "page_size", "group_id"),
        descricao="Quais perfis existem, com identidade e grupo — sem sessao e sem conta."),
    "inventario_grupos": Acao(
        nome="inventario_grupos", metodo="GET", caminho="/api/v1/group/list", muta=False,
        exige_perfil=False, parametros=("page", "page_size"),
        descricao="Quais grupos de perfil existem."),
    "estado_do_perfil": Acao(
        nome="estado_do_perfil", metodo="GET", caminho="/api/v1/browser/active", muta=False,
        exige_perfil=True, parametros=("user_id",),
        descricao="Este perfil ja esta aberto? Le o estado; nao abre e nao fecha."),
}

#: As acoes que EXISTEM no AdsPower, mutam, e por isso sao recusadas por nome.
#:
#: Recusar por nome e diferente de nao conhecer. "acao desconhecida" faria o
#: proximo supor erro de digitacao e tentar de novo; "esta acao exige
#: checkpoint" diz o que falta e a quem pedir.
ACOES_QUE_EXIGEM_CHECKPOINT: dict[str, str] = {
    "abrir_perfil": "abre um navegador real e inicia uma sessao autenticada (/api/v1/browser/start)",
    "fechar_perfil": "encerra uma sessao em andamento (/api/v1/browser/stop)",
    "criar_perfil": "cria um perfil no cliente AdsPower (/api/v1/user/create)",
    "atualizar_perfil": "altera um perfil existente (/api/v1/user/update)",
    "apagar_perfil": "apaga um perfil e a sessao dele (/api/v1/user/delete)",
    "criar_grupo": "cria um grupo de perfis (/api/v1/group/create)",
}


def exigir_acao(nome: str) -> Acao:
    acao = ACOES.get(nome)
    if acao is not None:
        return acao
    motivo = ACOES_QUE_EXIGEM_CHECKPOINT.get(nome)
    if motivo is not None:
        raise BrokerRecusado(
            f"a acao {nome} exige checkpoint de autorizacao: ela {motivo}. Esta versao "
            "do broker so pergunta — nao abre perfil, nao inicia navegador e nao "
            "altera nada.",
            estado="blocked/exige_checkpoint",
        )
    raise BrokerRecusado(
        f"acao desconhecida: {nome}. As permitidas sao: " + ", ".join(sorted(ACOES)))


def exigir_parametros(acao: Acao, parametros: Mapping[str, Any]) -> dict[str, str]:
    """So os nomes que a acao declara, e so valor escalar simples.

    Um parametro fora da lista nao e ignorado: e recusado. Ignorar em silencio e
    como `extra="forbid"` existe no Cofre — quem mandou acha que pegou.
    """
    sobrando = sorted(set(parametros) - set(acao.parametros))
    if sobrando:
        raise BrokerRecusado(
            f"a acao {acao.nome} nao aceita: {', '.join(sobrando)}. "
            f"Aceita: {', '.join(acao.parametros) or '(nenhum)'}.")
    saida: dict[str, str] = {}
    for chave, valor in parametros.items():
        if valor is None:
            continue
        if isinstance(valor, bool) or not isinstance(valor, (str, int)):
            raise BrokerRecusado(f"o parametro {chave} precisa ser texto ou inteiro.")
        texto = str(valor).strip()
        if not texto or len(texto) > 120 or not re.fullmatch(r"[A-Za-z0-9._:-]+", texto):
            raise BrokerRecusado(
                f"o parametro {chave} tem valor invalido: use ate 120 caracteres entre "
                "letras, digitos, '.', '_', ':' e '-'.")
        saida[chave] = texto
    return saida


# ── Perfil: identidade e allowlist ──────────────────────────────────────────

#: O `user_id` do AdsPower e um identificador curto do cliente local. Ele nao e
#: segredo — e inutil sem a chave da Local API, e por isso `display_id` do Cofre
#: o guarda inteiro (ver P03-T07). Mas ele tem de ter FORMA, senao qualquer
#: string vira caminho de query.
PERFIL = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def exigir_perfil(perfil: str | None, permitidos: Iterable[str]) -> str:
    lista = [p for p in permitidos if p]
    if not lista:
        raise BrokerRecusado(
            "nenhum perfil na allowlist. Um broker que aceita qualquer perfil e um "
            "broker que qualquer processo local pode usar para tocar qualquer sessao.")
    if not perfil or not PERFIL.match(perfil):
        raise BrokerRecusado(
            "identificador de perfil invalido: use ate 64 caracteres entre letras, "
            "digitos, '_' e '-'.")
    if perfil not in lista:
        # A mensagem NAO lista os permitidos: quem nao esta na allowlist tambem
        # nao precisa saber quem esta.
        raise BrokerRecusado(f"o perfil {perfil} nao esta na allowlist deste broker.")
    return perfil


# ── Tempo e ritmo ───────────────────────────────────────────────────────────

TIMEOUT_PADRAO_S = 12.0
TIMEOUT_MAXIMO_S = 60.0
#: A Local API do AdsPower documenta um limite de aproximadamente uma chamada
#: por segundo. Respeitar o limite e parte do contrato, nao gentileza: estourar
#: devolve erro que o broker leria como "AdsPower fora do ar".
INTERVALO_MINIMO_S = 1.0


def exigir_timeout(valor: float | None) -> float:
    if valor is None:
        return TIMEOUT_PADRAO_S
    try:
        segundos = float(valor)
    except (TypeError, ValueError):
        raise BrokerRecusado("o timeout precisa ser um numero de segundos.") from None
    if not (0.5 <= segundos <= TIMEOUT_MAXIMO_S):
        raise BrokerRecusado(
            f"o timeout precisa ficar entre 0.5 e {TIMEOUT_MAXIMO_S:g} segundos. "
            "Sem limite superior, um sidecar travado vira um job travado.")
    return segundos


# ── Idempotencia ────────────────────────────────────────────────────────────


def exigir_chave_de_idempotencia(valor: str) -> str:
    """A mesma gramatica do Cofre, de proposito.

    Duas gramaticas para a mesma ideia produzem uma chave que o broker aceita e
    o Cofre recusa — e o recibo do broker precisa virar verificacao no Cofre.

    ⚠️ A EXCECAO e traduzida. Reaproveitar a regra sem traduzir o erro faria
    `PayloadRecusado` — o vocabulario do Cofre — subir por um `except` que so
    conhece `BrokerRecusado`, e a recusa mais comum do CLI viraria traceback.
    """
    try:
        return cofre.exigir_chave_de_idempotencia(valor)
    except cofre.PayloadRecusado as exc:
        raise BrokerRecusado(str(exc)) from None


def impressao_digital(acao: str, perfil: str | None, parametros: Mapping[str, str],
                      endereco: str) -> str:
    """Identidade do PEDIDO, para a chave de idempotencia poder ser conferida.

    Deriva de conteudo, nunca de relogio — pela mesma razao de `chaveDoAto` no
    frontend: um retry que gera identidade nova deixa de ser retry.
    """
    canonico = json.dumps(
        {"acao": acao, "perfil": perfil, "parametros": dict(sorted(parametros.items())),
         "endereco": endereco},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def forma_da_referencia(localizador: str | None) -> dict[str, Any]:
    """So a FORMA e um digest — nunca os segmentos.

    Mesma disciplina de `tools/onepassword-smoke.forma_da_referencia`. O digest
    e de LOCALIZADOR, nao de segredo: ele correlaciona duas execucoes sem abrir
    caminho para adivinhar valor nenhum. Cofre, item e campo nao saem daqui.
    """
    if not localizador:
        return {"presente": False}
    corpo = localizador[len("op://"):] if localizador.startswith("op://") else localizador
    corpo, _, query = corpo.partition("?")
    segmentos = [s for s in corpo.split("/") if s]
    return {
        "presente": True,
        "esquema_op": localizador.startswith("op://"),
        "segmentos": len(segmentos),
        "tem_secao": len(segmentos) == 4,
        "tem_query": bool(query),
        "digest": hashlib.sha256(localizador.encode("utf-8")).hexdigest()[:16],
    }


# ── Sanitizacao da resposta: projecao, nao filtro ───────────────────────────

_REDACAO = "<omitido>"
_LIMITE_DE_TEXTO = 160


def redigir(valor: Any) -> str | None:
    """Texto livre vindo do AdsPower, sem material reconhecivel de credencial.

    `name` e `remark` de um perfil sao escritos por gente, e gente as vezes cola
    coisa errada ali. Recusar o inventario inteiro por causa disso seria pior do
    que redigir: o operador perderia a unica lista que ele tem.
    """
    if valor is None:
        return None
    texto = " ".join(str(valor).split())
    if not texto:
        return None
    texto = cofre.MATERIAL_DE_CREDENCIAL.sub(_REDACAO, texto)
    if len(texto) > _LIMITE_DE_TEXTO:
        texto = texto[:_LIMITE_DE_TEXTO] + "…"
    return texto


#: Os UNICOS campos de um perfil que entram num recibo VOLC.
#:
#: ⚠️ Isto e uma projecao, e a diferenca importa. O `user/list` do AdsPower
#: devolve o perfil inteiro, e o perfil guarda a CONTA que ele autentica:
#: usuario, senha, cookie e chave de 2FA da plataforma. Uma sanitizacao por
#: remocao ("tire `password`, `cookie` e `fakey`") copia todo campo novo que o
#: AdsPower adicionar numa versao futura. Uma projecao copia o que esta escrito
#: aqui, e nada mais — inclusive `remark`, que fica de fora de proposito por ser
#: campo livre sem funcao de identidade.
CAMPOS_DE_PERFIL: tuple[str, ...] = (
    "user_id", "serial_number", "name", "group_id", "group_name",
    "domain_name", "created_time",
)
CAMPOS_DE_GRUPO: tuple[str, ...] = ("group_id", "group_name")


def _escalar(valor: Any) -> Any:
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, (int, float)):
        return valor
    return redigir(valor)


def projetar_perfil(bruto: Any) -> dict[str, Any]:
    if not isinstance(bruto, Mapping):
        raise AcessoIndisponivel(
            "a Local API respondeu um perfil em forma inesperada.",
            estado="falha/resposta_ilegivel")
    projetado: dict[str, Any] = {c: _escalar(bruto.get(c)) for c in CAMPOS_DE_PERFIL}
    # Booleano, nunca a configuracao. Host, porta, usuario e senha do proxy sao
    # exatamente o tipo de dado que o ADR mantem fora do Cofre e do recibo.
    proxy = bruto.get("user_proxy_config")
    tipo = proxy.get("proxy_soft") if isinstance(proxy, Mapping) else None
    projetado["tem_proxy"] = bool(proxy) and str(tipo or "").lower() not in ("", "no_proxy")
    return projetado


def projetar_grupo(bruto: Any) -> dict[str, Any]:
    if not isinstance(bruto, Mapping):
        raise AcessoIndisponivel(
            "a Local API respondeu um grupo em forma inesperada.",
            estado="falha/resposta_ilegivel")
    return {c: _escalar(bruto.get(c)) for c in CAMPOS_DE_GRUPO}


def projetar_resposta(acao: Acao, bruto: Any) -> dict[str, Any]:
    """Traduz a resposta da Local API para o vocabulario do recibo.

    Nada aqui devolve o corpo cru. Um recibo que carrega `resposta_bruta` "para
    depurar depois" e o caminho mais curto para uma senha de perfil acabar num
    arquivo versionado.
    """
    if not isinstance(bruto, Mapping):
        raise AcessoIndisponivel(
            "a Local API respondeu em forma inesperada.", estado="falha/resposta_ilegivel")
    codigo = bruto.get("code")
    dados = bruto.get("data")
    saida: dict[str, Any] = {
        "codigo": codigo if isinstance(codigo, int) else None,
        "mensagem": redigir(bruto.get("msg")),
    }
    if acao.nome == "inventario_perfis":
        lista = dados.get("list") if isinstance(dados, Mapping) else dados
        if lista is None:
            lista = []
        if not isinstance(lista, list):
            raise AcessoIndisponivel(
                "a Local API respondeu o inventario em forma inesperada.",
                estado="falha/resposta_ilegivel")
        saida["perfis"] = [projetar_perfil(p) for p in lista]
        saida["total"] = len(saida["perfis"])
    elif acao.nome == "inventario_grupos":
        lista = dados.get("list") if isinstance(dados, Mapping) else dados
        if lista is None:
            lista = []
        if not isinstance(lista, list):
            raise AcessoIndisponivel(
                "a Local API respondeu os grupos em forma inesperada.",
                estado="falha/resposta_ilegivel")
        saida["grupos"] = [projetar_grupo(g) for g in lista]
        saida["total"] = len(saida["grupos"])
    elif acao.nome == "estado_do_perfil":
        estado = dados.get("status") if isinstance(dados, Mapping) else None
        # ⚠️ Tres valores, e `desconhecido` NAO e `fechado`. A Local API responde
        # "Active"/"Inactive"; qualquer outra coisa e ausencia de resposta, e
        # achatar ausencia em "fechado" e como o QA visual conclui que o perfil
        # esta livre e abre um segundo navegador sobre a mesma sessao.
        normal = str(estado or "").strip().lower()
        saida["aberto"] = True if normal == "active" else (False if normal == "inactive" else None)
    elif acao.nome == "status":
        saida["no_ar"] = codigo == 0
    return saida


def recusar_vazamento(recibo: Mapping[str, Any]) -> None:
    """Ultima peneira antes de o recibo virar arquivo, log ou resposta.

    Mesma linha que `infraestrutura.executar` ja tem no Cofre, e pela mesma
    razao: a lista de campos projetados envelhece quando alguem adiciona um
    campo novo, e esta varredura nao depende de ninguem lembrar.
    """
    try:
        cofre.recusar_chave_sensivel(recibo, "recibo")
    except cofre.PayloadRecusado as exc:
        # Traduzida, e nao repassada: quem chama esta funcao trata
        # `BrokerRecusado`, e um vazamento e a ultima coisa que pode escapar
        # como excecao de outra familia.
        raise BrokerRecusado(str(exc), estado="falha/vazamento") from None
    serializado = json.dumps(recibo, ensure_ascii=False, default=str)
    if cofre.MATERIAL_DE_CREDENCIAL.search(serializado):
        raise BrokerRecusado(
            "o recibo contem material que parece credencial e foi descartado inteiro. "
            "O valor nao e repetido aqui de proposito.",
            estado="falha/vazamento")
