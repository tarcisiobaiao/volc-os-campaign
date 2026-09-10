from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.criativos import arquivar_asset


class Repo:
    def __init__(self):
        self.owner = str(uuid4())
        self.asset = str(uuid4())
        self.row = {"id": self.asset, "arquivado_em": None}
        self.aprovado = False

    async def buscar_master_do_dono(self, asset_id, *, criado_por):
        return self.row if asset_id == self.asset and criado_por == self.owner else None

    async def aprovacoes_vigentes_de(self, ids):
        return ({self.asset: {"decisao": "aprovado"}}
                if self.aprovado and self.asset in ids else {})

    async def arquivar_master_do_dono(self, asset_id, *, criado_por):
        if asset_id != self.asset or criado_por != self.owner or self.row["arquivado_em"]:
            return None
        self.row = {**self.row, "arquivado_em": "2026-09-08T00:00:00Z"}
        return self.row


@pytest.mark.asyncio
async def test_archive_is_owner_scoped_and_preserves_history():
    repo = Repo()
    result = await arquivar_asset(repo.asset, SimpleNamespace(sub=repo.owner), repo)
    assert result == {
        "assetId": repo.asset, "estado": "arquivado", "historicoPreservado": True,
    }
    assert repo.row["arquivado_em"] is not None

    with pytest.raises(HTTPException) as hidden:
        await arquivar_asset(repo.asset, SimpleNamespace(sub=str(uuid4())), repo)
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_approved_asset_must_be_revoked_before_archive():
    repo = Repo(); repo.aprovado = True
    with pytest.raises(HTTPException) as blocked:
        await arquivar_asset(repo.asset, SimpleNamespace(sub=repo.owner), repo)
    assert blocked.value.status_code == 409
    assert repo.row["arquivado_em"] is None
