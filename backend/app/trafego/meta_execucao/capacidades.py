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
FLAG_DESTINO_SHOP = "META_SHOP_REDIRECT_CLEARED"

#: Ordem estável: a lista de bloqueios que a tela mostra não pode dançar entre
#: dois carregamentos da mesma página.
FLAGS_DE_CRIACAO: tuple[str, ...] = (FLAG_CRIACAO, FLAG_LEDGER, FLAG_DESTINO_SHOP)

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


def autorizacoes_ausentes() -> list[str]:
    """As flags fechadas, em ordem estável."""
    return [nome for nome in FLAGS_DE_CRIACAO if os.environ.get(nome) != "1"]


def motivos_ausentes() -> list[str]:
    """As causas dos bloqueios, prontas para a tela."""
    return [MOTIVO_DA_FLAG[nome] for nome in autorizacoes_ausentes()]


def criacao_liberada() -> bool:
    return not autorizacoes_ausentes()


def ledger_liberado() -> bool:
    """Autoriza recibos/aprovação/reconciliação, mas nunca o despacho Meta."""
    return os.environ.get(FLAG_LEDGER) == "1"


def destino_website_liberado() -> bool:
    """Se a leitura de elegibilidade a Shop já foi feita e deu não-elegível."""
    return os.environ.get(FLAG_DESTINO_SHOP) == "1"


def motivos_do_ledger_ausente() -> list[str]:
    return [] if ledger_liberado() else [MOTIVO_DA_FLAG[FLAG_LEDGER]]


def motivo_da_criacao_fechada() -> str:
    """Uma frase só, para o painel de bloqueios das capacidades."""
    faltando = motivos_ausentes()
    if not faltando:
        return (
            "A criação PAUSED está liberada neste servidor. Ela ainda exige aprovação "
            "humana vinculada ao plano validado e nasce sempre em estado pausado."
        )
    return " ".join(faltando)
