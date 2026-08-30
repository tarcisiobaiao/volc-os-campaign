"""
Runtime configuration for the Pautador Pro backend.

Everything is env-driven. The backend is designed to run with ZERO secrets
(it falls back to a deterministic mock LLM and an in-memory store), so it
boots locally and on Vercel even before real keys exist.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- LLM engine selection -------------------------------------------------
    # "auto"   -> use the first provider that has a key, else "mock"
    # "mock"   -> deterministic generator (no network, always available)
    # "gemini" | "openai"
    pautador_engine: str = "auto"

    # Google Gemini (primary, mirrors the n8n prototype)
    gemini_api_key: Optional[str] = None

    # ── Estúdio Criativo ────────────────────────────────────────────────────
    #
    # ⚠️ Estas quatro moram aqui, e não em `os.environ`, e isso é conserto de um
    # defeito medido em 28/08/2026.
    #
    # `pydantic-settings` lê `.env` e **não popula `os.environ`**, e não há
    # `load_dotenv` em lugar nenhum do backend. O Estúdio lia as suas variáveis
    # direto do ambiente do processo, então, seguindo a documentação da casa
    # (`backend/.env.example` -> `backend/.env`, `./start-dev.sh`), 11 das 15
    # rotas respondiam 503 "o servidor está sem chave de assinatura" com a chave
    # presente no arquivo. Na Vercel os dois canais coincidem, então o defeito só
    # aparecia no ambiente que a documentação manda montar.
    criativo_url_secret: Optional[str] = None
    criativo_storage_dir: Optional[str] = None
    volc_factory_raiz: Optional[str] = None
    google_api_key: Optional[str] = None  # alias accepted
    pautador_gemini_model: str = "gemini-2.0-flash"
    # Cap on Gemini output tokens. None = omit (model uses its own outputTokenLimit,
    # e.g. 65536 for gemini-3.x flash). Set a number only to force a smaller cap.
    pautador_gemini_max_output_tokens: Optional[int] = None

    # Perplexity (the mandated external grounding tool — Sonar Pro)
    perplexity_api_key: Optional[str] = None
    pautador_perplexity_model: str = "sonar-pro"
    pautador_grounding_enabled: bool = True

    # OpenAI (optional alternative discovery/funnel engine)
    openai_api_key: Optional[str] = None
    pautador_openai_model: str = "gpt-4o-mini"

    # ---- KW Mining (Fase 2) / Funnel Builder (Fase 3) -------------------------
    # Per-operation Gemini models (mirror the n8n workflows, which used
    # models/gemini-3.1-pro-preview for kw research + funnel architecture).
    # The "models/" prefix is tolerated and stripped by GeminiClient.
    pautador_kw_gemini_model: str = "models/gemini-3.1-pro-preview"
    pautador_funnel_gemini_model: str = "models/gemini-3.1-pro-preview"
    # Entity Funil (Fase 3) — usa o agente ARQUITETO do FUNNEL.json ipsis litteris,
    # com gemini-3.5-flash (modelo do export). Roda no worker Python interno.
    pautador_entity_funnel_model: str = "models/gemini-3.5-flash"

    # KW Mining via n8n: quando setado, o botão "Minerar" dispara um WEBHOOK para
    # este n8n (flow webhook->Supabase). Vazio = minerador interno (mock/gemini).
    pautador_n8n_kw_webhook_url: Optional[str] = None

    # URL pública deste backend, para o comentário do ClickUp linkar o briefing.
    # VAZIA por padrão, e isso é comportamento definido, não pendência: sem ela
    # o comentário diz ONDE achar no sistema em vez de mandar um link quebrado.
    # Meia informação certa vale mais que um link que erra.
    public_base_url: Optional[str] = None

    # DataForSEO (Google Autocomplete + Related Keywords Labs) — Basic auth.
    # MIGRATED from a hardcoded Authorization header in the n8n JSON; keep EMPTY
    # here and fill in .env (never commit). Empty => mining uses the honest mock.
    dataforseo_login: Optional[str] = None
    dataforseo_password: Optional[str] = None

    # Google Ads Keyword Planner (generateKeywordIdeas). Two auth modes:
    #   "service_account"     -> JWT (RS256) signed with the SA private key
    #   "oauth_refresh_token" -> OAuth2 refresh-token flow (the original n8n path)
    #   "auto" (default)      -> service_account if SA present, else oauth refresh
    # MIGRATED from hardcoded mcc_id/customer_id/developer_token in the n8n JSON.
    google_ads_auth_mode: str = "auto"
    google_ads_developer_token: Optional[str] = None
    google_ads_login_customer_id: Optional[str] = None  # MCC id (required, both modes)
    google_ads_customer_id: Optional[str] = None        # target account (required, both modes)
    # -- oauth_refresh_token mode --
    google_ads_client_id: Optional[str] = None
    google_ads_client_secret: Optional[str] = None
    google_ads_refresh_token: Optional[str] = None
    # -- service_account mode (inline JSON OR a path to the key file) --
    google_ads_service_account_json: Optional[str] = None
    google_ads_json_key_file_path: Optional[str] = None
    google_ads_impersonated_email: Optional[str] = None  # optional: domain-wide delegation subject

    # KW mining engine: "auto" => use real Google Ads/DataForSEO when fully
    # configured, else fall back to the deterministic mock. "mock" forces mock.
    # "live" requires real creds (errors clearly if missing).
    pautador_kw_engine: str = "auto"
    pautador_kw_max_loops: int = 5
    pautador_kw_min_volume_gold: int = 10

    # ---- Supabase (service-role; server-side ONLY, never shipped to client) ---
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    # ---- cofre de credenciais de terceiros -----------------------------------
    # Chave Fernet que cifra o Application Password do WordPress de cada projeto
    # (ver app/seguranca/segredo.py). Fica AQUI e não só em os.environ porque o
    # pydantic-settings carrega o .env para este objeto, não para o ambiente do
    # processo — foi exatamente essa a pegadinha que fez o cofre nascer "não
    # configurado" com a chave já gravada no backend/.env.
    volc_segredo_key: Optional[str] = None

    # ---- ClickUp (entrega do briefing ao mover o card p/ "Pronto") ------------
    # Ao mover um card para "Pronto", o backend gera o DOCX do funil e abre uma
    # TASK no ClickUp (nome "Entidade - País"), anexa o DOCX e comenta.
    #   clickup_api_token   -> token pessoal (pk_...). Header Authorization (sem Bearer).
    #   clickup_list_id     -> ID da LISTA onde a task é criada (a task nasce numa LISTA,
    #                          não num Space; a lista vive em Space > (Folder) > Lista).
    #   clickup_task_status -> status inicial (ex.: "pendente"); precisa EXISTIR na lista.
    #                          Vazio => usa o status default da lista.
    # Server-side ONLY — nunca vai pro frontend.
    clickup_api_token: Optional[str] = None
    clickup_list_id: Optional[str] = None
    clickup_task_status: Optional[str] = None

    # ---- HTTP / CORS / auth ---------------------------------------------------
    pautador_allowed_origins: str = "*"
    request_timeout_seconds: float = 120.0
    # Geração de LLM não é chamada de API comum: a descoberta de 20 entidades leva
    # ~81s medidos (30k tokens de saída + "pensamento"), e o teto de 120s deixava
    # margem quase nula — um dia mais lento estourava e a run inteira caía no
    # fallback mock, com erro VAZIO (assinatura de ReadTimeout do httpx).
    llm_timeout_seconds: float = 420.0
    # Optional shared secret. When set, mutating/compute endpoints require the
    # header `X-API-Key: <this>`. Left empty in dev/mock so it boots open.
    pautador_api_key: Optional[str] = None

    # Credencial de SERVIÇO (n8n, cron, integrações internas). Separada da
    # sessão do navegador de propósito: `pautador_api_key` foi exposta ao bundle
    # via VITE_PAUTADOR_API_KEY e por isso deixou de ser segredo. Esta NUNCA
    # ganha equivalente VITE_*. Ver app/seguranca/identidade.py.
    volc_service_key: Optional[str] = None

    # ---- Behaviour ------------------------------------------------------------
    pautador_persist_default: bool = True  # persist to Supabase when creds exist
    pautador_default_count: int = 40

    # --- derived helpers -------------------------------------------------------
    @property
    def resolved_gemini_key(self) -> Optional[str]:
        return self.gemini_api_key or self.google_api_key

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def has_dataforseo(self) -> bool:
        return bool(self.dataforseo_login and self.dataforseo_password)

    @property
    def has_clickup(self) -> bool:
        return bool(self.clickup_api_token and self.clickup_list_id)

    def google_ads_auth_status(self) -> dict:
        """Readiness of Google Ads auth, WITHOUT exposing any secret values.

        Returns {mode, ready, missing[]}. `mode` is the resolved auth mode
        (service_account | oauth_refresh_token | none); `missing` lists the
        env keys still needed for that mode.
        """
        common = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": bool(self.google_ads_developer_token),
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": bool(self.google_ads_login_customer_id),
            "GOOGLE_ADS_CUSTOMER_ID": bool(self.google_ads_customer_id),
        }
        has_sa = bool(self.google_ads_service_account_json or self.google_ads_json_key_file_path)
        has_oauth = bool(
            self.google_ads_client_id and self.google_ads_client_secret and self.google_ads_refresh_token
        )

        requested = (self.google_ads_auth_mode or "auto").lower()
        if requested not in ("service_account", "oauth_refresh_token", "auto"):
            requested = "auto"
        if requested == "auto":
            mode = "service_account" if has_sa else "oauth_refresh_token" if has_oauth else "none"
        else:
            mode = requested

        missing = [k for k, ok in common.items() if not ok]
        if mode == "service_account":
            if not has_sa:
                missing.append("GOOGLE_ADS_SERVICE_ACCOUNT_JSON ou GOOGLE_ADS_JSON_KEY_FILE_PATH")
        elif mode == "oauth_refresh_token":
            for key, ok in (
                ("GOOGLE_ADS_CLIENT_ID", bool(self.google_ads_client_id)),
                ("GOOGLE_ADS_CLIENT_SECRET", bool(self.google_ads_client_secret)),
                ("GOOGLE_ADS_REFRESH_TOKEN", bool(self.google_ads_refresh_token)),
            ):
                if not ok:
                    missing.append(key)
        else:  # none
            missing.append("GOOGLE_ADS_SERVICE_ACCOUNT_JSON/JSON_KEY_FILE_PATH ou CLIENT_ID+SECRET+REFRESH_TOKEN")

        ready = mode in ("service_account", "oauth_refresh_token") and not missing
        return {"mode": mode, "ready": ready, "missing": missing}

    @property
    def has_google_ads(self) -> bool:
        return self.google_ads_auth_status()["ready"]

    def resolve_kw_engine(self) -> str:
        """Decide the KW mining data source: 'live' (real Google Ads/DataForSEO)
        or 'mock' (deterministic). 'auto' picks live only when fully configured."""
        engine = (self.pautador_kw_engine or "auto").lower()
        if engine == "mock":
            return "mock"
        if engine == "live":
            return "live"
        # auto
        return "live" if (self.has_google_ads or self.has_dataforseo) else "mock"

    @property
    def allowed_origins(self) -> List[str]:
        raw = (self.pautador_allowed_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def resolve_engine(self) -> str:
        """Decide which LLM engine to actually use for discovery."""
        engine = (self.pautador_engine or "auto").lower()
        if engine == "auto":
            if self.resolved_gemini_key:
                return "gemini"
            if self.openai_api_key:
                return "openai"
            return "mock"
        return engine


@lru_cache
def get_settings() -> Settings:
    return Settings()
