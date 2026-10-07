"""A REGRA DE LEGADO da tipagem de fatos — UM lugar só, para o motor e a ponte.

## Por que um arquivo só (S2 · item 5, 30/09/2026)

Um fato de `state.json` anterior à pesquisa tipada não declara `tipo`. Ele não é
descartado nem renomeado em silêncio: recebe o tipo por uma regra conservadora
sobre CAMPOS ESTRUTURADOS e fica marcado `tipo_origem = "regra_legado"`.

Até aqui havia DUAS regras. O motor (`pipeline/inventario.py`) procurava a norma
em qualquer lugar da unidade, sem fronteira no fim; a ponte do volc_ads
(`pautador_ponte.py`) ancorava no começo, conhecia "Dispositivo Legal" e as
formas em espanhol. O mesmo fato saía `numero` num lado e `fonte_legal` no
outro — medido nos 328 `fatos_verificados` dos runs em disco: 12 casos de
"Dispositivo Legal" divergiam, e "horas de leitura" virava lei no motor.

Agora a regra mora AQUI. O motor importa este módulo; o volc_ads carrega ESTE
MESMO ARQUIVO por caminho (`volc_ads/tipagem_de_fatos.py`), porque os dois rodam
em ambientes Python diferentes e o volc_ads não importa o pacote do motor.
Por isso este arquivo só usa a biblioteca padrão. O teste de contrato
(`volc_ads/copy/testes_contrato_motor.py`) prova que os dois lados dão o mesmo
tipo para os mesmos fatos.

## A regra

- `dados_validados` → `contexto` (descritivo com fonte: sustenta relevância e
  nomeação, nunca número, prazo ou condição);
- `fatos_verificados` → `fonte_legal` quando a UNIDADE diz que o valor É a
  própria norma ("Lei Ordinária", "Portaria", "número do Decreto-Lei que
  autorizou…"); senão `numero`.

Ancorada no começo de propósito: "salários mínimos (conforme a Lei 8.213)" cita a
norma que FUNDAMENTA o número, e o fato continua sendo número. `(?![a-z])` no fim
impede "lei" de casar dentro de "leitura".

⚠️ NUNCA sobre `dispositivo`: ele é obrigatório em todo `VerifiedFact` e, nos 4
fatos Senac, cita o decreto que fundamenta o valor — uma regra sobre ele marcaria
os 4 como `fonte_legal`.
"""
from __future__ import annotations

import re
import unicodedata

ORIGENS = ("dados_validados", "fatos_verificados")

_UNIDADE_E_NORMA = re.compile(
    r"^(?:(?:o|a|el|la)\s+)?(?:(?:numero|n[oº°]\.?)\s+(?:d[aoe]s?|de\s+la|del)\s+)?"
    r"(?:decreto(?:[\s-]+le[iy])?|lei|ley|portaria|resolucao|resolucion|"
    r"medida\s+provisoria|instrucao\s+normativa|emenda\s+constitucional|"
    r"constituicao|constitucion|artigo|articulo|art\.|dispositivo\s+legal|"
    r"reglamento)(?![a-z])"
)


def _sem_acento_minusculo(texto: object) -> str:
    normal = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in normal if not unicodedata.combining(c)).strip().lower()


def unidade_e_norma(unidade: object) -> bool:
    """A unidade diz que o valor É a própria norma?"""
    return bool(_UNIDADE_E_NORMA.match(_sem_acento_minusculo(unidade)))


def tipo_pela_regra_de_legado(origem: str, unidade: object = "") -> str:
    """O tipo de um fato SEM tipo declarado. `origem` é a lista de onde ele veio."""
    if origem == "dados_validados":
        return "contexto"
    return "fonte_legal" if unidade_e_norma(unidade) else "numero"
