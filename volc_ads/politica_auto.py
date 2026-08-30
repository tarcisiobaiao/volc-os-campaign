"""Quando o Google recusa por política: isentar, ou tirar do caminho?

## O caso que originou este módulo

Medido no card 65 em 19/08/2026, `validate_only` contra a conta real. Duas
keywords derrubaram um mutate de 114 operações — os 15 títulos, as 4 descrições,
os sitelinks e os callouts passaram todos:

    NON_FAMILY_SAFE  · 'como sacar o fgts na caixa'                    isentável
    PERSONAL_LOANS   · 'saldo bloqueado fgts empréstimo como desbloquear'  isentável

A API marcou as DUAS como `is_exemptible=True`. E mesmo assim elas não merecem o
mesmo tratamento — é exatamente essa diferença que este módulo carrega.

## A regra: o padrão é REMOVER, não isentar

Pedir isenção é AFIRMAR ao Google que o anúncio não é daquela categoria. Quando
é verdade — um classificador marcou "sacar o fgts na caixa" como impróprio para
família, o que não se sustenta ao ler a frase —, o pedido é honesto e o certo.

Quando a política nomeia uma categoria que o texto REALMENTE toca — uma keyword
que contém "empréstimo" marcada como `PERSONAL_LOANS` —, pedir isenção é
declarar o que não se é. O resultado não é anúncio aprovado: é anúncio que sobe,
veicula e cai depois, com a conta marcada. É a mesma doutrina já escrita no
portão de política do cockpit: *declarar uma certificação que você não tem não
engana o Google — só troca "barrado antes" por "reprovado depois de veicular"*.

Por isso `ISENTAR_SOZINHO` é uma ALLOWLIST, e curta. O desconhecido cai no
padrão seguro: a keyword sai, a campanha sobe sem ela.

⚠️ E a lista nasce do que foi MEDIDO, não do que dá para imaginar. Só entra
política que apareceu numa recusa real e cuja natureza de ruído foi lida. Uma
lista inventada de dez nomes seria pior que uma lista de um: daria a impressão
de cobertura onde há palpite.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .gads.errors import ChavePolitica, FalhaGads

#: Políticas cuja isenção o motor pede SOZINHO.
#:
#: `NON_FAMILY_SAFE` entrou por evidência: o classificador marcou
#: 'como sacar o fgts na caixa' — uma consulta de utilidade pública sobre um
#: fundo de garantia. Não há leitura da frase em que ela seja imprópria para
#: família. É ruído de classificador, e isenção é o remédio desenhado para isso.
ISENTAR_SOZINHO: frozenset[str] = frozenset({"NON_FAMILY_SAFE"})


@dataclass(frozen=True)
class Decisao:
    """O que fazer com uma falha de política, item por item.

    Os três grupos são disjuntos e nomeiam destinos diferentes — misturá-los
    faria a tela dizer "resolvido" sobre algo que só foi escondido.
    """

    #: Chaves a mandar em `exempt_policy_violation_keys`.
    isentar: tuple[ChavePolitica, ...] = ()
    #: Textos que violaram e vão SAIR do brief (keywords, hoje).
    remover: tuple[str, ...] = ()
    #: Violações sem remédio automático — nem isenção, nem remoção segura.
    sem_remedio: tuple[str, ...] = ()
    #: Uma linha por decisão, para o recibo e para a tela.
    diario: tuple[str, ...] = field(default_factory=tuple)

    @property
    def acionavel(self) -> bool:
        return bool(self.isentar or self.remover)

    def resumo(self) -> str:
        partes = []
        if self.isentar:
            partes.append(f"{len(self.isentar)} isenção(ões)")
        if self.remover:
            partes.append(f"{len(self.remover)} keyword(s) removida(s)")
        if self.sem_remedio:
            partes.append(f"{len(self.sem_remedio)} sem remédio")
        return " · ".join(partes) or "nada a fazer"


def decidir(falha: FalhaGads, *,
            isentar_sozinho: frozenset[str] = ISENTAR_SOZINHO) -> Decisao:
    """Lê a evidência de política e decide o destino de cada violação.

    NÃO chama rede, NÃO muda nada. Devolve a decisão para quem orquestra
    aplicar — do mesmo jeito que `isencao.montar` devolve o plano sem executá-lo.
    """
    isentar: list[ChavePolitica] = []
    remover: list[str] = []
    sem_remedio: list[str] = []
    diario: list[str] = []

    for erro in (falha.erros or ()):
        p = erro.politica
        if p is None:
            continue
        chave = p.chave
        texto = (chave.violating_text if chave else "") or erro.gatilho
        nome = (chave.policy_name if chave else "") or "?"

        if p.formato != "violacao" or not texto:
            # Formato `achado` traz TÓPICOS, não chave — o remédio é outro
            # campo (`ignorable_policy_topics`) e a decisão é diferente. Fora
            # do escopo deste módulo, e dizê-lo é melhor que tratar errado.
            sem_remedio.append(f"{nome}: formato {p.formato}, sem chave")
            diario.append(f"⊘ {nome} — formato {p.formato}: não tratado aqui")
            continue

        if p.isentavel is not True:
            remover.append(texto)
            diario.append(f"✂ {nome} sobre {texto!r}: não é isentável — removida")
            continue

        if nome in isentar_sozinho:
            if chave is not None:
                isentar.append(chave)
                diario.append(f"✓ {nome} sobre {texto!r}: isenção pedida "
                              f"(ruído de classificador conhecido)")
            continue

        # Isentável, mas fora da allowlist: o padrão seguro. Pedir isenção de
        # uma política que o texto realmente toca troca "barrado agora" por
        # "reprovado depois de veicular".
        remover.append(texto)
        diario.append(f"✂ {nome} sobre {texto!r}: isentável, mas a política "
                      f"nomeia a categoria do texto — removida em vez de isentada")

    return Decisao(
        isentar=tuple(isentar),
        remover=tuple(dict.fromkeys(remover)),
        sem_remedio=tuple(sem_remedio),
        diario=tuple(diario),
    )


def podar(keywords: list[str], remover: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Tira do conjunto as keywords que violaram. Devolve (ficaram, saíram).

    A comparação é frouxa de propósito — sem caixa e sem espaço nas pontas. O
    `violating_text` volta do Google normalizado, e uma comparação exata
    deixaria a keyword no brief; a próxima validação reprovaria igual, e o
    motor pareceria não ter feito nada.
    """
    alvo = {t.strip().lower() for t in remover if t and t.strip()}
    if not alvo:
        return list(keywords), []
    ficaram = [k for k in keywords if k.strip().lower() not in alvo]
    sairam = [k for k in keywords if k.strip().lower() in alvo]
    return ficaram, sairam
