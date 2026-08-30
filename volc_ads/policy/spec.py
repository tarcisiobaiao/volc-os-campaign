"""Validador de política multi-país — policy-first, dirigido pela fonte.

Arquitetura em três camadas, e a separação não é estética:

  ESTRUTURAIS   forma do texto — capitalização, pontuação, emoji, espaçamento,
                repetição. **Independem de idioma**: um emoji é emoji em
                qualquer língua, e "F.L.O.R.E.S." é o mesmo defeito que
                "F.L.O.W.E.R.S.". Os regexes usam classes Unicode, não [a-z].

  SEMÂNTICAS    sentido do texto — clickbait, promessas, termos regulados.
                **Dependem do idioma**: uma lista por locale.

  HABILITAÇÃO   portão por país + vertical — certificação ou verificação
                exigida ANTES de anunciar. Não é sobre texto; é sobre
                elegibilidade, e é o que reprova campanha inteira.

Regra sem fonte não entra. Se não dá para citar o documento oficial, é
opinião — e opinião não bloqueia campanha.
"""

from __future__ import annotations

import json
import pathlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_SPEC = pathlib.Path(__file__).resolve().parent / "spec.json"

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF"
    "\U0000FE00-\U0000FE0F\U00002190-\U000021FF\U00002B00-\U00002BFF]"
)

# A política vale para o texto que o usuário vê. A tag DKI é template:
# avaliá-la crua produz falso positivo de caixa alternada ("KeyWord") e de
# espaço omitido ("d:P").
_DKI = re.compile(r"\{KeyWord:([^}]*)\}", re.IGNORECASE)

# País → idioma padrão do anúncio. O idioma decide quais regras semânticas
# valem; o país decide quais habilitações são exigidas. São eixos distintos:
# uma campanha em espanhol segmentando os EUA usa regras `es` e portão `US`.
IDIOMA_PADRAO = {
    "BR": "pt", "PT": "pt",
    "ES": "es", "MX": "es", "AR": "es", "CL": "es", "CO": "es", "PE": "es",
    "US": "en", "GB": "en", "CA": "en", "AU": "en",
}


def resolver_dki(texto: str) -> str:
    return _DKI.sub(lambda m: m.group(1), texto)


def carregar(caminho: pathlib.Path | None = None) -> dict:
    return json.loads((caminho or _SPEC).read_text())


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _palavras(texto: str, minimo: int = 1) -> list[str]:
    return [p for p in re.findall(r"(?u)[^\W_]+", texto) if len(p) >= minimo]


@dataclass(frozen=True)
class Violacao:
    regra: str
    titulo: str
    severidade: str      # erro | aviso | bloqueio | limitacao
    campo: str
    texto: str
    politica: str
    url: str
    detalhe: str = ""

    def __str__(self) -> str:
        return (f"[{self.severidade}] {self.campo}: {self.titulo} "
                f"(política {self.politica}) → {self.texto!r}")


