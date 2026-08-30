"""Referência de países e idiomas — completa, não hardcoded.

O runner tem que rodar no Brasil, na França, na Dinamarca ou no Senegal com
o mesmo código. Para isso, país e idioma saem da fonte (219 países no arquivo
oficial de geotargets, 151 idiomas na API), nunca de um dicionário escrito
à mão com os sete países do momento.

Decisão de projeto: **país e idioma são eixos independentes e ambos explícitos.**
A segmentação por idioma no Google Ads é sobre a língua da interface do
usuário, não sobre a língua oficial do país. Adivinhar produz erro silencioso
— no Senegal a língua oficial é o wolof, que a API marca como
`targetable=False`; quem anuncia lá segmenta francês. Por isso `sugerir_idioma`
apenas sugere, e o brief precisa declarar.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
import zipfile
from dataclasses import dataclass
from functools import lru_cache

_RAIZ = pathlib.Path(__file__).resolve().parents[1]
# A fonte oficial vive junto da documentação da API, não duplicada aqui.
_GEOTARGETS = (pathlib.Path(__file__).resolve().parents[1]
               / "google_ads_api" / "geotargets-2026-07-06.csv.zip")
_IDIOMAS_CACHE = pathlib.Path(__file__).resolve().parent / "dados" / "idiomas.json"


@dataclass(frozen=True)
class Pais:
    codigo: str        # ISO-2
    criterio_id: int   # geoTargetConstants/{id}
    nome: str

    @property
    def resource_name(self) -> str:
        return f"geoTargetConstants/{self.criterio_id}"


@dataclass(frozen=True)
class Idioma:
    codigo: str
    criterio_id: int
    nome: str
    segmentavel: bool

    @property
    def resource_name(self) -> str:
        return f"languageConstants/{self.criterio_id}"


@lru_cache(maxsize=1)
def paises() -> dict[str, Pais]:
    """Todos os países ativos do arquivo oficial de geotargets."""
    if not _GEOTARGETS.exists():
        raise FileNotFoundError(
            f"arquivo de geotargets ausente: {_GEOTARGETS}. "
            "Baixe de developers.google.com/google-ads/api/data/geotargets"
        )
    out: dict[str, Pais] = {}
    with zipfile.ZipFile(_GEOTARGETS) as z:
        with z.open(z.namelist()[0]) as fh:
            for linha in csv.DictReader(io.TextIOWrapper(fh, "utf-8")):
                if linha["Target Type"] != "Country" or linha["Status"] != "Active":
                    continue
                cc = linha["Country Code"].strip().upper()
                out[cc] = Pais(cc, int(linha["Criteria ID"]), linha["Name"].strip())
    return out


@lru_cache(maxsize=1)
def idiomas() -> dict[str, Idioma]:
    """Idiomas da API, com cache em disco para não depender de rede."""
    if _IDIOMAS_CACHE.exists():
        dados = json.loads(_IDIOMAS_CACHE.read_text())
        return {k: Idioma(**v) for k, v in dados.items()}
    return {}


def atualizar_idiomas(customer_id: str, *, login_customer_id: str) -> dict[str, Idioma]:
    """Recarrega os idiomas da API e grava o cache. Requer rede."""
    from ..gads.client import buscar

    out: dict[str, Idioma] = {}
    for r in buscar(
        customer_id,
        """SELECT language_constant.id, language_constant.code,
                  language_constant.name, language_constant.targetable
           FROM language_constant""",
        login_customer_id=login_customer_id,
    ):
        l = r.language_constant
        out[l.code] = Idioma(l.code, int(l.id), l.name, bool(l.targetable))
    _IDIOMAS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _IDIOMAS_CACHE.write_text(
        json.dumps({k: v.__dict__ for k, v in out.items()}, ensure_ascii=False, indent=1)
    )
    idiomas.cache_clear()
    return out


# Sugestão de idioma por país — conveniência, NUNCA default silencioso.
# Só entram casos onde a escolha é inequívoca na prática publicitária.
_SUGESTAO = {
    "BR": "pt", "PT": "pt", "AO": "pt", "MZ": "pt",
    "ES": "es", "MX": "es", "AR": "es", "CL": "es", "CO": "es", "PE": "es",
    "UY": "es", "PY": "es", "BO": "es", "EC": "es", "VE": "es", "CR": "es",
    "FR": "fr", "BE": "fr", "SN": "fr", "CI": "fr", "ML": "fr", "CM": "fr",
    "DK": "da", "SE": "sv", "NO": "no", "FI": "fi", "IS": "is",
    "DE": "de", "AT": "de", "CH": "de", "NL": "nl", "IT": "it", "PL": "pl",
    "US": "en", "GB": "en", "CA": "en", "AU": "en", "NZ": "en", "IE": "en",
    "NG": "en", "ZA": "en", "KE": "en", "GH": "en", "IN": "en",
    "JP": "ja", "KR": "ko", "CN": "zh_CN", "TW": "zh_TW", "TH": "th",
    "ID": "id", "VN": "vi", "TR": "tr", "RU": "ru", "SA": "ar", "AE": "ar",
}


def sugerir_idioma(codigo_pais: str) -> str | None:
    """Sugere o idioma de anúncio para um país. None quando não é óbvio.

    Devolver None em vez de chutar é deliberado: idioma errado gasta verba
    numa audiência que não lê o anúncio, e falha em silêncio.
    """
    return _SUGESTAO.get(codigo_pais.upper())


def resolver(codigo_pais: str, codigo_idioma: str) -> tuple[Pais, Idioma]:
    """Valida o par (país, idioma) contra a fonte. Levanta ValueError com
    mensagem acionável — o erro tem que dizer o que fazer, não só o que houve."""
    cc = codigo_pais.upper()
    p = paises().get(cc)
    if p is None:
        raise ValueError(
            f"país {cc!r} não encontrado entre os {len(paises())} países ativos"
        )

    todos = idiomas()
    if not todos:
        raise RuntimeError(
            "cache de idiomas vazio — rode referencia.geo.atualizar_idiomas() uma vez"
        )
    i = todos.get(codigo_idioma)
    if i is None:
        raise ValueError(f"idioma {codigo_idioma!r} não existe na API")
    if not i.segmentavel:
        sugestao = sugerir_idioma(cc)
        extra = f" Para {p.nome}, considere {sugestao!r}." if sugestao else ""
        raise ValueError(
            f"idioma {i.nome} ({codigo_idioma}) não é segmentável no Google Ads.{extra}"
        )
    return p, i
