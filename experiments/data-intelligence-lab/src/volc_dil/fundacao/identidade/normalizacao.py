"""Normalização de UTM idêntica à do VOLC Sensor v3 e do WEBS Wrapper v2.

Origem (lida, não importada; nenhuma das duas existe em `main`):

- Sensor: `wip/historico-measurement-20261015` (918e9571),
  `measurement/gtm/volc-sensor-v3.html`, sha256 `cb018224…a41e4`
  (idêntico ao arquivo não rastreado do checkout histórico `volc-os-campaign/`):
  `PII` em :69-74, `clean()` em :75-79, `utmValue()` em :107-112,
  `campaign()` em :116-135.
- Wrapper: mesmo ref, `measurement/gtm/webs-wrapper-v2.html`, sha256 `bbd4c821…ed699`:
  `PII` em :34-39, `safeValue()` em :74-80.

A equivalência é provada contra vetores-ouro gerados executando o JavaScript real
em Node (`docs/data-intelligence/fundacao-20261016/receipts/identidade/`).

Ressalva Unicode (R1-F24): "idêntica" vale até o Unicode 15.1 do `unicodedata` do CPython 3.13.
O Node 26 usa Unicode 17; para caracteres atribuídos no Unicode 16/17, `toLowerCase`/`NFD` podem
divergir (o revisor mediu 3.536 de 4.000 vetores desse recorte divergentes; 0 de 6.003 até 15.1).
O navegador do visitante usa o Unicode do seu próprio motor — nenhuma réplica é exata para todos.
UTMs de campanha são ASCII na prática; para um valor fora do 15.1, trate a chave como probabilística.

Fidelidade a JavaScript que o Python não dá de graça (e que os vetores cobrem):

- `\\s` do JS ≠ `\\s` do Python (JS inclui U+FEFF; Python inclui U+001C–U+001F e U+0085);
- `\\d` do JS é só ASCII; `[a-z]` com `/i` não casa `K` (Kelvin) nem `ſ`;
- `String.prototype.slice` corta em unidades UTF-16, não em code points;
- `URLSearchParams` decodifica `+` como espaço e troca UTF-8 inválido por U+FFFD.
"""
from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.parse import unquote

#: Conjunto exato de `\s`/`trim()` do JavaScript (ECMAScript WhiteSpace + LineTerminator).
JS_WS = "\t\n\u000b\u000c\r    -     　﻿"
_WS_RUN = re.compile(f"[{JS_WS}]+")
_WS_TRIM = re.compile(f"^[{JS_WS}]+|[{JS_WS}]+$")
_NOT_WS_AT = f"[^{JS_WS}@]"

#: Limites do sensor (CFG e utmValue).
LIMITE_VALOR_UTM = 40  # .slice(0, 40) — regra de key-value do Ad Manager
LIMITE_CHECAGEM_PII = 200  # clean(v, 200): acima disto o valor é DESCARTADO, não truncado
CHAVES_UTM_SENSOR = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
CLICK_IDS_SENSOR = ("gclid", "gbraid", "wbraid")

_CHARS_PROIBIDOS = re.compile(r"[\"'=!+#*~;^()<>\[\],]")
_MARCAS = re.compile("[̀-ͯ]")

# PII do sensor (com \b, flag g; replace troca por '[x]').
_PII_SENSOR = (
    re.compile(f"{_NOT_WS_AT}+@{_NOT_WS_AT}+\\.[a-z]{{2,}}", re.IGNORECASE | re.ASCII),
    re.compile(r"\b[0-9]{2}\.?[0-9]{3}\.?[0-9]{3}/?[0-9]{4}-?[0-9]{2}\b", re.ASCII),
    re.compile(r"\b[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}\b", re.ASCII),
    re.compile(f"\\+?[0-9][0-9{JS_WS}().-]{{8,}}[0-9]"),
)
# PII do wrapper (sem \b, sem g; só .test()).
_PII_WRAPPER = (
    re.compile(f"{_NOT_WS_AT}+@{_NOT_WS_AT}+\\.[a-z]{{2,}}", re.IGNORECASE | re.ASCII),
    re.compile(r"[0-9]{2}\.?[0-9]{3}\.?[0-9]{3}/?[0-9]{4}-?[0-9]{2}"),
    re.compile(r"[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}"),
    re.compile(f"\\+?[0-9][0-9{JS_WS}().-]{{8,}}[0-9]"),
)

