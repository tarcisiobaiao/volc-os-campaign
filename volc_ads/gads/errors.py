"""Classificação de erros da Google Ads API — e preservação da evidência.

O ponto central do anti-falha: um erro da Google Ads API não é "um erro".
São três classes com tratamentos opostos, e confundi-las é o que produz
tanto retry inútil quanto — pior — retry perigoso.

  TRANSIENT  → retenta com backoff. Falha de infra, não sua.
  THROTTLED  → retenta, mas respeitando o retry_delay que a própria API manda.
  TERMINAL   → NUNCA retenta. O payload está errado ou a política foi violada;
               retentar só queima cota e, no caso de política, chama atenção.

## O que este arquivo passou a preservar, e por quê

A versão anterior lia `error_code`, `field_path` e `message[:400]`. Três coisas
se perdiam nesse caminho, e as três são pré-requisito de qualquer autocorreção:

1. **O índice.** `ErrorLocation.FieldPathElement` tem `field_name` E `index`.
   Só o `field_name` era lido, então
   `mutate_operations[12]...headlines[3].text` virava
   `mutate_operations.headlines.text`. Num mutate atômico de ~70 operações
   isso significa saber que ALGO violou e não saber O QUÊ — e a cascata de
   regeneração precisa regenerar UM asset, não o conjunto.

2. **`err.details`.** É onde vivem `policy_violation_details` (com
   `is_exemptible` e a `PolicyViolationKey`) e `policy_finding_details` (com
   os `policy_topic_entries`). Sem eles, pedir isenção é estruturalmente
   impossível — capacidade que o flow n8n tinha e que se perdeu na migração.

3. **`err.trigger`.** O valor que disparou o erro, que a API entrega mastigado.

## Dois formatos de erro de política, dois remédios distintos

Eles não são sinônimos e a API os trata em campos diferentes da requisição:

  policy_violation_error → `PolicyViolationDetails`, com `key`
                           (policy_name + violating_text) e `is_exemptible`.
                           Remédio: `exempt_policy_violation_keys` no
                           AdGroupAdOperation, com a chave EXATA.

  policy_finding_error   → `PolicyFindingDetails`, com `policy_topic_entries`
                           (topic + type_ + evidences). Não tem chave.
                           Remédio: `ignorable_policy_topics`, com o `topic`.

Passar a chave onde se espera o tópico não faz nada — falha silenciosamente e
o anúncio continua reprovado. Por isso `Politica.remedio` nomeia o campo certo
em vez de deixar a decisão para quem chama.

**Nada aqui pede isenção.** Este módulo só preserva a evidência para que a
decisão seja possível e auditável. Pedir isenção é escrita, e a trava de
`modo.py` continua fechada.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field

# Truncamento de exibição. A mensagem CRUA é guardada inteira em
# `ErroGads.mensagem`: quem corta é quem imprime, não quem classifica. O
# limite antigo de 400 caracteres cortava a descrição externa de política
# no meio exatamente nos casos em que ela era a única pista acionável.
MAX_MSG_RESUMO = 400
MAX_MSG_DETALHE = 2000


class Classe(enum.Enum):
    TRANSIENT = "transient"
    THROTTLED = "throttled"
    TERMINAL = "terminal"


# Códigos gRPC que indicam falha de transporte/infra — sempre retentáveis.
_GRPC_TRANSIENT = {
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
    "INTERNAL",
    "ABORTED",
}

# Nomes de campo de erro (dentro de GoogleAdsFailure.errors[].error_code)
# que representam condição temporária do lado do Google.
_ERRO_TRANSIENT = {
    "internal_error",
    "database_error",
}

# Valores de enum que indicam concorrência/transitório mesmo dentro de
# um campo que normalmente seria terminal.
_VALOR_TRANSIENT = {
    "CONCURRENT_MODIFICATION",
    "TRANSIENT_ERROR",
    "INTERNAL_ERROR",
    "DEADLINE_EXCEEDED",
    "RESOURCE_TEMPORARILY_EXHAUSTED",
}

_ERRO_THROTTLED = {"quota_error"}
_VALOR_THROTTLED = {"RESOURCE_EXHAUSTED", "RESOURCE_TEMPORARILY_EXHAUSTED"}

# Os dois códigos de política. Ambos TERMINAIS — o que muda é o REMÉDIO, e é
# por isso que eles têm nome próprio aqui em vez de sumirem no conjunto abaixo.
ERRO_POLITICA_VIOLACAO = "policy_violation_error"
ERRO_POLITICA_ACHADO = "policy_finding_error"

# Erros que jamais devem ser retentados, nem com backoff infinito.
_ERRO_TERMINAL = {
    "authentication_error",
    "authorization_error",
    ERRO_POLITICA_VIOLACAO,
    ERRO_POLITICA_ACHADO,
    "request_error",
    "field_error",
    "field_mask_error",
    "mutate_error",
    "not_empty_error",
    "operation_access_denied_error",
    "resource_access_denied_error",
    "size_limit_error",
    "string_length_error",
    "url_field_error",
}


# ── evidência de política ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ChavePolitica:
    """`PolicyViolationKey` — o par exato que a isenção exige.

    `violating_text` é a string que violou, palavra por palavra. É a coisa
    mais valiosa deste arquivo para a cascata de copy: identifica o asset
    reprovado sem depender do índice do field_path.
    """

    policy_name: str
    violating_text: str

    def __str__(self) -> str:
        return f"{self.policy_name}({self.violating_text!r})"


@dataclass(frozen=True)
class TopicoPolitica:
    """`PolicyTopicEntry` — o que `ignorable_policy_topics` recebe.

    Só o `topico` entra no campo de remédio; `tipo` e `evidencias` existem
    para o operador entender o que está aceitando ignorar. PROHIBITED nunca
    é ignorável — ignorar um tópico proibido não o torna publicável.
    """

    topico: str
    tipo: str = ""
    evidencias: tuple[str, ...] = ()
    restricoes: tuple[str, ...] = ()

    @property
    def ignoravel(self) -> bool:
        return self.tipo not in ("PROHIBITED", "UNKNOWN", "UNSPECIFIED", "")


@dataclass(frozen=True)
class Politica:
    """A evidência de política de UM erro, nos dois formatos possíveis."""

    formato: str  # "violacao" | "achado"
    descricao_externa: str = ""
    nome_externo: str = ""
    isentavel: bool | None = None
    chave: ChavePolitica | None = None
    topicos: tuple[TopicoPolitica, ...] = ()

    @property
    def remedio(self) -> str:
        """O campo da requisição que trataria este erro — ou por que não há um.

        Nomear o campo aqui evita o erro silencioso de passar uma chave onde
        se espera um tópico: a API aceita a requisição e não isenta nada.
        """
        if self.formato == "violacao":
            if self.isentavel is False:
                return "nenhum — is_exemptible=False"
            if self.chave is None:
                return "nenhum — violation sem PolicyViolationKey"
            return "exempt_policy_violation_keys"
        if self.formato == "achado":
            if not any(t.ignoravel for t in self.topicos):
                return "nenhum — nenhum tópico ignorável (PROHIBITED)"
            return "ignorable_policy_topics"
        return "nenhum"

    @property
    def textos_violadores(self) -> tuple[str, ...]:
        """Toda string que a API apontou como causa, sem repetir.

        Vem da `PolicyViolationKey.violating_text` e das evidências de texto
        dos tópicos. É por aqui que a cascata acha o asset a regenerar.
        """
        vistos: list[str] = []
        if self.chave is not None and self.chave.violating_text:
            vistos.append(self.chave.violating_text)
        for t in self.topicos:
            for ev in t.evidencias:
                if ev and ev not in vistos:
                    vistos.append(ev)
        return tuple(vistos)

    def resumo(self) -> str:
        if self.formato == "violacao":
            isento = {True: "isentável", False: "NÃO isentável", None: "isenção ?"}[
                self.isentavel
            ]
            alvo = f" → {self.chave}" if self.chave else ""
            return f"violação[{isento}] {self.nome_externo or '?'}{alvo}"
        topicos = ", ".join(f"{t.topico}:{t.tipo}" for t in self.topicos) or "?"
        return f"achado[{topicos}]"


# ── erro individual ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ErroGads:
    """Um erro individual dentro de um GoogleAdsFailure."""

    campo_codigo: str  # ex.: "quota_error"
    valor_codigo: str  # ex.: "RESOURCE_EXHAUSTED"
    mensagem: str      # CRUA e inteira — quem trunca é quem imprime
    caminho_campo: str = ""  # ex.: "mutate_operations[12].create.ad...headlines[3].text"
    indice_operacao: int | None = None  # a posição no mutate atômico
    gatilho: str = ""   # err.trigger, o valor que disparou
    politica: Politica | None = None

    @property
    def classe(self) -> Classe:
        if self.campo_codigo in _ERRO_THROTTLED or self.valor_codigo in _VALOR_THROTTLED:
            return Classe.THROTTLED
        if self.campo_codigo in _ERRO_TRANSIENT or self.valor_codigo in _VALOR_TRANSIENT:
            return Classe.TRANSIENT
        if self.campo_codigo in _ERRO_TERMINAL:
            return Classe.TERMINAL
        # Desconhecido: tratamos como terminal por segurança. Retentar um erro
        # que não sabemos classificar é como insistir numa porta trancada.
        return Classe.TERMINAL

    @property
    def de_politica(self) -> bool:
        return self.campo_codigo in (ERRO_POLITICA_VIOLACAO, ERRO_POLITICA_ACHADO)

    def resumo(self) -> str:
        loc = f" @{self.caminho_campo}" if self.caminho_campo else ""
        pol = f" [{self.politica.resumo()}]" if self.politica else ""
        return (
            f"{self.campo_codigo}.{self.valor_codigo}{loc}{pol}: "
            f"{self.mensagem[:MAX_MSG_RESUMO]}"
        )

    def detalhe(self) -> str:
        linhas = [f"{self.campo_codigo}.{self.valor_codigo}"]
        if self.caminho_campo:
            linhas.append(f"  campo:   {self.caminho_campo}")
        if self.indice_operacao is not None:
            linhas.append(f"  operação: [{self.indice_operacao}]")
        if self.gatilho:
            linhas.append(f"  gatilho: {self.gatilho!r}")
        linhas.append(f"  mensagem: {self.mensagem[:MAX_MSG_DETALHE]}")
        if self.politica:
            p = self.politica
            linhas.append(f"  política: {p.resumo()}")
            if p.descricao_externa:
                linhas.append(f"    descrição: {p.descricao_externa[:MAX_MSG_DETALHE]}")
            linhas.append(f"    remédio:   {p.remedio}")
            for t in p.textos_violadores:
                linhas.append(f"    violou:    {t!r}")
        return "\n".join(linhas)


@dataclass(frozen=True)
class FalhaGads:
    """Resultado da classificação de uma GoogleAdsException inteira."""

    erros: tuple[ErroGads, ...] = field(default_factory=tuple)
    request_id: str = ""
    retry_apos_s: float | None = None

    @property
    def classe(self) -> Classe:
        """A classe da falha é a mais restritiva entre seus erros.

        Se qualquer erro for TERMINAL, a requisição inteira é terminal —
        retentar reenviaria o operation inválido junto com os válidos.
        """
        classes = {e.classe for e in self.erros}
        if not classes or Classe.TERMINAL in classes:
            return Classe.TERMINAL
        if Classe.THROTTLED in classes:
            return Classe.THROTTLED
        return Classe.TRANSIENT

    @property
    def retentavel(self) -> bool:
        return self.classe in (Classe.TRANSIENT, Classe.THROTTLED)

    # ── evidência agregada, que é o que a cascata consome ───────────────────

    @property
    def de_politica(self) -> bool:
        """Verdadeiro se ALGUM erro é de política.

        Distinto de `classe is TERMINAL`: um `string_length_error` também é
        terminal, e ele é defeito de FORMA — conserta-se sem LLM e sem
        regenerar nada. Confundir os dois faz a cascata gastar geração num
        problema que uma contagem de caracteres resolvia.
        """
        return any(e.de_politica for e in self.erros)

    @property
    def politicas(self) -> tuple[Politica, ...]:
        return tuple(e.politica for e in self.erros if e.politica is not None)

    @property
    def textos_violadores(self) -> tuple[str, ...]:
        vistos: list[str] = []
        for p in self.politicas:
            for t in p.textos_violadores:
                if t not in vistos:
                    vistos.append(t)
        return tuple(vistos)

    @property
    def chaves_isentaveis(self) -> tuple[ChavePolitica, ...]:
        """As chaves que `exempt_policy_violation_keys` aceitaria.

        Só as marcadas `is_exemptible=True`. Pedir isenção de uma violação
        não isentável é requisição rejeitada, não anúncio publicado.
        """
        return tuple(
            p.chave
            for p in self.politicas
            if p.formato == "violacao" and p.isentavel and p.chave is not None
        )

    @property
    def topicos_ignoraveis(self) -> tuple[str, ...]:
        vistos: list[str] = []
        for p in self.politicas:
            if p.formato != "achado":
                continue
            for t in p.topicos:
                if t.ignoravel and t.topico not in vistos:
                    vistos.append(t.topico)
        return tuple(vistos)

    def resumo(self) -> str:
        return " | ".join(e.resumo() for e in self.erros)

    def detalhe(self) -> str:
        cabeca = f"request_id={self.request_id or '?'} classe={self.classe.value}"
        return "\n".join([cabeca, *(e.detalhe() for e in self.erros)])


_RETRY_DELAY_RE = re.compile(r"retry.{0,12}?(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def classificar(exc: Exception) -> FalhaGads:
    """Converte uma GoogleAdsException em FalhaGads classificada.

    Aceita qualquer exceção: se não for uma GoogleAdsException reconhecível,
    devolve uma falha TERMINAL com a mensagem crua — o chamador nunca fica
    sem resposta, e o default é o seguro (não retentar).
    """
    failure = getattr(exc, "failure", None)
    request_id = str(getattr(exc, "request_id", "") or "")

    if failure is None:
        nome = type(exc).__name__
        classe_grpc = _codigo_grpc(exc)
        valor = classe_grpc if classe_grpc in _GRPC_TRANSIENT else ""
        return FalhaGads(
            erros=(
                ErroGads(
                    campo_codigo="internal_error" if valor else "request_error",
                    valor_codigo=valor or nome,
                    mensagem=str(exc),
                ),
            ),
            request_id=request_id,
        )

    erros: list[ErroGads] = []
    retry_apos: float | None = None

    for err in failure.errors:
        campo, valor = _extrair_codigo(err.error_code)
        caminho, indice = _extrair_local(err)
        erros.append(
            ErroGads(
                campo_codigo=campo,
                valor_codigo=valor,
                mensagem=str(getattr(err, "message", "")),
                caminho_campo=caminho,
                indice_operacao=indice,
                gatilho=_extrair_gatilho(err),
                politica=_extrair_politica(err),
            )
        )
        if retry_apos is None:
            retry_apos = _extrair_retry_delay(err)

    return FalhaGads(
        erros=tuple(erros), request_id=request_id, retry_apos_s=retry_apos
    )


def _extrair_codigo(error_code) -> tuple[str, str]:
    """Descobre qual dos ~150 campos do oneof ErrorCode está preenchido."""
    try:
        campo = error_code._pb.WhichOneof("error_code")
    except Exception:
        campo = None
    if not campo:
        return ("request_error", "UNKNOWN")
    valor = getattr(error_code, campo, None)
    nome = getattr(valor, "name", None) or str(valor)
    return (campo, nome)


def _extrair_local(err) -> tuple[str, int | None]:
    """Monta o caminho do campo PRESERVANDO o índice de cada elemento.

    `FieldPathElement` tem `field_name` e `index`, e `index` é opcional — o
    valor 0 não distinguível da ausência se lido direto, daí o `HasField`.
    Sem o índice, `headlines[3].text` vira `headlines` e a cascata perde o
    único ponteiro que tinha para o asset reprovado.

    Devolve também o índice da operação de topo do mutate atômico, que é o
    que localiza a operação dentro das ~70 do grafo.
    """
    location = getattr(err, "location", None)
    elementos = getattr(location, "field_path_elements", None) or []

    partes: list[str] = []
    indice_op: int | None = None

    for p in elementos:
        nome = str(getattr(p, "field_name", "") or "")
        if not nome:
            continue
        idx = _indice(p)
        partes.append(f"{nome}[{idx}]" if idx is not None else nome)
        if indice_op is None and idx is not None and nome.endswith("operations"):
            indice_op = idx

    return ".".join(partes), indice_op


def _indice(elemento) -> int | None:
    """`index` é proto3 optional: 0 e ausente são indistinguíveis sem HasField."""
    try:
        if elemento._pb.HasField("index"):
            return int(elemento.index)
    except Exception:
        pass
    return None


def _extrair_gatilho(err) -> str:
    """`err.trigger` é um `Value` com oneof — devolve o preenchido, como texto."""
    trigger = getattr(err, "trigger", None)
    if trigger is None:
        return ""
    try:
        campo = trigger._pb.WhichOneof("value")
    except Exception:
        campo = None
    if not campo:
        return ""
    return str(getattr(trigger, campo, "") or "")


def _extrair_politica(err) -> Politica | None:
    """Lê `err.details` nos dois formatos de política.

    O padrão de navegação é o mesmo de `_extrair_retry_delay`: `details` é um
    oneof-ish de sub-mensagens e a ausência é o caso comum, então tudo é
    `getattr` defensivo. Um erro que não é de política devolve None e a
    cascata trata como defeito de forma.
    """
    detalhes = getattr(err, "details", None)
    if detalhes is None:
        return None

    violacao = getattr(detalhes, "policy_violation_details", None)
    if violacao is not None and _preenchido(detalhes, "policy_violation_details"):
        bruta = getattr(violacao, "key", None)
        chave = None
        if bruta is not None:
            nome = str(getattr(bruta, "policy_name", "") or "")
            texto = str(getattr(bruta, "violating_text", "") or "")
            if nome or texto:
                chave = ChavePolitica(policy_name=nome, violating_text=texto)
        return Politica(
            formato="violacao",
            descricao_externa=str(
                getattr(violacao, "external_policy_description", "") or ""
            ),
            nome_externo=str(getattr(violacao, "external_policy_name", "") or ""),
            isentavel=bool(getattr(violacao, "is_exemptible", False)),
            chave=chave,
        )

    achado = getattr(detalhes, "policy_finding_details", None)
    if achado is not None and _preenchido(detalhes, "policy_finding_details"):
        topicos = tuple(
            TopicoPolitica(
                topico=str(getattr(entrada, "topic", "") or ""),
                tipo=_nome_enum(getattr(entrada, "type_", None)),
                evidencias=_evidencias(entrada),
                restricoes=_restricoes(entrada),
            )
            for entrada in (getattr(achado, "policy_topic_entries", None) or [])
        )
        if topicos:
            return Politica(formato="achado", topicos=topicos)

    return None


def _preenchido(mensagem, campo: str) -> bool:
    """`details` traz sub-mensagens vazias por padrão; HasField separa as reais."""
    try:
        return bool(mensagem._pb.HasField(campo))
    except Exception:
        # Sem `_pb` (mocks de teste, dicionários): presença do atributo basta.
        return getattr(mensagem, campo, None) is not None


def _nome_enum(valor) -> str:
    return str(getattr(valor, "name", None) or (valor if valor is not None else "") or "")


def _evidencias(entrada) -> tuple[str, ...]:
    """Só as evidências de TEXTO — as outras não apontam para um asset.

    `PolicyTopicEvidence` tem seis formatos (website_list, text_list,
    language_code, destination_text_list, destination_mismatch,
    destination_not_working). `text_list.texts` é o único que nomeia a string
    do anúncio, e é dele que a cascata precisa.
    """
    out: list[str] = []
    for ev in getattr(entrada, "evidences", None) or []:
        lista = getattr(ev, "text_list", None)
        for t in getattr(lista, "texts", None) or []:
            texto = str(t or "")
            if texto and texto not in out:
                out.append(texto)
    return tuple(out)


def _restricoes(entrada) -> tuple[str, ...]:
    """Nome do tipo de restrição — país exigido, certificado faltando, revenda.

    Não é acionável por texto (nenhuma reescrita resolve "falta certificado"),
    mas é exatamente o que distingue "a copy está errada" de "a CONTA não está
    habilitada" — a decisão aberta do brief do FGTS, em forma de evidência.
    """
    out: list[str] = []
    for c in getattr(entrada, "constraints", None) or []:
        try:
            nome = c._pb.WhichOneof("value")
        except Exception:
            nome = None
        if nome and nome not in out:
            out.append(nome)
    return tuple(out)


def _extrair_retry_delay(err) -> float | None:
    """Lê o retry_delay que a API manda em erros de cota, quando presente."""
    detalhes = getattr(err, "details", None)
    quota = getattr(detalhes, "quota_error_details", None) if detalhes else None
    if quota is not None:
        delay = getattr(quota, "retry_delay", None)
        segundos = getattr(delay, "seconds", None)
        if segundos:
            return float(segundos)
    m = _RETRY_DELAY_RE.search(str(getattr(err, "message", "")))
    return float(m.group(1)) if m else None


def _codigo_grpc(exc: Exception) -> str:
    for attr in ("code", "grpc_status_code"):
        valor = getattr(exc, attr, None)
        if callable(valor):
            try:
                valor = valor()
            except Exception:
                valor = None
        nome = getattr(valor, "name", None)
        if nome:
            return str(nome)
    return ""
