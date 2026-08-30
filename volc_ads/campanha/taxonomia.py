"""Taxonomia de nomenclatura — nome para humano, label para máquina.

Aprendido observando 383 campanhas dos primos, e corrigindo os três pontos
onde o padrão deles quebra:

  1. O modificador de canal é inconsistente justamente no Demand Gen (cinco
     convenções em 24 campanhas) e quatro campanhas Demand Gen dizem
     "Display" no nome. Aqui o modificador é canônico e obrigatório.
  2. O número é sequencial por site e não carrega canal — mantemos assim,
     porque o canal vira label, que é consultável de verdade.
  3. Eles não usam `label` nenhum: o nome virou banco de dados. Aqui o nome
     serve à leitura humana e os labels carregam a mesma informação de forma
     estruturada, consultável por GAQL e imune a truncamento.

Propriedade central: o nome é **round-trip**. `analisar(montar(x)) == x`.
Se não for possível reconstruir, o nome não serve para automação.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_NOME_CAMPANHA = 255
MAX_NOME_ADGROUP = 255

# Modificador canônico por canal. Sempre presente — inclusive no Search, que
# os primos deixam implícito. Implícito não é legível por máquina.
MODIFICADOR = {
    "SEARCH": "Search",
    "DISPLAY": "Display",
    "DEMAND_GEN": "GD",
    "PERFORMANCE_MAX": "Pmax",
}
CANAL_POR_MODIFICADOR = {v: k for k, v in MODIFICADOR.items()}

SEP_SITE = " - "
SEP_CAMPO = " / "


def ascii_slug(texto: str, *, maxlen: int = 60) -> str:
    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:maxlen].rstrip("-")


@dataclass(frozen=True)
class Nomenclatura:
    site: str          # sigla curta e estável: D2, PMM, CU
    sequencia: int     # sequencial por site, 1..999
    tema: str          # "Pis Pasep", "Programa Pé de Meia"
    canal: str         # SEARCH | DISPLAY | DEMAND_GEN | PERFORMANCE_MAX
    slug: str          # slug do destino, sem domínio
    subformato: str = ""   # "Youtube", "Discovery" — só onde faz sentido

    def __post_init__(self) -> None:
        if self.canal not in MODIFICADOR:
            raise ValueError(f"canal {self.canal!r} fora de {sorted(MODIFICADOR)}")
        if not (1 <= self.sequencia <= 999):
            raise ValueError("sequencia precisa estar entre 1 e 999")
        if not self.site.isupper() or not self.site.isalnum():
            raise ValueError("site deve ser sigla alfanumérica maiúscula (ex.: D2, PMM)")
        if not self.tema.strip():
            raise ValueError("tema vazio")

    @property
    def rotulo_canal(self) -> str:
        base = MODIFICADOR[self.canal]
        return f"{base} {self.subformato}".strip() if self.subformato else base

    def campanha(self) -> str:
        """`D2 - 104 / Pis Pasep [Display] / pis-pasep-entenda-tudo`

        O canal vai entre colchetes: delimitador explícito impede que um tema
        contendo a palavra "Display" seja lido como canal — o erro que faz
        quatro campanhas Demand Gen deles se passarem por Display.
        """
        nome = (
            f"{self.site}{SEP_SITE}{self.sequencia:03d}"
            f"{SEP_CAMPO}{self.tema} [{self.rotulo_canal}]"
            f"{SEP_CAMPO}{self.slug}"
        )
        if len(nome) > MAX_NOME_CAMPANHA:
            corte = len(nome) - MAX_NOME_CAMPANHA
            nome = (
                f"{self.site}{SEP_SITE}{self.sequencia:03d}"
                f"{SEP_CAMPO}{self.tema} [{self.rotulo_canal}]"
                f"{SEP_CAMPO}{self.slug[: max(0, len(self.slug) - corte)]}"
            )
        return nome

    def ad_group(self, segmento: str) -> str:
        """`D2 - 104 / Pis Pasep [Display] / SEG:audiencia-afinidade`

        O ad group é a unidade onde o tCPA vive (9,4× mais ajustado que a
        campanha). Nome que não identifica o segmento — "KW", "Tema", "SP",
        "Aberto" — torna a otimização por segmento ilegível.
        """
        seg = segmento.strip() or "geral"
        nome = (
            f"{self.site}{SEP_SITE}{self.sequencia:03d}"
            f"{SEP_CAMPO}{self.tema} [{self.rotulo_canal}]"
            f"{SEP_CAMPO}SEG:{ascii_slug(seg, maxlen=40)}"
        )
        return nome[:MAX_NOME_ADGROUP]

    def labels(self, *, versao_runner: str = "v1", lote: str = "") -> dict[str, str]:
        """Marcação estruturada — é isto que a máquina lê, não o nome."""
        d = {
            "site": self.site.lower(),
            "canal": self.canal.lower(),
            "tema": ascii_slug(self.tema, maxlen=40),
            "slug": ascii_slug(self.slug, maxlen=60),
            "forge": versao_runner,
        }
        if self.subformato:
            d["subformato"] = ascii_slug(self.subformato, maxlen=20)
        if lote:
            d["lote"] = lote
        return d


_RE = re.compile(
    r"^(?P<site>[A-Z0-9]+) - (?P<seq>\d{3}) / (?P<tema>.+?) \[(?P<canal>[^\]]+)\] / (?P<slug>.*)$"
)


def analisar(nome: str) -> Nomenclatura | None:
    """Reconstrói a nomenclatura a partir do nome. None se não seguir o padrão.

    Devolver None em vez de adivinhar é deliberado: campanha fora do padrão
    (legado, ou criada na mão) deve ser tratada como desconhecida, nunca
    classificada por heurística — foi assim que quatro Demand Gen viraram
    "Display" na conta dos primos.
    """
    m = _RE.match(nome.strip())
    if not m:
        return None
    rotulo = m.group("canal").strip()
    partes = rotulo.split(" ", 1)
    canal = CANAL_POR_MODIFICADOR.get(partes[0])
    if canal is None:
        return None
    return Nomenclatura(
        site=m.group("site"),
        sequencia=int(m.group("seq")),
        tema=m.group("tema").strip(),
        canal=canal,
        slug=m.group("slug").strip(),
        subformato=partes[1].strip() if len(partes) > 1 else "",
    )
