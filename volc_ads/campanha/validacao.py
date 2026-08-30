"""Validação de conteúdo antes de qualquer chamada à API.

Três camadas, do mais barato ao mais caro:
  1. esta (local, microssegundos) — limites de caractere, contagem, DKI
  2. `validate_only` na API (rede, custo zero, nada criado)
  3. revisão de política do Google (dias, e reprovação mancha a conta)

O objetivo é que nada chegue na camada 3 sem ter passado pelas duas primeiras.
"""

from __future__ import annotations

import pathlib
import re
import unicodedata
from dataclasses import dataclass, field

import yaml

_LIM = yaml.safe_load((pathlib.Path(__file__).parent / "limites.yaml").read_text())

_DKI = re.compile(r"\{KeyWord:([^}]*)\}", re.IGNORECASE)
_DKI_ABERTO = re.compile(r"\{KeyWord:[^}]*$", re.IGNORECASE)


@dataclass
class Achado:
    severidade: str  # "erro" | "aviso"
    campo: str
    valor: str
    motivo: str


@dataclass
class Resultado:
    achados: list[Achado] = field(default_factory=list)

    @property
    def erros(self) -> list[Achado]:
        return [a for a in self.achados if a.severidade == "erro"]

    @property
    def ok(self) -> bool:
        return not self.erros

    def erro(self, campo, valor, motivo):
        self.achados.append(Achado("erro", campo, str(valor)[:80], motivo))

    def aviso(self, campo, valor, motivo):
        self.achados.append(Achado("aviso", campo, str(valor)[:80], motivo))

    def resumo(self) -> str:
        if not self.achados:
            return "sem achados"
        return "\n".join(
            f"  [{a.severidade}] {a.campo}: {a.motivo}  →  {a.valor!r}"
            for a in self.achados
        )


def comprimento_efetivo(texto: str) -> int:
    """Comprimento que o Google conta, resolvendo o DKI pelo fallback.

    '{KeyWord:Pé de Meia} 2026' conta como 'Pé de Meia 2026' = 15, não 25.
    Era exatamente aqui que o n8n errava: truncava a string crua e cortava
    a tag no meio, gerando '{KeyWord:Curso' — que a API recusa.
    """
    return len(_DKI.sub(lambda m: m.group(1), texto))


def dki_integro(texto: str) -> bool:
    """Detecta tag DKI truncada — o erro clássico do truncamento cego."""
    return not _DKI_ABERTO.search(texto) and texto.count("{") == texto.count("}")


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def checar_politica(texto: str, campo: str, r: Resultado) -> None:
    alvo = _normalizar(texto)
    for termo in _LIM["politica"]["proibidos"]:
        if _normalizar(termo) in alvo:
            r.erro(campo, texto, f"termo proibido: {termo!r}")
    for termo in _LIM["politica"]["suspeitos_execucao"]:
        if _normalizar(termo) in alvo:
            r.aviso(campo, texto, f"sugere execução de serviço: {termo!r}")


def checar_lista(
    itens: list[str], chave: str, r: Resultado, *, permitir_dki: bool = False
) -> list[str]:
    """Valida uma lista de textos contra os limites e devolve os aprovados."""
    lim = _LIM["texto"][chave]
    aprovados: list[str] = []

    for texto in itens:
        texto = (texto or "").strip()
        if not texto:
            r.erro(chave, texto, "texto vazio")
            continue
        if not dki_integro(texto):
            r.erro(chave, texto, "tag DKI truncada ou chave desbalanceada")
            continue
        if not permitir_dki and _DKI.search(texto):
            r.erro(chave, texto, "DKI não é permitido neste campo")
            continue
        n = comprimento_efetivo(texto)
        if n > lim["max_chars"]:
            r.erro(chave, texto, f"{n} chars > limite {lim['max_chars']}")
            continue
        checar_politica(texto, chave, r)
        aprovados.append(texto)

    # duplicatas são recusadas pela API em headlines/descriptions
    vistos, unicos = set(), []
    for t in aprovados:
        k = _normalizar(t)
        if k in vistos:
            r.aviso(chave, t, "duplicado — removido")
            continue
        vistos.add(k)
        unicos.append(t)

    if len(unicos) < lim["min_itens"]:
        r.erro(chave, f"{len(unicos)} itens", f"mínimo é {lim['min_itens']}")
    return unicos[: lim["max_itens"]]


