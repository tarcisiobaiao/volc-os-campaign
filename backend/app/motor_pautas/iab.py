"""Camada IAB — a ponte entre o que medimos e o vocabulário de quem compra.

Três coisas que esta camada resolve, e nenhuma delas é cosmética.

**1. Arquétipo independente de idioma.** Regras de classificação por regex são
sempre presas a um idioma e não escalam para tailandês nem dinamarquês — e é
exatamente esse o problema de "funcionar em qualquer país". A categoria IAB é
um identificador padronizado e universal: mapeado o arquétipo uma vez, um termo
vietnamita classificado como IAB 394 entra no mesmo balde sem que ninguém
escreva uma linha de regex em vietnamita.

**2. A armadilha de lookup já é um vetor padronizado.** O `Content Purpose` do
IAB distingue:

    Informational → Instructional   "describing how to do things or how things work"
    Utility/Online Tool             "appearing in a utility/tool"

A primeira são as páginas que ganham; a segunda é o Simit. A distinção que
custou R$ 138.814 para ser descoberta na base já estava no padrão — o mercado
sabe que são compras diferentes e precifica diferente.

**3. Os órfãos são o ativo.** Varrendo as 704 categorias, dois arquétipos que
funcionam bem — `documento_identidade_civil` e `app_servico_gov` — **não têm
categoria IAB**. Não existe nó para "documento de identidade civil". Isso não é
falha de mapeamento: é um fato sobre o mercado. Nenhum comprador mira esse
inventário porque não há como pedi-lo, e ninguém compete no lado da compra
porque ninguém o nomeou. É o fosso, escrito no vocabulário de quem compra — e é
um fosso com prazo de validade.

Este módulo NÃO lê mais nenhum arquivo de lucro. A taxonomia e o vetor de
propósito valem por si; o ranking de RPM que existia aqui dependia da carteira
da operação-exemplo e saiu junto com ela.
"""

from __future__ import annotations

import csv
import pathlib
import re
from dataclasses import dataclass
from functools import lru_cache

# a taxonomia IAB fica fora do repo, ao lado dele
_IAB = pathlib.Path(__file__).resolve().parents[2].parent / "iab"
_CONTENT = _IAB / "content_taxonomy.tsv"


# ── mapa arquétipo → categoria IAB ──────────────────────────────────────────
# `None` significa ÓRFÃO: não existe nó na taxonomia para aquilo. Ver o docstring
# do módulo — a ausência é informação, não lacuna a preencher com o nó mais
# parecido. Forçar `documento_identidade_civil` para "Government Business"
# destruiria justamente o sinal que interessa.

@dataclass(frozen=True)
class Mapeamento:
    iab_id: str | None
    caminho: str
    nota: str = ""

    @property
    def orfao(self) -> bool:
        return self.iab_id is None

    @property
    def tier1(self) -> str | None:
        return self.caminho.split(" > ")[0] if self.iab_id else None


