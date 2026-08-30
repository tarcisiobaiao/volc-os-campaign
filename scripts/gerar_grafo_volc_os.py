#!/usr/bin/env python3
"""Combina a curadoria humana com os snapshots vivos e gera o Mapa Mestre.

## A ordem das fontes, e por que ela existe

1. **curadoria operacional humana** — `docs/volc-os-graph/curadoria-operacional.json`.
   Capacidades, conceitos, decisões, documentos, relações de negócio e prioridades.
   É EDITÁVEL À MÃO e este script **nunca a escreve** (`_guarda_fonte_humana`).
2. **snapshot operacional gerado** — `docs/volc-os-graph/volc-os-graph.json`, saída deste
   script. NÃO é lugar de edição manual: qualquer mudança aqui é perdida no próximo build.
3. extração técnica (`.graphify-cache/`), 4. grafo híbrido (`graphify-out/`),
5. exports e visualizações.

⚠️ O defeito que este desenho corrige: a curadoria morava numa lista embutida neste arquivo,
enquanto o `CLAUDE.md` apontava a saída gerada como "fonte curada". Quem editava a saída
perdia o trabalho no build seguinte — e foi o que aconteceu em 24/08/2026.

Entradas: curadoria humana · código do produto e do backend · inventário sanitizado do n8n ·
snapshot somente-leitura do PostgREST e do ClickUp em /private/tmp.

Saídas: JSON, CSV, GraphML, Mermaid e um HTML navegável sem dependências externas.
"""

from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "volc-os-graph"
DELIVERY = ROOT / "entregaveis" / "Mapa_Mestre_VOLC_OS.html"
CURADORIA = OUT / "curadoria-operacional.json"
DB_SNAPSHOT = Path("/private/tmp/volc-supabase-inventory.json")
CLICKUP_SNAPSHOT = Path("/private/tmp/volc-clickup-tasks-p0.json")
SENSITIVE_COLUMN = re.compile(r"password|secret|token|credential|api[_-]?key", re.I)


CLUSTERS = {
    "strategy": "Estratégia & portfólio",
    "discovery": "Descoberta & pauta",
    "production": "Conteúdo & publicação",
    "acquisition": "Aquisição & campanhas",
    "measurement": "Medição & monetização",
    "decision": "Decisão & atuação",
    "publisher_quality": "Qualidade do publisher",
    "governance": "Governança & operação",
    "platform": "Plataforma & integrações",
    "data": "Dados & modelos",
}


STATE_LABELS = {
    "live": "Vivo agora",
    "implemented": "Implementado",
    "partial": "Parcial / elo incompleto",
    "historical": "Histórico com evidência",
    "declared_active": "Ativo declarado; eficácia não provada",
    "inactive": "Inativo / laboratório",
    "empty": "Estrutura vazia",
    "reference": "Referência",
    "decision": "Decisão aberta",
    "risk": "Risco / divergência",
    "todo": "Planejado",
}


nodes: dict[str, dict] = {}
edges: list[dict] = []
edge_keys: set[tuple] = set()


def add_node(node_id: str, label: str, node_type: str, cluster: str, state: str,
             tier: int, summary: str = "", evidence: str = "", source: str = "",
             **extra):
    if node_id in nodes:
        current = nodes[node_id]
        for key, value in {"summary": summary, "evidence": evidence, "source": source, **extra}.items():
            if value and not current.get(key):
                current[key] = value
        return current
    node = {
        "id": node_id, "label": label, "type": node_type,
        "cluster": cluster, "cluster_label": CLUSTERS[cluster],
        "state": state, "state_label": STATE_LABELS[state], "tier": tier,
        "summary": summary, "evidence": evidence, "source": source,
    }
    node.update(extra)
    nodes[node_id] = node
    return node


def add_edge(source: str, target: str, relation: str, evidence: str = "",
             confidence: str = "measured"):
    if source not in nodes or target not in nodes:
        return
    key = (source, target, relation)
    if key in edge_keys:
        return
    edge_keys.add(key)
    edges.append({
        "source": source, "target": target, "relation": relation,
        "evidence": evidence, "confidence": confidence,
    })


class CuradoriaInvalida(SystemExit):
    """Erro de curadoria falha o build. Grafo com referência quebrada mente pior que
    grafo desatualizado: ele responde com confiança sobre um nó que não existe."""


def _erro(msg: str):
    raise CuradoriaInvalida(f"curadoria-operacional.json: {msg}")


def carregar_curadoria() -> dict:
    """Lê a fonte humana e valida antes de qualquer nó existir.

    Valida aqui o que não depende dos extratores: schema, clusters, estados e IDs
    duplicados. As referências de aresta só podem ser checadas depois que os
    snapshots produzirem os nós deles — ver `aplicar_arestas_curadas`.
    """
    if not CURADORIA.exists():
        _erro(f"não encontrada em {CURADORIA}. É a fonte humana; sem ela não há o que gerar.")
    try:
        cur = json.loads(CURADORIA.read_text())
    except json.JSONDecodeError as exc:
        _erro(f"JSON inválido — {exc}")

    for chave in ("meta", "capabilities", "concepts", "documents", "edges", "priorities"):
        if chave not in cur:
            _erro(f"falta a chave obrigatória '{chave}'")

    vistos: dict[str, str] = {}
    for seccao, campos in (("capabilities", ("id", "label", "cluster", "state", "summary", "evidence")),
                           ("concepts", ("id", "label", "cluster", "state", "summary", "evidence")),
                           ("documents", ("id", "label", "cluster", "documenta"))):
        for i, item in enumerate(cur[seccao]):
            for campo in campos:
                if campo not in item or item[campo] in (None, ""):
                    _erro(f"{seccao}[{i}] sem '{campo}'")
            if item["cluster"] not in CLUSTERS:
                _erro(f"{seccao}[{i}] ({item['id']}) usa cluster inexistente '{item['cluster']}'")
            if seccao != "documents" and item["state"] not in STATE_LABELS:
                _erro(f"{seccao}[{i}] ({item['id']}) usa estado inexistente '{item['state']}'")
            if item["id"] in vistos:
                _erro(f"ID duplicado '{item['id']}' — em '{vistos[item['id']]}' e em '{seccao}'")
            vistos[item["id"]] = seccao

    for i, e in enumerate(cur["edges"]):
        for campo in ("source", "target", "relation"):
            if campo not in e or not e[campo]:
                _erro(f"edges[{i}] sem '{campo}'")

    return cur


