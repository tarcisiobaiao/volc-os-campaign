"""Prontidao de operacao: as nove respostas, dadas sem executar nada.

Nove respostas, e a nona nao e uma pergunta: sao oito entradas em `perguntas`
mais `bloqueios` — o que impede a publicacao, em portugues.


## O que esta rota responde, e por que ela nao e o handoff

`handoff` responde ao PROXIMO COMPONENTE: "quem recebe a peca, o que produz,
qual referencia sera resolvida". `prontidao` responde a QUEM OPERA: "esta
pagina esta pronta para receber uma peca aprovada, e se nao esta, o que falta".

Sao publicos diferentes e vocabularios diferentes. Juntar os dois faria a rota
do broker carregar frase de tela, e a tela ter de reimplementar a regra.

## O vocabulario de tres valores, e por que dois nao bastam

Cada pergunta e respondida com `sim`, `nao` ou `desconhecido` — nunca com um
booleano. `desconhecido` NAO e `nao`:

* "nao ha perfil de navegador relacionado" e um FATO do inventario;
* "nao sei se o perfil esta aberto" e a ausencia de uma observacao.

Achatar os dois num booleano e como o painel aprende a dizer "perfil
indisponivel" sobre um perfil que ninguem olhou — e a decisao seguinte
(cadastrar um perfil, ou ir ate a maquina) e completamente diferente.

## A procedencia de cada resposta

`registro` — saiu das tabelas do Cofre. E o unico valor que esta API produz.
`sonda`   — saiu de uma observacao ao vivo, feita pelo broker no host isolado.

Esta rota NAO sonda. Ela nao alcanca a Local API do AdsPower (que so escuta em
loopback, na outra maquina) e nao resolve `op://`. Quando a pergunta so pode ser
respondida ao vivo, ela responde `desconhecido` e diz por quem a resposta viria.
Uma API que fingisse sondar produziria a pior resposta possivel: um `sim`
plausivel sobre um perfil que nao existe mais.
"""
from __future__ import annotations

from typing import Any, Mapping

#: Os componentes que vem DEPOIS do Cofre, com o estado real de cada um.
#:
#: Fonte unica: `aplicacao.CasosDeUso.handoff` importa daqui. Duas copias
#: divergiriam, e a divergencia apareceria como uma rota dizendo que o broker
#: existe enquanto a outra diz que nao.
COMPONENTES_SEGUINTES: dict[str, dict[str, str]] = {
    "producao_criativa": {"tarefa": "P17", "estado": "fora desta missao"},
    # Estado factual da CAPACIDADE, nao promocao editorial do Roadmap.
    # P03-T11 permanece partial: tools/adspower-broker foi provado
    # localmente; nenhuma leitura real do AdsPower aconteceu.
    "broker_de_acesso": {
        "tarefa": "P03-T11",
        "implementacao": "local_verified",
        "operacao_real": "live_read_not_proven",
    },
    "porta_de_publicacao": {"tarefa": "P12-T09", "estado": "todo"},
    "qa_visual": {"tarefa": "P12-T11", "estado": "todo"},
}

SIM, NAO, DESCONHECIDO = "sim", "nao", "desconhecido"


def _resposta(valor: str, motivo: str, procedencia: str = "registro") -> dict[str, str]:
    return {"valor": valor, "motivo": motivo, "procedencia": procedencia}


def _sem_duplicatas(partes: list[str]) -> list[str]:
    """Lista global deterministica: preserva a primeira ocorrencia, sem esconder nada.

    `bloqueios_publicacao` carrega tambem bloqueios de recebimento/acesso porque
    publicar depende dos dois. O resumo global nao pode concatena-los de novo,
    senao o React recebe chaves duplicadas e o operador le o mesmo impedimento
    duas vezes.
    """
    vistos: set[str] = set()
    saida: list[str] = []
    for bloqueio in partes:
        if bloqueio not in vistos:
            vistos.add(bloqueio)
            saida.append(bloqueio)
    return saida


#: Como o estado de verificacao de uma REFERENCIA vira resposta sobre "da para
#: resolver isto em runtime?". Os seis estados nao sao sinonimos, e o mapa
#: preserva a diferenca que o schema criou para preservar.
_RESOLVIVEL_POR_VERIFICACAO: dict[str, tuple[str, str]] = {
    "verified": (SIM, "a referencia foi resolvida com sucesso na ultima prova"),
    "partial": (DESCONHECIDO, "a ultima prova foi parcial: parte do acesso nao foi conferida"),
    "failed": (NAO, "a ultima tentativa de resolver a referencia falhou"),
    "expired": (NAO, "a referencia expirou e precisa ser renovada no cofre externo"),
    "blocked": (NAO, "na ultima tentativa o cofre externo estava trancado; "
                     "reautorize o 1Password e prove de novo"),
    "unverified": (DESCONHECIDO, "a referencia esta registrada, mas nunca foi resolvida"),
}


