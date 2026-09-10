"""Owner-scoped editable intent. Saved drafts never carry launch authority."""
from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.config import get_settings
from app.services.supabase_service import SupabaseService

Short = Annotated[str, StringConstraints(max_length=180)]
Text = Annotated[str, StringConstraints(max_length=2200)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")]
Ref = Annotated[str, StringConstraints(pattern=r"^(?:|[A-Za-z][A-Za-z0-9:_-]{7,179})$")]
Refs = Annotated[list[Ref], Field(max_length=100)]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Point(Closed):
    latitude: Short
    longitude: Short
    raio: Short
    unidade: Literal["kilometer", "mile"]


class Place(Closed):
    key: Short
    nome: Short
    tipo: Literal["region", "city", "zip", "country"]
    excluido: bool


class Geography(Closed):
    paisesTexto: Short
    exclusoesTexto: Short
    pontos: list[Point] = Field(max_length=50)
    lugares: list[Place] = Field(max_length=300)


class Audience(Closed):
    modo: Literal["BROAD", "MANUAL", "EXISTING_CUSTOM", "EXISTING_LOOKALIKE"]
    geo: Geography
    idadeMin: int = Field(ge=13,le=65)
    idadeMax: int = Field(ge=13,le=65)
    incluirRefs: Refs
    excluirRefs: Refs
    lookalikeRefs: Refs
    interesseRefs: Refs
    localeRefs: Refs
    expansao: bool


class Measurement(Closed):
    proposito: Literal["REPORT_ONLY", "OPTIMIZE"]
    fonteTipo: Literal["", "PIXEL", "DATASET"]
    fonteRef: Ref
    conversaoRef: Ref
    eventoPadrao: Short


class FlexibleTextsDraft(Closed):
    # Autosave admite edição incompleta. Compilar cobra min1 e texto não vazio.
    primary_text: list[Text] = Field(max_length=5)
    headline: list[Annotated[str, StringConstraints(max_length=255)]] = Field(max_length=5)
    description: list[Annotated[str, StringConstraints(max_length=255)]] = Field(default_factory=list, max_length=5)


class Adset(Closed):
    flexibleTexts: FlexibleTextsDraft | None = None
    regulatoryIdentityRef: Annotated[str, StringConstraints(pattern=r"^metareg_[a-f0-9]{32}$")] | None = None
    key: Key
    nome: Annotated[str,StringConstraints(max_length=400)]
    startTime: Short
    endTime: Short
    orcamentoBrl: Short
    publico: Audience
    posicionamentoModo: Literal["FACEBOOK_ONLY", "MANUAL"]
    posicionamentoValores: list[Short] = Field(max_length=10)
    mensuracao: Measurement

    @field_validator('regulatoryIdentityRef', mode='before')
    @classmethod
    def empty_regulatory_selection(cls, value):
        # The browser's empty option clears an existing selection. Persisted
        # intent omits None; the database never stores an empty/raw identity.
        return None if value == '' else value


class PackOrigin(Closed):
    packId: Annotated[str,StringConstraints(pattern=r"^[0-9a-fA-F-]{36}$")]
    manifestHash: Annotated[str,StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    masterRef: Annotated[str,StringConstraints(pattern=r"^[0-9a-fA-F-]{36}$")]
    accountRef: Ref
    selectionVersion: int = Field(ge=1,le=2147483647)


class Variation(Closed):
    packOrigin: PackOrigin | None = None
    existingPostRef: Annotated[str, StringConstraints(pattern=r"^metapost_[a-f0-9]{32}$")] | None = None
    key: Key
    adsetKey: Key
    midia: Literal["image", "video"]
    assetRef: Ref
    videoRef: Ref
    creativeName: Annotated[str,StringConstraints(max_length=400)]
    adName: Annotated[str,StringConstraints(max_length=400)]
    message: Text
    headline: Annotated[str,StringConstraints(max_length=255)]
    description: Annotated[str,StringConstraints(max_length=255)]
    cta: Annotated[str,StringConstraints(max_length=40)]
    assetRightsConfirmed: bool
    thirdPartyIdentityCleared: bool
    assetPolicyConfirmedAt: Short


class NamingDraft(Closed):
    enabled: bool
    topic: Annotated[str, StringConstraints(max_length=200)]
    site: Annotated[str, StringConstraints(max_length=80)]
    landingType: Annotated[str, StringConstraints(max_length=40)]
    quiz: bool
    conversionLabel: Annotated[str, StringConstraints(max_length=80)]
    topicSourceUrl: Annotated[str, StringConstraints(max_length=2000)] | None = None
    campaignNumber: Annotated[int, Field(ge=1, le=2147483647)] | None = None
    accountRef: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9:_-]{7,179}$")] | None = None
    adsetNumbers: dict[Key, Annotated[int, Field(ge=1, le=2147483647)]] = Field(max_length=100)
    adNumbers: dict[Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9:_-]{0,64}$")], Annotated[int, Field(ge=1, le=2147483647)]] = Field(max_length=100)
    generated: dict[Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9:_-]{1,80}$")],
                    Annotated[str, StringConstraints(max_length=400)]] = Field(max_length=100)