def adicionar_nos_curados(cur: dict):
    """Os nós que um humano decidiu que existem. Entram antes dos extratores para que
    as arestas técnicas possam encontrá-los."""
    fonte = f"Curadoria humana, atualizada em {cur['meta'].get('curadoria_atualizada_em', '—')}"
    for c in cur["capabilities"]:
        add_node(c["id"], c["label"], "capability", c["cluster"], c["state"], 1,
                 c["summary"], c["evidence"], fonte)
    for c in cur["concepts"]:
        add_node(c["id"], c["label"], "concept", c["cluster"], c["state"], 1,
                 c["summary"], c["evidence"], fonte)
    for d in cur["documents"]:
        add_node(d["id"], d["label"], "document", d["cluster"], "reference", 3,
                 d.get("summary", "Fonte de contexto, regra ou arquitetura."),
                 d.get("evidence", "Incluída na cartografia global."), fonte)


def aplicar_arestas_curadas(cur: dict):
    """Aplica as relações humanas DEPOIS dos extratores, e falha alto se alguma
    apontar para um nó que não existe.

    ⚠️ `add_edge` descarta em silêncio aresta com ponta faltando — é o comportamento
    certo para relação inferida de código, e o errado para relação curada: ali o
    silêncio esconde erro de digitação do humano.
    """
    orfas = []
    for e in cur["edges"]:
        if e["source"] not in nodes:
            orfas.append(f"  {e['source']} --{e['relation']}--> {e['target']}   (origem inexistente)")
        elif e["target"] not in nodes:
            orfas.append(f"  {e['source']} --{e['relation']}--> {e['target']}   (destino inexistente)")
        else:
            add_edge(e["source"], e["target"], e["relation"], e.get("evidence", ""), "curated")
    for d in cur["documents"]:
        if d["documenta"] not in nodes:
            orfas.append(f"  {d['id']} --documenta--> {d['documenta']}   (destino inexistente)")
        else:
            add_edge(d["id"], d["documenta"], "documenta", "", "curated")
    if orfas:
        _erro("relações apontando para nós que não existem:\n" + "\n".join(orfas))


def _guarda_fonte_humana(assinatura_antes: str):
    """A fonte humana não pode ser tocada por este script. Se for, o build falha —
    silenciosamente sobrescrever curadoria é exatamente o defeito que este desenho corrige."""
    import hashlib
    depois = hashlib.sha256(CURADORIA.read_bytes()).hexdigest()
    if depois != assinatura_antes:
        _erro("o gerador modificou a fonte humana. Isto é um defeito do gerador, não da curadoria.")


def load_database():
    snap = json.loads(DB_SNAPSHOT.read_text())
    today = "2026-08-22"
    for item in snap["tables_and_views"]:
        name = item["name"]
        count = item.get("exact_count", 0)
        last = str(item.get("last") or "")
        if count == 0:
            state = "empty"
        elif last.startswith(today) or last.startswith("2026-08-21") or last.startswith("2026-08-20"):
            state = "live"
        elif last:
            state = "historical"
        else:
            state = "implemented"
        cluster = infer_table_cluster(name)
        safe_columns = [c for c in item.get("columns", []) if not SENSITIVE_COLUMN.search(c)]
        add_node(f"db:{name}", name, "table_or_view", cluster, state, 3,
                 f"{count} linha(s) no snapshot exato.",
                 f"Contagem exata: {count}. Campo temporal: {item.get('temporal_column') or 'não identificado'}. "
                 f"Primeiro: {item.get('first') or '—'}. Último: {item.get('last') or '—'}.",
                 "PostgREST self-hosted, leitura em 22/08/2026",
                 exact_count=count, columns=safe_columns, first=item.get("first"), last=item.get("last"))
    for rpc_path in snap["rpc_paths"]:
        name = rpc_path.rsplit("/", 1)[-1]
        cluster = infer_rpc_cluster(name)
        add_node(f"rpc:{name}", name, "database_function", cluster, "implemented", 3,
                 "Função exposta pelo PostgREST.", "Catálogo OpenAPI vivo.",
                 "PostgREST self-hosted, 22/08/2026")


def infer_table_cluster(name: str) -> str:
    if name.startswith("pautador_") or name in {"market_configs", "mining_runs", "expanded_keywords", "seed_keywords", "seed_categories", "keyword_blacklist", "discovered_opportunities"}:
        return "discovery"
    if name.startswith("incubator_") or name == "project_wordpress" or name == "v_incubator_schedule_progress":
        return "production"
    if name in {"campaigns", "campaign_funnel_urls", "niche_conversion_mappings"}:
        return "acquisition"
    if any(k in name for k in ("metrics", "revenue", "display_", "site_visits", "raw_events", "fact_", "hourly", "conversion_", "adsense", "joinads", "gam_")):
        return "measurement"
    if name in {"bid_actions", "campaign_highlights"}:
        return "decision"
    if name in {"users", "user_campaigns", "user_projects", "operational_costs", "operational_cost_categories", "tax_history", "system_settings", "exchange_rate_history"}:
        return "governance"
    return "data"


def infer_rpc_cluster(name: str) -> str:
    if any(k in name for k in ("revenue", "adsense", "gam", "exchange", "dollar", "metrics", "dashboard", "funnel", "page", "cta")):
        return "measurement"
    if any(k in name for k in ("campaign", "google_ads", "status")):
        return "acquisition"
    if any(k in name for k in ("commission", "cost", "tax", "setting", "user", "revshare")):
        return "governance"
    if any(k in name for k in ("project", "incubator")):
        return "production"
    return "data"


