"""Releitura do ledger pela identidade canonica COMPLETA da fotografia PMax.

Camada de dominio: recebe linhas cruas do ledger e decide quais delas compoem a
fotografia de UMA campanha, num bucket, numa origem, numa versao de API. Nao
abre socket, nao fala com o Supabase e nao tem relogio proprio — quem busca as
linhas e ``persistencia.SupabaseGoogleIntelligence.coletas_por_identidade``.

## Por que este modulo existe

``avaliar_prontidao_pmax`` sempre soube exigir as sete familias observadas,
gravadas e recentes. O que faltava era a FONTE dessas sete: ate aqui o unico
chamador era a propria execucao, que se autoatesta —
``linhagem="execucao_local"``, ``autoatestada: true``. Um veredito autoatestado
descreve o que o processo ACHA que gravou. Este modulo produz o outro:
``linhagem="releitura_do_ledger"``, montado sobre linhas que o banco devolveu.

## A fronteira, e por que ela nao pode ser frouxa

O modo errado de fazer isto ja existe no repositorio e vale como aviso:
``backend/app/trafego/diagnostico_persistido`` le a coleta MAIS RECENTE de um
``tipo_sinal`` por ``volc_campaign_id`` — sem conta, sem MCC, sem bucket, sem
origem, sem versao de API. Numa carteira com a mesma campanha em duas contas, ou
com duas fotografias no mesmo dia, "a mais recente" responde por uma pergunta
que ninguem fez.

Aqui uma linha so entra na fotografia se casar em TODOS os componentes:

===========================  ==========================================
componente                   onde ele vive no ledger
===========================  ==========================================
``customer_id``              coluna
``login_customer_id``        coluna
``volc_campaign_id``         coluna
``campaign_id``              coluna
``api_versao``               coluna
``canal``                    ``payload.canal``
``familia``                  ``payload.familia``
``bucket``                   ``payload.bucket``
``origem``                   ``payload.origem``
``tipo_sinal``               coluna, conferida CONTRA a familia
===========================  ==========================================

⚠️ ``tipo_sinal`` conferido contra a familia nao e redundancia. Sem ele, uma
linha de ``DIAGNOSTICO_ENTREGA`` com ``payload.familia`` preenchido passaria a
responder por uma familia PMax — e e exatamente essa a confusao que a v12_03
existe para nao precisar cometer. E e ele que mantem a setima familia honesta:
``PMAX_RECOMENDACOES_FORCA`` grava sob ``RECOMENDACOES_ARMAZENADAS``, entao a
dupla (tipo_sinal, familia) e o unico par que a identifica.

## Ausencia, falha e ambiguidade

Nenhuma das tres vira fotografia verde:

* linha que nao casa e DESCARTADA com motivo, e o motivo viaja em
  ``descartadas`` — quem le a fotografia consegue ver que havia linhas e por que
  elas nao valeram, em vez de receber um vazio mudo;
* familia sem linha simplesmente NAO ENTRA, e ``avaliar_prontidao_pmax`` a
  reporta como ausente;
* duas linhas materiais para a MESMA familia e a mesma identidade sao
  ambiguidade, e ambiguidade levanta ``ErroReleituraAmbigua``. Escolher "a mais
  recente" entre elas seria reintroduzir, dentro da fronteira, o defeito que a
  fronteira existe para impedir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .alvo import ORIGEM_ALVO
from .modelo import API_VERSAO
from .pmax import (
    CANAL_PMAX, FAMILIAS_PMAX, FRESCOR_MAXIMO_SEGUNDOS, LINHAGEM_RELEITURA,
    TIPO_SINAL_POR_FAMILIA, ProntidaoPMax, avaliar_prontidao_pmax,
)

#: Os `tipo_sinal` que uma fotografia PMax pode ocupar no ledger. Seis proprios
#: (v12_03) mais `RECOMENDACOES_ARMAZENADAS`, que a setima familia divide com a
#: varredura de conta.
TIPOS_SINAL_DA_FOTOGRAFIA = frozenset(TIPO_SINAL_POR_FAMILIA.values())

#: As colunas que a releitura precisa. `payload` vem junto porque canal, familia,
#: bucket e origem moram nele — o ledger v12_01 nao tem coluna para nenhum dos
#: quatro, e esta lane amplia vocabulario, nao schema.
CAMPOS_DA_RELEITURA = (
    "coleta_id,chave_idempotencia,tipo_sinal,estado,customer_id,"
    "login_customer_id,volc_campaign_id,campaign_id,janela_inicio,janela_fim,"
    "competencia,coletada_em,api_versao,coletor_versao,quantidade,payload,"
    "payload_sha256,erro_codigo,erro_classe"
)


class ErroReleitura(RuntimeError):
    """A releitura nao pode ser feita, e nao vai fingir um vazio."""


class ErroReleituraAmbigua(ErroReleitura):
    """Duas linhas materiais disputam a mesma familia na mesma identidade."""


@dataclass(frozen=True)
class IdentidadeDaFotografia:
    """A fronteira inteira, junta. Faltar um componente e nao ter fronteira."""

    customer_id: str
    login_customer_id: str
    volc_campaign_id: str
    campaign_id: str
    bucket: str
    canal: str = CANAL_PMAX
    origem: str = ORIGEM_ALVO
    api_versao: str = API_VERSAO

    def __post_init__(self) -> None:
        for campo in (
            "customer_id", "login_customer_id", "volc_campaign_id",
            "campaign_id", "bucket", "canal", "origem", "api_versao",
        ):
            if not str(getattr(self, campo) or "").strip():
                raise ErroReleitura(
                    f"identidade da fotografia sem {campo}: uma fronteira "
                    f"incompleta deixaria passar recibo de outra leitura"
                )

    def json(self) -> dict[str, str]:
        return {
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "volc_campaign_id": self.volc_campaign_id,
            "campaign_id": self.campaign_id,
            "bucket": self.bucket,
            "canal": self.canal,
            "origem": self.origem,
            "api_versao": self.api_versao,
        }


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def divergencia(linha: Mapping[str, Any], identidade: IdentidadeDaFotografia) -> str | None:
    """O PRIMEIRO componente em que a linha discorda da identidade, ou ``None``.

    Devolve o nome do componente, e nao um booleano, porque "esta linha nao
    serve" sem dizer por que e o mesmo silencio que produz um vazio inventado
    tres camadas acima.
    """

    payload = linha.get("payload")
    if not isinstance(payload, Mapping):
        return "payload"

    esperado = (
        ("customer_id", _texto(linha.get("customer_id")), identidade.customer_id),
        ("login_customer_id", _texto(linha.get("login_customer_id")),
         identidade.login_customer_id),
        ("volc_campaign_id", _texto(linha.get("volc_campaign_id")),
         identidade.volc_campaign_id),
        ("campaign_id", _texto(linha.get("campaign_id")), identidade.campaign_id),
        ("api_versao", _texto(linha.get("api_versao")), identidade.api_versao),
        ("canal", _texto(payload.get("canal")), identidade.canal),
        ("bucket", _texto(payload.get("bucket")), identidade.bucket),
        ("origem", _texto(payload.get("origem")), identidade.origem),
    )
    for nome, achado, alvo in esperado:
        if achado != alvo:
            return nome
    return None


def familia_da_linha(linha: Mapping[str, Any]) -> str | None:
    """A familia que a linha declara — se ela e uma familia PMax reconhecida E
    o ``tipo_sinal`` gravado e o que aquela familia pede.

    O segundo teste e o que impede um recibo de outra pergunta, com o payload
    preenchido a mao, de se apresentar como leitura PMax.
    """

    payload = linha.get("payload")
    if not isinstance(payload, Mapping):
        return None
    familia = _texto(payload.get("familia"))
    if familia not in FAMILIAS_PMAX:
        return None
    if _texto(linha.get("tipo_sinal")) != TIPO_SINAL_POR_FAMILIA[familia]:
        return None
    return familia


def _coleta_id(linha: Mapping[str, Any]) -> str:
    return _texto(linha.get("coleta_id"))


def fotografia_relida(
    linhas: Sequence[Mapping[str, Any]], identidade: IdentidadeDaFotografia,
) -> dict[str, Any]:
    """As linhas do ledger viram a fotografia que ``avaliar_prontidao_pmax`` le.

    Sai no MESMO formato do resultado de uma execucao — ``coletas`` com
    ``familia``, ``estado``, ``persistido`` e ``coletada_em`` — para que o
    veredito seja calculado pela mesma funcao. O que muda e a linhagem, e ela
    viaja junto.
    """

    aceitas: dict[str, dict[str, Any]] = {}
    descartadas: list[dict[str, Any]] = []

    for linha in linhas:
        if not isinstance(linha, Mapping):
            descartadas.append({"motivo": "linha nao e objeto", "coleta_id": None})
            continue

        familia = familia_da_linha(linha)
        if familia is None:
            descartadas.append({
                "coleta_id": _coleta_id(linha) or None,
                "tipo_sinal": _texto(linha.get("tipo_sinal")) or None,
                "motivo": "familia ausente, desconhecida ou incoerente com o tipo_sinal",
            })
            continue

        fora = divergencia(linha, identidade)
        if fora is not None:
            descartadas.append({
                "coleta_id": _coleta_id(linha) or None,
                "familia": familia,
                "motivo": f"fora da identidade: {fora} nao confere",
            })
            continue

        # ⚠️ SEM `coleta_id` a linha nao prova persistencia nenhuma. Ela pode ter
        # vindo de um dublê, de um cache ou de uma projecao em memoria; o que
        # torna um recibo um recibo e existir no banco com identificador.
        if not _coleta_id(linha):
            descartadas.append({
                "coleta_id": None, "familia": familia,
                "motivo": "linha sem coleta_id nao prova gravacao no ledger",
            })
            continue

        anterior = aceitas.get(familia)
        if anterior is not None:
            if _coleta_id(anterior["_linha"]) == _coleta_id(linha):
                continue  # a mesma linha repetida na resposta nao e ambiguidade
            raise ErroReleituraAmbigua(
                f"{familia}: duas coletas distintas para a mesma identidade e "
                f"o mesmo bucket ({_coleta_id(anterior['_linha'])} e "
                f"{_coleta_id(linha)}); escolher a mais recente entre elas "
                f"apagaria a fronteira que esta releitura existe para respeitar"
            )

        aceitas[familia] = {
            "familia": familia,
            "tipo_sinal": _texto(linha.get("tipo_sinal")),
            "estado": _texto(linha.get("estado")),
            # `persistido` NAO vem de ninguem afirmando que gravou: ele vem de a
            # linha ter `coleta_id`, que so o banco emite.
            "persistido": True,
            "coleta_id": _coleta_id(linha),
            "coletada_em": linha.get("coletada_em"),
            "quantidade": linha.get("quantidade"),
            "erro_codigo": linha.get("erro_codigo"),
            "erro_classe": linha.get("erro_classe"),
            "janela_inicio": linha.get("janela_inicio"),
            "janela_fim": linha.get("janela_fim"),
            "chave_idempotencia": _texto(linha.get("chave_idempotencia")) or None,
            "_linha": linha,
        }

    coletas = [
        {k: v for k, v in aceitas[familia].items() if k != "_linha"}
        for familia in FAMILIAS_PMAX
        if familia in aceitas
    ]
    return {
        "linhagem": LINHAGEM_RELEITURA,
        "identidade": identidade.json(),
        "canal": identidade.canal,
        "bucket": identidade.bucket,
        "origem": identidade.origem,
        "customer_id": identidade.customer_id,
        "campaign_id": identidade.campaign_id,
        "volc_campaign_id": identidade.volc_campaign_id,
        "coletas": coletas,
        "total": len(coletas),
        "linhas_lidas": len(linhas),
        "descartadas": descartadas,
    }


def avaliar_prontidao_relida(
    linhas: Sequence[Mapping[str, Any]], identidade: IdentidadeDaFotografia, *,
    agora: datetime, frescor_maximo_segundos: int = FRESCOR_MAXIMO_SEGUNDOS,
) -> ProntidaoPMax:
    """O veredito de observabilidade calculado sobre recibos RELIDOS.

    Mesma funcao de sempre, mesma exigencia de sempre — as sete familias
    observadas, gravadas e recentes. O que este caminho acrescenta e que
    ``persistido`` deixou de ser uma afirmacao do processo e passou a ser um
    ``coleta_id`` devolvido pelo banco.
    """

    return avaliar_prontidao_pmax(
        fotografia_relida(linhas, identidade), agora=agora,
        frescor_maximo_segundos=frescor_maximo_segundos,
        linhagem=LINHAGEM_RELEITURA,
    )


def fotografia_do_ledger(
    persistencia: Any, identidade: IdentidadeDaFotografia,
) -> dict[str, Any]:
    """Busca as linhas e monta a fotografia. ``persistencia`` e uma porta.

    Recebida por parametro, e nao importada: ``persistencia.py`` importa ESTE
    modulo, e inverter a seta criaria um ciclo. Mais importante, e o que permite
    provar a releitura inteira sem Supabase e sem rede.
    """

    return fotografia_relida(persistencia.coletas_por_identidade(identidade), identidade)


def prontidao_do_ledger(
    persistencia: Any, identidade: IdentidadeDaFotografia, *,
    agora: datetime, frescor_maximo_segundos: int = FRESCOR_MAXIMO_SEGUNDOS,
) -> ProntidaoPMax:
    """O caminho inteiro: ledger -> fotografia -> veredito com linhagem.

    ⚠️ Este caminho NAO toca no Google Ads. Ele nao constroi cliente, nao le
    credencial e nao emite GAQL — e por isso que nenhuma superficie de mutacao e
    alcancavel a partir dele, nem por acidente. A observabilidade de uma campanha
    PMax e decidida sobre o que o BANCO devolveu, nunca sobre uma leitura nova
    feita na hora de decidir.
    """

    return avaliar_prontidao_relida(
        persistencia.coletas_por_identidade(identidade), identidade,
        agora=agora, frescor_maximo_segundos=frescor_maximo_segundos,
    )