ARQUETIPO_IAB: dict[str, Mapeamento] = {
    # ── Personal Finance ────────────────────────────────────────────────────
    "transferencia_renda": Mapeamento(
        "394", "Personal Finance > Financial Assistance > Government Support and Welfare"),
    "cadastro_social_unico": Mapeamento(
        "394", "Personal Finance > Financial Assistance > Government Support and Welfare",
        "cadastro é porta de entrada do benefício; mesmo nó, mesma demanda"),
    "fundo_verba_trabalhista": Mapeamento(
        "393", "Personal Finance > Financial Assistance",
        "FGTS/Cesantias não são 'welfare' — são verba própria retida; sobe um nível"),
    "previdencia_aposentadoria": Mapeamento(
        "416", "Personal Finance > Retirement Planning"),
    "saude_publica": Mapeamento(
        "399", "Personal Finance > Insurance > Health Insurance",
        "EPS/ADRES/SUS são cobertura; o comprador adjacente é seguro-saúde"),
    "tributo_fiscal": Mapeamento(
        "415", "Personal Finance > Personal Taxes"),
    "habitacao_popular": Mapeamento(
        "407", "Personal Finance > Personal Debt > Home Financing",
        "não é Real Estate > Houses: quem busca subsídio quer financiamento, não imóvel"),
    "educacao_superior_bolsa": Mapeamento(
        "395", "Personal Finance > Financial Assistance > Student Financial Aid"),
    "credito_financeiro": Mapeamento(
        "408", "Personal Finance > Personal Debt > Personal Loans"),

    # ── Careers: bairro pequeno (9 nós) e desproporcionalmente rentável ─────
    "curso_gratuito_profissionalizante": Mapeamento(
        "131", "Careers > Vocational Training"),
    "emprego_jovem_aprendiz": Mapeamento(
        "124", "Careers > Apprenticeships",
        "correspondência literal — o IAB tem um nó exato para isto"),
    "emprego_gig_entrega": Mapeamento(
        "127", "Careers > Job Search"),
    "emprego_concurso_publico": Mapeamento(
        "127", "Careers > Job Search"),
    "emprego_vaga_privada": Mapeamento(
        "127", "Careers > Job Search"),

    # ── demais ──────────────────────────────────────────────────────────────
    "transito_veicular": Mapeamento(
        "35", "Automotive > Auto Safety",
        "encaixe ruim e é sintoma: multa de trânsito não tem comprador natural"),
    "transporte_publico": Mapeamento(
        "1", "Automotive"),
    "leilao_bens": Mapeamento(
        "451", "Real Estate > Real Estate Buying and Selling"),
    "ecommerce_logistica": Mapeamento(
        "473", "Shopping"),
    "entretenimento_midia": Mapeamento(
        "199", "Entertainment"),

    # ── ÓRFÃOS — a ausência é o ativo ──────────────────────────────────────
    "documento_identidade_civil": Mapeamento(
        None, "(sem nó IAB)",
        "Não existe categoria para documento de identidade civil nas 704 do "
        "IAB. Nenhum comprador mira; ninguém compete. É o fosso — e ele acaba "
        "no dia em que o IAB criar o nó."),
    "app_servico_gov": Mapeamento(
        None, "(sem nó IAB)",
        "Aplicativo oficial de governo não tem nó. Mesmo fenômeno."),
    "outros": Mapeamento(None, "(não classificado)"),
}


# ── vetores de propósito: onde a armadilha de lookup vira padrão ────────────

PROPOSITO_INSTRUCIONAL = "Informational > Instructional"
PROPOSITO_UTILITARIO = "Utility/Online Tool"
PROPOSITO_NOTICIA = "Informational > News"

# "describing how to do things or how things work" — a definição do IAB é
# literalmente a página que ganha dinheiro nesta operação.
_INSTRUCIONAL = re.compile(
    r"\b(como|c[oó]mo|how to|passo a passo|paso a paso|guia|gu[ií]a|"
    r"tutorial|quem tem direito|qui[eé]n (tiene|puede)|requisitos|"
    r"o que [eé]|qu[eé] es|entenda|entender|aprenda)\b", re.IGNORECASE)

# "appearing in a utility/tool" — a página que responde e some. O usuário
# consulta, recebe o dado e fecha. Um pageview, zero profundidade.
_UTILITARIO = re.compile(
    r"\b(multa|infra[cç][aã]o|placa|patente|comparendo|antecedente|"
    r"situa[cç][aã]o cadastral|status|protocolo|saldo|extrato|"
    r"pontos na|d[ií]vida ativa|rastrear|rastreio)\b", re.IGNORECASE)


def classificar_proposito(termo: str, descricao: str = "") -> str:
    """Qual vetor de Content Purpose a página serve.

    A ordem importa: o utilitário vence. Uma página "como consultar multa por
    placa" ainda é uma consulta de registro — o `como` não salva, porque o que
    o usuário quer é o dado, não a explicação.
    """
    alvo = f"{termo} {descricao}"
    if _UTILITARIO.search(alvo):
        return PROPOSITO_UTILITARIO
    if _INSTRUCIONAL.search(alvo):
        return PROPOSITO_INSTRUCIONAL
    return PROPOSITO_NOTICIA


# ── taxonomia ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def taxonomia() -> dict[str, dict]:
    """As 704 categorias, por ID."""
    if not _CONTENT.exists():
        return {}
    linhas = list(csv.reader(_CONTENT.open(), delimiter="\t"))
    out = {}
    for r in linhas[2:]:
        if len(r) < 4 or not r[0].strip():
            continue
        out[r[0].strip()] = {
            "nome": r[2].strip() if len(r) > 2 else "",
            "caminho": " > ".join(x.strip() for x in r[3:7] if x.strip()),
            "tier1": r[3].strip() if len(r) > 3 else "",
        }
    return out


def de(arquetipo: str | None) -> Mapeamento | None:
    return ARQUETIPO_IAB.get(arquetipo or "")