def add_frontend():
    route_map = [
        ("/", "GeneralDashboard", "cap_portfolio"),
        ("/dashboard/projects", "ProjectsSettings", "cap_portfolio"),
        ("/dashboard/campaign/:campaignId", "CampaignDetailDashboard", "cap_campaign_cockpit"),
        ("/dashboard/project/:projectId", "ProjectDashboard", "cap_portfolio"),
        ("/reports", "Reports", "cap_portfolio"),
        ("/settings/projects", "ProjectsSettings", "cap_portfolio"),
        ("/settings/campaigns", "CampaignsSettings", "cap_campaign_cockpit"),
        ("/settings/costs", "CostsSettings", "cap_finance"),
        ("/settings/integrations", "IntegrationsSettings", "cap_workflows"),
        ("/settings/users", "UsersSettings", "cap_people"),
        ("/incubator", "IncubatorPage", "cap_incubator"),
        ("/incubator/:siteId", "IncubatorDetailPage", "cap_incubator"),
        ("/pautador-pro", "PautadorProPage", "cap_discovery"),
        ("/redator", "RedatorPage", "cap_funnel"),
        ("/redator/config", "ConfigRedatorPage", "cap_funnel"),
        ("/redator/funil/:runId", "FunilPage", "cap_funnel"),
        ("/redator/funil/:runId/p/:n", "PaginaDoFunilPage", "cap_funnel"),
        ("/trafego", "TrafegoPage", "cap_traffic_queue"),
        ("/trafego/nova/:opportunityId", "NovaCampanhaPage", "cap_search_birth"),
        ("/admin/v6", "V6AdminPage", "cap_people"),
        ("/login", "Login", "cap_people"),
        ("/change-password", "ChangePassword", "cap_people"),
    ]
    page_files = {p.stem: p for p in (ROOT / "src" / "pages").rglob("*.tsx")}
    for route, component, cap in route_map:
        cluster = nodes[cap]["cluster"]
        file = page_files.get(component)
        add_node(f"ui:{route}", route, "ui_surface", cluster, "implemented", 2,
                 f"Tela {component}.", f"Rota registrada em src/App.tsx.",
                 str(file.relative_to(ROOT)) if file else "src/App.tsx", component=component)
        add_edge(cap, f"ui:{route}", "materializa_em")
        if file:
            connect_ts_file(f"ui:{route}", file, cluster)
    # Componentes de negócio que completam o cockpit de campanha.
    for comp, cap in [
        ("OrientacaoBox", "cap_decision"), ("OtimizacaoBox", "cap_decision"),
        ("BiddingActionBox", "cap_execution"), ("DisplayROITable", "cap_display"),
        ("PlacementNegationCard", "cap_display"), ("FunnelUrlsEditor", "cap_attribution"),
        ("SinoDeAlertas", "cap_health"), ("MetaCapiWizard", "cap_capi"),
    ]:
        paths = list((ROOT / "src" / "components").rglob(f"{comp}.tsx"))
        if not paths:
            continue
        path = paths[0]
        nid = f"component:{comp}"
        add_node(nid, comp, "business_component", nodes[cap]["cluster"], "implemented", 2,
                 "Componente de produto.", "Presente no código e incluído no build.", str(path.relative_to(ROOT)))
        add_edge(cap, nid, "materializa_em")
        connect_ts_file(nid, path, nodes[cap]["cluster"])


def connect_ts_file(owner_id: str, path: Path, cluster: str):
    text = path.read_text(errors="ignore")
    for service in re.findall(r'from\s+["\']@/services/([A-Za-z0-9_-]+)["\']', text):
        sid = f"service:{service}"
        service_path = ROOT / "src" / "services" / f"{service}.ts"
        add_node(sid, service, "frontend_service", cluster, "implemented", 2,
                 "Serviço de dados do frontend.", "Importado por uma superfície do produto.",
                 str(service_path.relative_to(ROOT)) if service_path.exists() else "src/services")
        add_edge(owner_id, sid, "usa")
    for table in re.findall(r"\.from\([\"']([a-zA-Z0-9_]+)[\"']\)", text):
        add_edge(owner_id, f"db:{table}", "lê_ou_escreve", str(path.relative_to(ROOT)))


def add_services():
    for path in sorted((ROOT / "src" / "services").glob("*.ts")):
        service = path.stem
        sid = f"service:{service}"
        text = path.read_text(errors="ignore")
        tables = sorted(set(re.findall(r"\.from\([\"']([a-zA-Z0-9_]+)[\"']\)", text)))
        rpcs = sorted(set(re.findall(r"\.rpc\([\"']([a-zA-Z0-9_]+)[\"']", text)))
        cluster = infer_service_cluster(service, tables)
        add_node(sid, service, "frontend_service", cluster, "implemented", 2,
                 f"Serviço do frontend; conecta {len(tables)} tabela(s) e {len(rpcs)} RPC(s).",
                 "Dependências extraídas estaticamente do código.", str(path.relative_to(ROOT)),
                 tables=tables, rpcs=rpcs)
        for table in tables:
            add_edge(sid, f"db:{table}", "lê_ou_escreve", str(path.relative_to(ROOT)))
        for rpc in rpcs:
            add_edge(sid, f"rpc:{rpc}", "chama", str(path.relative_to(ROOT)))


def infer_service_cluster(service: str, tables: list[str]) -> str:
    joined = " ".join([service, *tables]).lower()
    if "pautador" in joined:
        return "discovery"
    if "incubator" in joined or "wordpress" in joined:
        return "production"
    if "campaign" in joined and "funnel" in joined:
        return "acquisition"
    if any(k in joined for k in ("metric", "revenue", "highlight", "report")):
        return "measurement"
    if any(k in joined for k in ("user", "cost", "tax", "setting", "currency")):
        return "governance"
    return "data"


def add_backend():
    mapping = {
        "pautador": ("discovery", "cap_keyword_mining", ["pautador_runs", "pautador_opportunities", "pautador_keyword_clusters"]),
        "entities": ("discovery", "cap_discovery", ["pautador_entities", "pautador_entity_opportunities", "pautador_entity_axes", "pautador_entity_pains", "pautador_entity_seed_queries", "pautador_entity_funnel_hypotheses", "pautador_question_choices"]),
        "publicacao": ("production", "cap_funnel", ["pautador_funnel_runs", "project_wordpress", "projects"]),
        "trafego": ("acquisition", "cap_search_birth", ["campaigns", "campaign_funnel_urls", "pautador_trafego_copy", "pautador_entity_opportunities", "pautador_funnel_runs"]),
    }
    for name, (cluster, cap, tables) in mapping.items():
        path = ROOT / "backend" / "app" / "routers" / f"{name}.py"
        text = path.read_text(errors="ignore")
        endpoints = re.findall(r'@router\.(get|post|put|patch|delete)\(["\']([^"\']+)', text)
        nid = f"backend:{name}"
        add_node(nid, f"API {name}", "backend_module", cluster, "implemented", 2,
                 f"Módulo FastAPI com {len(endpoints)} endpoints.",
                 "Endpoints medidos no código.", str(path.relative_to(ROOT)),
                 endpoints=[f"{method.upper()} {route}" for method, route in endpoints])
        add_edge(cap, nid, "materializa_em")
        for table in tables:
            add_edge(nid, f"db:{table}", "lê_ou_escreve", str(path.relative_to(ROOT)))
    # Edge Function Meta CAPI.
    nid = "backend:capi-router"
    add_node(nid, "Edge Function capi-router", "edge_function", "platform", "implemented", 2,
             "Resolve site e roteia eventos Meta CAPI.", "Código presente no repositório.",
             "supabase/functions/capi-router/index.ts")
    add_edge("cap_capi", nid, "materializa_em")