def _melhor(estados: list[str]) -> str:
    """A referencia mais adiantada manda, e a ordem nao e alfabetica.

    Um ativo com duas referencias — uma `verified` e uma `unverified` — TEM um
    acesso comprovado. Responder pelo pior deixaria de reconhecer o que ja foi
    provado; responder pela media nao significa nada.

    ⚠️ Um estado que este mapa nao conhece volta COMO VEIO, e nao vira
    `unverified`. Traduzir o desconhecido para o valor mais proximo e como um
    ramo de erro vira codigo morto: se o schema ganhar um setimo estado, quem le
    precisa ver o nome dele na resposta, e nao um sinonimo inventado aqui.
    """
    ordem = ("verified", "partial", "unverified", "blocked", "expired", "failed")
    for estado in ordem:
        if estado in estados:
            return estado
    return estados[0] if estados else "unverified"


def avaliar(detalhe: Mapping[str, Any], engines: list[Mapping[str, Any]] | None = None,
            sonda: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """As nove perguntas sobre um ativo, com bloqueios nomeados.

    `sonda` e a observacao ao vivo do broker, quando existir. Ausente, as duas
    perguntas que so o host isolado pode responder ficam em `desconhecido` — e
    o campo `procedencia` diz de onde a resposta veio.
    """
    engines = list(engines or [])
    credenciais = list(detalhe.get("credencial") or [])
    relacoes = list(detalhe.get("relacoes") or [])
    verificacoes = list(detalhe.get("verificacao") or [])
    perfis = [r for r in relacoes if str(r.get("tipo")) == "authenticates_through"]
    aposentado = bool(detalhe.get("aposentado_em"))

    bloqueios: list[str] = []
    bloqueios_recebimento: list[str] = []
    bloqueios_acesso: list[str] = []
    bloqueios_publicacao: list[str] = []

    # 1. Qual e a pagina de destino
    if detalhe.get("ativo_id"):
        destino = _resposta(SIM, f"{detalhe.get('nome')} ({detalhe.get('kind')})")
    else:
        destino = _resposta(NAO, "o ativo nao tem identidade no Cofre")
        bloqueios_recebimento.append("o ativo nao tem identidade no Cofre")

    # 2. Quem responde por ela
    dono_nome = str(detalhe.get("dono_nome") or "").strip()
    custodia = str(detalhe.get("dono_custodia") or "unassigned")
    if not dono_nome or custodia == "unassigned":
        dono = _resposta(NAO, "o ativo nao tem dono nomeado")
        bloqueios_recebimento.append("o ativo nao tem dono nomeado: ninguem responde por uma peca associada a ele")
    elif custodia == "declared":
        dono = _resposta(SIM, f"{dono_nome} — custodia declarada, nao conferida")
    else:
        dono = _resposta(SIM, f"{dono_nome} — custodia comprovada")

    # 3. O que esta relacionado a ela
    if relacoes:
        relacionados = _resposta(
            SIM, f"{len(relacoes)} relacao(oes) declarada(s), sendo {len(perfis)} de acesso")
    else:
        relacionados = _resposta(NAO, "nenhuma relacao declarada")

    # 4. Qual perfil de navegador a autentica
    if perfis:
        perfil = _resposta(SIM, str(perfis[0].get("rotulo") or perfis[0].get("destino")))
    else:
        perfil = _resposta(NAO, "nenhuma aresta authenticates_through declarada")
        bloqueios_acesso.append(
            "nenhum perfil de navegador relacionado (authenticates_through): "
            "o QA visual nao saberia qual perfil abrir")

    # 5. Onde a credencial esta — sem saber o valor
    if credenciais:
        nomes = ", ".join(
            f"{c.get('provider')}:{c.get('nome_logico')}" for c in credenciais[:4])
        onde = _resposta(SIM, f"referencia registrada em {nomes}")
    else:
        onde = _resposta(NAO, "nenhuma referencia de acesso registrada")
        bloqueios_acesso.append(
            "nenhuma referencia de acesso registrada: o broker nao teria o que resolver")

    # 6. A referencia pode ser resolvida em runtime
    if not credenciais:
        resolvivel = _resposta(NAO, "nao ha referencia para resolver")
    else:
        estado = _melhor([str(c.get("verificacao_estado") or "unverified") for c in credenciais])
        valor, motivo = _RESOLVIVEL_POR_VERIFICACAO.get(
            estado, (DESCONHECIDO, f"estado de verificacao nao reconhecido: {estado}"))
        resolvivel = _resposta(valor, motivo)
        if valor != SIM:
            bloqueios_acesso.append(f"a referencia de acesso nao esta comprovada: {motivo}")

    # 7. O perfil esta disponivel AGORA
    #
    # ⚠️ So o broker sabe. Esta API nao alcanca a Local API do AdsPower, que
    # escuta em loopback no outro host — e inventar um `sim` aqui seria a pior
    # resposta possivel.
    if sonda is not None and sonda.get("perfil_disponivel") is not None:
        vivo = bool(sonda.get("perfil_disponivel"))
        disponivel = _resposta(
            SIM if vivo else NAO,
            str(sonda.get("motivo") or ("o broker encontrou o perfil"
                                        if vivo else "o broker nao encontrou o perfil")),
            procedencia="sonda")
        if not vivo:
            bloqueios_acesso.append("o broker nao encontrou o perfil no host isolado")
    elif not perfis:
        disponivel = _resposta(NAO, "nao ha perfil relacionado para consultar")
    else:
        disponivel = _resposta(
            DESCONHECIDO,
            "disponibilidade so e observavel pelo broker (P03-T11), no host do AdsPower; "
            "esta API responde pelo registro, nunca ao vivo",
            procedencia="registro")

    # 8. Uma peca aprovada pode ser associada a este destino no Cofre.
    #
    # Receber/associar uma peca e diferente de PUBLICAR. P12-T09 ausente bloqueia
    # publicacao, mas nao torna falso que existe um destino com owner ao qual uma
    # peca aprovada futura possa ser relacionada.
    if aposentado:
        bloqueios_recebimento.append("o ativo esta aposentado")
    roteavel = _resposta(
        NAO if bloqueios_recebimento else SIM,
        bloqueios_recebimento[0] if bloqueios_recebimento
        else "ativo, destino e owner estao identificados; a peca pode ser associada ao Cofre")

    # Portoes separados: acesso operacional e publicacao final.
    if disponivel["valor"] == DESCONHECIDO:
        bloqueios_acesso.append(
            "perfil relacionado sem leitura ao vivo: broker local foi provado, mas live-read nao")

    porta = COMPONENTES_SEGUINTES["porta_de_publicacao"]
    if porta["estado"] != "done":
        bloqueios_publicacao.append(
            f"nao existe porta de publicacao no VOLC ({porta['tarefa']}): "
            "nenhuma peca aprovada tem por onde sair")
    bloqueios_publicacao.extend(bloqueios_recebimento)
    bloqueios_publicacao.extend(bloqueios_acesso)
    bloqueios_publicacao.append("nenhuma autorizacao de ato de publicacao foi concedida nesta rota")

    bloqueios = _sem_duplicatas(bloqueios_recebimento + bloqueios_acesso + bloqueios_publicacao)
    pronto_para_receber_peca = not bloqueios_recebimento
    pronto_para_operar_acesso = not bloqueios_acesso
    pronto_para_publicar = False

    return {
        "ativo_id": detalhe.get("ativo_id"),
        "perguntas": {
            "pagina_de_destino": destino,
            "dono": dono,
            "ativos_relacionados": relacionados,
            "perfil_de_navegador": perfil,
            "onde_esta_a_credencial": onde,
            "referencia_resolvivel": resolvivel,
            "perfil_disponivel": disponivel,
            "peca_roteavel": roteavel,
        },
        "retrato": {
            "estado": detalhe.get("estado"),
            "criticidade": detalhe.get("criticidade"),
            "dono_nome": detalhe.get("dono_nome"),
            "dono_custodia": detalhe.get("dono_custodia"),
            "finalidade": detalhe.get("proxima_acao"),
            "revisao_atual": detalhe.get("revisao_atual"),
            "atualizado_em": detalhe.get("atualizado_em"),
            "ultima_revisao_em": (verificacoes[0].get("observado_em")
                                  if verificacoes else None),
            "ultima_revisao_resultado": (verificacoes[0].get("resultado")
                                         if verificacoes else None),
            "aposentado_em": detalhe.get("aposentado_em"),
        },
        # A producao criativa que PODE alimentar este destino, pelo que os
        # manifestos declaram. Capacidade declarada, nunca fila disponivel.
        "producao_possivel": [
            {"ativo_id": e.get("ativo_id"), "nome": e.get("nome"),
             "modalidade": e.get("modalidade"),
             "estado_operacional": e.get("estado_operacional")}
            for e in engines
        ],
        "componentes_seguintes": COMPONENTES_SEGUINTES,
        "pronto_para_receber_peca": pronto_para_receber_peca,
        "pronto_para_operar_acesso": pronto_para_operar_acesso,
        "pronto_para_publicar": pronto_para_publicar,
        "bloqueios": bloqueios,
        "bloqueios_por_portao": {
            "recebimento": bloqueios_recebimento,
            "acesso": bloqueios_acesso,
            "publicacao": bloqueios_publicacao,
        },
        # A publicacao continua sendo um ato separado e explicito. Esta rota
        # RESPONDE; ela nao cria job, nao abre navegador e nao publica.
        "publica": False,
    }
