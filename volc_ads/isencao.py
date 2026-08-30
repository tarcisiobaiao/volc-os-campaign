"""Monta o PEDIDO de isenção de política. Não envia, não decide, não corrige.

## O que uma isenção realmente faz — leia antes de usar este módulo

O proto da v25 diz, com todas as letras, nos dois campos de isenção:

    "Resources that violate these policies will be saved, but will not be
     eligible to serve. They may begin serving at a later time due to a change
     in policies, re-review of the resource, or a change in advertiser
     certificates."
    (google/ads/googleads/v25/common/types/policy.py, PolicyValidationParameter)

Isento não é aprovado. A isenção faz o **mutate passar** e o recurso ser
**salvo**; ele continua **inelegível para servir**. Quem já viu isso na
operação reconhece o estado: é o `FULLY_LIMITED` medido em 57 anúncios de 39
contas sob GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES. Ou seja, pedir isenção
troca "o mutate falhou" por "a campanha existe e não roda". Às vezes é
exatamente o que se quer — persistir o recurso para que a re-revisão o alcance.
Nunca é um conserto.

Por isso **nada aqui pede isenção sozinho**. O módulo monta o pedido, nomeia o
campo exato e explica o que aceitar aquilo significa. Quem decide é o humano, e
quem aplica o pedido a uma operação é quem chama `aplicar()`.

## Os dois formatos, e por que confundi-los falha em silêncio

`gads/errors.py` já preserva a evidência e já nomeia o remédio em
`Politica.remedio`. Este módulo é o passo seguinte: transformar o nome do
remédio no CAMPO da requisição — e os campos não são os mesmos entre alvos.
Medido lendo os protos da v25 instalada (`google-ads` 31.3.0):

    AdGroupAdOperation      .policy_validation_parameter.exempt_policy_violation_keys
    AdGroupAdOperation      .policy_validation_parameter.ignorable_policy_topics
    AdOperation             .policy_validation_parameter.(os mesmos dois)
    AdGroupCriterionOperation.exempt_policy_violation_keys        ← direto, sem parâmetro
    AssetGroupSignalOperation.exempt_policy_violation_keys        ← direto, sem parâmetro

⚠️ Duas consequências que o cabeçalho de `errors.py` não detalha, e que custam
uma requisição recusada:

1. No anúncio, `exempt_policy_violation_keys` **não** fica na operação: fica
   dentro de `policy_validation_parameter`. No critério (keyword), fica na
   operação, e **`ignorable_policy_topics` não existe lá** (verificado:
   `AdGroupCriterionOperation` levanta AttributeError). Achado de política numa
   keyword, portanto, não tem remédio nesta superfície da API.

2. Os dois campos são **mutuamente exclusivos**: "If this field is populated,
   then `exempt_policy_violation_keys` must be empty" — e o simétrico. Uma
   operação carrega UM remédio, nunca os dois.

E a armadilha que `errors.py` já avisava: passar a chave onde se espera o
tópico não levanta erro nenhum. A requisição é aceita, nada é isentado, e o
anúncio segue reprovado. É o motivo de o `Pedido` carregar o caminho do campo
por escrito em vez de deixar a escolha para quem chama.

Uso:
    plano = isencao.montar(falha)          # `falha` é a FalhaGads do recibo
    print(plano.relatorio())               # o humano lê e decide
    isencao.aplicar(c, operacao, pedido)   # só depois, e só se ele mandar
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gads.errors import ChavePolitica, ErroGads, FalhaGads

# Alvos que a v25 aceita isentar, e como. `parametro=True` significa que os
# campos moram dentro de `policy_validation_parameter`; `False`, que moram na
# própria operação. `topicos=False` significa que o alvo não tem
# `ignorable_policy_topics` — achado de política ali é irremediável por API.
ALVO_AD = "ad_group_ad"
ALVO_CRITERIO = "ad_group_criterion"

ALVOS: dict[str, dict[str, bool]] = {
    ALVO_AD: {"parametro": True, "topicos": True},
    ALVO_CRITERIO: {"parametro": False, "topicos": False},
}

CAMPO_CHAVES = "exempt_policy_violation_keys"
CAMPO_TOPICOS = "ignorable_policy_topics"

# O que a isenção significa, em uma frase, colada do proto da v25. Vai em todo
# relatório porque é a informação que muda a decisão e a que mais se esquece.
SIGNIFICADO = (
    "isentar NÃO publica: o recurso é SALVO e fica INELEGÍVEL para servir; "
    "pode passar a servir depois por mudança de política, nova revisão ou "
    "certificado do anunciante (proto v25, PolicyValidationParameter)"
)


class RemedioConflitante(RuntimeError):
    """Tentativa de pôr os dois remédios na mesma operação."""


class AlvoTrocado(RuntimeError):
    """O pedido é de um tipo de operação e a operação recebida é de outro."""


@dataclass(frozen=True)
class Recusa:
    """Um erro de política para o qual NÃO existe pedido a montar.

    Existe como registro, não como exceção: um erro sem remédio é informação
    para o operador ("esse aqui reescreva, não adianta pedir"), e some se for
    tratado como falha do módulo.
    """

    motivo: str
    evidencia: str

    def __str__(self) -> str:
        return f"{self.motivo} — {self.evidencia}"


@dataclass(frozen=True)
class Pedido:
    """Um pedido de isenção pronto, para UMA operação do mutate.

    Não é uma ação. É a descrição completa de uma ação possível: onde ela
    encosta (`alvo`, `indice_operacao`), em que campo (`caminho`), com que
    conteúdo (`chaves` ou `topicos`).
    """

    alvo: str                       # ALVO_AD | ALVO_CRITERIO
    formato: str                    # "violacao" | "achado"
    indice_operacao: int
    chaves: tuple[ChavePolitica, ...] = ()
    topicos: tuple[str, ...] = ()

    @property
    def campo(self) -> str:
        return CAMPO_CHAVES if self.formato == "violacao" else CAMPO_TOPICOS

    @property
    def caminho(self) -> str:
        """O caminho EXATO na requisição — é isto que o operador confere."""
        meio = ".policy_validation_parameter" if ALVOS[self.alvo]["parametro"] else ""
        return f"{self.alvo}_operation{meio}.{self.campo}"

    def descrever(self) -> str:
        linhas = [
            f"operação [{self.indice_operacao}] · {self.caminho}",
            f"  significado: {SIGNIFICADO}",
        ]
        for c in self.chaves:
            linhas.append(f"  isentar   {c.policy_name} sobre {c.violating_text!r}")
        for t in self.topicos:
            linhas.append(f"  ignorar   tópico {t}")
        return "\n".join(linhas)


@dataclass(frozen=True)
class Plano:
    """Tudo o que dá para pedir a partir de UMA falha, e tudo o que não dá."""

    pedidos: tuple[Pedido, ...] = ()
    recusas: tuple[Recusa, ...] = ()

    @property
    def acionavel(self) -> bool:
        return bool(self.pedidos)

    def relatorio(self) -> str:
        linhas: list[str] = []
        if not self.pedidos:
            linhas.append("nenhum pedido de isenção é possível para esta falha.")
        for p in self.pedidos:
            linhas.append(p.descrever())
        for r in self.recusas:
            linhas.append(f"sem remédio: {r}")
        if self.pedidos:
            linhas.append(
                "DECISÃO HUMANA: nada foi aplicado nem enviado. Aplicar exige "
                "chamar aplicar() operação por operação."
            )
        return "\n".join(linhas)


# ── montagem ───────────────────────────────────────────────────────────────


def montar(falha: FalhaGads) -> Plano:
    """Lê a evidência de política de uma falha e monta os pedidos possíveis.

    Percorre `falha.erros` um a um em vez de usar `falha.chaves_isentaveis` /
    `falha.topicos_ignoraveis`: essas propriedades agregam a falha inteira e
    perdem o `indice_operacao`, que é justamente o que diz EM QUAL das ~72
    operações o parâmetro de isenção precisa ser escrito. Agregado é bom para
    relatório; para montar requisição, o índice é o dado.
    """
    pedidos: list[Pedido] = []
    recusas: list[Recusa] = []

    for erro in falha.erros:
        if not erro.de_politica or erro.politica is None:
            continue
        pedido, recusa = _do_erro(erro)
        if pedido is not None:
            pedidos.append(pedido)
        if recusa is not None:
            recusas.append(recusa)

    pedidos, conflitos = _separar_conflitos(pedidos)
    return Plano(pedidos=tuple(pedidos), recusas=tuple(recusas) + tuple(conflitos))


def _do_erro(erro: ErroGads) -> tuple[Pedido | None, Recusa | None]:
    pol = erro.politica
    assert pol is not None  # garantido por quem chama

    if erro.indice_operacao is None:
        return None, Recusa(
            "sem índice de operação",
            f"{erro.campo_codigo} em {erro.caminho_campo or '?'} — não há como "
            "saber em qual operação escrever o parâmetro de isenção",
        )

    alvo = _alvo_do_caminho(erro.caminho_campo)
    if alvo is None:
        return None, Recusa(
            "alvo não reconhecido",
            f"{erro.caminho_campo or '?'} — a v25 só aceita isenção em "
            f"{', '.join(sorted(ALVOS))} (e em ad/asset_group_signal, fora "
            "do escopo do construtor de Search)",
        )

    if pol.formato == "violacao":
        if pol.isentavel is not True:
            return None, Recusa(
                "violação não isentável",
                f"is_exemptible={pol.isentavel} · {pol.nome_externo or '?'} — "
                "pedir isenção aqui é requisição rejeitada, não anúncio salvo",
            )
        if pol.chave is None:
            return None, Recusa(
                "violação sem PolicyViolationKey",
                f"{pol.nome_externo or '?'} — sem a chave exata não há o que "
                "pôr em exempt_policy_violation_keys",
            )
        # `violating_text` é opcional no proto, mas o próprio proto diz: "Must
        # be specified for ad exemptions". No critério, ausente = a política
        # inteira. Deixar passar vazio num anúncio seria montar um pedido que a
        # API recusa, com a mensagem genérica de campo obrigatório.
        if alvo == ALVO_AD and not pol.chave.violating_text:
            return None, Recusa(
                "chave sem violating_text",
                f"{pol.chave.policy_name} — o proto exige violating_text para "
                "isenção de anúncio",
            )
        return Pedido(alvo=alvo, formato="violacao",
                      indice_operacao=erro.indice_operacao,
                      chaves=(pol.chave,)), None

    if pol.formato == "achado":
        if not ALVOS[alvo]["topicos"]:
            return None, Recusa(
                "achado sem campo de remédio neste alvo",
                f"{alvo}_operation não tem {CAMPO_TOPICOS} na v25 — achado de "
                "política em keyword só se resolve reescrevendo a keyword",
            )
        topicos = tuple(t.topico for t in pol.topicos if t.ignoravel and t.topico)
        if not topicos:
            proibidos = ", ".join(f"{t.topico}:{t.tipo}" for t in pol.topicos) or "?"
            return None, Recusa(
                "nenhum tópico ignorável",
                f"{proibidos} — PROHIBITED não vira publicável por ser ignorado",
            )
        return Pedido(alvo=alvo, formato="achado",
                      indice_operacao=erro.indice_operacao,
                      topicos=topicos), None

    return None, Recusa("formato de política desconhecido", pol.formato)


def _alvo_do_caminho(caminho: str) -> str | None:
    """Descobre o alvo lendo o `field_path` que `errors.py` preservou.

    O caminho de um mutate atômico nomeia a operação:
    `mutate_operations[12].ad_group_ad_operation.create.ad...`. Ler dali é
    melhor que perguntar ao operador — a evidência já diz, e adivinhar errado
    escreve o parâmetro na operação errada.
    """
    for alvo in ALVOS:
        if f"{alvo}_operation" in caminho:
            return alvo
    return None


def _separar_conflitos(pedidos: list[Pedido]) -> tuple[list[Pedido], list[Recusa]]:
    """Duas isenções de formatos diferentes na MESMA operação não existem.

    O proto é explícito: populado um campo, o outro tem de ficar vazio. Se a
    falha produziu os dois para o mesmo índice, aplicar ambos daria requisição
    recusada — e aplicar só um, escolhido por ordem de chegada, esconderia
    metade do problema. Os dois viram recusa e o operador decide qual pedir.
    """
    por_indice: dict[int, list[Pedido]] = {}
    for p in pedidos:
        por_indice.setdefault(p.indice_operacao, []).append(p)

    limpos: list[Pedido] = []
    conflitos: list[Recusa] = []
    for indice, grupo in por_indice.items():
        formatos = {p.formato for p in grupo}
        if len(formatos) > 1:
            conflitos.append(Recusa(
                "remédios mutuamente exclusivos na mesma operação",
                f"operação [{indice}] gerou violação E achado; o proto exige "
                f"que {CAMPO_CHAVES} e {CAMPO_TOPICOS} não sejam populados "
                "juntos. Escolha um e monte o pedido à mão",
            ))
            continue
        limpos.extend(_fundir(grupo))
    return limpos, conflitos


def _fundir(grupo: list[Pedido]) -> list[Pedido]:
    """Vários erros na mesma operação e no mesmo formato viram UM pedido.

    A operação recebe um `policy_validation_parameter` só; dois pedidos para o
    mesmo índice fariam o segundo `aplicar()` sobrescrever ou duplicar o
    primeiro, dependendo de quem chama. Fundir aqui tira essa decisão da mão de
    quem chama.
    """
    if len(grupo) == 1:
        return grupo
    base = grupo[0]
    chaves: list[ChavePolitica] = []
    topicos: list[str] = []
    for p in grupo:
        for c in p.chaves:
            if c not in chaves:
                chaves.append(c)
        for t in p.topicos:
            if t not in topicos:
                topicos.append(t)
    return [Pedido(alvo=base.alvo, formato=base.formato,
                   indice_operacao=base.indice_operacao,
                   chaves=tuple(chaves), topicos=tuple(topicos))]


# ── aplicação (monta o payload; NÃO envia) ─────────────────────────────────


def aplicar(c: Any, operacao: Any, pedido: Pedido) -> Any:
    """Escreve o pedido na `MutateOperation`. Nenhuma chamada de rede acontece.

    Devolve a própria operação, alterada no lugar. Enviar é problema de quem
    chama, e passa pela trava de `modo.py` como qualquer outra escrita.
    """
    nome_sub = f"{pedido.alvo}_operation"
    atual = _qual_oneof(operacao, "operation")

    # ⚠️ Sem esta porta, aplicar um pedido de anúncio a uma operação de
    # critério destruiria a operação em silêncio. Medido no proto da v25:
    # depois de `op.ad_group_ad_operation.create.ad_group = "x"`, escrever em
    # `op.ad_group_criterion_operation` deixa `WhichOneof("operation")` em
    # `ad_group_criterion_operation` e `ad_group_ad_operation.create.ad_group`
    # volta a `''`. O oneof não avisa: ele apaga.
    if atual and atual != nome_sub:
        raise AlvoTrocado(
            f"o pedido é para {nome_sub} e a operação recebida é {atual}. "
            "Escrever assim apagaria a operação existente — o oneof do "
            "MutateOperation troca sem avisar. Nada foi alterado."
        )

    sub = getattr(operacao, nome_sub)
    destino = sub.policy_validation_parameter if ALVOS[pedido.alvo]["parametro"] else sub

    ja_chaves = len(getattr(destino, CAMPO_CHAVES, ()) or ())
    ja_topicos = len(getattr(destino, CAMPO_TOPICOS, ()) or ())

    if pedido.formato == "violacao":
        if ja_topicos:
            raise RemedioConflitante(
                f"{CAMPO_TOPICOS} já tem {ja_topicos} tópico(s) nesta operação; "
                f"o proto exige {CAMPO_CHAVES} vazio quando ele está populado. "
                "Nada foi alterado."
            )
        alvo_lista = getattr(destino, CAMPO_CHAVES)
        for chave in pedido.chaves:
            k = c.get_type("PolicyViolationKey")
            k.policy_name = chave.policy_name
            k.violating_text = chave.violating_text
            alvo_lista.append(k)
        return operacao

    if pedido.formato == "achado":
        if not ALVOS[pedido.alvo]["topicos"]:
            raise RemedioConflitante(
                f"{pedido.alvo}_operation não tem {CAMPO_TOPICOS} na v25. "
                "Nada foi alterado."
            )
        if ja_chaves:
            raise RemedioConflitante(
                f"{CAMPO_CHAVES} já tem {ja_chaves} chave(s) nesta operação; o "
                f"proto exige {CAMPO_TOPICOS} vazio quando ele está populado. "
                "Nada foi alterado."
            )
        getattr(destino, CAMPO_TOPICOS).extend(pedido.topicos)
        return operacao

    raise RemedioConflitante(f"formato desconhecido: {pedido.formato!r}")


def _qual_oneof(mensagem: Any, nome: str) -> str:
    """`WhichOneof` mora no pb2; proto-plus o esconde atrás de `_pb`."""
    for alvo in (mensagem, getattr(mensagem, "_pb", None)):
        which = getattr(alvo, "WhichOneof", None)
        if which is None:
            continue
        try:
            campo = which(nome)
        except Exception:  # noqa: BLE001 — objeto sem esse oneof
            continue
        if campo:
            return str(campo)
    return ""