MANIFESTO_N8N = ROOT / "docs" / "volc-os-graph" / "inventario-n8n-sanitizado.json"


def add_n8n():
    """Monta os nós n8n a partir do manifesto sanitizado e RASTREADO.

    Antes, isto lia ``inventario-n8n/flows/*.meta.json`` — diretório gitignored,
    ausente de qualquer worktree limpa. O build dependia de uma máquina e as 19
    arestas da curadoria pendiam no vazio. Não há fallback para o diretório
    local: a fonte é o manifesto ou o build falha.

    Consequência declarada: as arestas que antes vinham da leitura do JSON
    completo do workflow (tabelas PostgREST, hosts Supabase, integrações
    externas) não são mais derivadas aqui, porque esses dados não entram no
    manifesto sanitizado.
    """

    if not MANIFESTO_N8N.exists():
        raise SystemExit(
            f"manifesto n8n rastreado ausente: {MANIFESTO_N8N.relative_to(ROOT)}. "
            "Gere com scripts/gerar_inventario_n8n_sanitizado.py --source-dir <dir>."
        )
    manifesto = json.loads(MANIFESTO_N8N.read_text())
    for meta in manifesto["workflows"]:
        slug = meta["slug"]
        flow_text = ""
        meta_path = MANIFESTO_N8N
        cluster = {
            "receita": "measurement", "custo": "measurement", "decisao": "decision",
            "preditivo": "decision", "criacao": "acquisition", "otimizacao": "decision",
            "pauta": "discovery", "atuacao": "decision", "front": "governance",
            "comportamento": "measurement",
        }.get(meta.get("camada"), "platform")
        old_hits = flow_text.count("txvvzpstquqmbhljudfn.supabase.co")
        self_hits = flow_text.count("database.agenciavolc.com.br")
        if not meta.get("ativo"):
            state = "inactive"
        elif old_hits and not self_hits:
            state = "declared_active"
        else:
            state = "declared_active"
        nid = f"n8n:{slug}"
        add_node(nid, meta["nome"], "workflow", cluster, state, 2,
                 f"{meta.get('nos', 0)} nós; {meta.get('linhas_de_codigo', 0)} linhas de código; "
                 f"gatilhos: {', '.join(meta.get('gatilhos_tipos') or []) or 'não identificado'}.",
                 f"Ativo declarado: {bool(meta.get('ativo'))}. Referências: hospedado={old_hits}, self-hosted={self_hits}.",
                 str(meta_path.relative_to(ROOT)), active=bool(meta.get("ativo")),
                 triggers=meta.get("gatilhos_tipos") or [], nodes_count=meta.get("nos", 0),
                 code_lines=meta.get("linhas_de_codigo", 0), old_db_refs=old_hits, self_db_refs=self_hits)
        add_edge("cap_workflows", nid, "contém")
        if meta.get("camada") == "receita": add_edge(nid, "cap_revenue_ingestion", "executa")
        if meta.get("camada") == "custo": add_edge(nid, "cap_cost_ingestion", "executa")
        if meta.get("camada") in {"decisao", "atuacao"}: add_edge(nid, "cap_decision", "implementa")
        if meta.get("camada") == "preditivo": add_edge(nid, "cap_forecast", "implementa")
        if meta.get("camada") == "criacao": add_edge(nid, "cap_search_birth", "implementa")
        if meta.get("camada") == "otimizacao": add_edge(nid, "cap_execution", "implementa")
        if meta.get("camada") == "pauta": add_edge(nid, "cap_keyword_mining", "implementa")
        table_names = sorted(set(re.findall(r"/rest/v1/([a-zA-Z0-9_]+)", flow_text)))
        for table in table_names:
            add_edge(nid, f"db:{table}", "lê_ou_escreve", "URL PostgREST detectada no workflow")
        if old_hits: add_edge(nid, "external:supabase-hosted", "aponta_para", f"{old_hits} referência(s)")
        if self_hits: add_edge(nid, "external:supabase-self", "aponta_para", f"{self_hits} referência(s)")
        for marker, external in [
            ("googleads.googleapis.com", "external:google-ads"), ("googleapis.com", "external:google"),
            ("clickup.com", "external:clickup"), ("join", "external:joinads"),
        ]:
            if marker in flow_text.lower():
                add_edge(nid, external, "integra_com")


def add_externals():
    items = [
        ("external:supabase-self", "Supabase oficial VOLC O.S.", "platform", "live", "Única autoridade operacional: https://database.agenciavolc.com.br."),
        ("external:supabase-hosted", "Supabase hospedado legado", "platform", "risk", "Destino proibido para nova operação; referências antigas exigem migração ou aposentadoria."),
        ("external:google-ads", "Google Ads", "acquisition", "live", "Compra de mídia, criação, leitura e mutação."),
        ("external:google", "Google APIs", "platform", "implemented", "Família de APIs Google."),
        ("external:gam", "Google Ad Manager", "measurement", "partial", "Monetização e placements."),
        ("external:adsense", "AdSense", "measurement", "historical", "Receita por URL/projeto."),
        ("external:joinads", "JoinAds", "measurement", "partial", "Receita alternativa por projeto/campanha."),
        ("external:wordpress", "WordPress", "production", "live", "Destino de publicação dos funis."),
        ("external:n8n", "n8n", "platform", "declared_active", "Orquestrador com 30 workflows inventariados."),
        ("external:pgcron", "pg_cron", "platform", "live", "Agendador de fatos comportamentais."),
        ("external:clickup", "ClickUp", "governance", "live", "Backlog Foco Genial e gatilhos legados."),
        ("external:dataforseo", "DataForSEO", "discovery", "implemented", "Validação e mineração de keywords."),
        ("external:gemini", "Gemini", "discovery", "implemented", "Agentes de descoberta e funil."),
        ("external:openai", "OpenAI", "discovery", "implemented", "Alternativa de modelo configurada."),
        ("external:perplexity", "Perplexity", "discovery", "implemented", "Pesquisa e grounding configurados."),
        ("external:meta", "Meta CAPI", "platform", "implemented", "Roteamento server-side por site."),
    ]
    for nid, label, cluster, state, summary in items:
        add_node(nid, label, "external_system", cluster, state, 2, summary, "Configuração ou código identificado.", "Repositório VOLC O.S.")
    add_edge("cap_source_truth", "external:supabase-self", "define_como_autoridade_unica")
    add_edge("cap_source_truth", "external:supabase-hosted", "proibe_como_destino_operacional")
    add_edge("cap_search_birth", "external:google-ads", "cria_em")
    add_edge("cap_cost_ingestion", "external:google-ads", "lê_de")
    add_edge("cap_revenue_ingestion", "external:gam", "lê_de")
    add_edge("cap_revenue_ingestion", "external:adsense", "lê_de")
    add_edge("cap_revenue_ingestion", "external:joinads", "lê_de")
    add_edge("cap_funnel", "external:wordpress", "publica_em")
    add_edge("cap_workflows", "external:n8n", "usa")
    add_edge("cap_workflows", "external:pgcron", "usa")
    add_edge("cap_publisher_quality", "external:clickup", "organizado_em")
    add_edge("cap_keyword_mining", "external:dataforseo", "mede_com")
    add_edge("cap_discovery", "external:gemini", "raciocina_com")
    add_edge("cap_capi", "external:meta", "envia_para")


