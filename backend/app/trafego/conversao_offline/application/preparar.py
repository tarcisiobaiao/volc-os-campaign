"""Preparar o lote: de cliques e receita datada a envelopes validados, sem rede.

Nada aqui fala com o Google. O resultado é a lista de decisões (elegível ou
pulado, com motivo e proveniência), gravada no registro ANTES de qualquer
envio, e os envelopes de `data_manager` já validados item a item.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.trafego import data_manager as dm
from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm

from ..domain import evento as ev
from ..domain import valor as vl
from . import portas
from .destino import TIPO_IMPORTACAO_DE_CLIQUES, AcaoOfflineInvalida


class ValorFixoRecusado(dm.FronteiraRecusou):
    """O perfil declara valor fixo. É o defeito que esta entrega remove."""


class RegraDeValorIncompativel(dm.FronteiraRecusou):
    """O perfil não declara valor por evento: não há o que medir por conversão."""


class MoedaDeOutraConta(dm.FronteiraRecusou):
    """A moeda lida não é da conta dona da ação."""


PULO_CLIQUE_REPETIDO = "clique_repetido"
PULO_COORTE_JA_RATEADA = "coorte_ja_rateada"
PULO_ENVIO_INCERTO = "envio_incerto"


@dataclass(frozen=True)
class LotePreparado:
    envelope: dm.Envelope
    recibo_local: dm.ReciboDeValidacao
    #: (transaction_id, valor_impressao) na ordem do envelope.
    itens: Tuple[Tuple[str, str], ...]
    #: A ação de destino é primária (move o lance)? Entra na aprovação.
    destino_primario: bool = False


@dataclass(frozen=True)
class Preparo:
    rodada: str
    customer_id: str
    operating_account_id: str
    product_destination_id: str
    decisoes: Tuple[ev.Decisao, ...]
    lotes: Tuple[LotePreparado, ...]

    def resumo(self) -> Dict[str, Any]:
        pulos = Counter(d.motivo for d in self.decisoes if d.estado == ev.PULADO)
        elegiveis = [d for d in self.decisoes if d.estado == ev.ELEGIVEL]
        return {
            "rodada": self.rodada,
            "customer_id": self.customer_id,
            "destino": {"operating_account_id": self.operating_account_id,
                        "product_destination_id": self.product_destination_id},
            "cliques": len(self.decisoes),
            "elegiveis": len(elegiveis),
            "estimados": sum(1 for d in elegiveis if d.valor and d.valor.estimado),
            "pulados": dict(sorted(pulos.items())),
            "lotes": [{"impressao": l.envelope.impressao(), "itens": len(l.itens),
                       "aceitos_localmente": l.recibo_local.aceitos,
                       "recusados_localmente": l.recibo_local.recusados}
                      for l in self.lotes],
        }


def _exigir_regra_por_evento(perfil: pdm.PerfilDeMensuracao) -> None:
    modo = perfil.regra_de_valor.modo
    if modo == pdm.VALOR_FIXO:
        raise ValorFixoRecusado(
            "o perfil de mensuração declara valor FIXO "
            f"({perfil.regra_de_valor.valor} {perfil.regra_de_valor.moeda}). Valor fixo é "
            "o que deixa o ROAS nativo falso; este caminho só envia valor medido por "
            "evento. Troque a regra do perfil para `por_evento`.")
    if modo != pdm.VALOR_POR_EVENTO:
        raise RegraDeValorIncompativel(
            f"o perfil declara regra de valor {modo!r}; o envio com receita medida exige "
            "`por_evento`.")


def _janela_expirada(perfil: pdm.PerfilDeMensuracao, clique: ev.CliqueObservado,
                     hoje: date) -> Optional[vl.Pulo]:
    janela = perfil.janela
    if janela.estado != pdm.JANELA_DECLARADA or not janela.dias_de_clique:
        return vl.Pulo(ev.PULO_JANELA_NAO_DECLARADA,
                       "a janela de clique da ação não foi declarada; sem ela não se sabe "
                       "se o Google ainda aceita este clique")
    idade = (hoje - clique.visitado_em.date()).days
    if idade > janela.dias_de_clique:
        return vl.Pulo(ev.PULO_CLIQUE_EXPIRADO,
                       f"o clique tem {idade} dia(s) e a janela da ação é "
                       f"{janela.dias_de_clique}")
    return None


def preparar_lote(*, plano: pm.PlanoDeMensuracao,
                  perfil: pdm.PerfilDeMensuracao,
                  moeda_da_conta: vl.MoedaDaConta,
                  politica: vl.PoliticaDeValor,
                  de: date, ate: date, hoje: date,
                  conhecido_ate: Optional[datetime],
                  rodada: str,
                  cliques: portas.FonteDeCliques,
                  receita: portas.FonteDeReceita,
                  cambio: portas.FonteDeCambio,
                  registro: portas.RegistroDeConversoes,
                  retomar_incertos: bool = False) -> Preparo:
    """Decide cada clique, grava as decisões e devolve os envelopes validados.

    `retomar_incertos=True` devolve ao envelope, com o MESMO valor, os itens
    cujo envio real ficou `sem_resposta`. É seguro do lado do Google (mesmo
    `transactionId` na mesma ação vira ajuste, a contagem não muda), e o banco
    só aceita o reenvio se o envelope for idêntico ao que ficou sem resposta.
    """
    if not str(rodada or "").strip():
        raise ValueError("rodada sem identificador")
    if de > ate:
        raise ValueError("intervalo invertido")
    _exigir_regra_por_evento(perfil)
    if not plano.destino.resolvido:
        raise dm.DestinoNaoResolvido(plano.destino.causa or "destino não resolvido")
    if plano.destino.tipo_da_acao != TIPO_IMPORTACAO_DE_CLIQUES:
        raise AcaoOfflineInvalida(
            f"o destino é uma ação {plano.destino.tipo_da_acao}; o valor medido só vai "
            f"para uma ação {TIPO_IMPORTACAO_DE_CLIQUES} (use `plano_para_acao_offline`)")
    if not perfil.aplicavel_a_envio_offline:
        raise dm.ConsentimentoInsuficiente(
            f"o consentimento da conta é {perfil.consentimento!r}; a ingestão offline "
            "exige 'concedido'")
    dono = str(plano.destino.operating_account_id)
    acao = str(plano.destino.product_destination_id)
    if moeda_da_conta.customer_id != dono:
        raise MoedaDeOutraConta(
            f"a moeda lida é da conta {moeda_da_conta.customer_id} e a ação pertence a "
            f"{dono}; o valor tem de estar na moeda da conta dona")

    # A maturidade é medida contra o que se sabia: num replay (`conhecido_ate`
    # no passado), "hoje" não pode ser o hoje do relógio.
    if conhecido_ate is not None:
        if conhecido_ate.tzinfo is None:
            raise ValueError("conhecido_ate sem fuso")
        hoje = min(hoje, conhecido_ate.astimezone(timezone.utc).date())

    def _ordem(c: ev.CliqueObservado):
        # ⚠️ Instante em UTC: o texto ISO com offsets diferentes não ordena o tempo.
        if c.visitado_em.tzinfo is None or c.visitado_em.utcoffset() is None:
            return (1, datetime.max.replace(tzinfo=timezone.utc), c.visita_ref)
        return (0, c.visitado_em.astimezone(timezone.utc), c.visita_ref)

    lidos = sorted(cliques.cliques(customer_id=plano.customer_id, de=de, ate=ate), key=_ordem)

    valores: Dict[vl.Coorte, vl.Resultado] = {}

    def valor_da_coorte(coorte: vl.Coorte) -> vl.Resultado:
        if coorte not in valores:
            linha = receita.receita_vigente(fonte=politica.fonte_de_receita,
                                            coorte=coorte, conhecido_ate=conhecido_ate)
            cot = None
            if (linha is not None and linha.receita is not None
                    and linha.moeda != moeda_da_conta.codigo):
                cot = cambio.resolver(data=coorte.data_referencia,
                                      par=f"{linha.moeda}/{moeda_da_conta.codigo}",
                                      max_defasagem_dias=politica.max_defasagem_cambio_dias,
                                      conhecido_ate=conhecido_ate)
            sessoes = cliques.sessoes_da_coorte(coorte) if linha is not None else None
            valores[coorte] = vl.calcular_valor(
                receita=linha, cotacao=cot, moeda_da_conta=moeda_da_conta,
                sessoes_da_coorte=sessoes, politica=politica, hoje=hoje)
        return valores[coorte]

    decisoes: List[ev.Decisao] = []
    candidatos: List[Tuple[ev.CliqueObservado, str, vl.ValorMedido]] = []
    vistos: set = set()
    for c in lidos:
        tid = ev.transaction_id(operating_account_id=dono, product_destination_id=acao,
                                clique=c.clique)
        pulo: Optional[vl.Pulo] = None
        if tid in vistos:
            pulo = vl.Pulo(PULO_CLIQUE_REPETIDO,
                           "o mesmo clique apareceu em outra visita (recarga); vale a primeira")
        elif c.consentimento != dm.CONSENTIMENTO_CONCEDIDO:
            pulo = vl.Pulo(ev.PULO_SEM_CONSENTIMENTO,
                           f"o consentimento do visitante é {c.consentimento!r}; ausência de "
                           "declaração não é permissão")
        elif c.visitado_em.tzinfo is None or c.visitado_em.utcoffset() is None:
            pulo = vl.Pulo(ev.PULO_HORA_SEM_FUSO, "a hora da visita não declara fuso")
        else:
            pulo = _janela_expirada(perfil, c, hoje)
        vistos.add(tid)
        if pulo is None:
            resultado = valor_da_coorte(c.coorte)
            if isinstance(resultado, vl.Pulo):
                pulo = resultado
            else:
                candidatos.append((c, tid, resultado))
                continue
        decisoes.append(ev.Decisao.pulada(tid=tid, clique=c, pulo=pulo))

    anteriores = registro.envios_reais_vivos(
        operating_account_id=dono, product_destination_id=acao,
        transaction_ids=[tid for _, tid, _ in candidatos]) if candidatos else {}

    # ⚠️ RATEIO CONGELADO POR COORTE. Se algum clique de uma coorte já foi
    # enviado de verdade, a coorte já foi dividida: um clique novo dela, com um
    # divisor que mudou, faria a soma enviada passar da receita. (Revisão
    # adversarial W14, bloqueante 2: 4 × 16,23 + 12,98 = 77,90 para 64,92.)
    tocadas = {c.coorte for c, tid, _ in candidatos if tid in anteriores}

    eventos: List[Tuple[dm.EventoDeConversao, str]] = []
    for c, tid, valor in candidatos:
        antes = anteriores.get(tid)
        retomar = (antes is not None and antes.estado == "sem_resposta" and retomar_incertos
                   and antes.valor_impressao == valor.impressao())
        if antes is None and c.coorte in tocadas:
            decisoes.append(ev.Decisao.pulada(tid=tid, clique=c, pulo=vl.Pulo(
                PULO_COORTE_JA_RATEADA,
                "outro clique desta coorte já foi enviado com o rateio daquela rodada; "
                "um clique novo mudaria o divisor e a soma enviada passaria da receita")))
            continue
        if antes is not None and not retomar:
            if antes.estado == "sem_resposta":
                pulo = vl.Pulo(PULO_ENVIO_INCERTO,
                               f"o lote {antes.lote_id} ficou sem resposta: ninguém disse se "
                               "entrou. Reenvie o MESMO envelope com retomar_incertos=True")
            elif antes.valor_impressao == valor.impressao():
                pulo = vl.Pulo(ev.PULO_JA_ENVIADO,
                               f"já enviado no lote {antes.lote_id} ({antes.estado}) com o mesmo valor")
            else:
                pulo = vl.Pulo(ev.PULO_AJUSTE_NAO_AUTORIZADO,
                               f"já enviado no lote {antes.lote_id} com outro valor; reenviar "
                               "seria um ajuste no Google, e ajuste não está autorizado")
            decisoes.append(ev.Decisao.pulada(tid=tid, clique=c, pulo=pulo))
            continue
        ocorrido = c.visitado_em.isoformat()
        decisoes.append(ev.Decisao(
            transaction_id=tid, visita_ref=c.visita_ref, clique_tipo=c.clique.tipo,
            clique_sha256=ev.sha256(c.clique.valor), ocorrido_em=ocorrido,
            estado=ev.ELEGIVEL, valor=valor))
        eventos.append((dm.EventoDeConversao(
            clique=c.clique, ocorrido_em=ocorrido, chave_de_deduplicacao=tid,
            valor=valor.valor, moeda=valor.moeda,
            consentimento_do_usuario=c.consentimento), valor.impressao()))

    # ⚠️ As decisões são gravadas ANTES de existir envelope: a proveniência de
    # cada valor fica no registro mesmo que nada seja enviado depois.
    registro.registrar_decisoes(rodada=rodada, customer_id=plano.customer_id,
                                operating_account_id=dono, product_destination_id=acao,
                                decisoes=[d.json() for d in decisoes])

    lotes: List[LotePreparado] = []
    for fatia in ev.fatiar(eventos):
        envelope = dm.montar_envelope(plano=plano, perfil=perfil,
                                      eventos=[e for e, _ in fatia])
        lotes.append(LotePreparado(
            envelope=envelope, recibo_local=dm.validar(envelope),
            itens=tuple((e.chave_de_deduplicacao, imp) for e, imp in fatia),
            destino_primario=bool(plano.acao_alvo is not None and plano.acao_alvo.primaria_efetiva)))

    return Preparo(rodada=rodada, customer_id=plano.customer_id,
                   operating_account_id=dono, product_destination_id=acao,
                   decisoes=tuple(decisoes), lotes=tuple(lotes))