#: Regex de "telefone" que descarta qualquer sequência de >= 10 dígitos — inclusive
#: `campaign.id` (11 dígitos) e `ad_group.id`. É ela que faz o sensor perder `{campaignid}`.
REGEX_TELEFONE = _PII_SENSOR[3]


def _js_slice(s: str, n: int) -> str:
    """`s.slice(0, n)` do JavaScript: corta em unidades UTF-16 (pode partir um par substituto)."""
    if len(s) <= n // 2:  # atalho: cada code point ocupa no máximo 2 unidades
        return s
    b = s.encode("utf-16-le", "surrogatepass")
    if len(b) <= 2 * n:
        return s
    return b[: 2 * n].decode("utf-16-le", "surrogatepass")


def _js_len(s: str) -> int:
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def _js_trim(s: str) -> str:
    return _WS_TRIM.sub("", s)


def _js_str(v: object) -> str:
    return "" if v is None else str(v)


def _clean(s: str, maximo: int) -> str:
    """`clean(s, max)` do sensor (:75-79)."""
    s = _js_trim(_WS_RUN.sub(" ", s))
    for rx in _PII_SENSOR:
        s = rx.sub("[x]", s)
    return _js_slice(s, maximo)


def _sanear(v: str, limite: Optional[int] = LIMITE_VALOR_UTM) -> str:
    """Trecho comum a utmValue/safeValue depois do filtro: sem acento, sem pontuação proibida."""
    v = _MARCAS.sub("", unicodedata.normalize("NFD", v))
    v = _WS_RUN.sub("_", _CHARS_PROIBIDOS.sub("", v))
    return v if limite is None else _js_slice(v, limite)


class MotivoDescarte(str, enum.Enum):
    """Por que o sensor devolveu '' para um valor de UTM."""

    MANTIDO = "mantido"
    VAZIO = "vazio"
    PII = "pii"  # casou alguma regex de PII (inclui número com >= 10 dígitos)
    LONGO_DEMAIS = "longo_demais"  # > 200 unidades UTF-16 depois de colapsar espaços


def diagnosticar_utm_sensor_v3(valor: object) -> tuple[str, MotivoDescarte]:
    """`utmValue(v)` do sensor v3 (:107-112), com o motivo quando o resultado é vazio."""
    v = _js_trim(_js_str(valor)).lower()
    if not v:
        return "", MotivoDescarte.VAZIO
    colapsado = _WS_RUN.sub(" ", v)
    if _clean(v, LIMITE_CHECAGEM_PII) != colapsado:
        if _js_len(_js_trim(colapsado)) > LIMITE_CHECAGEM_PII and not any(
            rx.search(colapsado) for rx in _PII_SENSOR
        ):
            return "", MotivoDescarte.LONGO_DEMAIS
        return "", MotivoDescarte.PII
    return _sanear(v), MotivoDescarte.MANTIDO


def normalizar_utm_sensor_v3(valor: object) -> str:
    """Valor exatamente como o sensor v3 grava em `payload.utm.*` ('' = descartado)."""
    return diagnosticar_utm_sensor_v3(valor)[0]


def chave_sem_corte_sensor_v3(valor: object) -> str:
    """Mesma regra do sensor sem o corte final de 40 — só para detectar truncamento ambíguo."""
    v, motivo = diagnosticar_utm_sensor_v3(valor)
    if motivo is not MotivoDescarte.MANTIDO:
        return ""
    return _sanear(_js_trim(_js_str(valor)).lower(), None)


