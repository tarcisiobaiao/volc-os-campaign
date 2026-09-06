"""As autorizações que abrem o nascimento Meta PAUSED, num lugar só.

## Por que isto não mora dentro de um router

Duas rotas precisam da mesma resposta e por motivos opostos: `capacidades`
(no plano de controle seguro) precisa **relatar** o que está fechado, e
`criar-pausada` precisa **recusar** quando está. Se cada uma lesse as variáveis
por conta própria, o dia em que uma terceira flag entrasse deixaria a tela
dizendo "disponível" sobre uma rota que recusa — e o operador aprenderia a não
acreditar na tela.

Colocar isto num dos dois routers criaria um ciclo de importação: a rota de
criação já importa o compilador e os modelos da rota de validação.

## O contrato

Fechado por padrão. Uma variável ausente, vazia ou com qualquer valor que não
seja exatamente ``"1"`` significa fechado. Não existe "ligado por engano".

⚠️ `META_VALIDATE_ONLY_ENABLED` NÃO está nesta lista e nunca deve entrar. Ela
autoriza uma chamada que não cria nada. Reaproveitá-la como autorização de
criação transformaria a licença de olhar em licença de gastar — e faria uma
lane inteira de segurança depender de um nome de variável.
"""
from __future__ import annotations

import os
from typing import Mapping

#: Autoriza o ato de criar objetos reais numa conta de anúncios.
FLAG_CRIACAO = "META_CREATE_PAUSED_ENABLED"

#: Autoriza a escrita do recibo durável. Sem ela não há registro antes da
#: chamada — e criar sem recibo é criar sem poder reconciliar depois.
FLAG_LEDGER = "META_CREATE_LEDGER_WRITE_ENABLED"

#: Declara que a leitura externa de elegibilidade a Shop já foi feita para as
#: contas deste servidor, e deu não-elegível.
#:
#: ## Por que isto é uma autorização de servidor, e não um campo do pedido
#:
#: A v26 redireciona o clique de anunciantes elegíveis a Shop. A evidência
#: oficial recolhida nesta lane NÃO estabelece o campo de opt-out nem a
#: máscara de leitura (`OFFICIAL-META-API-EVIDENCE.json`, fonte `META-SHOP`:
#: `RESEARCH_REQUIRED`, `remote_behavior_proven: false`), e o contrato mestre
#: (C01) proíbe enviar campo não provado e manda bloquear `create_paused`
#: enquanto a ausência de redirecionamento não for provada.
#:
#: Pedir essa confirmação ao OPERADOR seria linhagem autoatestável: a mesma
#: parte interessada em subir a campanha assinaria a prova. Por isso ela mora
#: aqui, junto das outras autorizações do servidor — um administrador a abre
#: DEPOIS de fazer a leitura documentada no runbook, e ela nunca é inferida.
#:
#: ⚠️ Ela NÃO é uma quarta permissão de criar. Sozinha não abre nada: a criação
#: continua exigindo `FLAG_CRIACAO` e `FLAG_LEDGER`.
#:
#: ⚠️ E ela é POR CONTA, não por processo. A primeira versão aceitava `"1"`, e
#: a revisão adversarial reproduziu o preço: conferir a elegibilidade da conta
#: A e exportar a variável autorizava destino website para a conta B, C e
#: qualquer outra que a credencial alcançasse. Uma evidência sobre uma conta
#: não é evidência sobre as outras.
#:
#: O valor é a lista de referências opacas de conta que foram conferidas,
#: separadas por vírgula: `META_SHOP_REDIRECT_CLEARED=metaacct_abc,metaacct_def`.
FLAG_DESTINO_SHOP = "META_SHOP_REDIRECT_CLEARED"

#: As autorizações que valem para o PROCESSO inteiro, independentes de conta.
#: São elas que a porta da rota cobra, antes de saber qual conta o pedido
#: escolheu.
FLAGS_DE_PROCESSO: tuple[str, ...] = (FLAG_CRIACAO, FLAG_LEDGER)

#: Ordem estável: a lista de bloqueios que a tela mostra não pode dançar entre
#: dois carregamentos da mesma página.
#:
#: ⚠️ Inclui a prova de destino, que é POR CONTA. Por isso toda função que a
#: consulta recebe `account_ref`: o painel de capacidades de uma conta não pode
#: dizer "liberado" por causa da conferência de outra.
FLAGS_DE_CRIACAO: tuple[str, ...] = (FLAG_CRIACAO, FLAG_LEDGER, FLAG_DESTINO_SHOP)