def add_clickup():
    if not CLICKUP_SNAPSHOT.exists():
        return
    payload = json.loads(CLICKUP_SNAPSHOT.read_text())
    for task in payload.get("tasks", []):
        tid = str(task.get("id"))
        status = ((task.get("status") or {}).get("status") or "").lower()
        state = "todo" if status in {"to do", "open", "aberto"} else "implemented"
        node_id = f"clickup:{tid}"
        add_node(node_id, task.get("name") or tid, "task", "publisher_quality", state, 3,
                 "Tarefa do backlog oficial Foco Genial.", f"Status ClickUp: {status or 'não informado'}.",
                 "ClickUp lista 901328196164, leitura em 22/08/2026", status=status)
        add_edge("cap_publisher_quality", node_id, "planeja")


def add_data_relationships():
    rels = [
        ("db:projects", "db:campaigns"), ("db:campaigns", "db:daily_campaign_metrics"),
        ("db:projects", "db:daily_project_metrics"), ("db:campaigns", "db:campaign_funnel_urls"),
        ("db:pautador_entities", "db:pautador_entity_opportunities"),
        ("db:pautador_entity_opportunities", "db:pautador_entity_seed_queries"),
        ("db:pautador_entity_opportunities", "db:pautador_keyword_clusters"),
        ("db:pautador_entity_opportunities", "db:pautador_entity_funnel_hypotheses"),
        ("db:pautador_entity_opportunities", "db:pautador_funnel_runs"),
        ("db:pautador_funnel_runs", "db:campaigns"),
        ("db:site_visits", "db:campaigns"), ("db:raw_events", "db:fact_page_daily"),
        ("db:fact_page_daily", "db:fact_funnel_daily"),
        ("db:site_visits", "db:conversion_queue"), ("db:conversion_queue", "db:conversion_batches"),
        ("db:gam_metrics", "db:daily_campaign_metrics"),
        ("db:joinads_metrics", "db:daily_campaign_metrics"),
        ("db:adsense_metrics", "db:daily_campaign_metrics"),
        ("db:display_ads_placements", "db:vw_display_roi"),
        ("db:display_gam_placements", "db:vw_display_roi"),
        ("db:users", "db:user_projects"), ("db:users", "db:user_campaigns"),
    ]
    for a, b in rels:
        add_edge(a, b, "relaciona", confidence="modeled")
    # Liga capacidades aos principais objetos de dados.
    mapping = {
        "cap_campaign_cockpit": ["campaigns", "daily_campaign_metrics", "gam_metrics", "campaign_funnel_urls", "vw_display_roi"],
        "cap_discovery": ["pautador_entities", "pautador_entity_opportunities", "pautador_entity_axes", "pautador_entity_pains"],
        "cap_keyword_mining": ["pautador_entity_seed_queries", "pautador_keyword_clusters", "pautador_validation_runs"],
        "cap_funnel": ["pautador_funnel_runs", "project_wordpress"],
        "cap_incubator": ["incubator_sites", "incubator_articles", "incubator_pipeline_logs"],
        "cap_search_birth": ["campaigns", "pautador_trafego_copy", "campaign_funnel_urls"],
        "cap_cost_ingestion": ["daily_campaign_metrics", "display_ads_placements"],
        "cap_revenue_ingestion": ["daily_project_metrics", "adsense_metrics", "gam_metrics", "joinads_metrics", "display_gam_placements"],
        "cap_behavior": ["raw_events", "fact_page_daily", "fact_funnel_daily"],
        "cap_attribution": ["site_visits", "campaigns", "campaign_funnel_urls", "pautador_funnel_runs"],
        "cap_offline_conversion": ["site_visits", "conversion_queue", "conversion_batches", "niche_conversion_mappings"],
        "cap_decision": ["daily_campaign_metrics", "campaign_highlights"],
        "cap_execution": ["bid_actions"],
        "cap_display": ["display_ads_placements", "display_gam_placements", "vw_display_roi"],
        "cap_finance": ["exchange_rate_history", "tax_history", "operational_costs", "system_settings"],
        "cap_people": ["users", "user_projects", "user_campaigns"],
    }
    for cap, tables in mapping.items():
        for table in tables:
            add_edge(cap, f"db:{table}", "usa_dado")


def write_json(graph):
    (OUT / "volc-os-graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2))


def write_csvs(graph):
    with (OUT / "nodes.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label", "type", "cluster", "state", "tier", "summary", "evidence", "source"])
        for n in graph["nodes"]:
            writer.writerow([n.get(k, "") for k in ("id", "label", "type", "cluster", "state", "tier", "summary", "evidence", "source")])
    with (OUT / "edges.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "target", "relation", "confidence", "evidence"])
        for e in graph["edges"]:
            writer.writerow([e.get(k, "") for k in ("source", "target", "relation", "confidence", "evidence")])


def write_graphml(graph):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
             '<key id="label" for="node" attr.name="label" attr.type="string"/>',
             '<key id="type" for="node" attr.name="type" attr.type="string"/>',
             '<key id="cluster" for="node" attr.name="cluster" attr.type="string"/>',
             '<key id="state" for="node" attr.name="state" attr.type="string"/>',
             '<key id="relation" for="edge" attr.name="relation" attr.type="string"/>',
             '<graph id="VOLC_OS" edgedefault="directed">']
    for n in graph["nodes"]:
        lines.append(f'<node id="{xml_escape(n["id"])}"><data key="label">{xml_escape(n["label"])}</data>'
                     f'<data key="type">{xml_escape(n["type"])}</data><data key="cluster">{xml_escape(n["cluster"])}</data>'
                     f'<data key="state">{xml_escape(n["state"])}</data></node>')
    for i, e in enumerate(graph["edges"]):
        lines.append(f'<edge id="e{i}" source="{xml_escape(e["source"])}" target="{xml_escape(e["target"])}">'
                     f'<data key="relation">{xml_escape(e["relation"])}</data></edge>')
    lines.extend(['</graph>', '</graphml>'])
    (OUT / "volc-os-graph.graphml").write_text("\n".join(lines))