class Validador:
    """Um validador por (país, vertical). O idioma sai do país, salvo override."""

    def __init__(self, spec: dict | None = None, *, pais: str = "BR",
                 vertical: str = "informativo", idioma: str | None = None):
        self.spec = spec or carregar()
        self.pais = pais.upper()
        self.vertical = vertical
        self.idioma = idioma or IDIOMA_PADRAO.get(self.pais, "en")

    # ── conjunto de regras aplicável ────────────────────────────────────────

    def _regras(self) -> list[dict]:
        regras = list(self.spec["estruturais"])
        regras += self.spec["semanticas"].get(self.idioma, [])
        return [r for r in regras
                if not r.get("verticais") or self.vertical in r["verticais"]]

    # ── texto ───────────────────────────────────────────────────────────────

    def checar_texto(self, texto: str, campo: str) -> list[Violacao]:
        visto = resolver_dki(texto)
        out = []
        for regra in self._regras():
            if campo not in regra.get("aplica_a", []):
                continue
            if self._dispara(regra["deteccao"], visto, regra):
                out.append(Violacao(
                    regra=regra["id"], titulo=regra["titulo"],
                    severidade=regra["severidade"], campo=campo,
                    texto=texto[:90], politica=regra["fonte"], url=regra["url"],
                    detalhe=regra.get("nota", "")))
        return out

    def checar_lista(self, textos: list[str], campo: str) -> list[Violacao]:
        out: list[Violacao] = []
        for t in textos:
            out += self.checar_texto(t, campo)
        for regra in self._regras():
            det = regra["deteccao"]
            if det["tipo"] != "repeticao_entre_itens" or campo not in regra["aplica_a"]:
                continue
            cont: Counter = Counter()
            for t in textos:
                cont.update(set(_sem_acento(p) for p in
                                _palavras(resolver_dki(t), det["min_tamanho_palavra"])))
            for palavra, n in cont.items():
                if n > det["limite_ocorrencias"]:
                    out.append(Violacao(
                        regra=regra["id"], titulo=regra["titulo"],
                        severidade=regra["severidade"], campo=campo, texto=palavra,
                        politica=regra["fonte"], url=regra["url"],
                        detalhe=f"aparece em {n} itens (limite {det['limite_ocorrencias']})"))
        return out

    # ── destino ─────────────────────────────────────────────────────────────

    def checar_destino(self, url: str, status_http: int | None) -> list[Violacao]:
        out = []
        for regra in self.spec["destino"]:
            det = regra["deteccao"]
            if det["tipo"] != "http_ok":
                continue
            if status_http is not None and status_http not in det["aceitos"]:
                out.append(Violacao(
                    regra=regra["id"], titulo=regra["titulo"], severidade="erro",
                    campo="url_final", texto=url, politica=regra["fonte"],
                    url=regra["url"], detalhe=f"HTTP {status_http}"))
        return out

    # ── habilitação: o portão que reprova a campanha inteira ────────────────

    def checar_habilitacao(self, *, certificacoes: set[str] | None = None) -> list[Violacao]:
        """Verifica se a vertical exige certificação neste país e se ela existe.

        `certificacoes` é o que a conta comprovadamente possui. Vazio =
        assume que não tem — o default seguro é bloquear, não torcer.
        """
        tem = certificacoes or set()
        hab = self.spec["habilitacao"].get(self.vertical)
        if not hab:
            return []
        if self.pais not in hab["paises_exigem"]:
            return []
        if hab["exige"] in tem:
            return []
        return [Violacao(
            regra=f"habilitacao.{self.vertical}", titulo=f"Exige {hab['exige']}",
            severidade=hab["severidade"], campo="conta", texto=f"{self.vertical}@{self.pais}",
            politica=self.spec["habilitacao"]["_fonte"].get("verificacao_financeira", ""),
            url=hab["url"], detalhe=hab.get("nota", ""))]

    def explicar_topico(self, topico: str) -> dict | None:
        return self.spec["topicos_api"].get(topico)

    # ── detectores ──────────────────────────────────────────────────────────

    def _dispara(self, det: dict, texto: str, regra: dict) -> bool:
        tipo = det["tipo"]

        if tipo == "regex":
            return bool(re.search(det["padrao"], texto))

        if tipo == "emoji":
            return bool(_EMOJI.search(texto))

        if tipo == "caixa_alta_excessiva":
            permitidos = set(regra.get("permitidos", []))
            return any(p.isupper() and p not in permitidos and not p.isdigit()
                       for p in _palavras(texto, det["min_palavra"]))

        if tipo == "caixa_alternada":
            # ⚠️ Conta BLOCOS de maiúscula no miolo, não TRANSIÇÕES de caixa.
            #
            # A versão anterior contava transições e disparava com `>= 2`. Só que
            # um único capital interno JÁ produz duas transições (entra e sai
            # dele), então toda palavra CamelCase era reprovada — inclusive as
            # que a política permite: nome de marca.
            #
            # Medido no card 74 em 19/08/2026: reprovou `PagBank`,
            # `InfiniteSmart`, `Point Pro 3` e `T3 Smart` — cinco headlines,
            # três descriptions, dois sitelinks e um snippet. Marcas reais,
            # escritas como o dono da marca escreve. O próprio arquivo já
            # registrava o sintoma na linha 38 ("KeyWord"), mas só o contornava
            # para a tag DKI.
            #
            # A política 14848295 mira grito gráfico — `FrEeMoNeY`, `CoMpRe` —,
            # que tem VÁRIOS blocos de maiúscula. Um bloco é marca; dois ou mais
            # é gimmick. É essa a fronteira.
            for p in _palavras(texto, 4):
                if p.isupper() or p.islower():
                    continue
                miolo = p[1:]
                blocos = sum(1 for i, c in enumerate(miolo)
                             if c.isupper() and (i == 0 or not miolo[i - 1].isupper()))
                if blocos >= 2:
                    return True
            return False

        if tipo == "frase":
            alvo = _sem_acento(texto)
            return any(_sem_acento(f) in alvo for f in det["frases"])

        if tipo == "repeticao_no_item":
            # Reduplicação idiomática ("passo a passo") é uso padrão, não
            # repetição gratuita. Removemos a expressão antes de contar.
            alvo = _sem_acento(texto)
            for expr in det.get("reduplicacoes_idiomaticas", {}).get(self.idioma, []):
                alvo = alvo.replace(_sem_acento(expr), " ")
            cont = Counter(_palavras(alvo, det["min_tamanho_palavra"]))
            return any(n > det["limite_ocorrencias"] for n in cont.values())

        return False


def cobertura_semantica(spec: dict, idioma: str) -> dict:
    """Diz o que a camada semântica cobre para um idioma.

    Sem isto, um anúncio em dinamarquês passaria "limpo" apenas porque não
    existe lista de clickbait em dinamarquês — falso negativo silencioso, que
    é pior que reprovar. O runner precisa saber que está parcialmente cego.
    """
    regras = spec["semanticas"].get(idioma, [])
    return {
        "idioma": idioma,
        "regras_semanticas": len(regras),
        "cobertura": "completa" if regras else "ausente",
        "estruturais_valem": True,
        "aviso": (
            ""
            if regras
            else f"Sem regras semânticas para {idioma!r}: clickbait, promessas "
            f"absolutas e termos regulados NÃO são verificados localmente. "
            f"As regras estruturais e o validate_only da API continuam valendo."
        ),
    }
