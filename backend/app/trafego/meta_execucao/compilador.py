"""Deterministic compiler for one Meta PAUSED website-traffic recipe."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .contrato import (
    DESTINO_SHOP_CONTA_NAO_ELEGIVEL,
    DESTINO_SHOP_NAO_PROVADO,
    PLACEHOLDER_DE_DEPENDENCIA,
    ErroDeNascimentoMeta,
    ManifestoSupplyMeta,
    PlanoMetaPausado,
    ReferenciasMetaResolvidas,
    VariacaoEstaticaMeta,
)


_CAMPAIGN = "$campaign.id"
_ADSET = "$adset.id"

#: Versão do compilador que produziu o plano congelado.
#:
#: Ela viaja com o snapshot para que uma mudança futura na forma do plano seja
#: DETECTÁVEL em vez de silenciosa. Um snapshot de outra versão não é
#: descongelado por adivinhação: ele é recusado com nome próprio, e a operação
#: antiga segue pelo caminho de recuperação manual.
VERSAO_DO_COMPILADOR = "meta-compilador-v2"


def _canonico(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _materia_do_plano(
    *,
    api_version: str,
    account_ref: str,
    destination_url: str,
    shop_redirect_proof: str,
    asset_supply: list[Mapping[str, Any]],
    operacoes: Sequence["OperacaoMeta"],
) -> dict[str, Any]:
    """A matéria canônica cujo sha256 é o `plano_sha256`.

    ⚠️ Extraída para função porque agora ela tem DOIS chamadores: o compilador,
    que a monta a partir da conta lida agora, e o descongelamento, que a remonta
    a partir do snapshot para conferir integridade. Se cada um montasse a sua,
    um snapshot íntegro poderia parecer adulterado — ou, pior, o contrário.
    """
    return {
        "api_version": api_version,
        "account_ref": account_ref,
        "destination_url": destination_url,
        # O selo cobre o DESTINO, e a prova de destino é parte dele: um plano
        # aprovado com a prova em mãos não pode ser recriado sem ela.
        "shop_redirect_proof": shop_redirect_proof,
        "asset_supply": list(asset_supply),
        "operations": [
            {
                "key": op.chave,
                "type": op.tipo_objeto,
                "endpoint": op.endpoint,
                "payload": op.payload,
            }
            for op in operacoes
        ],
    }


@dataclass(frozen=True)
class OperacaoMeta:
    nome: str
    endpoint: str
    payload: Mapping[str, Any]
    depende_de: tuple[str, ...] = ()
    validavel_sem_criar_pai: bool = False
    tipo: str | None = None

    @property
    def chave(self) -> str:
        return self.nome

    @property
    def tipo_objeto(self) -> str:
        return self.tipo or self.nome.split(":", 1)[0]


@dataclass(frozen=True)
class PlanoCompiladoMeta:
    account_ref: str
    destination_url: str
    operacoes: tuple[OperacaoMeta, ...]
    plano_sha256: str
    asset_supply_manifests: tuple[ManifestoSupplyMeta, ...] = ()
    estado_ao_nascer: str = "PAUSED"
    api_version: str = "v26.0"
    #: Viaja com o plano porque o executor só recebe o plano compilado, e é ele
    #: quem precisa recusar o despacho. Entra no hash: o selo cobre o destino.
    shop_redirect_proof: str = DESTINO_SHOP_NAO_PROVADO

    @property
    def conta_externa(self) -> str:
        """Conta resolvida, derivada do endpoint. Nunca sai em resposta pública."""
        return self.operacoes[0].endpoint.split("/act_", 1)[1].split("/", 1)[0]

    @property
    def manifesto_de_passos(self) -> tuple[str, ...]:
        """A lista ordenada de passos que a aprovação durável precisa fixar.

        É o mesmo `steps_expected` de `trafego_meta_create_approval`. Derivar
        do plano compilado — em vez de montar à mão na futura rota de
        aprovação — impede que a autoridade persistente autorize um conjunto de
        passos diferente do que o operador conferiu.
        """
        return tuple(op.chave for op in self.operacoes)

    @property
    def destino_website_provado(self) -> bool:
        """Se o despacho pode acontecer sem redirecionamento não autorizado."""
        return self.shop_redirect_proof == DESTINO_SHOP_CONTA_NAO_ELEGIVEL

    def provas_de_midia_vencidas(self, agora: datetime) -> tuple[str, ...]:
        """As peças cuja atestação já não cobre um NOVO despacho.

        ⚠️ A pergunta é feita ao SNAPSHOT, não à conta de hoje, e é isso que a
        separa da recompilação que `F02` proibiu: nada é relido, nada é
        rebaixado do CDN, nenhum recibo novo é emitido, o hash não muda e nada é
        gravado. O manifesto congelado já declara até quando a atestação vale;
        despachar depois disso é criar mídia paga sob uma autorização que deixou
        de existir.

        Devolve os `asset_ref` vencidos — e não um booleano — porque num lote de
        dez variações o operador precisa saber QUAL peça reconferir.
        """
        return tuple(
            manifesto.asset_ref
            for manifesto in self.asset_supply_manifests
            if manifesto.policy_expires_at <= agora
        )

    @property
    def prova_de_midia_expira_em(self) -> datetime | None:
        """O instante em que a PRIMEIRA atestação deste plano vence.

        É o teto da autoridade de despacho: uma aprovação não pode viver mais do
        que a prova que a sustenta. `None` só acontece em snapshot sem recibo
        nenhum, e quem pergunta recusa esse caso com nome próprio.
        """
        return min(
            (item.policy_expires_at for item in self.asset_supply_manifests),
            default=None,
        )

    def publico(self) -> Mapping[str, Any]:
        return {
            "account_ref": self.account_ref,
            "destination_url": self.destination_url,
            "api_version": self.api_version,
            "plano_sha256": self.plano_sha256,
            "estado_ao_nascer": self.estado_ao_nascer,
            "shop_redirect_proof": self.shop_redirect_proof,
            "destino_website_provado": self.destino_website_provado,
            "asset_supply": [item.prova_publica() for item in self.asset_supply_manifests],
            "operacoes": [
                {
                    "nome": op.nome,
                    "chave": op.chave,
                    "tipo": op.tipo_objeto,
                    "endpoint": (
                        f"/act_<conta>/{op.endpoint.rsplit('/', 1)[-1]}"
                        if op.endpoint.startswith("/act_") else op.endpoint
                    ),
                    "depende_de": list(op.depende_de),
                    "validavel_sem_criar_pai": op.validavel_sem_criar_pai,
                    "status": op.payload.get("status"),
                }
                for op in self.operacoes
            ],
        }

    def congelar(self) -> dict[str, Any]:
        """O plano DESPACHÁVEL congelado, para o servidor guardar na aprovação.

        ## Por que ele existe

        Sem snapshot, criar e reconciliar precisavam RECOMPILAR — e recompilar
        significa abrir o Keychain, reler a conta, rebaixar os bytes da peça do
        CDN e depender da atestação de direitos ainda estar dentro da validade.
        O preço estava medido em `FINDINGS.json:F02`: a atestação vale uma hora,
        a aprovação vale quinze minutos, e um passo ambíguo ficava recuperável
        só dentro de uma janela que fecha sessenta minutos depois de um clique
        feito ANTES de aprovar. Passada a janela, a recuperação histórica era
        impossível — embora os objetos pudessem existir na conta.

        Com o snapshot, recuperar deixa de fazer perguntas sobre o presente.

        ## O que ele NÃO contém

        Token, `app_secret`, conteúdo de Keychain e URL assinada de CDN. O
        snapshot carrega identidades resolvidas do provedor (`page_id`,
        `image_hash`, endpoint com a conta) porque sem elas ele não seria
        despachável — mas essas identidades são dado sensível de operação, não
        segredo de autenticação, e por isso ele é SERVER-ONLY: projetado no
        manifesto interno, nunca no recibo que vai ao navegador.
        """
        return {
            "compiler_version": VERSAO_DO_COMPILADOR,
            "api_version": self.api_version,
            "account_ref": self.account_ref,
            "destination_url": self.destination_url,
            "shop_redirect_proof": self.shop_redirect_proof,
            "estado_ao_nascer": self.estado_ao_nascer,
            "plano_sha256": self.plano_sha256,
            "asset_supply": [item.congelado() for item in self.asset_supply_manifests],
            "operacoes": [
                {
                    "nome": op.nome,
                    "endpoint": op.endpoint,
                    "payload": op.payload,
                    "depende_de": list(op.depende_de),
                    "validavel_sem_criar_pai": op.validavel_sem_criar_pai,
                    "tipo": op.tipo_objeto,
                }
                for op in self.operacoes
            ],
        }


class SnapshotMetaInvalido(ErroDeNascimentoMeta):
    """O snapshot existe mas não pode ser usado como plano despachável."""


def descongelar_plano(materia: Mapping[str, Any]) -> PlanoCompiladoMeta:
    """Reconstrói o plano congelado e CONFERE a integridade dele.

    ⚠️ A conferência é o ponto inteiro. Um snapshot é uma autorização de gasto
    guardada num banco; se ele pudesse ser editado por fora e ainda assim
    despachar, a aprovação deixaria de descrever o que nasce. Por isso a matéria
    canônica é remontada aqui e o `plano_sha256` é RECALCULADO — não lido.

    Falhar aqui nunca é motivo para recompilar em silêncio. A recompilação
    produziria outro plano com cara do mesmo, e é exatamente o que
    `MASTER-SPEC.json` proíbe em `immutable_dispatch.migration_compatibility`.
    """
    if not isinstance(materia, Mapping) or not materia:
        raise SnapshotMetaInvalido(
            "META_PLAN_SNAPSHOT_MISSING", "esta aprovação não guarda um plano congelado")
    versao = str(materia.get("compiler_version") or "")
    if versao != VERSAO_DO_COMPILADOR:
        raise SnapshotMetaInvalido(
            "META_PLAN_SNAPSHOT_VERSION_UNSUPPORTED",
            "o plano congelado foi produzido por outra versão do compilador",
        )
    operacoes_cruas = materia.get("operacoes")
    if not isinstance(operacoes_cruas, (list, tuple)) or not operacoes_cruas:
        raise SnapshotMetaInvalido(
            "META_PLAN_SNAPSHOT_INVALID", "o plano congelado não tem operações")
    operacoes: list[OperacaoMeta] = []
    for bruta in operacoes_cruas:
        if not isinstance(bruta, Mapping):
            raise SnapshotMetaInvalido(
                "META_PLAN_SNAPSHOT_INVALID", "o plano congelado tem operação inválida")
        payload = bruta.get("payload")
        if not isinstance(payload, Mapping):
            raise SnapshotMetaInvalido(
                "META_PLAN_SNAPSHOT_INVALID", "o plano congelado tem payload inválido")
        operacoes.append(OperacaoMeta(
            nome=str(bruta.get("nome") or ""),
            endpoint=str(bruta.get("endpoint") or ""),
            payload=dict(payload),
            depende_de=tuple(str(item) for item in (bruta.get("depende_de") or ())),
            validavel_sem_criar_pai=bool(bruta.get("validavel_sem_criar_pai")),
            tipo=str(bruta.get("tipo") or "") or None,
        ))
    manifestos = tuple(
        ManifestoSupplyMeta.descongelado(item)
        for item in (materia.get("asset_supply") or ())
    )
    gravado = str(materia.get("plano_sha256") or "")
    recalculado = hashlib.sha256(_canonico(_materia_do_plano(
        api_version=str(materia.get("api_version") or ""),
        account_ref=str(materia.get("account_ref") or ""),
        destination_url=str(materia.get("destination_url") or ""),
        shop_redirect_proof=str(materia.get("shop_redirect_proof") or ""),
        asset_supply=[item.prova_publica() for item in manifestos],
        operacoes=operacoes,
    )).encode("utf-8")).hexdigest()
    if recalculado != gravado:
        raise SnapshotMetaInvalido(
            "META_PLAN_SNAPSHOT_TAMPERED",
            "o plano congelado não confere com a identidade que ele declara",
        )
    return PlanoCompiladoMeta(
        account_ref=str(materia.get("account_ref") or ""),
        destination_url=str(materia.get("destination_url") or ""),
        operacoes=tuple(operacoes),
        plano_sha256=gravado,
        asset_supply_manifests=manifestos,
        estado_ao_nascer=str(materia.get("estado_ao_nascer") or "PAUSED"),
        api_version=str(materia.get("api_version") or "v26.0"),
        shop_redirect_proof=str(materia.get("shop_redirect_proof") or DESTINO_SHOP_NAO_PROVADO),
    )


def compilar_plano_pausado(
    plano: PlanoMetaPausado,
    referencias: ReferenciasMetaResolvidas,
) -> PlanoCompiladoMeta:
    conta = referencias.account_id
    campaign = {
        "name": plano.campaign_name,
        "objective": plano.objective,
        "buying_type": "AUCTION",
        "special_ad_categories": list(plano.special_ad_categories),
        "is_adset_budget_sharing_enabled": plano.is_adset_budget_sharing_enabled,
        "status": "PAUSED",
    }
    targeting: dict[str, Any] = {
        "geo_locations": {"countries": list(plano.countries)},
        "age_min": plano.age_min,
        "age_max": plano.age_max,
        # Sem Instagram provado, o P0 não deixa a Meta escolher placements que
        # poderiam exigir outra identidade. A Page veio de /promote_pages.
        "publisher_platforms": ["facebook"],
        # A ausência deste campo não é neutra desde a v23.0: a Meta assume 1 e
        # liga o Advantage+ Audience sozinha. A escolha do operador viaja
        # sempre explícita, como 1 ou 0.
        "targeting_automation": {
            "advantage_audience": 1 if plano.advantage_audience else 0,
        },
    }
    adset = {
        "name": plano.adset_name,
        "campaign_id": _CAMPAIGN,
        "daily_budget": plano.daily_budget_minor,
        "billing_event": plano.billing_event,
        "optimization_goal": plano.optimization_goal,
        "bid_strategy": plano.bid_strategy,
        # `destination_type` não entra: para OUTCOME_TRAFFIC a tabela oficial
        # aceita apenas UNDEFINED, MESSENGER, WHATSAPP e PHONE_CALL. O campo é
        # opcional e o tráfego para site é o comportamento padrão do objetivo.
        "start_time": plano.start_time.isoformat(),
        "targeting": targeting,
        "status": "PAUSED",
    }
    operacoes_base = (
        OperacaoMeta("campaign", f"/act_{conta}/campaigns", campaign,
                     validavel_sem_criar_pai=True, tipo="campaign"),
        OperacaoMeta("adset", f"/act_{conta}/adsets", adset,
                     depende_de=("campaign",), tipo="adset"),
    )
    variacoes = plano.variacoes_estaticas or (
        VariacaoEstaticaMeta(
            variation_key="legacy",
            creative_name=plano.creative_name,
            ad_name=plano.ad_name,
            asset_ref=plano.asset_ref,
            message=plano.message,
            headline=plano.headline,
            description=plano.description,
            call_to_action_type=plano.call_to_action_type,
        ),
    )
    lote_explicito = bool(plano.variacoes_estaticas)
    operacoes_variacoes: list[OperacaoMeta] = []
    for variacao in variacoes:
        sufixo = f":{variacao.variation_key}" if lote_explicito else ""
        chave_criativo = f"creative{sufixo}"
        chave_anuncio = f"ad{sufixo}"
        story: dict[str, Any] = {
            "page_id": referencias.page_id,
            "link_data": {
                "image_hash": referencias.image_hash_for(
                    variacao.asset_ref, fallback_ref=plano.asset_ref),
                "link": plano.destination_url,
                "message": variacao.message,
                "name": variacao.headline,
                "description": variacao.description,
                "call_to_action": {
                    "type": variacao.call_to_action_type,
                    "value": {"link": plano.destination_url},
                },
            },
        }
        if referencias.instagram_actor_id is not None:
            story["instagram_actor_id"] = referencias.instagram_actor_id
        creative = {
            "name": variacao.creative_name,
            "object_story_spec": story,
            # ⚠️ NENHUM `destination_spec` É ENVIADO, e a ausência é a decisão.
            #
            # A v26 redireciona o clique de anunciantes elegíveis a Shop, e a
            # correção óbvia seria declarar o opt-out aqui. A evidência oficial
            # desta lane não sustenta esse campo: `META-SHOP` em
            # `OFFICIAL-META-API-EVIDENCE.json` está `RESEARCH_REQUIRED` /
            # `P0_BLOCKING` / `remote_behavior_proven: false` — "exact
            # writable/readable shop opt-out placement not established here" — e
            # a política de autoridade do mesmo arquivo declara todo campo
            # registrado NÃO despachável nesta missão.
            #
            # Enviar um campo que a Meta talvez não aceite faria o payload
            # aprovado divergir do payload aceito, e um enum inventado seria
            # recusado no lote — depois do despacho da campanha. O contrato
            # mestre (C01) fecha a questão: nada não provado é enviado, e a
            # incapacidade de provar bloqueia CRIAR, não compilar.
            #
            # O bloqueio mora em `shop_redirect_proof`, que viaja no plano e é
            # cobrado pelo executor antes do primeiro POST.
        }
        ad = {
            "name": variacao.ad_name,
            "adset_id": _ADSET,
            "creative": {"creative_id": f"${chave_criativo}.id"},
            "status": "PAUSED",
        }
        operacoes_variacoes.extend((
            OperacaoMeta(
                chave_criativo,
                f"/act_{conta}/adcreatives",
                creative,
                validavel_sem_criar_pai=True,
                tipo="creative",
            ),
            OperacaoMeta(
                chave_anuncio,
                f"/act_{conta}/ads",
                ad,
                depende_de=("adset", chave_criativo),
                tipo="ad",
            ),
        ))
    operacoes = operacoes_base + tuple(operacoes_variacoes)
    manifestos = tuple(
        referencias.manifesto_for(ref)
        for ref in dict.fromkeys(item.asset_ref for item in variacoes)
    )
    materia = _materia_do_plano(
        api_version="v26.0",
        account_ref=plano.account_ref,
        destination_url=plano.destination_url,
        shop_redirect_proof=referencias.shop_redirect_proof,
        asset_supply=[item.prova_publica() for item in manifestos],
        operacoes=operacoes,
    )
    return PlanoCompiladoMeta(
        account_ref=plano.account_ref,
        destination_url=plano.destination_url,
        operacoes=operacoes,
        asset_supply_manifests=manifestos,
        shop_redirect_proof=referencias.shop_redirect_proof,
        plano_sha256=hashlib.sha256(_canonico(materia).encode("utf-8")).hexdigest(),
    )


# Os únicos lugares estruturais onde o compilador escreve um marcador. Resolver
# apenas aqui impede que um texto do operador com a mesma sintaxe — um nome de
# conjunto igual a "$campaign.id", por exemplo — seja trocado por um ID real
# depois de o plano já ter sido aprovado e hasheado.
CAMINHOS_DE_DEPENDENCIA: tuple[tuple[str, ...], ...] = (
    ("campaign_id",),
    ("adset_id",),
    ("creative", "creative_id"),
)


def _copia_simples(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return {str(chave): _copia_simples(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_copia_simples(item) for item in valor]
    return valor


def _exigir_sem_marcador(valor: Any) -> None:
    if isinstance(valor, str):
        if PLACEHOLDER_DE_DEPENDENCIA.fullmatch(valor):
            raise ErroDeNascimentoMeta(
                "META_UNRESOLVED_DEPENDENCY",
                "o payload ainda contém um marcador de dependência não resolvido",
            )
        return
    if isinstance(valor, Mapping):
        for item in valor.values():
            _exigir_sem_marcador(item)
        return
    if isinstance(valor, (list, tuple)):
        for item in valor:
            _exigir_sem_marcador(item)


def resolver_dependencias(payload: Mapping[str, Any], ids: Mapping[str, str]) -> dict[str, Any]:
    """Resolve compiler-owned placeholders at their structural paths only."""
    saida = _copia_simples(payload)
    for caminho in CAMINHOS_DE_DEPENDENCIA:
        alvo: Any = saida
        for chave in caminho[:-1]:
            alvo = alvo.get(chave) if isinstance(alvo, dict) else None
        if not isinstance(alvo, dict):
            continue
        folha = caminho[-1]
        bruto = alvo.get(folha)
        if not isinstance(bruto, str) or not PLACEHOLDER_DE_DEPENDENCIA.fullmatch(bruto):
            continue
        referencia = bruto[1:-3]
        if referencia not in ids:
            raise KeyError(referencia)
        alvo[folha] = ids[referencia]
    _exigir_sem_marcador(saida)
    return saida