def checar_keywords(kws: list[str], r: Resultado) -> list[str]:
    lim = _LIM["texto"]["keyword"]
    maxp = _LIM["keyword"]["max_palavras"]
    ok: list[str] = []
    vistos = set()
    for k in kws:
        k = (k or "").strip()
        if not k:
            continue
        if len(k) > lim["max_chars"]:
            r.erro("keyword", k, f"{len(k)} chars > {lim['max_chars']}")
            continue
        if len(k.split()) > maxp:
            r.erro("keyword", k, f"{len(k.split())} palavras > {maxp}")
            continue
        n = _normalizar(k)
        if n in vistos:
            continue
        vistos.add(n)
        ok.append(k)
    if not ok:
        r.erro("keyword", "", "nenhuma keyword válida")
    return ok


def checar_criterios(
    criterios: list,
    r: Resultado,
    *,
    exigir_pelo_menos_um: bool = False,
    rotulo: str = "keyword",
) -> list:
    """Valida critérios TIPADOS e devolve os aprovados, com os achados no `r`.

    Existe ao lado de `checar_keywords` — e não no lugar dela — por duas
    diferenças que não dava para acomodar sem quebrar o chamador antigo:

    1. **Lista vazia não é erro por padrão.** `checar_keywords` emite
       `"nenhuma keyword válida"` numa lista vazia, o que é certo para as
       positivas (campanha sem keyword não veicula) e errado para as
       negativas (a maioria das campanhas não declara nenhuma). Era por causa
       disso que `search.py` passava um `Resultado()` descartável para as
       negativas: para engolir esse erro fantasma. E, junto com ele, engolia
       os erros de verdade — negativa com 90 caracteres sumia do payload sem
       uma linha de aviso.

    2. **A identidade aqui é a DA EMISSÃO: (texto, match type).** Esta função
       roda depois de resolvido quem vale neste recurso, então dois critérios
       que o operador declarou diferente — um "em todos os grupos", outro "só
       no VALOR" — já chegaram os dois ao mesmo ad group. Comparar pela
       identidade declarada deixaria passar duas operações idênticas, e a API
       recusa a segunda. Ver `criterio.deduplicar_por_emissao`.

       O match type continua fazendo parte: `"curso"` EXACT e `"curso"` PHRASE
       são dois critérios legítimos e coexistentes no mesmo ad group.

    O `rotulo` entra no campo do achado para dizer DE ONDE ele veio
    ("negativa_campanha", "negativa[ACESSO]") — sem isso, "80 chars > 80" num
    brief de quatro grupos não diz onde procurar.
    """
    # local: `criterio` não importa este módulo
    from .criterio import deduplicar_por_emissao

    lim = _LIM["texto"]["keyword"]
    maxp = _LIM["keyword"]["max_palavras"]

    validos: list = []
    for c in criterios:
        texto = (c.texto or "").strip()
        if not texto:
            # Não deveria chegar aqui: `Criterio` recusa texto vazio na
            # construção. Mantido como rede, e como ERRO — chegar aqui
            # significa que alguém montou o objeto por outro caminho.
            r.erro(rotulo, texto, "critério sem texto")
            continue
        if len(texto) > lim["max_chars"]:
            r.erro(rotulo, texto, f"{len(texto)} chars > {lim['max_chars']}")
            continue
        if len(texto.split()) > maxp:
            r.erro(rotulo, texto, f"{len(texto.split())} palavras > {maxp}")
            continue
        validos.append(c)

    unicos, descartados = deduplicar_por_emissao(validos)
    for perdedor, dono in descartados:
        # Aviso e não erro: a duplicata é removida e a campanha sobe. Mas ela
        # aparece, porque as duas podiam ter motivo e origem diferentes e quem
        # revisa precisa saber qual sobreviveu.
        r.aviso(
            rotulo,
            perdedor.texto,
            f"duplicata de {dono.texto!r} ({dono.match_type}) — removida, "
            f"mantida a primeira declarada",
        )

    if exigir_pelo_menos_um and not unicos:
        r.erro(rotulo, "", "nenhuma keyword válida")
    return unicos


def checar_snippet_header(header: str, r: Resultado) -> str:
    if header not in _LIM["snippet_headers_pt"]:
        r.erro(
            "snippet_header",
            header,
            f"header inválido; aceitos: {', '.join(_LIM['snippet_headers_pt'][:5])}...",
        )
    return header
