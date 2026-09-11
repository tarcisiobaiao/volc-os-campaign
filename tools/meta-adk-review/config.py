"""Immutable model and lane configuration for the Meta ADK review."""
from __future__ import annotations

from dataclasses import dataclass

MODEL = "gemini-3.8-flash"
THINKING = "HIGH"


@dataclass(frozen=True)
class Lane:
    slug: str
    title: str
    outcome: str
    research: str
    entrypoints: tuple[str, ...]
    write_prefixes: tuple[str, ...]
    test_prefixes: tuple[str, ...]


LANES: dict[str, Lane] = {
    "wizard_ux": Lane(
        slug="wizard_ux",
        title="Jornada, rascunhos e esforço mínimo",
        outcome=(
            "A jornada deve carregar ativos conhecidos automaticamente, persistir e retomar sem perda, "
            "pedir somente decisões humanas e manter acessibilidade, feedback assíncrono e estados de erro claros."
        ),
        research=(
            "Pesquise somente documentação oficial Meta sobre hierarquia Business/ad account/Page, "
            "pixels/datasets e requisitos de special_ad_categories. Separe obrigação da API de escolha de UX."
        ),
        entrypoints=(
            "src/pages/trafego/MetaCriacaoPage.tsx",
            "src/hooks/useMetaCampaignDraft.ts",
            "src/components/trafego/meta/EscolherBusinessMeta.tsx",
            "src/components/trafego/meta/PainelDeMensuracao.tsx",
            "src/components/trafego/meta/RascunhosMeta.tsx",
            "backend/app/trafego/meta/draft_storage.py",
        ),
        write_prefixes=(
            "src/pages/trafego/MetaCriacaoPage.tsx",
            "src/pages/trafego/__tests__/meta-criacao-",
            "src/hooks/useMetaCampaignDraft",
            "src/components/trafego/meta/",
            "backend/app/trafego/meta/draft_storage.py",
            "backend/app/routers/trafego_meta",
            "backend/tests/test_meta_draft",
            "backend/tests/test_trafego_meta",
        ),
        test_prefixes=(
            "src/pages/trafego/__tests__/meta-criacao-",
            "src/hooks/useMetaCampaignDraft.test.tsx",
            "src/components/trafego/meta/__tests__/rascunhos",
            "backend/tests/test_meta_draft",
            "backend/tests/test_trafego_meta",
        ),
    ),
    "creative_system": Lane(
        slug="creative_system",
        title="Criativos, packs, copy e formato flexível",
        outcome=(
            "LP e contexto persistido alimentam briefing/spec/copy sem trabalho repetido; geração progride em paralelo; "
            "packs são editáveis e reutilizáveis; flexível representa os pools reais e nunca inventa compatibilidade."
        ),
        research=(
            "Pesquise somente documentação oficial Meta para Ad Creative, flexible ad format, Advantage+ Creative, "
            "asset groups, limites de texto/ativos e reutilização de posts. Não misture creative_asset_groups_spec "
            "com asset_feed_spec e não prometa preservação de social proof sem post_id elegível."
        ),
        entrypoints=(
            "src/features/creative-studio/api.ts",
            "src/features/creative-studio/componentes/PainelDeEstrategia.tsx",
            "src/components/trafego/meta/TextosDoAnuncioFlexivel.tsx",
            "src/components/trafego/meta/VarinhaDeCopy.tsx",
            "src/components/trafego/meta/PrepararPackMeta.tsx",
            "backend/app/criativo/execucao.py",
            "backend/app/trafego/meta/copy_context.py",
            "backend/app/trafego/meta/copy_suggestions.py",
        ),
        write_prefixes=(
            "src/features/creative-studio/",
            "src/components/trafego/meta/",
            "backend/app/criativo/",
            "backend/app/routers/criativo",
            "backend/app/trafego/meta/copy_",
            "backend/tests/test_criativo",
            "backend/tests/test_meta_copy",
        ),
        test_prefixes=(
            "src/features/creative-studio/__tests__/",
            "src/components/trafego/meta/__tests__/",
            "backend/tests/test_criativo",
            "backend/tests/test_meta_copy",
        ),
    ),
    "publishing_contract": Lane(
        slug="publishing_contract",
        title="Compilação e nascimento PAUSED reconciliável",
        outcome=(
            "Plano aprovado compila campanha, todos os conjuntos, criativos e anúncios pretendidos; chamadas são "
            "idempotentes, sempre PAUSED, reconciliáveis após falha parcial e nunca ativam nem duplicam silenciosamente."
        ),
        research=(
            "Pesquise somente documentação oficial Meta para campaign/adset/ad/adcreative creation, validation_only, "
            "status PAUSED, object_story_spec, flexible assets, advertiser identity e erros/retries. "
            "Documente campos condicionais por objetivo e não trate aceitação remota como garantia de entrega."
        ),
        entrypoints=(
            "backend/app/trafego/meta_execucao/compilador.py",
            "backend/app/trafego/meta_execucao/executor.py",
            "backend/app/trafego/meta_execucao/registro.py",
            "backend/app/trafego/meta_execucao/reconciliacao.py",
            "backend/app/trafego/meta_execucao/capacidades.py",
            "backend/app/trafego/meta_execucao/posts_existentes.py",
            "backend/tests/test_meta_paused_birth.py",
        ),
        write_prefixes=(
            "backend/app/trafego/meta_execucao/",
            "backend/app/routers/trafego_meta",
            "backend/app/trafego/meta/adaptador.py",
            "backend/tests/test_meta_",
            "backend/tests/test_trafego_meta",
        ),
        test_prefixes=(
            "backend/tests/test_meta_",
            "backend/tests/test_trafego_meta",
        ),
    ),
    "measurement_ops": Lane(
        slug="measurement_ops",
        title="Mensuração, receita e operação hierárquica",
        outcome=(
            "Insights respeitam campanha→conjunto→anúncio→criativo; GAM Meta casa utm_campaign com adset_id, "
            "sobe receita ao pai sem rateio ou duplicação e ações operacionais usam identidade e estado reais."
        ),
        research=(
            "Pesquise somente documentação oficial Meta para Insights nos níveis campaign/adset/ad, breakdowns, "
            "creative fatigue/ad recommendations webhooks e ações de pausa/duplicação. Diferencie métricas de anúncio, "
            "identidade de criativo e receita externa que não pode ser atribuída ao anúncio sem evidência."
        ),
        entrypoints=(
            "backend/app/trafego/meta/desempenho_anuncios.py",
            "backend/app/trafego/meta/financeiro.py",
            "backend/app/trafego/meta/sincronizador.py",
            "src/components/trafego/meta/MetaCampaignReadView.tsx",
            "src/components/trafego/meta/MetaCampaignData.tsx",
            "src/components/trafego/meta/AcoesDaHierarquia.tsx",
            "src/pages/MetaCampaignInsightPage.tsx",
        ),
        write_prefixes=(
            "backend/app/trafego/meta/financeiro.py",
            "backend/app/trafego/meta/desempenho_anuncios.py",
            "backend/app/trafego/meta/sincronizador.py",
            "backend/app/trafego/meta/read_model.py",
            "backend/tests/test_meta_financial",
            "backend/tests/test_meta_",
            "src/components/trafego/meta/",
            "src/pages/MetaCampaignInsightPage.tsx",
            "src/pages/__tests__/meta-campaign",
            "src/pages/__tests__/campaign-metric",
        ),
        test_prefixes=(
            "backend/tests/test_meta_",
            "src/components/trafego/meta/__tests__/",
            "src/pages/__tests__/meta-campaign",
            "src/pages/__tests__/campaign-metric",
        ),
    ),
}


def lane(name: str) -> Lane:
    try:
        return LANES[name]
    except KeyError as exc:
        raise ValueError(f"unknown lane: {name}") from exc
