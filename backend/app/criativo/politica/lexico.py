"""O léxico de identidade de terceiro, e o casamento determinístico dele.

## Por que um léxico, e por que versionado

A peça que motivou esta lane trazia um envelope com marca de banco. Ninguém
mentiu: o gerador produziu o que foi pedido, o operador não olhou de perto, e a
peça foi para mídia paga afirmando um vínculo que não existia.

Um portão que dependa de alguém *reparar* na marca não é um portão. E um portão
que use um modelo não determinístico não pode ser reexecutado: o mesmo recibo
precisa poder ser reconferido amanhã, com o mesmo resultado, ou ele não é prova.

Por isso o léxico é um ARQUIVO versionado (`lexico_identidade.v1.json`) e o
casamento é determinístico. A versão entra no recibo: quando o léxico muda de
forma que afeta a classe de um achado, o recibo anterior precisa ser refeito —
e o sistema sabe disso porque a versão que o assinou está gravada nele.

## O que um achado significa, e o que ele NÃO significa

Um achado NÃO é uma acusação de fraude. Ele é a exigência de uma AUTORIZAÇÃO
registrada: se a peça de fato pode citar aquele banco, existe um documento, e o
documento mora no Cofre. Texto livre no formulário não serve — seria a mesma
parte interessada assinando a própria licença.

## A identidade própria nunca é terceiro

O site que anuncia pode dizer o próprio nome. `identity_ref` traz os termos
próprios, e eles entram como ALLOWLIST antes de qualquer classe. Sem isso o
portão bloquearia o anunciante por se identificar — e um portão que dá falso
positivo é um portão que alguém desliga.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping


ARQUIVO_DO_LEXICO = Path(__file__).with_name("lexico_identidade.v1.json")

#: As origens possíveis de um achado. Vocabulário fechado: o recibo declara de
#: ONDE veio cada marca, e a tela mostra isso ao operador.
ORIGENS: tuple[str, ...] = ("prompt", "copy", "ocr", "filename")


@dataclass(frozen=True)
class Achado:
    """Uma marca de terceiro encontrada, com o suficiente para ser conferida."""

    classe: str
    termo: str
    origem: str
    posicao: int
    peso: str
    #: Preenchido pelo portão quando uma autorização do Cofre cobre este achado.
    coberto_por_autorizacao: bool = False

    def publico(self) -> dict[str, Any]:
        return {
            "classe": self.classe,
            "termo": self.termo,
            "origem": self.origem,
            "posicao": self.posicao,
            "peso": self.peso,
            "coberto_por_autorizacao": self.coberto_por_autorizacao,
        }


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def normalizar(texto: Any) -> str:
    """NFKD + casefold + sem diacrítico. É a forma em que os termos casam."""
    return _sem_acento(str(texto or "")).casefold()


@lru_cache(maxsize=1)
def carregar() -> Mapping[str, Any]:
    """O léxico como está no disco. Cacheado: é arquivo, não configuração viva."""
    return json.loads(ARQUIVO_DO_LEXICO.read_text(encoding="utf-8"))


def versao() -> str:
    return str(carregar()["versao"])


@lru_cache(maxsize=1)
def _padroes() -> tuple[tuple[str, str, str, re.Pattern[str]], ...]:
    """(classe, termo, peso, regex) para cada termo, compilado uma vez só.

    ⚠️ `\\b` nos dois lados, e a razão é um falso positivo real: sem fronteira,
    "tim" casaria dentro de "estimativa" e "oficial" dentro de "beneficial".
    Um portão que acusa palavra dentro de palavra é um portão que o operador
    aprende a ignorar.
    """
    saida: list[tuple[str, str, str, re.Pattern[str]]] = []
    for classe, dados in carregar()["classes"].items():
        peso = str(dados.get("peso") or "medio")
        for termo in dados.get("termos") or ():
            alvo = normalizar(termo)
            saida.append((classe, termo, peso,
                          re.compile(rf"\b{re.escape(alvo)}\b")))
    return tuple(saida)


@lru_cache(maxsize=1)
def _siglas() -> tuple[tuple[str, str, str, re.Pattern[str]], ...]:
    """As siglas casam SÓ EM MAIÚSCULAS, no texto original.

    ⚠️ Sem essa restrição, `pis` dentro de "episódio" e `bb` dentro de
    "abbey" viram achado. Uma sigla em caixa alta é uma afirmação; a mesma
    sequência em caixa baixa quase sempre é acidente de palavra.
    """
    saida: list[tuple[str, str, str, re.Pattern[str]]] = []
    for classe, dados in carregar()["classes"].items():
        peso = str(dados.get("peso") or "medio")
        for sigla in dados.get("siglas") or ():
            saida.append((classe, sigla, peso,
                          re.compile(rf"\b{re.escape(sigla)}\b")))
    return tuple(saida)


def _allowlist(identidade_propria: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(
        n for n in (normalizar(t) for t in (identidade_propria or ())) if n
    )


def _e_identidade_propria(termo_normalizado: str, propria: tuple[str, ...]) -> bool:
    """O termo é do próprio anunciante — por igualdade ou por conter o termo.

    Conter, e não apenas igualar: um site chamado "Portal Mundo Mais Oficial"
    declara "oficial" como parte da própria identidade, e acusá-lo de afirmar
    vínculo com terceiro seria acusá-lo do próprio nome.
    """
    return any(
        termo_normalizado == p or termo_normalizado in p for p in propria
    )


def procurar(
    texto: Any,
    *,
    origem: str,
    identidade_propria: Iterable[str] | None = None,
) -> tuple[Achado, ...]:
    """Todos os achados de um texto, em ordem estável (classe, termo, posição).

    Ordem estável porque o recibo é assinado: duas execuções sobre os mesmos
    bytes precisam produzir a mesma assinatura.
    """
    if origem not in ORIGENS:
        raise ValueError(f"origem desconhecida: {origem!r}")
    bruto = str(texto or "")
    if not bruto.strip():
        return ()
    propria = _allowlist(identidade_propria)
    alvo = normalizar(bruto)
    achados: list[Achado] = []
    for classe, termo, peso, padrao in _padroes():
        if _e_identidade_propria(normalizar(termo), propria):
            continue
        for casamento in padrao.finditer(alvo):
            achados.append(Achado(classe=classe, termo=termo, origem=origem,
                                  posicao=casamento.start(), peso=peso))
    for classe, sigla, peso, padrao in _siglas():
        if _e_identidade_propria(normalizar(sigla), propria):
            continue
        # No ORIGINAL, não no normalizado: caixa alta é a condição.
        for casamento in padrao.finditer(bruto):
            achados.append(Achado(classe=classe, termo=sigla, origem=origem,
                                  posicao=casamento.start(), peso=peso))
    return tuple(sorted(achados, key=lambda a: (a.classe, a.termo, a.posicao)))


def procurar_em_varios(
    partes: Mapping[str, Any],
    *,
    identidade_propria: Iterable[str] | None = None,
) -> tuple[Achado, ...]:
    """`{origem: texto}` → achados de todas as origens, em ordem estável."""
    achados: list[Achado] = []
    for origem in ORIGENS:
        if origem in partes:
            achados.extend(procurar(partes[origem], origem=origem,
                                    identidade_propria=identidade_propria))
    return tuple(sorted(
        achados, key=lambda a: (a.origem, a.classe, a.termo, a.posicao)))
