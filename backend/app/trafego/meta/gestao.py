"""Read-model-backed management proposals. This module has no Meta transport.

Proposals are not approvals, mutations or replayable executor payloads. They
keep missing before-values visible until a governed management executor exists.
"""
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PedidoDeGestaoMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conta_ref: str = Field(pattern=r"^[A-Za-z0-9:_-]{8,180}$")
    campanha_ref: str = Field(pattern=r"^[A-Za-z0-9:_-]{8,180}$")
    entidade: Literal["campanha", "conjunto"]
    referencia: str = Field(pattern=r"^[A-Za-z0-9:_-]{8,180}$")
    acao: Literal["PAUSAR", "ORCAMENTO_DIARIO", "LANCE", "DUPLICAR_CONJUNTO"]
    valor_minor: int | None = Field(default=None, strict=True, gt=0, le=100_000_000)
    estrategia: Literal["LOWEST_COST_WITHOUT_CAP", "COST_CAP", "LOWEST_COST_WITH_BID_CAP"] | None = None
    nome: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def conferir(self):
        if self.acao == "DUPLICAR_CONJUNTO":
            if self.entidade != "conjunto" or not (self.nome or "").strip():
                raise ValueError("Escolha um conjunto e dê um nome à cópia.")
        elif self.nome is not None:
            raise ValueError("Nome só pertence à proposta de duplicação.")
        if self.acao == "ORCAMENTO_DIARIO" and self.valor_minor is None:
            raise ValueError("Informe o orçamento diário em centavos.")
        if self.acao == "LANCE":
            if self.estrategia is None:
                raise ValueError("Escolha a estratégia de lance.")
            if (self.estrategia != "LOWEST_COST_WITHOUT_CAP") != (self.valor_minor is not None):
                raise ValueError("Estratégia com limite exige valor; sem limite não admite valor.")
        elif self.estrategia is not None:
            raise ValueError("Estratégia só pertence à proposta de lance.")
        if self.acao in {"PAUSAR", "DUPLICAR_CONJUNTO"} and self.valor_minor is not None:
            raise ValueError("Esta proposta não recebe valor de lance ou orçamento.")
        return self


async def planejar_gestao(repo, pedido: PedidoDeGestaoMeta, *, ator: str) -> dict:
    campanha = await repo.detalhe("campanhas", pedido.campanha_ref, pedido.conta_ref)
    pai = campanha.get("item") if campanha.get("estado") == "COM_SNAPSHOT" else None
    if not pai:
        raise ValueError("Campanha não encontrada nesta conta. Atualize a leitura antes de preparar a alteração.")
    if pedido.entidade == "campanha":
        if pedido.referencia not in {pedido.campanha_ref, pai.get("entity_ref"), pai.get("meta_campaign_id")}:
            raise ValueError("A proposta precisa pertencer à campanha aberta.")
        item = pai
    else:
        detalhe = await repo.detalhe("conjuntos", pedido.referencia, pedido.conta_ref)
        item = detalhe.get("item") if detalhe.get("estado") == "COM_SNAPSHOT" else None
        if not item or not pai.get("meta_campaign_id") or item.get("meta_campaign_id") != pai["meta_campaign_id"]:
            raise ValueError("Conjunto não encontrado nesta campanha e conta.")
    if item.get("status") in {"DELETED", "ARCHIVED"}:
        raise ValueError("Objetos removidos ou arquivados não aceitam proposta nesta bancada.")

    # Explicit projection, never echo the repository's entire record.
    antes = {k: item.get(k) for k in ("status", "daily_budget", "lifetime_budget", "bid_strategy", "bid_amount")}
    requisitos = [
        "Reler na Meta o objeto e sua hierarquia antes de autorizar.",
        "Vincular aprovação ao estado anterior, conta, escopo e hash do plano.",
        "Executor de gestão com recibo durável e read-back ainda não disponível.",
    ]
    if pedido.acao == "PAUSAR":
        depois = {"status": "PAUSED"}
        efeito = "Interromper a entrega deste escopo; receita histórica permanece atribuída."
        if item.get("status") == "PAUSED":
            raise ValueError("O estado configurado já é PAUSED na leitura disponível.")
    elif pedido.acao == "ORCAMENTO_DIARIO":
        depois = {"daily_budget_minor": pedido.valor_minor, "moeda_proposta": "BRL"}
        efeito = "Alterar a verba diária disponível para este escopo."
        requisitos.append("Confirmar moeda, limites e dono do orçamento: campanha em CBO, conjunto em ABO. Orçamento vitalício exige outro plano.")
    elif pedido.acao == "LANCE":
        depois = {"bid_strategy": pedido.estrategia, "bid_amount_minor": pedido.valor_minor}
        if pedido.valor_minor is not None:
            depois["moeda_proposta"] = "BRL"
        efeito = "Alterar a estratégia de entrega; pode afetar aprendizado e gasto."
        requisitos.append("Validar moeda da conta, estratégia, objetivo, otimização e dono do lance antes de compilar payload Meta.")
    else:
        depois = {"nome": pedido.nome.strip(), "status": "PAUSED", "incluir_anuncios": True}
        efeito = "Criar um novo conjunto e cópias de seus anúncios, todos pausados, na mesma campanha."
        requisitos.extend([
            "Reler todos os anúncios e criativos, com paginação completa e sem copiar IDs antigos.",
            "Recompilar url_tags por conjunto. O novo ID terá receita própria; não transferir histórico da origem.",
            "Em timeout após despacho, manter ambíguo sem repetir criação automaticamente.",
        ])
    material = {
        "versao": "meta-gestao-proposta-v1", "pedido": pedido.model_dump(),
        "ator": ator, "antes": antes, "depois": depois,
        "observado_em": item.get("observado_em"),
    }
    return {
        "estado": "PROPOSTA_LOCAL_NAO_EXECUTAVEL", "efeito_externo": "NENHUM",
        "executavel": False, "persistida": False,
        "plano_sha256": hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "acao": pedido.acao, "entidade": pedido.entidade, "referencia": pedido.referencia,
        "nome": item.get("nome"), "observado_em": item.get("observado_em"),
        "antes": antes, "depois": depois, "efeito_proposto": efeito,
        "requisitos_para_executar": requisitos,
        "receita": "GAM por adset_id; campanha soma conjuntos. Histórico não é reatribuído por edição ou cópia.",
    }
