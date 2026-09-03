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
    SEVERIDADE_BLOQUEIO,
    SEVERIDADE_OBSERVACAO,
    SEVERIDADE_RISCO,
    Achado,
    PapelDestino,
    PontoDePortao,
    Veredito,
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
        return (
            self.papel is PapelDestino.PAID_DESTINATION
            and not self.bloqueios
            and not self.desconhecidos
        )

    @property
    def motivos(self) -> list[str]:
        """Por que não está pronto, em uma linha por motivo."""
        if self.paid_destination_ready:
            return []
        fora: list[str] = []
        if self.papel is not PapelDestino.PAID_DESTINATION:
            fora.append(
                f"papel avaliado foi {self.papel.value}, não paid_destination"
            )
        fora += [f"bloqueio {a.codigo}: {a.mensagem}" for a in self.bloqueios]
        fora += [
            f"desconhecido {d['verificacao']}: {d['motivo']}" for d in self.desconhecidos
        ]
        return fora


def _chave(achado: Achado) -> tuple[str, str]:
    import json

    return (achado.codigo, json.dumps(achado.evidencia, sort_keys=True, ensure_ascii=False))


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

    desconhecidos = [
        {
            "verificacao": v.nome,
            "status": v.status,
            "motivo": v.detalhe or f"verificação exigida terminou como {v.status}",
        }
        for v in verificacoes
        if v.nome in exigidas and not v.conclusiva
    ]

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
