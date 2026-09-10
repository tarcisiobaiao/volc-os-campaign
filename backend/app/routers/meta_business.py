"""ADMIN-only credential management. Never return secrets or provider error bodies."""
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, SecretStr, ConfigDict
from app.seguranca.identidade import exigir_admin, Identidade
from app.seguranca.segredo import cofre_configurado, CofreSemChave
from app.trafego.meta import business_credentials as store

class SecretSafeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                # FastAPI's default validation response echoes input, including tokens.
                raise HTTPException(422, "Confira os campos da conexão. O token não foi salvo.") from None
        return handler


router = APIRouter(prefix="/api/trafego/meta/business", tags=["meta-business"], route_class=SecretSafeRoute)
GRAPH = "https://graph.facebook.com/v26.0"


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    business_id: str = Field(pattern=r"^[0-9]{5,30}$")
    name: str = Field(min_length=1, max_length=120)
    token: SecretStr = Field(min_length=20, max_length=4096)


async def repo_dependency(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        yield store.repository()
    except httpx.HTTPError:
        raise HTTPException(503, "Não foi possível acessar o cofre oficial. Tente novamente.") from None


async def verify(token: str, business: str):
    """Prove /me belongs to Business system_users; permission errors never pass."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        async def get(path, params):
            try:
                res = await client.get(f"{GRAPH}/{path}", params=params, headers={"Authorization": f"Bearer {token}"})
                res.raise_for_status()
                data = res.json()
                if not isinstance(data, dict) or "error" in data:
                    raise ValueError()
                return data
            except (httpx.HTTPError, ValueError):
                raise HTTPException(422, "A Meta não confirmou o acesso. Confira o token, o Business ID e a permissão business_management.") from None
        actor = await get("me", {"fields": "id"})
        after = None
        for _ in range(20):
            page = await get(f"{business}/system_users", {"fields": "id", "limit": 100, **({"after": after} if after else {})})
            if not isinstance(page.get("data"), list):
                raise HTTPException(422, "A Meta retornou uma lista incompleta de usuários de sistema.")
            if actor.get("id") and any(x.get("id") == actor["id"] for x in page.get("data", []) if isinstance(x, dict)):
                return
            paging = page.get("paging") or {}
            if not isinstance(paging, dict):
                raise HTTPException(422, "A Meta retornou uma paginação inválida.")
            if not paging.get("next"):
                break
            cursor = (paging.get("cursors") or {}).get("after")
            if not cursor or cursor == after:
                break
            after = cursor
        raise HTTPException(422, "Não foi possível comprovar que este é um usuário de sistema desse Business Manager.")


@router.get("")
async def listing(quem: Identidade = Depends(exigir_admin), repo=Depends(repo_dependency)):
    rows = await repo.select(store.TABLE, {"select": store.PUBLIC_COLUMNS, "owner_id": f"eq.{quem.sub}", "order": "name.asc,id.asc", "limit": 101})
    selected = await repo.select(store.SELECTION, {"select": "credential_id", "owner_id": f"eq.{quem.sub}", "limit": 1})
    # Explicit whitelist even if a repository implementation returns extra data.
    return {"connections": [{key: row.get(key) for key in store.PUBLIC_COLUMNS.split(",")} for row in rows[:100]],
            "truncated": len(rows) > 100, "selected_id": selected[0]["credential_id"] if selected else None,
            "vault_ready": cofre_configurado(), "sync_mode": "ON_DEMAND"}


@router.post("")
async def register(body: Register, quem: Identidade = Depends(exigir_admin), repo=Depends(repo_dependency)):
    if not cofre_configurado():
        raise HTTPException(503, "A chave de criptografia precisa ser configurada no servidor.")
    token = body.token.get_secret_value()
    if any(c.isspace() for c in token) or not body.name.strip():
        raise HTTPException(422, "Informe um nome e um token sem espaços.")
    await verify(token, body.business_id)
    try:
        ciphertext = store.seal(quem.sub, body.business_id, token)
    except CofreSemChave:
        raise HTTPException(503, "A chave de criptografia não está disponível.") from None
    await store.upsert(repo, store.TABLE, "owner_id,business_id", {
        "owner_id": quem.sub, "business_id": body.business_id, "name": body.name.strip(),
        "ciphertext": ciphertext, "enabled": True, "verified_at": store.now(), "updated_at": store.now()})
    return {"saved": True, "selected": False}


@router.post("/{connection}/select")
async def select(connection: UUID, quem: Identidade = Depends(exigir_admin), repo=Depends(repo_dependency)):
    row = await store.owned(repo, quem.sub, str(connection))
    token = store.unseal(row, quem.sub)
    await verify(token, row["business_id"])
    await store.upsert(repo, store.SELECTION, "owner_id", {"owner_id": quem.sub, "credential_id": str(connection), "updated_at": store.now()})
    return {"selected": True}


@router.post("/{connection}/disable")
async def disable(connection: UUID, quem: Identidade = Depends(exigir_admin), repo=Depends(repo_dependency)):
    await store.owned(repo, quem.sub, str(connection))
    await repo.patch(store.TABLE, {"owner_id": f"eq.{quem.sub}", "id": f"eq.{connection}"}, {"enabled": False, "updated_at": store.now()})
    return {"disabled": True}
