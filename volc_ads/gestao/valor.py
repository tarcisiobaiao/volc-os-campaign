"""`ValorMonetario`: todo número que vira verba ou lance diz de onde veio.

Sem isto, `AlterarOrcamento(…, 35_000_000)` não distinguia um valor digitado
pelo operador de um CPC de SERP, de uma ideia do Keyword Planner ou de uma
estimativa de modelo — e qualquer um deles autorizaria verba.

A regra (C-google.md, 15/10; endurecida no ciclo 1 da revisão R-W5): só duas
origens LIBERAM dinheiro, e as duas são escritas pelo SERVIDOR, nunca por quem
chama.

  operador         um humano numa sessão autenticada digitou o número.
                   evidência: `operador:<sub>/<papel>@<quando>` carimbada pelo
                   backend a partir da identidade, + `justificativa` (≥ 10
                   caracteres). Identidade de serviço (n8n, script) não é operador.
  medido_na_conta  o número foi LIDO na conta pelo próprio backend e está
                   guardado. evidência: `medicao:<fonte>/<ref>#<campo>@<as_of>
                   sha256=<hash do registro>`. Texto livre ("SELECT … -- semrush")
                   não é medição. A fonte é conferida contra o registro guardado
                   na borda (`backend/.../casos_de_uso.py`, `_conferir_medicoes`).

Qualquer outra origem (serp, keyword_planner, dataforseo, ferramenta_externa,
estimativa_modelo, nao_informada) é ANOTAÇÃO: o valor pode existir, ser
mostrado e ser gravado, mas `autoriza()` levanta. As ações de gestão chamam
`autoriza()` dentro de `operacoes()` — a função que monta a `MutateOperation`
—, e a criação de campanha confere em `subir.preparar()` antes do
`validate_only`: a recusa vem antes de existir requisição, no ensaio também.

`micros=None` é ausência, nunca zero, e não autoriza nada. Negativo não é verba.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal


Origem = Literal["operador", "medido_na_conta", "serp", "keyword_planner", "dataforseo",
                 "ferramenta_externa", "estimativa_modelo", "nao_informada"]
ORIGENS: frozenset[str] = frozenset(Origem.__args__)  # type: ignore[attr-defined]
ORIGENS_QUE_AUTORIZAM: frozenset[str] = frozenset({"operador", "medido_na_conta"})

_EVIDENCIA_OPERADOR = re.compile(r"operador:[^/\s@]+/[^/\s@]+@\S+")
_EVIDENCIA_MEDICAO = re.compile(
    r"medicao:(?P<fonte>[a-z_.]+)/(?P<ref>[^#\s]+)#(?P<campo>[a-z_]+)"
    r"@(?P<as_of>\S+) sha256=(?P<sha256>[0-9a-f]{64})")
#: Onde o backend guarda o que ele mesmo leu na conta.
#:   trafego_proposta.valor_atual  o "antes" que `propor` leu (ref = proposta_id)
#:   valor_anterior                o que `aplicar` leu no envio (só o reverso usa)
FONTES_DE_MEDICAO: frozenset[str] = frozenset({"trafego_proposta.valor_atual",
                                               "valor_anterior"})
JUSTIFICATIVA_MINIMA = 10


def sha256_canonico(registro: Any) -> str:
    """O hash que amarra a evidência ao registro guardado (mesma forma do jsonb)."""
    corpo = json.dumps(registro, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                       default=str)
    return hashlib.sha256(corpo.encode()).hexdigest()


class AcaoRecusada(ValueError):
    """A ação não sai da máquina: inválida em si, ou incompatível com o "antes".

    Mora aqui (e `acoes.py` a reexporta) para `ValorSemAutoridade` ser uma
    recusa de ação sem import circular.
    """


class ValorSemAutoridade(AcaoRecusada):
    """O número existe, mas a origem dele não libera verba nem lance."""


@dataclass(frozen=True)
class Medicao:
    fonte: str
    ref: str
    campo: str
    as_of: str
    sha256: str


@dataclass(frozen=True)
class ValorMonetario:
    micros: int | None
    origem: str
    evidencia: str
    justificativa: str = ""

    def __post_init__(self):
        if self.origem not in ORIGENS:
            raise AcaoRecusada(
                f"origem de valor desconhecida: {self.origem!r} (válidas: {sorted(ORIGENS)})")
        if self.micros is not None and (isinstance(self.micros, bool)
                                        or not isinstance(self.micros, int)):
            raise AcaoRecusada(f"micros tem de ser inteiro ou None: {self.micros!r}")
        if self.micros is not None and self.micros < 0:
            raise AcaoRecusada(f"micros negativo não é verba nem lance: {self.micros}")
        if not isinstance(self.evidencia, str) or not self.evidencia.strip():
            raise AcaoRecusada(f"valor de origem {self.origem!r} sem evidência")

    def autoriza(self) -> int:
        """O único jeito de um número virar verba ou lance. Estimativa nunca passa."""
        if self.origem not in ORIGENS_QUE_AUTORIZAM:
            raise ValorSemAutoridade(
                f"origem {self.origem!r} é anotação, não autoriza verba nem lance "
                f"(só {sorted(ORIGENS_QUE_AUTORIZAM)})")
        if self.micros is None:
            raise ValorSemAutoridade("valor ausente não autoriza nada")
        if self.origem == "operador":
            if not _EVIDENCIA_OPERADOR.fullmatch(self.evidencia):
                raise ValorSemAutoridade(
                    "origem operador exige a evidência carimbada pelo servidor "
                    f"`operador:<sub>/<papel>@<quando>`: {self.evidencia!r}")
            if len("".join(str(self.justificativa or "").split())) < JUSTIFICATIVA_MINIMA:
                raise ValorSemAutoridade(
                    f"origem operador exige justificativa (≥ {JUSTIFICATIVA_MINIMA} caracteres)")
        if self.origem == "medido_na_conta":
            m = self.medicao
            if m is None or m.fonte not in FONTES_DE_MEDICAO:
                raise ValorSemAutoridade(
                    "origem medido_na_conta exige referência a uma leitura guardada pelo "
                    "backend (`medicao:<fonte>/<ref>#<campo>@<as_of> sha256=<hash>`, fonte em "
                    f"{sorted(FONTES_DE_MEDICAO)}); texto livre não é medição: "
                    f"{self.evidencia[:200]!r}")
        return self.micros

    @property
    def medicao(self) -> Medicao | None:
        m = _EVIDENCIA_MEDICAO.fullmatch(self.evidencia)
        return Medicao(**m.groupdict()) if m else None

    def json(self) -> dict:
        """O que vai para `valor_proposto.origem_valor` (o número já está ao lado)."""
        v = {"origem": self.origem, "evidencia": self.evidencia}
        if self.justificativa:
            v["justificativa"] = self.justificativa
        return v


def operador(micros: int, sub: str, papel: str, quando: str,
             justificativa: str) -> ValorMonetario:
    """Só o servidor chama: `sub`/`papel` vêm da identidade autenticada."""
    return ValorMonetario(micros, "operador", f"operador:{sub}/{papel}@{quando}", justificativa)


def medido_na_conta(micros: int, *, fonte: str, ref: str, campo: str, as_of: str,
                    registro: Any) -> ValorMonetario:
    """Valor lido pelo backend, amarrado ao registro guardado por hash."""
    if not isinstance(registro, dict) or registro.get(campo) != micros:
        raise AcaoRecusada(f"a medição {fonte}/{ref} não tem {campo} = {micros}")
    return ValorMonetario(
        micros, "medido_na_conta",
        f"medicao:{fonte}/{ref}#{campo}@{as_of} sha256={sha256_canonico(registro)}")


# ── criação de campanha: o mesmo crivo, sobre as operações prontas ─────────

#: Campos de proto que põem dinheiro na conta: lance, teto, meta e orçamento.
#: `amount_micros` só conta dentro de `CampaignBudget` (em `Money`, num asset
#: de preço, é vitrine, não verba). `percent_cpc_bid_micros` é percentual.
CAMPOS_DE_DINHEIRO: frozenset[str] = frozenset({
    "cpc_bid_micros", "cpm_bid_micros", "cpv_bid_micros", "target_cpa_micros",
    "target_cpm_micros", "target_cpc_micros", "cpc_bid_ceiling_micros",
    "total_amount_micros",
})


def dinheiro_nas_operacoes(operacoes: Any) -> list[tuple[str, int]]:
    """(caminho, micros) de todo número > 0 de verba/lance nas `MutateOperation`.

    Varre o proto cru (`_pb`), sem saber o canal: o que importa é o que vai ao
    Google, não o builder que o montou. Zero é "sem alvo", não dinheiro.
    """
    achados: list[tuple[str, int]] = []

    def varrer(msg: Any, caminho: str) -> None:
        for campo, valor in msg.ListFields():
            aqui = f"{caminho}.{campo.name}" if caminho else campo.name
            repetido = (campo.is_repeated if hasattr(campo, "is_repeated")
                        else campo.label == campo.LABEL_REPEATED)
            if campo.message_type is not None:
                filhos = valor if repetido else (valor,)
                for i, filho in enumerate(filhos):
                    varrer(filho, f"{aqui}[{i}]" if repetido else aqui)
                continue
            dinheiro = campo.name in CAMPOS_DE_DINHEIRO or (
                campo.name == "amount_micros"
                and msg.DESCRIPTOR.name == "CampaignBudget")
            if dinheiro and isinstance(valor, int) and valor > 0:
                achados.append((aqui, int(valor)))

    for i, op in enumerate(operacoes):
        varrer(getattr(op, "_pb", op), f"operacoes[{i}]")
    return achados


def exigir_dinheiro_autorizado(operacoes: Any, valores: Any) -> None:
    """Todo número de verba/lance das operações tem um `ValorMonetario` que autoriza.

    Casa por valor em micros: o operador declara "orçamento R$ 50, CPC R$ 1,20",
    e o payload não pode carregar um número que ninguém declarou (um CPC
    derivado de SERP no meio do builder, um default esquecido). Levanta
    `ValorSemAutoridade` com o primeiro número sem dono.
    """
    autorizados: set[int] = set()
    for v in valores or ():
        if not isinstance(v, ValorMonetario):
            raise ValorSemAutoridade(f"valor sem origem na criação: {v!r}")
        autorizados.add(v.autoriza())
    for caminho, micros in dinheiro_nas_operacoes(operacoes):
        if micros not in autorizados:
            raise ValorSemAutoridade(
                f"{caminho} = {micros} micros não tem origem que autorize "
                "(operador ou medido_na_conta): a criação não monta verba nem lance "
                "que ninguém declarou")


#: Chaves de um pedido/brief que carregam dinheiro na MOEDA da conta (não micros).
CHAVES_DE_DINHEIRO_DECLARADO: frozenset[str] = frozenset({
    "budget_diario", "cpc_inicial", "tcpa", "target_cpa", "target_cpc", "teto_cpc",
    "cpc_bid_ceiling",
})


def micros_declarados(objeto: Any) -> set[int]:
    """Os números de verba/lance que um pedido (dict) ou brief (dataclass) declara."""
    import dataclasses  # noqa: PLC0415

    numeros: set[int] = set()

    def varrer(no: Any) -> None:
        if dataclasses.is_dataclass(no) and not isinstance(no, type):
            no = {f.name: getattr(no, f.name) for f in dataclasses.fields(no)}
        if isinstance(no, dict):
            for k, v in no.items():
                if (k in CHAVES_DE_DINHEIRO_DECLARADO and isinstance(v, (int, float))
                        and not isinstance(v, bool) and v > 0):
                    numeros.add(int(round(float(v) * 1_000_000)))
                else:
                    varrer(v)
        elif isinstance(no, (list, tuple)):
            for v in no:
                varrer(v)

    varrer(objeto)
    return numeros


def valores_do_operador(objeto: Any, *, sub: str, papel: str, quando: str,
                        justificativa: str) -> list[ValorMonetario]:
    """Cada número declarado vira `operador` — só quem tem a identidade chama."""
    return [operador(m, "_".join(sub.split()), "_".join((papel or "-").split()), quando,
                     justificativa) for m in sorted(micros_declarados(objeto))]