def autorizacoes_de_processo_ausentes() -> list[str]:
    """As travas que não dependem de conta, para a porta da rota."""
    return [n for n in FLAGS_DE_PROCESSO if os.environ.get(n) != "1"]


def motivos_de_processo_ausentes() -> list[str]:
    return [MOTIVO_DA_FLAG[n] for n in autorizacoes_de_processo_ausentes()]

#: A causa de cada bloqueio em linguagem de operador. O NOME DA VARIÁVEL nunca
#: viaja para o navegador: quem lê a tela precisa saber que autorização falta,
#: não qual chave de ambiente alguém teria que exportar.
MOTIVO_DA_FLAG: Mapping[str, str] = {
    FLAG_CRIACAO: (
        "A criação de objetos reais está fechada neste servidor. Um administrador "
        "precisa liberá-la explicitamente antes de qualquer nascimento."
    ),
    FLAG_LEDGER: (
        "O registro durável da criação está fechado neste servidor. Sem ele não há "
        "recibo antes da chamada, e criar sem recibo é criar sem poder reconciliar."
    ),
    FLAG_DESTINO_SHOP: (
        "Ninguém provou que o clique desta conta não pode ser redirecionado para uma "
        "Shop. Desde a v26 esse desvio é o padrão de contas elegíveis, e o primeiro "
        "canário só aceita destino website. Um administrador precisa conferir a "
        "elegibilidade da conta antes de qualquer nascimento."
    ),
}


def autorizacoes_ausentes(account_ref: str | None = None) -> list[str]:
    """As flags fechadas, em ordem estável.

    `FLAG_DESTINO_SHOP` é julgada por conta; sem `account_ref` ela conta como
    ausente, que é o lado seguro para o painel de capacidades.
    """
    faltando: list[str] = []
    for nome in FLAGS_DE_CRIACAO:
        if nome == FLAG_DESTINO_SHOP:
            if not destino_website_liberado(account_ref):
                faltando.append(nome)
        elif os.environ.get(nome) != "1":
            faltando.append(nome)
    return faltando


def motivos_ausentes(account_ref: str | None = None) -> list[str]:
    """As causas dos bloqueios, prontas para a tela."""
    return [MOTIVO_DA_FLAG[nome] for nome in autorizacoes_ausentes(account_ref)]


def criacao_liberada(account_ref: str | None = None) -> bool:
    return not autorizacoes_ausentes(account_ref)


def ledger_liberado() -> bool:
    """Autoriza recibos/aprovação/reconciliação, mas nunca o despacho Meta."""
    return os.environ.get(FLAG_LEDGER) == "1"


def contas_com_destino_liberado() -> frozenset[str]:
    """As contas cuja elegibilidade a Shop já foi conferida, e deu não-elegível."""
    bruto = str(os.environ.get(FLAG_DESTINO_SHOP) or "").strip()
    if not bruto:
        return frozenset()
    return frozenset(
        parte.strip() for parte in bruto.split(",") if parte.strip())


def destino_website_liberado(account_ref: str | None = None) -> bool:
    """Se ESTA conta teve a elegibilidade a Shop conferida.

    ⚠️ `account_ref=None` devolve False mesmo com a variável preenchida. Quem
    não sabe de qual conta está falando não pode receber a prova de nenhuma —
    e um default permissivo aqui reabriria exatamente o buraco que a lista por
    conta veio fechar.
    """
    if not account_ref:
        return False
    return account_ref in contas_com_destino_liberado()


def motivos_do_ledger_ausente() -> list[str]:
    return [] if ledger_liberado() else [MOTIVO_DA_FLAG[FLAG_LEDGER]]


def motivo_da_criacao_fechada(account_ref: str | None = None) -> str:
    """Uma frase só, para o painel de bloqueios das capacidades."""
    faltando = motivos_ausentes(account_ref)
    if not faltando:
        return (
            "A criação PAUSED está liberada neste servidor. Ela ainda exige aprovação "
            "humana vinculada ao plano validado e nasce sempre em estado pausado."
        )
    return " ".join(faltando)
