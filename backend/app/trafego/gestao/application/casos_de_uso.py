"""Os casos de uso da gestão sobre o ledger v10_02. Sem HTTP, sem PostgREST, sem SDK.

    propor     lê o "antes" na conta → evidência → diagnóstico → proposta.
               Idempotente só enquanto a anterior do mesmo conteúdo está viva
    aprovar    a decisão humana, com o diff que a tela MOSTROU
    aplicar    relê o "antes"; diverge → recusa. Igual → aplicação `em_voo` →
               validate_only → escrita pela trava → desfecho. Idempotente.
    verificar  relê e compara com o proposto → `trafego_acompanhamento`
    reverter   do `valor_anterior` capturado no envio → `trafego_atuacao_reversao`
    importar   identidade em `trafego_campanha` para campanha que não nasceu aqui
    recomendacoes  GAQL `recommendation` (leitura pura)

## A ordem das escritas, e por que ela não é uma transação

O PostgREST não abre transação entre tabelas, e a v10_02 não tem RPC para o
ciclo. Então a ordem foi escolhida para que a falha no meio deixe HISTÓRIA, e
nunca autorização:

  · tudo que o gatilho `trafego_proposta_respeita_regra` recusaria é conferido
    ANTES da primeira escrita (espelho de `intencao.pode_aplicar`, pela mesma
    razão: a recusa vira mensagem antes de virar linha órfã);
  · evidência insuficiente FICA gravada como `insuficiente` — é observação
    ("olhei e falta"), e a v10_02 a quer append-only;
  · aplicação: a linha `em_voo` é commitada ANTES da chamada que muta (mesmo
    protocolo do recibo da v10_01). Processo que morre deixa `em_voo`, e
    `em_voo` manda verificar, nunca reenviar.

## "Verificar, nunca reenviar"

Uma aplicação `em_voo` ou `sem_resposta` bloqueia nova tentativa até uma
verificação dizer o que a conta tem. Se a verificação mostra que a mudança
entrou, a proposta vira `aplicada` sem segunda chamada; se mostra que não
entrou, uma nova tentativa (linha nova, `tentativa + 1`) é permitida. Orçamento
dobrado duas vezes é orçamento quadruplicado.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from app.trafego import escopo, intencao
from volc_ads.gestao import ledger as motor_ledger
from volc_ads.gestao.acoes import AcaoRecusada

from . import autonomia, sem_delta
from .efeito import conferir_efeito
from .erros import (AcaoInvalida, AntesDivergiu, BancoRecusou, CampanhaNaoImportada,
                    ConflitoDeEstado, EmCarencia, ErroDeGestao, EscritaBloqueada,
                    EvidenciaInsuficiente, ExigeAprovacaoHumana, ForaDaCasa, ForaDaRegra,
                    Indisponivel, NaoEncontrado, RegraAusente)
from .payload import acao_da_proposta, customer_id_da_proposta, pedido_do_payload
from .portas import ContaGoogle, Ledger

PLATAFORMA = "GOOGLE_ADS"
ORIGEM_DA_EVIDENCIA = "gestao:gaql_metricas"

#: Abaixo disto, uma aplicação `em_voo` pode ainda estar NO AR (outra requisição
#: esperando o Google). A verificação não a fecha antes: fechá-la faria a
#: requisição viva falhar ao gravar o desfecho de uma escrita que deu certo.
EM_VOO_ORFA_APOS = timedelta(minutes=5)

#: Os estados em que uma proposta ainda está NO CICLO (v10_02,
#: `trafego_proposta_estado_conhecido`). Só eles seguram a idempotência de
#: `propor`: repetir o pedido devolve a mesma. `recusada`, `expirada`,
#: `cancelada`, `revertida` e `aplicada` fecharam o ciclo — o mesmo pedido sobre
#: o mesmo "antes" vira proposta NOVA (`ledger.chave_da_tentativa`). `aplicada`
#: está fora de propósito: ler de novo o "antes" que ela mudou quer dizer que a
#: conta voltou a ele por outro caminho, e reaplicar exige outra decisão humana.
ESTADOS_VIVOS = ("aguardando_aprovacao", "aprovada")

#: Teto de repropostas do mesmo conteúdo. Não é regra de negócio: é o freio de
#: um laço que lê o banco. Cem recusas do mesmo diff é defeito de quem propõe.
MAX_TENTATIVAS_DE_PROPOSTA = 100


class GoogleRecusou(ErroDeGestao):
    """O Google recusou o payload (no validate_only ou na escrita). Registrado como `erro`."""

    status = 422
    codigo = "google_recusou"


@dataclass(frozen=True)
class Configuracao:
    #: A regra que uma proposta HUMANA cita quando o pedido não nomeia outra.
    #: Ela tem de existir e estar vigente em `trafego_regra_otimizacao`: este
    #: módulo não a inventa — regra é dado com dono (ver o contrato).
    regra_padrao: str = "gestao_manual_google"
    validade_padrao_horas: int = 24
    validade_maxima_horas: int = 168
    #: O fuso das contas da casa. `segments.date` é no fuso da CONTA.
    fuso: str = "America/Sao_Paulo"


# ── utilidades puras ────────────────────────────────────────────────────────


def _canon(v: Any) -> Any:
    """O valor como o jsonb o devolve: ida e volta por JSON."""
    return json.loads(json.dumps(v, sort_keys=True, ensure_ascii=False, default=str))


def campos_divergentes(aprovado: Mapping[str, Any], agora: Mapping[str, Any]) -> List[str]:
    """As chaves cujo valor mudou entre o "antes" aprovado e o relido."""
    a, b = _canon(dict(aprovado or {})), _canon(dict(agora or {}))
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()


def _quando(bruto: Any) -> Optional[datetime]:
    if isinstance(bruto, datetime):
        return bruto if bruto.tzinfo else bruto.replace(tzinfo=timezone.utc)
    if not bruto:
        return None
    try:
        d = datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def regra_de_dominio(linha: Mapping[str, Any]) -> "intencao.RegraDeOtimizacao":
    """A linha do banco no tipo do domínio — o que `avaliar_suficiencia` lê."""
    nomes = {f.name for f in fields(intencao.RegraDeOtimizacao)}
    d = {k: v for k, v in linha.items() if k in nomes}
    for k in ("plataformas", "canais", "dados_obrigatorios"):
        d[k] = tuple(d.get(k) or ())
    for k in ("confianca_minima", "limite_alteracao_pct", "amostra_minima_conversoes"):
        if d.get(k) is not None:
            d[k] = float(d[k])
    try:
        return intencao.RegraDeOtimizacao(**d)
    except (intencao.ErroDeIntencao, TypeError) as exc:
        raise ConflitoDeEstado(f"a regra {linha.get('chave')} v{linha.get('versao')} não "
                               f"passa no domínio: {exc}", codigo="regra_invalida") from exc


def conferir_contra_regra(linha: Mapping[str, Any], regra: Mapping[str, Any],
                          *, agora: datetime) -> None:
    """Espelho de `trafego_proposta_respeita_regra` (travas 2–5). Levanta `ForaDaRegra`.

    ⚠️ A trava 4a: regra com limite de alteração + ação SEM número (pausa,
    negativa, lista, exclusão, agenda, ajuste, recomendação) = recusa
    `regra_exige_delta`, como na v10_02 — A MENOS QUE a regra liste a operação
    em `operacoes_sem_delta` (v17_03). Listada, a proposta passa pelo teto
    próprio da operação (`teto_sem_delta` se não couber). Inventar um delta 0
    para passar continua sendo o furo que a trava fecha, e não é feito aqui.
    """
    chave = regra.get("chave")
    lido = _quando(linha.get("valor_atual_lido_em"))
    if lido is not None and agora - lido > timedelta(hours=int(regra["frescor_maximo_horas"])):
        raise ForaDaRegra(f"o 'antes' foi lido há mais de {regra['frescor_maximo_horas']} h "
                          f"(frescor da regra {chave})", codigo="antes_velho")
    pct, absoluto = regra.get("limite_alteracao_pct"), regra.get("limite_alteracao_absoluto_micros")
    dpct, dabs = linha.get("delta_pct"), linha.get("delta_absoluto_micros")
    operacao = str(linha.get("operacao") or "")
    tetos = sem_delta.declaradas(regra)
    if dpct is None and dabs is None and operacao in tetos:
        # O ramo IF da trava 4a da v17_03: a regra autoriza esta operação sem delta.
        motivo = sem_delta.defeito(tetos[operacao], operacao, linha.get("alvo_nivel"),
                                   linha.get("valor_atual"), linha.get("valor_proposto"))
        if motivo:
            raise ForaDaRegra(
                f"a regra {chave} autoriza {operacao} sem delta, mas esta proposta passa do "
                f"teto declarado: {motivo}",
                codigo="teto_sem_delta",
                detalhe={"operacao": operacao, "classe": sem_delta.classe(operacao),
                         "regra": chave, "teto": tetos[operacao], "motivo": motivo})
    elif ((pct is not None and absoluto is not None and dpct is None and dabs is None)
          or (pct is not None and absoluto is None and dpct is None)
          or (absoluto is not None and pct is None and dabs is None)):
        # O ELSE: a trava 4a da v10_02 como sempre.
        if operacao in sem_delta.MONETARIAS:
            porque = ("operação monetária exige delta e limite de alteração; nenhuma "
                      "declaração de regra a dispensa")
        else:
            porque = (f"a regra não lista {operacao} em `operacoes_sem_delta` (v17_03). "
                      "Para propor esta operação, o dono publica a versão seguinte da regra "
                      "declarando-a, com o teto próprio dela")
        raise ForaDaRegra(
            f"a regra {chave} declara limite de alteração e a operação {operacao} não tem "
            f"tamanho numérico (trava 4a de `trafego_proposta_respeita_regra`): {porque}.",
            codigo="regra_exige_delta",
            detalhe={"operacao": operacao, "regra": chave,
                     "classe": sem_delta.classe(operacao),
                     "operacoes_sem_delta_da_regra": sorted(tetos)})
    if dpct is not None and pct is not None and abs(float(dpct)) > float(pct):
        raise ForaDaRegra(f"alteração de {dpct}% estoura o limite de {pct}% da regra {chave}",
                          codigo="limite_pct", detalhe={"delta_pct": dpct, "limite": pct})
    if dabs is not None and absoluto is not None and abs(int(dabs)) > int(absoluto):
        raise ForaDaRegra(f"alteração de {dabs} micros estoura o limite de {absoluto} micros "
                          f"da regra {chave}", codigo="limite_absoluto",
                          detalhe={"delta_absoluto_micros": dabs, "limite": absoluto})
    teto = regra.get("teto_orcamento_micros")
    proposto = (linha.get("valor_proposto") or {}).get("verba_diaria_micros")
    if teto is not None and isinstance(proposto, int) and not isinstance(proposto, bool):
        moeda = linha.get("moeda")
        if moeda is not None and moeda != regra.get("teto_orcamento_moeda"):
            raise ForaDaRegra(f"proposta em {moeda} e teto da regra {chave} em "
                              f"{regra.get('teto_orcamento_moeda')}", codigo="moeda_do_teto")
        if proposto > int(teto):
            raise ForaDaRegra(f"verba diária proposta ({proposto} micros) estoura o teto de "
                              f"{teto} micros da regra {chave}", codigo="teto_orcamento",
                              detalhe={"proposto": proposto, "teto": teto})


def janela_da_regra(regra: Mapping[str, Any], hoje: date) -> tuple[date, date]:
    """Dias inteiros, fechados, que já cobrem o atraso de conversão da regra.

    `fim` é ontem menos o atraso: com `colhida_em` = agora, a pergunta (3) de
    `avaliar_suficiencia` ("o atraso já passou?") é verdadeira por construção,
    em vez de recusar toda proposta feita no mesmo dia.
    """
    fim = hoje - timedelta(days=1 + int(regra.get("atraso_conversao_dias") or 0))
    inicio = fim - timedelta(days=int(regra["janela_minima_dias"]) - 1)
    return inicio, fim


def _nivel_das_metricas(acao: Any) -> tuple[str, str]:
    """Onde medir a evidência de uma ação. Conta quando o alvo não é medível sozinho."""
    nivel, alvo = acao.alvo_nivel, str(acao.alvo_id)
    if nivel in ("campanha", "grupo", "anuncio", "asset_group") and alvo[:1].isdigit():
        return nivel, alvo
    return "conta", ""


# ── os casos de uso ─────────────────────────────────────────────────────────


class Gestao:
    """Fachada dos casos de uso. Cada método é uma transição do ciclo v10_02."""

    def __init__(self, ledger: Ledger, conta: ContaGoogle, *,
                 config: Configuracao = Configuracao(),
                 agora: Optional[Callable[[], datetime]] = None,
                 escrita_habilitada: Optional[Callable[[], bool]] = None,
                 portao: Optional[Callable[[str], Any]] = None) -> None:
        self.ledger = ledger
        self.conta = conta
        self.config = config
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._escrita_habilitada = escrita_habilitada or _env_de_escrita
        self._portao = portao or escopo.conta_da_casa

    def agora(self) -> datetime:
        return self._agora()

    async def _no_escopo(self, customer_id: Any) -> str:
        """A conta tem de ser da casa — antes de qualquer leitura ou escrita.

        `conta_da_casa` e não `exigir_escopo`: aqui a resposta precisa dizer O
        QUE está errado, e a gestão escreve no ledger antes de falar com o
        Google — o 403 do próprio Google chegaria tarde demais. Custa ~1,6 s.
        """
        cid = escopo.so_digitos(customer_id)
        try:
            await asyncio.to_thread(self._portao, cid)
        except escopo.ForaDoEscopo as exc:
            raise ForaDaCasa(str(exc), detalhe={"customer_id": cid}) from exc
        except Exception as exc:  # noqa: BLE001
            raise Indisponivel(f"não deu para conferir a conta {cid} contra a árvore da "
                               f"casa: {str(exc)[:300]}", codigo="escopo_indisponivel") from exc
        return cid

    async def _google(self, fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
        """Chama a conta numa thread; traduz recusa do motor e falha de rede."""
        try:
            return await asyncio.to_thread(fn, *args, **kw)
        except ErroDeGestao:
            raise
        except AcaoRecusada as exc:
            raise AcaoInvalida(str(exc), codigo="estado_nao_permite") from exc
        except Exception as exc:  # noqa: BLE001
            raise Indisponivel(f"o Google Ads não respondeu: {type(exc).__name__}: "
                               f"{str(exc)[:400]}") from exc

    def _exigir_trava_aberta(self) -> None:
        """A trava de dois fatores, conferida ANTES de qualquer linha nova.

        O segundo fator (`modo.destravar`) é aberto pelo adaptador no momento da
        escrita; o primeiro é ambiente, e conferi-lo aqui evita gravar uma
        aplicação/reversão que nasce condenada — a reversão principalmente, que
        só pode existir UMA por aplicação.
        """
        if not self._escrita_habilitada():
            raise EscritaBloqueada(
                "a escrita no Google está desligada neste processo (FORGE_PERMITIR_ESCRITA "
                "≠ 1). Nada foi gravado no ledger e nada foi enviado.")

    # ── propor ──────────────────────────────────────────────────────────────

    async def propor(self, customer_id: str, acao_payload: Mapping[str, Any], *,
                     motivo: str, autor: str, regra_chave: Optional[str] = None,
                     validade_horas: Optional[int] = None) -> Dict[str, Any]:
        customer_id = await self._no_escopo(customer_id)
        motivo = (motivo or "").strip()
        if not motivo:
            raise AcaoInvalida("proposta sem motivo: o diagnóstico exige explicação "
                               "(sem ela o humano aprova uma caixa-preta)", codigo="sem_motivo")
        horas = validade_horas or self.config.validade_padrao_horas
        if not 1 <= int(horas) <= self.config.validade_maxima_horas:
            raise AcaoInvalida(f"validade_horas fora de [1, {self.config.validade_maxima_horas}]")
        pedido = pedido_do_payload(acao_payload)

        chave = regra_chave or self.config.regra_padrao
        regra = await self.ledger.regra_vigente(chave)
        if not regra:
            raise RegraAusente(
                f"não há versão vigente da regra {chave!r} em trafego_regra_otimizacao. "
                "Toda proposta cita a regra que a limita; publicar a regra é decisão do dono.",
                detalhe={"regra_chave": chave})
        dominio = regra_de_dominio(regra)
        if PLATAFORMA not in dominio.plataformas:
            raise ForaDaRegra(f"a regra {chave} não vale para {PLATAFORMA}", codigo="plataforma")

        antes = await self._google(self.conta.ler_antes, customer_id, pedido.acao,
                                   conferir=pedido.completar is None)
        acao = pedido.acao
        if pedido.completar is not None:
            try:
                acao = pedido.completar(antes.dados)
                acao.conferir(antes.dados)
            except AcaoRecusada as exc:
                raise AcaoInvalida(str(exc), codigo="estado_nao_permite") from exc

        linha = motor_ledger.proposta(acao, customer_id, antes.dados, antes.lido_em)
        ja, linha["idempotency_key"] = await self._viva_ou_chave_livre(linha["idempotency_key"])
        if ja:
            return await self._ja_existia(ja)

        volc_campaign_id = None
        if acao.alvo_nivel == "campanha":
            ident = await self.ledger.identidade_campanha(customer_id, str(acao.alvo_id))
            if not ident:
                raise CampanhaNaoImportada(
                    f"a campanha {acao.alvo_id} da conta {customer_id} não tem identidade em "
                    "trafego_campanha. Importe-a antes (POST /api/trafego/gestao/campanhas/"
                    "importar): proposta de nível campanha exige volc_campaign_id.",
                    detalhe={"customer_id": customer_id, "campaign_id": str(acao.alvo_id)})
            volc_campaign_id = ident["volc_campaign_id"]

        agora = self.agora()
        conferir_contra_regra(linha, regra, agora=agora)

        hoje = agora.astimezone(ZoneInfo(self.config.fuso)).date()
        inicio, fim = janela_da_regra(regra, hoje)
        nivel, alvo = _nivel_das_metricas(acao)
        metricas = await self._google(self.conta.ler_metricas, customer_id, nivel, alvo,
                                      inicio.isoformat(), fim.isoformat())
        colhida = self.agora()
        medidas = {k: metricas.get(k) for k in ("impressoes", "cliques", "custo_micros",
                                                "conversoes", "valor_conversao_micros")}
        suf = intencao.avaliar_suficiencia(
            {**medidas, "janela_inicio": inicio, "janela_fim": fim, "colhida_em": colhida},
            dominio, agora=colhida)
        evidencia = await self.ledger.inserir_evidencia({
            "regra_id": regra["regra_id"], "plataforma": PLATAFORMA,
            "conta_externa": customer_id, "volc_campaign_id": volc_campaign_id,
            "janela_inicio": inicio.isoformat(), "janela_fim": fim.isoformat(),
            "colhida_em": _iso(colhida), "origem": ORIGEM_DA_EVIDENCIA, **medidas,
            "moeda": metricas.get("moeda"),
            "metricas": {"nivel": nivel, "alvo": alvo or None,
                         "sem_linhas": bool(metricas.get("sem_linhas"))},
            "suficiencia": suf.veredito, "suficiencia_motivo": suf.motivo,
            "suficiencia_em": _iso(colhida),
            "faltantes": list(suf.faltantes) or None,
        })
        if not suf.suficiente:
            raise EvidenciaInsuficiente(
                f"evidência insuficiente para a regra {chave}: {suf.motivo}",
                detalhe={"evidencia_id": evidencia["evidencia_id"],
                         "faltantes": list(suf.faltantes)})

        diagnostico = await self.ledger.inserir_diagnostico({
            "evidencia_id": evidencia["evidencia_id"], "regra_id": regra["regra_id"],
            "detectado_em": _iso(agora), "produtor": f"humano:{autor}",
            "sintoma": f"pedido humano: {acao.tipo}", "explicacao": motivo,
        })
        try:
            gravada = await self.ledger.inserir_proposta({
                **linha, "diagnostico_id": diagnostico["diagnostico_id"],
                "regra_id": regra["regra_id"], "volc_campaign_id": volc_campaign_id,
                "criada_por": f"humano:{autor}",
                "expira_em": _iso(agora + timedelta(hours=int(horas))),
            })
        except BancoRecusou as exc:
            # Corrida: outra requisição gravou a MESMA proposta (chave do conteúdo).
            # A chave é determinística (base + tentativa): quem perdeu a corrida
            # calculou a MESMA `base:tN` e devolve a que ganhou.
            if (exc.detalhe or {}).get("sqlstate") == "23505":
                ja = await self.ledger.proposta_por_chave(linha["idempotency_key"])
                if ja:
                    return await self._ja_existia(ja)
            raise
        return {"proposta": gravada, "evidencia_id": evidencia["evidencia_id"],
                "diagnostico_id": diagnostico["diagnostico_id"], "ja_existia": False}

    async def _viva_ou_chave_livre(self, base: str) -> tuple[Optional[Dict[str, Any]], str]:
        """(proposta viva do mesmo conteúdo, None) ou (None, a chave da próxima tentativa).

        Percorre `base`, `base:t2`, … até a primeira chave livre. Só a ÚLTIMA
        tentativa pode estar viva (os estados de fim não voltam), mas cada uma é
        conferida: custa uma leitura por tentativa e não depende disso.
        """
        for n in range(1, MAX_TENTATIVAS_DE_PROPOSTA + 1):
            chave = motor_ledger.chave_da_tentativa(base, n)
            p = await self.ledger.proposta_por_chave(chave)
            if p is None:
                return None, chave
            if await self._ainda_viva(p):
                return p, chave
        raise ConflitoDeEstado(
            f"o mesmo pedido já foi proposto {MAX_TENTATIVAS_DE_PROPOSTA} vezes sobre o mesmo "
            "'antes' e nenhuma proposta seguiu viva; algo está repropondo em laço.",
            codigo="repropostas_demais", detalhe={"chave_base": base})

    async def _ainda_viva(self, p: Mapping[str, Any]) -> bool:
        """A proposta ainda segura a idempotência? (ver `ESTADOS_VIVOS`)

        Vencida em `aguardando_aprovacao`/`aprovada` é marcada `expirada` aqui —
        é o que `aprovar`/`aplicar` fariam ao tocá-la —, MENOS a que tem
        tentativa em voo ou sem resposta não verificada: essa pode estar na
        conta agora, e uma segunda proposta do mesmo diff seria a porta para
        aplicar duas vezes. Ela segue viva até alguém verificar.
        """
        if p.get("estado") not in ESTADOS_VIVOS:
            return False
        if p.get("estado") == "aprovada":
            aplicacoes = await self.ledger.aplicacoes_da_proposta(p["proposta_id"])
            if await self._tentativa_pendente(aplicacoes):
                return True
        expira = _quando(p.get("expira_em"))
        if expira is None or expira > self.agora():
            return True
        marcada = await self.ledger.atualizar_estado_proposta(
            p["proposta_id"], list(ESTADOS_VIVOS), "expirada")
        if marcada is None:  # outra requisição mudou o estado no meio: vale o de agora
            atual = await self.ledger.proposta(p["proposta_id"]) or {}
            return atual.get("estado") in ESTADOS_VIVOS
        return False

    async def _ja_existia(self, p: Mapping[str, Any]) -> Dict[str, Any]:
        """A resposta de "já existia" no MESMO formato da proposta nova (contrato §3.2)."""
        diagnostico_id = p.get("diagnostico_id")
        diag = await self.ledger.diagnostico(diagnostico_id) if diagnostico_id else None
        return {"proposta": dict(p), "evidencia_id": (diag or {}).get("evidencia_id"),
                "diagnostico_id": diagnostico_id, "ja_existia": True}

    # ── aprovar / recusar ───────────────────────────────────────────────────

    async def _proposta(self, proposta_id: str) -> Dict[str, Any]:
        p = await self.ledger.proposta(proposta_id)
        if not p:
            raise NaoEncontrado(f"proposta {proposta_id} não existe")
        return p

    async def _expirar_se_vencida(self, p: Mapping[str, Any]) -> None:
        expira = _quando(p.get("expira_em"))
        if expira is not None and expira <= self.agora():
            await self.ledger.atualizar_estado_proposta(
                p["proposta_id"], ["aguardando_aprovacao", "aprovada"], "expirada")
            raise ConflitoDeEstado(
                f"a proposta expirou em {expira.isoformat()}. Proponha de novo: o 'antes' "
                "que o humano viu já não é o 'antes' da conta.", codigo="proposta_expirada")

    async def aprovar(self, proposta_id: str, decisao: str, *, motivo: Optional[str],
                      aprovador: str, diff_apresentado: Any) -> Dict[str, Any]:
        if decisao not in ("aprovada", "recusada"):
            raise AcaoInvalida(f"decisão desconhecida: {decisao!r}")
        p = await self._proposta(proposta_id)
        await self._no_escopo(customer_id_da_proposta(p))
        existente = await self.ledger.aprovacao_da_proposta(proposta_id)
        if existente:
            if existente.get("decisao") == decisao:
                return {"aprovacao": existente, "proposta": p, "ja_existia": True}
            raise ConflitoDeEstado(
                f"a proposta já foi decidida como {existente.get('decisao')!r} por "
                f"{existente.get('decidida_por')}; a decisão é única e não se reescreve",
                codigo="ja_decidida")
        if p.get("estado") != "aguardando_aprovacao":
            raise ConflitoDeEstado(f"proposta em {p.get('estado')!r}, não aguarda decisão")
        await self._expirar_se_vencida(p)
        if decisao == "recusada" and not (motivo or "").strip():
            raise AcaoInvalida("recusa sem motivo não ensina nada a quem escreveu a regra",
                               codigo="recusa_sem_motivo")
        if not isinstance(diff_apresentado, Mapping):
            raise AcaoInvalida("`diff_apresentado` é obrigatório: o diff que a tela MOSTROU",
                               codigo="sem_diff_apresentado")
        if decisao == "aprovada":
            for coluna in ("valor_proposto", "valor_atual"):
                if coluna not in diff_apresentado and coluna == "valor_proposto":
                    raise AcaoInvalida("aprovar exige `diff_apresentado.valor_proposto`",
                                       codigo="sem_diff_apresentado")
                if coluna in diff_apresentado and \
                        _canon(diff_apresentado[coluna]) != _canon(p.get(coluna)):
                    raise ConflitoDeEstado(
                        f"a tela mostrou um {coluna} diferente do gravado; aprovar seria "
                        "autorizar outra coisa. Recarregue a proposta.",
                        codigo="diff_divergente",
                        detalhe={"coluna": coluna, "gravado": p.get(coluna),
                                 "apresentado": diff_apresentado[coluna]})
        aprovacao = await self.ledger.inserir_aprovacao({
            "proposta_id": proposta_id, "decisao": decisao,
            "decidida_por": f"humano:{aprovador}",
            "observacao": (motivo or "").strip() or None,
            "diff_apresentado": dict(diff_apresentado),
        })
        nova = await self.ledger.atualizar_estado_proposta(
            proposta_id, ["aguardando_aprovacao"], decisao)
        return {"aprovacao": aprovacao, "proposta": nova or p, "ja_existia": False}

    # ── aplicar ─────────────────────────────────────────────────────────────

    async def _ultima_verificacao(self, aplicacao_id: str) -> Optional[Dict[str, Any]]:
        linhas = await self.ledger.acompanhamentos_da_aplicacao(aplicacao_id)
        verif = [a for a in linhas if a.get("momento") == "verificacao"]
        return max(verif, key=lambda a: str(a.get("observado_em") or "")) if verif else None

    async def _tentativa_pendente(self, aplicacoes: Sequence[Mapping[str, Any]]
                                  ) -> Optional[Mapping[str, Any]]:
        """A tentativa que pode ter entrado na conta sem sabermos, se houver.

        `em_voo` bloqueia SEMPRE: pode estar no ar agora. Só `sem_resposta`
        verificado como "não entrou" libera a tentativa seguinte.
        """
        for a in aplicacoes:
            if a.get("desfecho") in ("em_voo", "sem_resposta"):
                verif = await self._ultima_verificacao(a["aplicacao_id"])
                if (a.get("desfecho") == "em_voo" or verif is None
                        or verif.get("confere") is not False):
                    return a
        return None

    async def aplicar(self, proposta_id: str, *, executor: str) -> Dict[str, Any]:
        p = await self._proposta(proposta_id)
        customer_id = await self._no_escopo(customer_id_da_proposta(p))
        aplicacoes = await self.ledger.aplicacoes_da_proposta(proposta_id)
        sucesso = next((a for a in aplicacoes if a.get("desfecho") == "sucesso"), None)
        if sucesso or p.get("estado") == "aplicada":
            # Idempotente: a mesma proposta não sai duas vezes. `aplicada` sem
            # linha `sucesso` é a que a VERIFICAÇÃO confirmou na conta depois de
            # uma tentativa sem resposta — reenviar seria aplicar de novo.
            ultima = sucesso or max(aplicacoes, key=lambda a: int(a.get("tentativa") or 0),
                                    default=None)
            return {"aplicacao": ultima, "proposta": p, "desfecho": "sucesso",
                    "ja_aplicada": True}
        pendente = await self._tentativa_pendente(aplicacoes)
        if pendente:
            raise ConflitoDeEstado(
                f"a tentativa {pendente.get('tentativa')} está {pendente.get('desfecho')}: a "
                "chamada pode ter entrado. Verifique antes (POST /aplicacoes/{id}/"
                "verificar); reenviar poderia aplicar duas vezes.",
                codigo="verificar_antes",
                detalhe={"aplicacao_id": pendente["aplicacao_id"]})

        regra = await self.ledger.regra(p["regra_id"]) or {}
        aprovacao = await self.ledger.aprovacao_da_proposta(proposta_id)
        if not aprovacao or aprovacao.get("decisao") != "aprovada":
            # O ponto único da autonomia. Hoje `aplica_sem_humano` é sempre False
            # (T2 não existe na v10_02); ver `autonomia.py` antes de mudar.
            operacao = str(p.get("operacao") or "")
            if autonomia.aplica_sem_humano(regra, operacao):  # pragma: no cover - vazio
                raise ExigeAprovacaoHumana("autonomia declarada sem a migration v17_02")
            raise ExigeAprovacaoHumana(
                "sem aprovação humana com decisão `aprovada` não há aplicação (T1: a "
                "máquina recomenda, o humano aplica)",
                detalhe={"decisao": (aprovacao or {}).get("decisao")})
        if p.get("estado") != "aprovada":
            raise ConflitoDeEstado(f"proposta em {p.get('estado')!r}, não em 'aprovada'")

        cool = await self.ledger.cooldown_ativo(str(regra.get("chave") or ""), p["alvo_chave"])
        pode, porque = intencao.pode_aplicar(p, aprovacao, agora=self.agora(),
                                             cooldown_ate=(cool or {}).get("expira_em"))
        if not pode:
            if cool:
                raise EmCarencia(porque, detalhe={"ate": cool.get("expira_em")})
            await self._expirar_se_vencida(p)
            raise ConflitoDeEstado(porque or "não pode aplicar")

        acao = acao_da_proposta(p)
        self._exigir_trava_aberta()
        antes = await self._google(self.conta.ler_antes, customer_id, acao, conferir=False)
        divergentes = campos_divergentes(p.get("valor_atual") or {}, antes.dados)
        if divergentes:
            raise AntesDivergiu(
                "o estado da conta mudou desde a proposta: o humano aprovou um diff sobre "
                "outro 'antes'. Nada foi enviado; proponha de novo sobre o estado de agora.",
                detalhe={"campos": divergentes, "aprovado": p.get("valor_atual"),
                         "lido_agora": _canon(antes.dados)})
        try:
            acao.conferir(antes.dados)
        except AcaoRecusada as exc:
            raise AcaoInvalida(str(exc), codigo="estado_nao_permite") from exc

        tentativa = 1 + max((int(a.get("tentativa") or 0) for a in aplicacoes), default=0)
        try:
            em_voo = await self.ledger.inserir_aplicacao({
                "proposta_id": proposta_id, "aprovacao_id": aprovacao["aprovacao_id"],
                "idempotency_key": p["idempotency_key"], "tentativa": tentativa,
                "enviado_em": _iso(self.agora()), "valor_anterior": antes.dados,
            })
        except BancoRecusou as exc:
            if (exc.detalhe or {}).get("sqlstate") == "23505":
                raise ConflitoDeEstado("outra aplicação desta proposta acabou de começar",
                                       codigo="aplicacao_em_andamento") from exc
            raise
        motivo_trava = (f"gestao: proposta {proposta_id} ({acao.tipo}) aprovada por "
                        f"{aprovacao.get('decidida_por')}, executada por {executor}")
        return await self._executar(p, em_voo, acao, customer_id, motivo_trava)

    async def _fechar(self, aplicacao_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        patch = {**patch, "respondido_em": _iso(self.agora())}
        try:
            fechada = await self.ledger.fechar_aplicacao(aplicacao_id, patch)
        except ErroDeGestao as exc:
            raise Indisponivel(
                f"o desfecho ({patch.get('desfecho')}) não pôde ser gravado: {exc}. A linha "
                "ficou em_voo — verifique a conta antes de qualquer nova tentativa.",
                codigo="desfecho_nao_gravado",
                detalhe={"aplicacao_id": aplicacao_id, "desfecho": patch.get("desfecho")}) from exc
        return fechada or {"aplicacao_id": aplicacao_id, **patch}

    async def _executar(self, p: Mapping[str, Any], em_voo: Mapping[str, Any], acao: Any,
                        customer_id: str, motivo_trava: str) -> Dict[str, Any]:
        from volc_ads.gads.modo import EscritaBloqueada as Trava  # noqa: PLC0415

        aid = em_voo["aplicacao_id"]
        ensaio_resumo: Optional[Dict[str, Any]] = None
        try:
            if acao.fora_do_mutate:
                # RecommendationService não tem validate_only na v25: chamar é aplicar.
                saida = await asyncio.to_thread(self.conta.aplicar_recomendacoes,
                                                customer_id, [acao], motivo_trava)
                lote = next(iter(saida.values()))
                resultado, request_id = lote.acoes[0], lote.request_id
            else:
                ensaio = await asyncio.to_thread(self.conta.validar, customer_id, [acao])
                r_ensaio = ensaio.acoes[0]
                ensaio_resumo = {"desfecho": r_ensaio.desfecho,
                                 "erros": [e.resumo() for e in r_ensaio.erros]}
                if r_ensaio.desfecho != "ok":
                    patch = motor_ledger.desfecho_da_aplicacao(r_ensaio)
                    patch["resposta_bruta"]["fase"] = "validate_only"
                    fechada = await self._fechar(aid, patch)
                    raise GoogleRecusou(
                        "o validate_only recusou a ação; nada foi escrito na conta",
                        detalhe={"aplicacao": fechada, "validate_only": ensaio_resumo})
                ensaio2, real = await asyncio.to_thread(self.conta.aplicar, customer_id,
                                                        [acao], motivo_trava)
                if real is None:
                    # `lote.aplicar` ensaia de novo e só manda o que passou inteiro.
                    patch = motor_ledger.desfecho_da_aplicacao(ensaio2.acoes[0])
                    patch["resposta_bruta"]["fase"] = "validate_only_do_lote"
                    fechada = await self._fechar(aid, patch)
                    raise GoogleRecusou("o ensaio do lote recusou; nada foi escrito",
                                        detalhe={"aplicacao": fechada})
                resultado, request_id = real.acoes[0], real.request_id
        except Trava as exc:
            fechada = await self._fechar(aid, {
                "desfecho": "erro", "erro_codigo": "escrita_bloqueada",
                "erro_mensagem": str(exc)[:4000],
                "resposta_bruta": {"fase": "trava", "validate_only": ensaio_resumo}})
            raise EscritaBloqueada(str(exc), detalhe={"aplicacao": fechada}) from exc
        except ErroDeGestao:
            raise
        except Exception as exc:  # noqa: BLE001
            # A chamada pode ter saído. `sem_resposta` = não sabemos o que a conta tem.
            fechada = await self._fechar(aid, {
                "desfecho": "sem_resposta",
                "erro_mensagem": f"{type(exc).__name__}: {str(exc)[:1000]}",
                "resposta_bruta": {"validate_only": ensaio_resumo}})
            raise Indisponivel(
                "a escrita não devolveu resposta; a conta pode ter recebido a mudança. "
                "Verifique antes de qualquer nova tentativa.", codigo="sem_resposta",
                detalhe={"aplicacao": fechada, "proximo_passo": "verificar"}) from exc

        patch = motor_ledger.desfecho_da_aplicacao(resultado)
        patch["resposta_bruta"]["validate_only"] = ensaio_resumo
        if request_id:
            patch["request_id"] = request_id
        fechada = await self._fechar(aid, patch)
        if patch["desfecho"] != "sucesso":
            raise GoogleRecusou(
                f"o Google recusou a escrita ({resultado.desfecho}); registrado como erro",
                detalhe={"aplicacao": fechada,
                         "criados": patch["resposta_bruta"].get("criados") or []})
        nova = await self.ledger.atualizar_estado_proposta(p["proposta_id"], ["aprovada"],
                                                           "aplicada")
        return {"aplicacao": fechada, "proposta": nova or p, "desfecho": "sucesso",
                "ja_aplicada": False}

    # ── verificar ───────────────────────────────────────────────────────────

    async def _aplicacao_e_proposta(self, aplicacao_id: str) -> tuple[dict, dict]:
        ap = await self.ledger.aplicacao(aplicacao_id)
        if not ap:
            raise NaoEncontrado(f"aplicação {aplicacao_id} não existe")
        p = await self._proposta(ap["proposta_id"])
        return ap, p

    async def verificar(self, aplicacao_id: str, *, observador: str) -> Dict[str, Any]:
        ap, p = await self._aplicacao_e_proposta(aplicacao_id)
        customer_id = await self._no_escopo(customer_id_da_proposta(p))
        acao = acao_da_proposta(p)
        obs = await self._google(self.conta.ler_antes, customer_id, acao, conferir=False)
        confere, motivo = conferir_efeito(acao, obs.dados)
        acompanhamento = await self.ledger.inserir_acompanhamento({
            "aplicacao_id": aplicacao_id, "momento": "verificacao",
            "observado_em": _iso(obs.lido_em), "observado_por": f"humano:{observador}",
            "valor_observado": obs.dados, "confere": confere, "motivo": motivo,
        })
        # Aplicação órfã em voo: a verificação é quem sabe o que a conta tem.
        enviado = _quando(ap.get("enviado_em"))
        if (ap.get("desfecho") == "em_voo" and enviado is not None
                and self.agora() - enviado >= EM_VOO_ORFA_APOS):
            desfecho = "sucesso" if confere is True else "sem_resposta"
            fechada = await self.ledger.fechar_aplicacao(aplicacao_id, {
                "desfecho": desfecho, "respondido_em": _iso(self.agora()),
                "resposta_bruta": {"fechada_por": "verificacao",
                                   "acompanhamento_id": acompanhamento["acompanhamento_id"]}})
            ap = fechada or ap
        nova = None
        if confere is True and p.get("estado") == "aprovada":
            nova = await self.ledger.atualizar_estado_proposta(p["proposta_id"], ["aprovada"],
                                                               "aplicada")
        return {"acompanhamento": acompanhamento, "confere": confere, "motivo": motivo,
                "aplicacao": ap, "proposta": nova or p}

    # ── reverter ────────────────────────────────────────────────────────────

    async def reverter(self, aplicacao_id: str, *, motivo: str, autor: str,
                       acompanhamento_id: Optional[str] = None) -> Dict[str, Any]:
        motivo = (motivo or "").strip()
        if not motivo:
            raise AcaoInvalida("reversão sem motivo", codigo="sem_motivo")
        ap, p = await self._aplicacao_e_proposta(aplicacao_id)
        customer_id = await self._no_escopo(customer_id_da_proposta(p))
        ja = await self.ledger.reversao_da_aplicacao(aplicacao_id)
        if ja:
            if ja.get("desfecho") == "sucesso":
                return {"reversao": ja, "proposta": p, "ja_revertida": True}
            raise ConflitoDeEstado(
                f"esta aplicação já tem reversão ({ja.get('desfecho')}). A v10_02 admite UMA "
                "por aplicação; para desfazer de novo, proponha a ação inversa como proposta "
                "nova.", codigo="reversao_ja_existe", detalhe={"reversao": ja})
        criados = tuple((ap.get("resposta_bruta") or {}).get("criados") or ())
        if ap.get("desfecho") != "sucesso" and not (ap.get("desfecho") == "erro" and criados):
            raise ConflitoDeEstado(
                f"aplicação {ap.get('desfecho')!r} não tem o que reverter"
                + (" — verifique antes" if ap.get("desfecho") in ("em_voo", "sem_resposta")
                   else ""), codigo="nada_a_reverter")
        acao = acao_da_proposta(p)
        rev = motor_ledger.reversao(acao, ap.get("valor_anterior") or {}, criados)
        if not rev["valor_restaurado"]["reversivel"]:
            raise ConflitoDeEstado(f"irreversível: {rev['valor_restaurado']['motivo']}",
                                   codigo="irreversivel")
        self._exigir_trava_aberta()
        if ap.get("desfecho") == "sucesso":
            obs = await self._google(self.conta.ler_antes, customer_id, acao, conferir=False)
            confere, porque = conferir_efeito(acao, obs.dados)
            if confere is False:
                raise ConflitoDeEstado(
                    "a conta não está mais no estado que a aplicação deixou; reverter agora "
                    "apagaria uma mudança feita depois, sem ninguém tê-la visto.",
                    codigo="estado_mudou_depois", detalhe={"motivo": porque,
                                                           "lido_agora": _canon(obs.dados)})
        passos = list(rev["acoes"])
        ensaio = await self._google(self.conta.validar, customer_id, passos)
        if not ensaio.tudo_ok:
            raise GoogleRecusou("o validate_only recusou o reverso; nada foi gravado nem enviado",
                                detalhe={"validate_only": ensaio.resumo()})
        pendente = await self.ledger.inserir_reversao({
            "aplicacao_id": aplicacao_id, "acompanhamento_id": acompanhamento_id,
            "motivo": motivo, "acionado_por": f"humano:{autor}",
            "valor_restaurado": rev["valor_restaurado"],
        })
        return await self._executar_reversao(p, pendente, passos, customer_id,
                                             f"gestao: reverter aplicação {aplicacao_id} — {motivo}")

    async def _executar_reversao(self, p: Mapping[str, Any], pendente: Mapping[str, Any],
                                 passos: Sequence[Any], customer_id: str,
                                 motivo_trava: str) -> Dict[str, Any]:
        from volc_ads.gads.modo import EscritaBloqueada as Trava  # noqa: PLC0415

        rid = pendente["reversao_id"]
        try:
            _, real = await asyncio.to_thread(self.conta.aplicar, customer_id, passos,
                                              motivo_trava)
        except Trava as exc:
            fechada = await self.ledger.fechar_reversao(rid, {
                "desfecho": "erro", "executado_em": _iso(self.agora()),
                "erro_mensagem": f"escrita bloqueada: {exc}"[:4000]})
            raise EscritaBloqueada(str(exc), detalhe={"reversao": fechada}) from exc
        except Exception as exc:  # noqa: BLE001
            fechada = await self.ledger.fechar_reversao(rid, {
                "desfecho": "sem_resposta", "executado_em": _iso(self.agora())})
            raise Indisponivel("o reverso não devolveu resposta; verifique a conta",
                               codigo="sem_resposta", detalhe={"reversao": fechada}) from exc
        ok = real is not None and real.tudo_ok
        patch: Dict[str, Any] = {"desfecho": "sucesso" if ok else "erro",
                                 "executado_em": _iso(self.agora())}
        if real is not None and real.request_id:
            patch["request_id"] = real.request_id
        if not ok:
            patch["erro_mensagem"] = (real.resumo() if real is not None
                                      else "o ensaio do lote recusou o reverso")[:4000]
        fechada = await self.ledger.fechar_reversao(rid, patch)
        if not ok:
            raise GoogleRecusou("o Google recusou o reverso; registrado como erro",
                                detalhe={"reversao": fechada})
        nova = await self.ledger.atualizar_estado_proposta(p["proposta_id"], ["aplicada"],
                                                           "revertida")
        return {"reversao": fechada, "proposta": nova or p, "ja_revertida": False}

    # ── importar campanha externa ───────────────────────────────────────────

    async def importar_campanha_externa(self, customer_id: str, campaign_id: str, *,
                                        autor: str) -> Dict[str, Any]:
        """Identidade em `trafego_campanha` para campanha que não nasceu pelo VOLC.

        Procedência `descoberta`: a campanha foi ENCONTRADA na conta, não criada
        aqui (CHECK `trafego_campanha_procedencia_conhecida`, v9_01). A
        identidade é a MESMA derivação da varredura (`sincronizador.
        volc_campaign_id`) — uma segunda derivação cunharia uma segunda
        identidade para a mesma campanha, e o índice do par externo abortaria.
        """
        from app.trafego import sincronizador  # noqa: PLC0415

        customer_id = await self._no_escopo(customer_id)
        kid = "".join(ch for ch in str(campaign_id or "") if ch.isdigit())
        if not kid:
            raise AcaoInvalida(f"campaign_id inválido: {campaign_id!r}")
        campanha = await self._google(self.conta.ler_campanha, customer_id, kid)
        if not campanha:
            raise NaoEncontrado(f"a campanha {kid} não existe na conta {customer_id}")
        if campanha.get("status") == "REMOVED":
            raise ConflitoDeEstado(f"a campanha {kid} está REMOVED; não há o que gerir",
                                   codigo="campanha_removida")
        agora = _iso(self.agora())
        declaracao = {"procedencia": "descoberta",
                      "procedencia_declarada_por": f"humano:{autor}",
                      "procedencia_declarada_em": agora}
        existente = await self.ledger.identidade_campanha(customer_id, kid)
        if existente:
            if existente.get("procedencia") == "desconhecida":
                # A v9_01 deixa resolver `desconhecida` UMA vez — e quem importa sabe.
                linha = await self.ledger.resolver_procedencia(
                    existente["volc_campaign_id"], declaracao)
                return {"campanha": linha, "google": campanha, "ja_existia": True,
                        "procedencia_resolvida": True}
            return {"campanha": existente, "google": campanha, "ja_existia": True,
                    "procedencia_resolvida": False}
        linha = await self.ledger.declarar_identidade({
            "volc_campaign_id": sincronizador.volc_campaign_id(customer_id, kid),
            "customer_id": customer_id, "campaign_id": kid, **declaracao,
            "criada_por": f"humano:{autor}",
        })
        return {"campanha": linha, "google": campanha, "ja_existia": False,
                "procedencia_resolvida": False}

    # ── leituras ────────────────────────────────────────────────────────────

    async def recomendacoes(self, customer_id: str) -> List[Dict[str, Any]]:
        customer_id = await self._no_escopo(customer_id)
        return await self._google(self.conta.recomendacoes, customer_id)

    async def painel(self, customer_id: str, *, estado: Optional[str] = None,
                     limite: int = 50) -> List[Dict[str, Any]]:
        if estado is not None and estado not in intencao.ESTADOS_DA_PROPOSTA:
            raise AcaoInvalida(f"estado desconhecido: {estado!r}",
                               detalhe={"validos": list(intencao.ESTADOS_DA_PROPOSTA)})
        customer_id = await self._no_escopo(customer_id)
        return await self.ledger.painel(customer_id, estado=estado,
                                        limite=max(1, min(int(limite), 200)))


def _env_de_escrita() -> bool:
    """O fator de AMBIENTE da trava (`modo._ENV`). O de código é `modo.destravar`."""
    import os  # noqa: PLC0415

    return os.environ.get("FORGE_PERMITIR_ESCRITA") == "1"
