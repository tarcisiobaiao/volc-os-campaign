"""O portão do destino pago — junta as varreduras e decide, fechando por ausência.

## As três regras, e por que nesta ordem

1. **Bloqueio reprova.** Achado com severidade de bloqueio no papel avaliado
   derruba o destino. Nada de "aprovado com ressalvas" para o que a política
   descreve como motivo de suspensão sem aviso prévio.

2. **Desconhecido reprova.** Verificação EXIGIDA naquele ponto de portão que não
   pôde ser concluída (`unavailable`/`failed`) vira `desconhecido`. Ela não vira
   "sem achados" — que é como o software costuma mentir. É por isso que
   `Verificacao` carrega status além de achados.

3. **Papel decide o peso, não o resultado.** O mesmo achado existe em toda
   página; o que muda é se ele reprova. Um artigo orgânico sem CNPJ é um defeito
   editorial; um destino pago sem identidade de operador é o que a política de
   `unacceptable business practices` descreve.

## `paid_destination_ready` é uma afirmação estreita

Ele significa: *nesta avaliação, neste ponto de portão, contra esta versão da
política, nenhum bloqueio e nenhum desconhecido restaram*. Não significa que o
Google vai aprovar, nem que a conta está limpa, nem que a página está correta —
o portão lê HTML, não a intenção do revisor. Um portão que prometesse mais que
isso seria a mesma alegação forte sem evidência que ele existe para impedir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.landing_policy.contrato import (
    EXIGENCIAS_POR_PONTO,
    NAO_APLICAVEL_E_DESCONHECIDO_EM,
    STATUS_FALHOU,
    STATUS_NAO_APLICAVEL,
    SEVERIDADE_BLOQUEIO,
    SEVERIDADE_OBSERVACAO,
    SEVERIDADE_RISCO,
    Achado,
    PapelDestino,
    PontoDePortao,
    Veredito,
    PAPEIS_ESTRITOS,
    Verificacao,
    carregar_fontes,
    fonte_do_codigo,
    severidade,
)
from app.landing_policy.varredura import (
    VARREDURAS,
    PaginaObservada,
)


@dataclass
class Avaliacao:
    """O desfecho completo de uma passagem pelo portão."""

    url: str
    papel: PapelDestino
    ponto: PontoDePortao
    veredito: Veredito
    verificacoes: list[Verificacao] = field(default_factory=list)
    bloqueios: list[Achado] = field(default_factory=list)
    riscos: list[Achado] = field(default_factory=list)
    observacoes: list[Achado] = field(default_factory=list)
    #: Verificações exigidas que não puderam ser concluídas. Cada uma sozinha
    #: já impede `paid_destination_ready`.
    desconhecidos: list[dict[str, str]] = field(default_factory=list)

    @property
    def paid_destination_ready(self) -> bool:
        """Só o papel `paid_destination` pode responder a esta pergunta.

        Avaliar um artigo orgânico e devolver `True` seria dizer que ele está
        pronto para receber clique comprado sem nunca ter sido medido como tal.
        Quem quer a resposta para um destino pago avalia com o papel de destino
        pago — é para isso que o ponto de portão de campanha força o papel.
        """
        # ⚠️ `conversion_page` TAMBÉM RESPONDE, e antes ela não podia.
        #
        # A regra pedia `papel is PAID_DESTINATION`, então uma página que
        # COLETA dado do visitante — o papel que a doutrina chama de mais duro —
        # jamais ficava verde. O efeito prático era o oposto do pretendido: para
        # publicar, a operação precisaria BAIXAR o papel para `paid_destination`,
        # trocando o regime estrito pelo menos estrito. Uma régua que ninguém
        # consegue atingir é uma régua que se contorna.
        #
        # Papel frouxo continua sem poder responder: aprovar um artigo orgânico
        # como pronto para clique comprado seria afirmar algo que ninguém mediu.
        return (
            self.papel in PAPEIS_ESTRITOS
            and not self.bloqueios
            and not self.desconhecidos
        )

    @property
    def motivos(self) -> list[str]:
        """Por que não está pronto, em uma linha por motivo."""
        if self.paid_destination_ready:
            return []
        fora: list[str] = []
        if self.papel not in PAPEIS_ESTRITOS:
            fora.append(
                f"papel avaliado foi {self.papel.value}, que não é papel estrito "
                f"(paid_destination ou conversion_page)"
            )
        fora += [f"bloqueio {a.codigo}: {a.mensagem}" for a in self.bloqueios]
        fora += [
            f"desconhecido {d['verificacao']}: {d['motivo']}" for d in self.desconhecidos
        ]
        return fora


def _chave(achado: Achado) -> tuple[str, str]:
    """Chave de deduplicação. NUNCA levanta.

    ⚠️ `json.dumps` de uma evidência não serializável levantava `TypeError`
    para fora de `avaliar()` — e sem `Avaliacao` não há recibo de recusa, no
    ponto de integração com mais chance de embrulhar tudo num `except`
    permissivo. Uma evidência esquisita é um defeito de quem a montou; ela não
    pode apagar o veredito das outras.
    """
    import json

    try:
        evidencia = json.dumps(achado.evidencia, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        evidencia = repr(achado.evidencia)[:400]
    return (achado.codigo, evidencia)


def avaliar(
    pagina: PaginaObservada,
    papel: PapelDestino,
    ponto: PontoDePortao,
    *,
    fontes: dict[str, Any] | None = None,
) -> Avaliacao:
    """Roda TODAS as varreduras e decide.

    Todas, sempre — inclusive as que não são exigidas naquele ponto. Uma
    verificação não exigida ainda produz achado útil; ela só não transforma
    "não deu para olhar" em reprova. Rodar um subconjunto esconderia defeito
    real por causa de uma escolha sobre exigibilidade.
    """
    fontes = fontes if fontes is not None else carregar_fontes()
    exigidas = EXIGENCIAS_POR_PONTO[ponto]

    verificacoes: list[Verificacao] = []
    for nome in sorted(VARREDURAS):
        try:
            verificacoes.append(VARREDURAS[nome](pagina))
        except Exception as exc:  # noqa: BLE001
            # Varredura que explode não é varredura que passou. O status `failed`
            # é o que faz o portão reprovar por ausência em vez de aprovar por
            # silêncio — e é por isso que a exceção não sobe.
            verificacoes.append(
                Verificacao(
                    nome=nome,
                    status="failed",
                    detalhe=f"{type(exc).__name__}: {str(exc)[:160]}",
                )
            )

    bloqueios: list[Achado] = []
    riscos: list[Achado] = []
    observacoes: list[Achado] = []
    vistos: set[tuple[str, str]] = set()

    for verificacao in verificacoes:
        for achado in verificacao.achados:
            chave = _chave(achado)
            if chave in vistos:
                continue
            vistos.add(chave)
            classificado = Achado(
                codigo=achado.codigo,
                mensagem=achado.mensagem,
                severidade=severidade(achado.codigo, papel),
                evidencia=achado.evidencia,
            )
            if classificado.severidade == SEVERIDADE_BLOQUEIO:
                bloqueios.append(classificado)
            elif classificado.severidade == SEVERIDADE_RISCO:
                riscos.append(classificado)
            else:
                observacoes.append(classificado)

    # ── DESCONHECIDOS: três caminhos, e cada um é um defeito diferente ──────
    #
    # 1. verificação EXIGIDA que não concluiu — o fecha-por-ausência original;
    # 2. verificação que saiu `not_applicable` num ponto em que "não se aplica"
    #    é impossível de boa-fé (uma página no ar sempre tem hash observável);
    # 3. varredura que EXPLODIU — em qualquer ponto, exigida ou não.
    #
    # O caso 3 é o que mais custava. `failed` só virava desconhecido quando o
    # nome estava em `exigidas`, então no portão de pré-publicação as quatro
    # verificações não exigidas podiam explodir inteiras e a publicação seguia
    # autorizada. "Não é exigível aqui" e "quebrou" são coisas diferentes:
    # a primeira é uma decisão do contrato, a segunda é um defeito do software —
    # e software quebrado nunca é evidência de página limpa.
    nao_aplicavel_reprova = NAO_APLICAVEL_E_DESCONHECIDO_EM.get(ponto, frozenset())
    desconhecidos: list[dict[str, str]] = []
    for v in verificacoes:
        if v.status == STATUS_FALHOU:
            motivo = v.detalhe or "a varredura levantou exceção"
        elif v.nome in exigidas and not v.conclusiva:
            motivo = v.detalhe or f"verificação exigida terminou como {v.status}"
        elif v.nome in nao_aplicavel_reprova and v.status == STATUS_NAO_APLICAVEL:
            motivo = (
                v.detalhe
                or "saiu 'não se aplica' num ponto em que a página já está no ar; "
                "uma página no ar sempre tem o que observar"
            )
        else:
            continue
        desconhecidos.append({"verificacao": v.nome, "status": v.status, "motivo": motivo})

    if bloqueios:
        veredito = Veredito.BLOQUEADO
    elif desconhecidos:
        veredito = Veredito.INDETERMINADO
    elif riscos:
        veredito = Veredito.APROVADO_COM_RESSALVAS
    else:
        veredito = Veredito.APROVADO

    ordenar = lambda lista: sorted(lista, key=lambda a: (a.codigo, str(a.evidencia)))  # noqa: E731
    return Avaliacao(
        url=pagina.url,
        papel=papel,
        ponto=ponto,
        veredito=veredito,
        verificacoes=verificacoes,
        bloqueios=ordenar(bloqueios),
        riscos=ordenar(riscos),
        observacoes=ordenar(observacoes),
        desconhecidos=sorted(desconhecidos, key=lambda d: d["verificacao"]),
    )


def sem_fonte_oficial(avaliacao: Avaliacao, fontes: dict[str, Any] | None = None) -> list[str]:
    """Códigos emitidos que não têm fonte oficial registrada.

    Existe para o gate: regra sem documento oficial do Google que a sustente é
    opinião, e opinião não reprova destino. Se isto voltar não vazio, o defeito
    é da matriz, não da página.
    """
    fontes = fontes if fontes is not None else carregar_fontes()
    emitidos = {
        a.codigo
        for a in (avaliacao.bloqueios + avaliacao.riscos + avaliacao.observacoes)
    }
    return sorted(c for c in emitidos if not fonte_do_codigo(c, fontes))


# ── autoridade do papel ────────────────────────────────────────────────────
#
# Ordem de RIGOR, do mais duro ao mais frouxo. É a espinha da função abaixo:
# um pedido do cliente pode subir nesta lista, nunca descer.
_RIGOR = (
    PapelDestino.CONVERSION_PAGE,
    PapelDestino.PAID_DESTINATION,
    PapelDestino.PRESELL,
    PapelDestino.EDITORIAL_SOLUTION,
    PapelDestino.ORGANIC_ARTICLE,
)

#: Como o papel EDITORIAL do motor (`funnelforge.domain.models.PageRole`) mapeia
#: para o papel de POLÍTICA. Não é sinônimo: o do motor descreve a posição no
#: funil, o daqui descreve a exposição a clique comprado. A LP é o destino que o
#: anúncio aponta; as interiores não recebem clique comprado direto.
_DO_MOTOR = {
    "LP": PapelDestino.PAID_DESTINATION,
    "PRESELL": PapelDestino.PRESELL,
    "SOLUTION": PapelDestino.EDITORIAL_SOLUTION,
}


class PapelRelaxadoPeloCliente(ValueError):
    """O cliente pediu um papel mais frouxo que o que o servidor apurou.

    É levantada em vez de ignorada em silêncio porque um pedido desses não é
    ruído: é alguém — pessoa ou script — tentando baixar o rigor do portão pela
    borda da API. Silenciar transformaria a tentativa em fato não registrado.
    """


def papel_do_servidor(
    *,
    e_destino_de_campanha: bool = False,
    coleta_dado_do_visitante: bool = False,
    papel_do_motor: str = "",
    papel_pedido_pelo_cliente: str = "",
) -> PapelDestino:
    """O papel que VALE, apurado de fatos do servidor.

    ## Por que esta função existe

    O `HANDOFF-PATCH-PUBLICACAO.md` derivava o papel de
    `plan.pages[].role == "LP"` — um campo que viaja no payload. Quem chama a
    API direto escolhe o que quiser ali, e o portão inteiro passa a ser
    desligável por configuração do chamador. É a mesma classe de defeito que
    `elegibilidade_de_destino_de_campanha` já evitava forçando o papel, agora
    escrita uma vez para os três pontos de portão.

    ## A ordem de decisão, e o motivo de cada degrau

    1. **Coleta dado do visitante** → `conversion_page`, o regime mais duro.
       Isto é apurado do ARTEFATO (existe campo de formulário?), não declarado.
    2. **É destino de campanha** → `paid_destination`, forçado. Uma campanha
       apontando para uma URL faz dela um destino pago, qualquer que seja o
       papel cadastrado.
    3. **Papel do motor**, traduzido — a LP é quem recebe o clique comprado.
    4. **Nada disso** → `organic_article`, o mais frouxo, porque afirmar mais
       sem fato que sustente seria inventar rigor onde não há evidência.

    ## O pedido do cliente só sobe

    Ele é aceito quando pede MAIS rigor (um operador que sabe que aquela página
    vai virar destino pago amanhã deve poder pedir a régua dura hoje) e
    recusado quando pede menos.
    """
    if coleta_dado_do_visitante:
        apurado = PapelDestino.CONVERSION_PAGE
    elif e_destino_de_campanha:
        apurado = PapelDestino.PAID_DESTINATION
    else:
        bruto = str(papel_do_motor or "").strip().upper()
        if not bruto:
            # Nenhuma informação de papel: a página não vem do motor de funil.
            # `organic_article` é a leitura correta — e é uma afirmação fraca,
            # que não promete nada sobre clique comprado.
            apurado = PapelDestino.ORGANIC_ARTICLE
        else:
            # ⚠️ INFORMAÇÃO DADA E NÃO RECONHECIDA FECHA, NÃO ABRE.
            #
            # `_DO_MOTOR.get(bruto, ORGANIC_ARTICLE)` mandava qualquer valor
            # irreconhecível para o papel MAIS FROUXO — então um erro de
            # digitação em `role` ("LPP", "Lp ", "landing") desligava a régua
            # inteira, em silêncio. É a mesma doutrina de
            # `contrato.severidade()`, que trata código não classificado como
            # bloqueio no papel estrito: o que ninguém classificou não entra em
            # produção valendo a classificação mais permissiva.
            apurado = _DO_MOTOR.get(bruto, PapelDestino.PAID_DESTINATION)

    pedido_bruto = str(papel_pedido_pelo_cliente or "").strip().lower()
    if not pedido_bruto:
        return apurado
    try:
        pedido = PapelDestino(pedido_bruto)
    except ValueError:
        # Papel desconhecido não vira default frouxo: fica o que o servidor
        # apurou. Aceitar um valor que ninguém definiu seria deixar um erro de
        # digitação decidir o rigor.
        return apurado
    if _RIGOR.index(pedido) < _RIGOR.index(apurado):
        return pedido
    if pedido is apurado:
        return apurado
    raise PapelRelaxadoPeloCliente(
        f"O cliente pediu o papel {pedido.value!r}, mais frouxo que o papel "
        f"{apurado.value!r} que o servidor apurou. O servidor é a autoridade: "
        f"nada foi avaliado com a régua pedida."
    )


def elegibilidade_de_destino_de_campanha(
    pagina: PaginaObservada, *, fontes: dict[str, Any] | None = None
) -> Avaliacao:
    """O ponto de portão 3, com o papel FORÇADO.

    Uma campanha apontando para uma URL faz dela um destino pago, qualquer que
    seja o papel que alguém tenha declarado no cadastro. Deixar o chamador
    escolher o papel aqui seria deixar o portão ser desligado por configuração.
    """
    return avaliar(
        pagina,
        PapelDestino.PAID_DESTINATION,
        PontoDePortao.ELEGIBILIDADE_DESTINO_CAMPANHA,
        fontes=fontes,
    )