def write_mermaid(graph):
    capability_ids = {n["id"] for n in graph["nodes"] if n["type"] == "capability"}
    lines = ["flowchart LR"]
    for n in graph["nodes"]:
        if n["id"] in capability_ids:
            safe = re.sub(r"[^A-Za-z0-9_]", "_", n["id"])
            lines.append(f'  {safe}["{n["label"]}"]')
    for e in graph["edges"]:
        if e["source"] in capability_ids and e["target"] in capability_ids:
            a = re.sub(r"[^A-Za-z0-9_]", "_", e["source"])
            b = re.sub(r"[^A-Za-z0-9_]", "_", e["target"])
            lines.append(f'  {a} -->|{e["relation"]}| {b}')
    (OUT / "visao-executiva.mmd").write_text("\n".join(lines))


HTML_TEMPLATE = r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mapa Mestre • VOLC O.S.</title>
<style>
:root{--navy:#0b1020;--deep:#0d47a1;--cyan:#00d4ff;--purple:#8a2be2;--orange:#ff3d00;--off:#f3f4f6;--ink:#1a1c1e;--muted:#8793a8;--panel:#121a30;--line:#34415d}
*{box-sizing:border-box}body{margin:0;background:var(--navy);color:#f7f9fc;font:14px Inter,Arial,sans-serif;overflow:hidden}
header{height:72px;display:flex;align-items:center;gap:18px;padding:0 24px;border-bottom:1px solid #25314a;background:#0b1020ee;position:relative;z-index:5}
.brand{font:700 20px 'Space Grotesk',Arial}.brand b{color:var(--cyan)}.stat{color:#aeb9cc;font-size:12px}.grow{flex:1}
button,.pill,input{border:1px solid #33415d;background:#131d34;color:#eaf0fb;border-radius:10px;padding:9px 12px}button{cursor:pointer}button.active{border-color:var(--cyan);color:var(--cyan);box-shadow:0 0 0 1px #00d4ff33 inset}
.app{display:grid;grid-template-columns:270px 1fr 340px;height:calc(100vh - 72px)}aside{background:#0e1629;border-right:1px solid #25314a;padding:18px;overflow:auto}.right{border-right:0;border-left:1px solid #25314a}
h2{font:700 18px 'Space Grotesk',Arial;margin:4px 0 10px}h3{font:700 12px 'Space Grotesk',Arial;text-transform:uppercase;letter-spacing:.12em;color:#94a3b8;margin:22px 0 8px}
input{width:100%;outline:none}.filters{display:flex;flex-wrap:wrap;gap:6px}.filters button{font-size:11px;padding:6px 8px}.legend{display:grid;gap:7px}.legend span{display:flex;align-items:center;gap:8px;color:#b6c0d1;font-size:12px}.dot{width:9px;height:9px;border-radius:50%}
main{position:relative;overflow:hidden;background:radial-gradient(circle at 45% 40%,#14264d 0,#0b1020 52%)}svg{width:100%;height:100%;touch-action:none}.edge{stroke:#52617d;stroke-opacity:.42;fill:none}.edge.hot{stroke:var(--cyan);stroke-opacity:.95}.node rect{fill:#121d35;stroke:#44516d;stroke-width:1.4}.node text{fill:#eef3fb;font-size:11px;pointer-events:none}.node .mini{fill:#91a0b9;font-size:8px}.node.live rect{stroke:#1fc58b}.node.partial rect{stroke:#ff7a45}.node.empty rect{stroke:#76839a;stroke-dasharray:4 3}.node.risk rect,.node.decision rect{stroke:#ff3d00}.node.historical rect,.node.inactive rect{stroke:#8a2be2}.node.declared_active rect{stroke:#f6c344}.node.todo rect{stroke:#0d9ee8}.node.selected rect{stroke:var(--cyan);stroke-width:3;filter:drop-shadow(0 0 8px #00d4ff66)}
.cluster-label{fill:#64748b;font:700 13px 'Space Grotesk',Arial;letter-spacing:.08em}.count{font-size:12px;color:#aeb9cc}.detail-state{display:inline-block;border:1px solid #43506b;border-radius:999px;padding:5px 8px;font-size:11px;color:var(--cyan)}.detail p{color:#c3ccda;line-height:1.55}.detail small{color:#8793a8}.neighbors{display:grid;gap:6px}.neighbor{padding:8px;border:1px solid #293650;border-radius:8px;background:#111b31;cursor:pointer}.neighbor b{display:block;font-size:12px}.neighbor span{font-size:10px;color:#8fa0b8}.priority{border-left:3px solid var(--orange);padding:9px 10px;background:#111b31;margin:8px 0;border-radius:0 8px 8px 0}.priority b{font-size:12px}.priority p{font-size:11px;margin:4px 0;color:#aeb9cc}.empty-detail{color:#8793a8;line-height:1.6}.footer-note{font-size:10px;color:#70809a;margin-top:18px}
@media(max-width:1050px){.app{grid-template-columns:220px 1fr}.right{display:none}}@media(max-width:760px){header{height:auto;min-height:72px;flex-wrap:wrap;padding:12px}.app{grid-template-columns:1fr;height:calc(100vh - 110px)}aside{display:none}}
</style></head><body>
<header><div class="brand">VOLC <b>O.S.</b> · Mapa Mestre</div><div class="stat" id="stats"></div><div class="grow"></div><button data-tier="1" class="active">Executiva</button><button data-tier="2">Sistema</button><button data-tier="3">Inventário total</button></header>
<div class="app"><aside><h2>Explorar</h2><input id="search" placeholder="Buscar capacidade, tela, tabela…"><h3>Clusters</h3><div class="filters" id="clusters"></div><h3>Estados</h3><div class="legend" id="legend"></div><h3>Prioridades corrigidas</h3><div id="priorities"></div><div class="footer-note">Snapshot: 22/08/2026. Contagens do banco são exatas. “Ativo” de n8n é estado declarado no inventário, não prova de sucesso.</div></aside>
<main><svg id="graph"><g id="viewport"><g id="clusterLabels"></g><g id="edges"></g><g id="nodes"></g></g></svg></main>
<aside class="right"><div id="detail" class="detail"><h2>Selecione um nó</h2><p class="empty-detail">Clique em qualquer capacidade para ver evidência, fonte e vizinhos. Use a visão “Sistema” para revelar telas, serviços, workflows e integrações; “Inventário total” inclui tabelas, RPCs, documentos e tarefas.</p></div></aside></div>
<script>const GRAPH=__GRAPH__;
const colors={live:'#1fc58b',implemented:'#0d9ee8',partial:'#ff7a45',historical:'#8a2be2',declared_active:'#f6c344',inactive:'#8a2be2',empty:'#76839a',reference:'#8793a8',decision:'#ff3d00',risk:'#ff3d00',todo:'#00d4ff'};
let tier=1,selected=null,clusterFilter=null,query='',scale=1,tx=0,ty=0;
const nodeById=Object.fromEntries(GRAPH.nodes.map(n=>[n.id,n]));const svg=document.getElementById('graph'),viewport=document.getElementById('viewport');
const clusterOrder=Object.keys(GRAPH.clusters);const centers={};clusterOrder.forEach((c,i)=>{centers[c]={x:240+(i%4)*420,y:170+Math.floor(i/4)*350}});
function visibleNodes(){return GRAPH.nodes.filter(n=>n.tier<=tier&&(!clusterFilter||n.cluster===clusterFilter)&&(!query||(`${n.label} ${n.summary} ${n.evidence}`).toLowerCase().includes(query)))}
function layout(vs){const groups={};vs.forEach(n=>(groups[n.cluster]??=[]).push(n));Object.entries(groups).forEach(([c,arr])=>{const cc=centers[c]||{x:600,y:400};arr.sort((a,b)=>a.type.localeCompare(b.type)||a.label.localeCompare(b.label));arr.forEach((n,i)=>{if(tier===1){const ang=(i/Math.max(1,arr.length))*Math.PI*2;n.x=cc.x+Math.cos(ang)*Math.min(125,arr.length*18);n.y=cc.y+Math.sin(ang)*Math.min(95,arr.length*14)}else{const cols=tier===2?3:5;n.x=cc.x+(i%cols-((cols-1)/2))*125;n.y=cc.y+(Math.floor(i/cols)-1)*62}})})}
function render(){const vs=visibleNodes(),ids=new Set(vs.map(n=>n.id));layout(vs);document.getElementById('stats').textContent=`${vs.length} de ${GRAPH.nodes.length} nós · ${GRAPH.edges.length} relações`;
document.getElementById('clusterLabels').innerHTML=clusterOrder.map(c=>{const cc=centers[c];return `<text class="cluster-label" x="${cc.x-155}" y="${cc.y-135}">${GRAPH.clusters[c].toUpperCase()}</text>`}).join('');
document.getElementById('edges').innerHTML=GRAPH.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>{const a=nodeById[e.source],b=nodeById[e.target],hot=selected&&(e.source===selected||e.target===selected);return `<path class="edge ${hot?'hot':''}" d="M${a.x},${a.y} L${b.x},${b.y}" stroke-width="${hot?2.2:1}"/>`}).join('');
document.getElementById('nodes').innerHTML=vs.map(n=>{const w=tier===1?180:118,h=tier===1?48:38;const label=n.label.length>(tier===1?27:18)?n.label.slice(0,tier===1?26:17)+'…':n.label;return `<g class="node ${n.state} ${selected===n.id?'selected':''}" data-id="${esc(n.id)}" transform="translate(${n.x-w/2},${n.y-h/2})"><rect width="${w}" height="${h}" rx="10"/><circle cx="12" cy="12" r="4" fill="${colors[n.state]||'#8793a8'}"/><text x="${w/2}" y="${tier===1?23:22}" text-anchor="middle">${esc(label)}</text>${tier===1?`<text class="mini" x="${w/2}" y="38" text-anchor="middle">${esc(n.state_label)}</text>`:''}</g>`}).join('');
document.querySelectorAll('.node').forEach(el=>el.onclick=()=>selectNode(el.dataset.id));applyTransform()}
function selectNode(id){selected=id;const n=nodeById[id];const connected=GRAPH.edges.filter(e=>e.source===id||e.target===id);const neighbors=connected.slice(0,30).map(e=>{const other=nodeById[e.source===id?e.target:e.source];return `<div class="neighbor" data-neighbor="${esc(other.id)}"><b>${esc(other.label)}</b><span>${esc(e.relation)} · ${esc(other.state_label)}</span></div>`}).join('');document.getElementById('detail').innerHTML=`<span class="detail-state">${esc(n.state_label)}</span><h2>${esc(n.label)}</h2><small>${esc(n.cluster_label)} · ${esc(n.type)}</small><p>${esc(n.summary||'Sem resumo.')}</p><h3>Evidência</h3><p>${esc(n.evidence||'Não registrada.')}</p><h3>Fonte</h3><p><small>${esc(n.source||'—')}</small></p><h3>Relações (${connected.length})</h3><div class="neighbors">${neighbors||'<span class="count">Sem relações visíveis.</span>'}</div>`;document.querySelectorAll('[data-neighbor]').forEach(el=>el.onclick=()=>selectNode(el.dataset.neighbor));render()}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
document.querySelectorAll('[data-tier]').forEach(b=>b.onclick=()=>{tier=+b.dataset.tier;document.querySelectorAll('[data-tier]').forEach(x=>x.classList.toggle('active',x===b));render()});
const cbox=document.getElementById('clusters');cbox.innerHTML=`<button class="active" data-cluster="">Todos</button>`+clusterOrder.map(c=>`<button data-cluster="${c}">${esc(GRAPH.clusters[c])}</button>`).join('');cbox.querySelectorAll('button').forEach(b=>b.onclick=()=>{clusterFilter=b.dataset.cluster||null;cbox.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));render()});
document.getElementById('legend').innerHTML=Object.entries(GRAPH.state_labels).map(([k,v])=>`<span><i class="dot" style="background:${colors[k]||'#8793a8'}"></i>${esc(v)}</span>`).join('');
document.getElementById('priorities').innerHTML=GRAPH.priorities.map(p=>`<div class="priority" data-priority="${p.rank}"><b>${p.rank}. ${esc(p.title)}</b><p>${esc(p.why)}</p></div>`).join('');document.querySelectorAll('[data-priority]').forEach(el=>el.onclick=()=>{const p=GRAPH.priorities.find(x=>x.rank==el.dataset.priority);tier=1;document.querySelectorAll('[data-tier]').forEach(x=>x.classList.toggle('active',x.dataset.tier==='1'));selectNode(p.nodes[0])});
document.getElementById('search').oninput=e=>{query=e.target.value.trim().toLowerCase();render()};
function applyTransform(){viewport.setAttribute('transform',`translate(${tx} ${ty}) scale(${scale})`)}function fit(){scale=Math.min((svg.clientWidth-30)/1700,(svg.clientHeight-30)/1040);tx=15;ty=15;applyTransform()}let pan=null;svg.onpointerdown=e=>{if(e.target===svg){pan={x:e.clientX-tx,y:e.clientY-ty};svg.setPointerCapture(e.pointerId)}};svg.onpointermove=e=>{if(pan){tx=e.clientX-pan.x;ty=e.clientY-pan.y;applyTransform()}};svg.onpointerup=()=>pan=null;svg.onwheel=e=>{e.preventDefault();scale=Math.max(.25,Math.min(2.5,scale*(e.deltaY<0?1.1:.9)));applyTransform()};render();fit();window.addEventListener('resize',fit);
</script></body></html>'''


def write_html(graph):
    payload = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    page = HTML_TEMPLATE.replace("__GRAPH__", payload)
    (OUT / "index.html").write_text(page)
    DELIVERY.parent.mkdir(parents=True, exist_ok=True)
    DELIVERY.write_text(page)


def write_readme(graph):
    type_counts = Counter(n["type"] for n in graph["nodes"])
    state_counts = Counter(n["state"] for n in graph["nodes"])
    text = f"""# Mapa Mestre do VOLC O.S.

Snapshot gerado em **22/08/2026** para impedir que roadmap, documentação e implementação se percam entre camadas.

## Artefatos

- `index.html` — grafo navegável, sem dependências externas.
- `volc-os-graph.json` — fonte de verdade legível por máquina.
- `volc-os-graph.graphml` — importável em Gephi, yEd e ferramentas compatíveis.
- `nodes.csv` / `edges.csv` — análise tabular.
- `visao-executiva.mmd` — recorte Mermaid das capacidades.

## Tamanho medido

- **{len(graph['nodes'])} nós** e **{len(graph['edges'])} relações**.
- Tipos: {', '.join(f'{k}={v}' for k,v in sorted(type_counts.items()))}.
- Estados: {', '.join(f'{k}={v}' for k,v in sorted(state_counts.items()))}.

## Regra de confiança

- Contagens do Supabase: `count=exact` pelo PostgREST em 22/08/2026.
- Datas: menor/maior valor da coluna temporal selecionada.
- n8n: `ativo` significa **estado declarado no inventário**, não execução bem-sucedida.
- Relações de código: extraídas de imports, `.from(...)`, `.rpc(...)`, rotas e URLs PostgREST.
- Relações de negócio: marcadas como modeladas quando não vêm de uma FK ou chamada direta.

## Correção mais importante em relação ao workbook v0.1

O monitoramento por campanha **já existe** e é robusto em `/dashboard/campaign/:campaignId`.
A prioridade correta não é criar outro monitoramento, e sim ligar a nova jornada de Tráfego a esse cockpit,
restabelecer frescor/reconciliação e fechar os elos de atribuição e conversão.
"""
    (OUT / "README.md").write_text(text)


def main():
    import hashlib

    if not DB_SNAPSHOT.exists():
        raise SystemExit("Execute scripts/inventariar_supabase.py antes.")
    OUT.mkdir(parents=True, exist_ok=True)

    # A fonte humana primeiro, e a assinatura dela guardada: o build falha se este
    # script a tocar (ver `_guarda_fonte_humana` no fim).
    cur = carregar_curadoria()
    assinatura = hashlib.sha256(CURADORIA.read_bytes()).hexdigest()

    adicionar_nos_curados(cur)
    load_database()
    add_externals()
    add_services()
    add_frontend()
    add_backend()
    add_n8n()
    add_clickup()
    add_data_relationships()
    # Por último: as relações curadas precisam que TODOS os nós já existam para que
    # uma referência quebrada seja erro, e não um descarte silencioso.
    aplicar_arestas_curadas(cur)

    meta = dict(cur["meta"])
    meta.pop("papel", None)
    meta.pop("saida_gerada", None)
    meta.update({
        "gerado": True,
        "nao_editar": "SNAPSHOT GERADO. Edite docs/volc-os-graph/curadoria-operacional.json; "
                      "qualquer mudança feita aqui é perdida no próximo build.",
        "fonte_curada": "docs/volc-os-graph/curadoria-operacional.json",
        "gerado_por": "scripts/gerar_grafo_volc_os.py",
    })
    graph = {
        "meta": meta,
        "clusters": CLUSTERS, "state_labels": STATE_LABELS,
        "nodes": sorted(nodes.values(), key=lambda n: (n["tier"], n["cluster"], n["type"], n["label"])),
        # Ordenadas para que dois builds do mesmo insumo produzam bytes iguais — sem
        # isso, o diff do grafo vira ruído e ninguém revisa mudança de mapa.
        "edges": sorted(edges, key=lambda e: (e["source"], e["target"], e["relation"])),
        "priorities": cur["priorities"],
    }
    write_json(graph); write_csvs(graph); write_graphml(graph); write_mermaid(graph); write_html(graph); write_readme(graph)
    # Snapshots sanitizados que permitem auditar números sem credenciais.
    db_safe = json.loads(DB_SNAPSHOT.read_text())
    for item in db_safe.get("tables_and_views", []):
        item["columns"] = [c for c in item.get("columns", []) if not SENSITIVE_COLUMN.search(c)]
    (OUT / "supabase-snapshot-2026-08-22.json").write_text(json.dumps(db_safe, ensure_ascii=False, indent=2))
    if CLICKUP_SNAPSHOT.exists():
        click = json.loads(CLICKUP_SNAPSHOT.read_text())
        safe = {"tasks": [{"id": t.get("id"), "name": t.get("name"),
                            "status": (t.get("status") or {}).get("status")}
                           for t in click.get("tasks", [])]}
        (OUT / "clickup-snapshot-2026-08-22.json").write_text(json.dumps(safe, ensure_ascii=False, indent=2))

    _guarda_fonte_humana(assinatura)
    print(json.dumps({"nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                      "curados": len(cur["capabilities"]) + len(cur["concepts"]) + len(cur["documents"]),
                      "html": str(DELIVERY)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