def normalizar_valor_wrapper_v2(valor: object) -> str:
    """`safeValue(v)` do WEBS Wrapper v2 (:74-80): key-value enviado ao GPT ('' = não enviado).

    Diverge do sensor em um ponto: não tem o teto de 200 (valor longo é truncado, não descartado).
    """
    v = _js_trim(_js_str(valor)).lower()
    if not v:
        return ""
    if any(rx.search(v) for rx in _PII_WRAPPER):
        return ""
    return _sanear(v)


def parse_query_urlsearchparams(query: str) -> dict[str, str]:
    """Primeiro valor de cada chave, como `new URL(href).searchParams.get(k)`."""
    if query.startswith("?"):
        query = query[1:]
    saida: dict[str, str] = {}
    for parte in query.split("&") if query else ():
        if not parte:
            continue
        nome, _, valor = parte.partition("=")
        nome = unquote(nome.replace("+", " "), errors="replace")
        valor = unquote(valor.replace("+", " "), errors="replace")
        saida.setdefault(nome, valor)
    return saida


@dataclass(frozen=True)
class UtmSessao:
    """`payload.utm` do evento `volc_sensor_ready` (o único evento que carrega UTM)."""

    source: Optional[str] = None
    medium: Optional[str] = None
    campaign: Optional[str] = None
    content: Optional[str] = None
    term: Optional[str] = None
    paid: int = 0

    def como_payload(self) -> dict:
        d = {k: getattr(self, k) for k in ("source", "medium", "campaign", "content", "term")}
        d = {k: v for k, v in d.items() if v}
        d["paid"] = self.paid
        return d

    @classmethod
    def de_payload(cls, d: Optional[Mapping]) -> "UtmSessao":
        d = d or {}
        paid = d.get("paid")
        return cls(
            source=d.get("source") or None,
            medium=d.get("medium") or None,
            campaign=d.get("campaign") or None,
            content=d.get("content") or None,
            term=d.get("term") or None,
            paid=1 if paid in (1, True) else 0,
        )


def utm_da_pagina_sensor_v3(
    query: str, armazenado: Optional[Mapping] = None
) -> tuple[UtmSessao, Optional[dict]]:
    """`campaign()` do sensor (:116-135): UTM da página + o que fica em `sessionStorage.volc_utm`.

    - Só `utm_source/medium/campaign/content/term` (allowlist); o resto do template é ignorado.
    - Presença (até vazia) de `gclid/gbraid/wbraid` vira `paid=1`; o VALOR nunca sai.
    - Se a URL não trouxer nenhum valor sobrevivente, herda o que a aba guardou.
    - Se trouxer algum (inclusive só `paid`), SOBRESCREVE o guardado inteiro.
    """
    q = parse_query_urlsearchparams(query)
    f: dict = {}
    for p in CHAVES_UTM_SENSOR:
        v = normalizar_utm_sensor_v3(q.get(p))
        if v:
            f[p[4:]] = v
    if any(k in q for k in CLICK_IDS_SENSOR):
        f["paid"] = 1
    if f:
        novo_armazenado: Optional[dict] = dict(f)
        o = dict(f)
    else:
        novo_armazenado = dict(armazenado) if armazenado else None
        o = dict(armazenado) if armazenado else {}
    o["paid"] = 1 if o.get("paid") else 0
    return UtmSessao.de_payload(o), novo_armazenado


def limpar_utm_ingest(payload_utm: object) -> dict:
    """Recorte de `cleanValue` do `volc-ingest` (index.ts:59-75) aplicado a `payload.utm`.

    Chaves fora de `^[a-zA-Z][a-zA-Z0-9_]{0,31}$` caem; strings perdem controle e são cortadas
    em 200; números são limitados a ±1e6. Valores já normalizados pelo sensor passam intactos.
    """
    if not isinstance(payload_utm, Mapping):
        return {}
    saida: dict = {}
    for k, v in list(payload_utm.items())[:20]:
        if not isinstance(k, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,31}", k):
            continue
        if isinstance(v, bool):
            saida[k] = v
        elif isinstance(v, str):
            saida[k] = _js_slice(re.sub(r"[\u0000-\u001f\u007f]", "", v), 200)
        elif isinstance(v, (int, float)):
            saida[k] = min(1_000_000, max(-1_000_000, v))
    return saida