class CampaignDraft(Closed):
    naming: NamingDraft | None = None
    recipeId: Short
    accountRef: Ref
    pageRef: Ref
    instagramActorRef: Ref
    campaignName: Annotated[str,StringConstraints(max_length=400)]
    destinationUrl: Annotated[str,StringConstraints(max_length=2000)]
    nivelDeOrcamento: Literal["ADSET", "CAMPAIGN"]
    periodoDeOrcamento: Literal["DAILY", "LIFETIME"]
    budgetBrl: Short
    categoryConfirmed: bool
    creativeMode: Literal["single", "batch", "flexible"]
    conjuntos: list[Adset] = Field(min_length=1,max_length=10)
    variations: list[Variation] = Field(max_length=10)

    @model_validator(mode="before")
    @classmethod
    def no_credentials(cls,value):
        raw=json.dumps(value,ensure_ascii=False,default=str)
        if len(raw.encode()) > 120000:
            raise ValueError("rascunho muito grande")
        # Known credential forms are refused even when pasted in copy or URL.
        if re.search(r"(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|EAA[A-Za-z0-9]{40,}|Bearer\s+[A-Za-z0-9._-]{12,}|eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|access_token=)",raw,re.I):
            raise ValueError("credenciais não pertencem ao rascunho")
        return value

    @model_validator(mode="after")
    def stable_links(self):
        keys=[item.key for item in self.conjuntos]
        variations=[item.key for item in self.variations]
        if len(keys)!=len(set(keys)) or len(variations)!=len(set(variations)):
            raise ValueError("identidades duplicadas no rascunho")
        if any(item.adsetKey not in keys for item in self.variations):
            raise ValueError("um anúncio aponta para conjunto inexistente")
        if any(item.packOrigin and item.packOrigin.accountRef != self.accountRef for item in self.variations):
            raise ValueError("a procedência de uma peça pertence a outra conta")
        return self

    def persisted(self) -> dict[str,Any]:
        result=self.model_dump(mode="json",exclude_none=True)
        result["categoryConfirmed"]=False
        for ad in result["variations"]:
            ad.update(assetRightsConfirmed=False,thirdPartyIdentityCleared=False,assetPolicyConfirmedAt="")
        return result


class SaveDraft(Closed):
    expected_version: int = Field(ge=0,le=2147483646)
    draft: CampaignDraft


class ArchiveDraft(Closed):
    expected_version: int = Field(ge=1, le=2147483646)


class DraftStorage:
    def __init__(self, service=None):
        self.service=service or SupabaseService(get_settings())

    async def list(self, owner: str, offset: int = 0):
        # The privileged transport MUST always filter by the authenticated owner.
        rows = await self.service.rpc("trafego_meta_campaign_draft_list", {
            "p_owner_id": owner, "p_offset": offset,
        })
        items = []
        for row in rows[:20]:
            items.append({"draft_ref": str(UUID(row["draft_ref"])), "version": row["version"],
                "updated_at": row["updated_at"], "campaign_name": row["campaign_name"],
                "adset_count": row["adset_count"], "ad_count": row["ad_count"]})
        more = len(rows) > 20
        return {"items": items, "has_more": more, "next_offset": offset + 20 if more else None,
                "scope": "DRAFT_ONLY", "launch_authorized": False}

    async def read(self, owner:str, draft_ref:UUID):
        return await self.service.rpc("trafego_meta_campaign_draft_read",{"p_owner_id":owner,"p_draft_ref":str(draft_ref)})

    async def archive(self, owner:str, draft_ref:UUID, version:int):
        return await self.service.rpc('trafego_meta_campaign_draft_archive', {
            'p_owner_id':owner,'p_draft_ref':str(draft_ref),'p_expected_version':version})

    async def save(self, owner:str, draft_ref:UUID, request:SaveDraft):
        return await self.service.rpc("trafego_meta_campaign_draft_save",{
            "p_owner_id":owner,"p_draft_ref":str(draft_ref),"p_expected_version":request.expected_version,
            "p_draft":request.draft.persisted()})
