#!/usr/bin/env python3
"""Cria o roadmap 80/20 de performance do Foco Genial no ClickUp.

Idempotente por nome: pode ser executado novamente sem duplicar Space, Folder,
List, tarefas, checklists ou dependências. O token vem exclusivamente de
CLICKUP_API_TOKEN no ambiente.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx


API_BASE = "https://api.clickup.com/api/v2"
WORKSPACE_ID = "9007096682"
SPACE_NAME = "PERFORMANCE LAB"
FOLDER_NAME = "Foco Genial"
LIST_NAME = "Sprint 01 · Performance First (80/20)"
REQUEST_GAP_SECONDS = 0.65


TASKS: list[dict[str, Any]] = [
    {
        "code": "FG-BASE-001",
        "priority": "P0",
        "title": "Baseline mínimo e mapa de superfícies",
        "outcome": "Registrar uma fotografia confiável do site antes de qualquer alteração.",
        "why": "Sem um antes comparável, melhorias de performance e monetização viram opinião.",
        "scope": "URLs e templates representativos; mobile/desktop; headers e cache; GTM/tags inline; scripts/plugins; elemento LCP; mapa inicial de slots.",
        "tools": "SSH/Hetzner, navegador/DevTools, Lighthouse/PageSpeed, GTM, GA4 e inspeção do tema.",
        "acceptance": "Baseline anexado por template/dispositivo, acessos confirmados, superfícies inventariadas e bloqueios registrados.",
        "evidence": "Relatórios antes, waterfall, headers, screenshots, inventário de tags/scripts e URLs testadas.",
        "checklist": [
            "Confirmar acessos de leitura: site, SSH, tema, GTM, GA4 e plataformas de anúncios",
            "Selecionar URLs representativas por template e dispositivo",
            "Coletar Lighthouse/PageSpeed, waterfall e headers com cache frio e aquecido",
            "Inventariar tags, scripts, plugins, elemento LCP e slots de anúncio",
            "Anexar o baseline e registrar bloqueios sem alterar produção",
        ],
        "refs": [
            ("PageSpeed Insights", "https://pagespeed.web.dev/"),
            ("Lighthouse", "https://developer.chrome.com/docs/lighthouse/overview"),
            ("WebPageTest", "https://www.webpagetest.org/"),
        ],
        "deps": [],
        "hours": 4,
    },
    {
        "code": "FG-PERF-005",
        "priority": "P0",
        "title": "Contrato mínimo do dataLayer",
        "outcome": "Publicar um schema pequeno e previsível para página, campanha, template e monetização.",
        "why": "O contrato elimina leituras repetidas do DOM e permite que métricas de experiência e receita conversem.",
        "scope": "project_id, site_id, page_type, template, content_category, device_class, campaign_id e ad_layout_version; sem reconstruir consentimento.",
        "tools": "Tema/WordPress, GTM Preview, console do navegador e GA4 DebugView.",
        "acceptance": "Schema versionado disponível antes das tags dependentes, sem valores pessoais e sem variáveis DOM custosas para os campos centrais.",
        "evidence": "Exemplo real do dataLayer, validação no Preview e mapa campo → consumidor.",
        "checklist": [
            "Definir nomes, tipos, obrigatoriedade e versão do schema mínimo",
            "Mapear origem de cada campo sem duplicar cálculo no GTM",
            "Publicar os dados antes das tags que os consomem",
            "Remover ou aposentar leituras DOM/JavaScript redundantes do caminho crítico",
            "Validar o contrato em templates representativos e anexar exemplo",
        ],
        "refs": [
            ("GTM dataLayer", "https://developers.google.com/tag-platform/tag-manager/datalayer"),
            ("GA4 event collection", "https://developers.google.com/analytics/devguides/collection/ga4"),
        ],
        "deps": ["FG-BASE-001"],
        "hours": 4,
    },
    {
        "code": "FG-PERF-001",
        "priority": "P0",
        "title": "Instrumentar Core Web Vitals em campo via GTM e GA4",
        "outcome": "Receber LCP, INP e CLS reais no GA4, com FCP/TTFB como diagnóstico e contexto suficiente para segmentar.",
        "why": "RUM mostra a experiência real; Lighthouse continua como ferramenta de diagnóstico, não como fonte única de decisão.",
        "scope": "web-vitals com atribuição quando disponível; valor, rating, delta, id e navigationType; eventos deduplicados e compatíveis com o consentimento já existente.",
        "tools": "GTM, web-vitals, GA4 DebugView, navegador e dataLayer.",
        "acceptance": "Eventos aparecem uma vez por métrica/navegação no DebugView, com tipos e unidades corretos, em mobile/desktop e nos templates principais.",
        "evidence": "Preview do GTM, DebugView, payloads de exemplo e registro da versão publicada.",
        "checklist": [
            "Escolher template GTM ou biblioteca web-vitals e registrar a versão",
            "Instrumentar LCP, INP, CLS e métricas diagnósticas FCP/TTFB",
            "Enviar valor, rating, delta, id, navigationType e atribuição disponível",
            "Validar deduplicação, unidades, tipos e ausência de erro no navegador",
            "Confirmar eventos no GA4 DebugView em templates e dispositivos representativos",
        ],
        "refs": [
            ("web-vitals", "https://github.com/GoogleChrome/web-vitals"),
            ("GA4 measurement", "https://developers.google.com/analytics/devguides/collection/ga4"),
            ("Core Web Vitals", "https://web.dev/articles/vitals"),
        ],
        "deps": ["FG-BASE-001", "FG-PERF-005"],
        "hours": 6,
    },
    {
        "code": "FG-PERF-003",
        "priority": "P1",
        "title": "CrUX como baseline externo",
        "outcome": "Registrar o p75 agregado de experiência por origem e, quando elegível, por URL e dispositivo.",
        "why": "CrUX oferece a visão macro externa usada pelo ecossistema Chrome, complementando o RUM próprio.",
        "scope": "PHONE/DESKTOP; LCP, INP, CLS, FCP e TTFB quando disponíveis; falha controlada para dados insuficientes.",
        "tools": "CrUX API, armazenamento de snapshot e rotina reexecutável.",
        "acceptance": "Consulta reproduzível retorna dados ou registra claramente ausência de elegibilidade, sem confundir CrUX com o RUM operacional.",
        "evidence": "Resposta sanitizada, data da coleta, origem/URLs consultadas e snapshot p75/histogramas.",
        "checklist": [
            "Confirmar chave/projeto e elegibilidade da origem na CrUX API",
            "Consultar origem em PHONE e DESKTOP",
            "Consultar URLs prioritárias quando houver dados suficientes",
            "Persistir p75/histogramas, contexto e data da coleta",
            "Registrar ausência de dados como resultado controlado e anexar evidência",
        ],
        "refs": [
            ("CrUX API", "https://developer.chrome.com/docs/crux/api"),
            ("CrUX methodology", "https://developer.chrome.com/docs/crux/methodology"),
        ],
        "deps": ["FG-BASE-001"],
        "hours": 3,
    },
    {
        "code": "FG-PERF-006",
        "priority": "P0",
        "title": "Consolidar cache, headers e higiene do tema",
        "outcome": "Alinhar WordPress/tema, cache de aplicação, servidor e CDN para reduzir TTFB e entregar assets estáveis.",
        "why": "Camadas de cache conflitantes e scripts herdados anulam otimizações de frontend e dificultam rollback.",
        "scope": "WP Rocket ou equivalente, Nginx, Cloudflare/CDN, compressão, protocolos, Cache-Control, purge e carregamentos duplicados do tema.",
        "tools": "SSH/Hetzner, Nginx, WordPress, CDN, curl/headers e Lighthouse.",
        "acceptance": "Cache frio/aquecido previsível, assets com políticas coerentes, compressão ativa, sem duplicidades críticas e rollback testável.",
        "evidence": "Headers antes/depois, configuração alterada, comandos de validação, backup e procedimento de rollback.",
        "checklist": [
            "Criar backup e registrar rollback antes de alterar cache/servidor/tema",
            "Mapear responsabilidades entre WordPress, plugin de cache, Nginx e CDN",
            "Validar compressão, HTTP/2 ou HTTP/3 e Cache-Control por tipo de recurso",
            "Remover conflitos, duplicidades e carregamentos herdados de maior custo",
            "Comparar cache frio/aquecido e anexar headers e métricas antes/depois",
        ],
        "refs": [
            ("HTTP caching", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching"),
            ("Cache-Control", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control"),
        ],
        "deps": ["FG-BASE-001"],
        "hours": 8,
    },
    {
        "code": "FG-PERF-007",
        "priority": "P0",
        "title": "Otimizar LCP por template",
        "outcome": "Fazer o elemento principal de cada template ser descoberto cedo, transferido com tamanho correto e renderizado sem bloqueios evitáveis.",
        "why": "LCP depende da soma de TTFB, descoberta, transferência e atraso de renderização; otimizar só a imagem pode não resolver.",
        "scope": "Home e templates principais; elemento LCP, HTML inicial, dimensões, srcset/sizes, WebP/AVIF, preload/fetchpriority, CSS/fontes bloqueantes.",
        "tools": "DevTools Performance, Lighthouse, PageSpeed, RUM, tema e pipeline de imagens.",
        "acceptance": "Elemento LCP conhecido por template; nenhuma imagem LCP em lazy; dimensões corretas; p75 perseguindo ≤2,5s sem regressão de CLS.",
        "evidence": "Elemento e breakdown LCP antes/depois, waterfall, diff do tema e eventos RUM após publicação.",
        "checklist": [
            "Identificar elemento e breakdown do LCP por template e dispositivo",
            "Garantir presença no HTML inicial e remover descoberta tardia por JavaScript",
            "Aplicar dimensões, srcset/sizes e formato adequado à imagem real",
            "Usar eager/fetchpriority/preload somente no LCP confirmado",
            "Validar Lighthouse/PageSpeed e RUM sem regressão de CLS",
        ],
        "refs": [
            ("Optimize LCP", "https://web.dev/articles/optimize-lcp"),
            ("LCP", "https://web.dev/articles/lcp"),
        ],
        "deps": ["FG-BASE-001"],
        "hours": 8,
    },
    {
        "code": "FG-PERF-008",
        "priority": "P1",
        "title": "Reduzir JavaScript e proteger INP",
        "outcome": "Reduzir bloqueio da main thread e manter interações responsivas mesmo com GTM e anúncios ativos.",
        "why": "Tema, plugins, GTM e ad tech disputam a mesma thread; o custo combinado é o que o usuário sente.",
        "scope": "Long tasks, scripts de terceiros, listeners, plugins, execução GTM, carregamento deferido e trabalho não crítico.",
        "tools": "DevTools Performance, Long Tasks/LoAF, web-vitals attribution, Coverage e inventário de terceiros.",
        "acceptance": "Principais long tasks atribuídas e reduzidas; interações críticas sem trabalho dispensável; INP p75 perseguindo ≤200ms.",
        "evidence": "Traces antes/depois, scripts responsáveis, alterações e eventos INP com atribuição.",
        "checklist": [
            "Capturar traces e atribuir long tasks aos scripts/handlers responsáveis",
            "Remover ou adiar plugins e terceiros sem valor no caminho crítico",
            "Reduzir listeners, leituras DOM e gatilhos GTM custosos",
            "Quebrar trabalho longo e priorizar feedback visual nas interações críticas",
            "Validar traces e INP em campo sem perda funcional",
        ],
        "refs": [
            ("Optimize INP", "https://web.dev/articles/optimize-inp"),
            ("Long animation frames", "https://web.dev/articles/long-animation-frames"),
            ("web-vitals attribution", "https://github.com/GoogleChrome/web-vitals"),
        ],
        "deps": ["FG-BASE-001", "FG-PERF-005"],
        "hours": 8,
    },
    {
        "code": "FG-ADS-001",
        "priority": "P0",
        "title": "Loader único, mapa de slots e reserva de CLS",
        "outcome": "Estabelecer uma arquitetura de anúncios única, assíncrona e visualmente estável antes de otimizar posições.",
        "why": "Lazy loading ou prioridade ATF sobre loaders duplicados e slots sem dimensão cria solicitações duplicadas, CLS e medições ruins.",
        "scope": "Um loader; inventário de slots/IDs/tamanhos/breakpoints; containers com espaço reservado; regras de collapse; evitar fluid ATF.",
        "tools": "Tema, GPT/AdSense/GAM conforme implementação real, DevTools Network/Layout Shifts e relatórios de anúncios.",
        "acceptance": "Um único loader, nenhum slot duplicado, mapa documentado e containers estáveis; CLS p75 perseguindo ≤0,1.",
        "evidence": "Mapa de slots, waterfall, layout-shift attribution, diff CSS/JS e screenshots por breakpoint.",
        "checklist": [
            "Inventariar loaders, IDs, tamanhos, breakpoints e posição de cada slot",
            "Consolidar carregamento assíncrono sem duplicidade",
            "Reservar dimensões/min-height por breakpoint antes da resposta do anúncio",
            "Definir collapse/fallback sem salto perceptível e evitar fluid ATF",
            "Validar requests e layout shifts em mobile/desktop e anexar mapa final",
        ],
        "refs": [
            ("Minimize layout shift", "https://developers.google.com/publisher-tag/guides/minimize-layout-shift"),
            ("Optimize CLS", "https://web.dev/articles/optimize-cls"),
        ],
        "deps": ["FG-BASE-001"],
        "hours": 6,
    },
    {
        "code": "FG-ADS-004",
        "priority": "P0",
        "title": "Lazy loading de anúncios abaixo da dobra",
        "outcome": "Adiar requests e renderização de slots BTF até proximidade útil do viewport, preservando oportunidade de leilão e viewability.",
        "why": "Solicitar todos os anúncios no carregamento disputa rede/CPU com conteúdo e desperdiça impressões pouco visíveis.",
        "scope": "Somente BTF; thresholds por dispositivo; espaço reservado; comportamento em scroll rápido; métricas de request, render e viewability.",
        "tools": "GPT/stack real de anúncios, IntersectionObserver quando aplicável, Network, Performance e relatórios Active View.",
        "acceptance": "Slots BTF não solicitam cedo, não duplicam requests, não geram CLS e mantêm ou melhoram viewability sem queda material de receita.",
        "evidence": "Waterfall/filmstrip antes/depois, logs de slot, CLS, Active View e receita/RPM na janela acordada.",
        "checklist": [
            "Classificar slots BTF elegíveis e excluir slots ATF do mecanismo",
            "Definir margens de fetch/render por dispositivo com hipótese registrada",
            "Preservar container e impedir requests/renderizações duplicadas",
            "Testar scroll lento/rápido, navegação e diferentes breakpoints",
            "Comparar CWV, Active View, impressões e receita antes/depois",
        ],
        "refs": [
            ("GPT lazy loading sample", "https://developers.google.com/publisher-tag/samples/lazy-loading"),
            ("Control ad loading", "https://developers.google.com/publisher-tag/guides/control-ad-loading"),
        ],
        "deps": ["FG-ADS-001", "FG-PERF-001"],
        "hours": 6,
    },
    {
        "code": "FG-ADS-003",
        "priority": "P1",
        "title": "Priorizar ATF sem bloquear conteúdo",
        "outcome": "Dar prioridade controlada ao melhor slot próximo/acima da dobra sem atrasar o conteúdo principal.",
        "why": "ATF tende a monetizar bem, mas pode competir diretamente com LCP, gerar CLS e prejudicar leitura.",
        "scope": "Um candidato por template; posição, ordem de request, reserva de espaço e concorrência de rede com o LCP; sem saturar a dobra.",
        "tools": "Tema, stack de anúncios, DevTools Priority/Network, RUM, Active View e receita por posição.",
        "acceptance": "Slot escolhido carrega de forma assíncrona, não bloqueia LCP/conteúdo, mantém estabilidade e demonstra ganho ou neutralidade econômica.",
        "evidence": "Waterfall de prioridades, LCP/CLS/INP, Active View, receita por posição e decisão manter/reverter.",
        "checklist": [
            "Escolher um único candidato ATF/próximo à dobra por template",
            "Garantir conteúdo principal e LCP priorizados antes da monetização concorrente",
            "Reservar espaço e impedir inserção dinâmica acima do conteúdo existente",
            "Testar mobile/desktop, cache frio/aquecido e diferentes fontes de tráfego",
            "Comparar CWV, Active View e receita e registrar decisão",
        ],
        "refs": [
            ("Control ad loading", "https://developers.google.com/publisher-tag/guides/control-ad-loading"),
            ("Optimize LCP", "https://web.dev/articles/optimize-lcp"),
            ("Optimize CLS", "https://web.dev/articles/optimize-cls"),
        ],
        "deps": ["FG-ADS-001", "FG-PERF-001", "FG-PERF-007"],
        "hours": 6,
    },
    {
        "code": "FG-PERF-002",
        "priority": "P0",
        "title": "Correlacionar CWV com receita e métricas de anúncios",
        "outcome": "Responder quanto a experiência vale financeiramente por URL, template, dispositivo, campanha e versão do layout de anúncios.",
        "why": "A meta não é apenas melhorar CWV; é encontrar configurações que aumentem ou protejam receita sem degradar experiência.",
        "scope": "LCP/INP/CLS p75 e faixas; Active View; impressões; RPM; receita por sessão/mil sessões; chaves de união e cardinalidade controlada.",
        "tools": "GA4, relatórios GAM/AdSense conforme fonte, Looker Studio ou camada analítica disponível e dataLayer.",
        "acceptance": "Dashboard segmenta por template/dispositivo e cruza CWV com receita/ads quando disponíveis, com definições e limitações documentadas.",
        "evidence": "Dicionário de métricas, consultas/fonte, dashboard, amostra validada e decisões geradas.",
        "checklist": [
            "Definir chaves de união e métricas econômicas sem cardinalidade explosiva",
            "Validar coleta de page/template/device/campaign/ad_layout_version",
            "Integrar dados GA4/RUM e fonte real de receita/anúncios",
            "Construir cortes por faixas de LCP/INP/CLS e por template/dispositivo",
            "Validar amostras, documentar limitações e publicar o dashboard",
        ],
        "refs": [
            ("GA4 reporting", "https://developers.google.com/analytics/devguides/reporting/data/v1"),
            ("Looker Studio", "https://cloud.google.com/looker/docs/studio"),
            ("Core Web Vitals", "https://web.dev/articles/vitals"),
        ],
        "deps": ["FG-PERF-001", "FG-PERF-005", "FG-ADS-001"],
        "hours": 8,
    },
    {
        "code": "FG-QA-001",
        "priority": "P0",
        "title": "Validação integrada, rollout e decisão",
        "outcome": "Concluir a sprint com comparação antes/depois, regressões conhecidas, rollback e próximos experimentos priorizados.",
        "why": "Mudanças isoladas podem parecer boas em laboratório e piorar receita, campo ou outro template.",
        "scope": "Templates/dispositivos, cache frio/aquecido, RUM/CrUX, LCP/INP/CLS, Active View, RPM/receita, erros funcionais e changelog.",
        "tools": "Relatórios acumulados, Lighthouse/PageSpeed, GA4, CrUX, ads reporting, SSH e histórico do ClickUp.",
        "acceptance": "Antes/depois verificável, P0 sem pendências críticas, decisão manter/reverter por mudança e backlog P1/P2 reordenado por impacto.",
        "evidence": "Matriz final de métricas, links para todos os artefatos, changelog, rollback e resumo executivo curto.",
        "checklist": [
            "Executar matriz final por template, dispositivo e estado de cache",
            "Comparar LCP ≤2,5s, INP ≤200ms e CLS ≤0,1 no p75 quando houver volume",
            "Verificar Active View, impressões, RPM/receita e erros funcionais",
            "Registrar manter/reverter, rollback e causa de qualquer regressão",
            "Publicar resumo final e reordenar o backlog pelo impacto observado",
        ],
        "refs": [
            ("Core Web Vitals", "https://web.dev/articles/vitals"),
            ("CrUX methodology", "https://developer.chrome.com/docs/crux/methodology"),
        ],
        "deps": [
            "FG-PERF-003",
            "FG-PERF-006",
            "FG-PERF-007",
            "FG-PERF-008",
            "FG-ADS-004",
            "FG-ADS-003",
            "FG-PERF-002",
        ],
        "hours": 6,
    },
]


class ClickUp:
    def __init__(self, token: str) -> None:
        self.client = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": token, "Content-Type": "application/json"},
            timeout=60,
        )

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in range(8):
            response = self.client.request(method, path, **kwargs)
            if response.status_code != 429:
                break
            wait = float(response.headers.get("Retry-After", 2 ** min(attempt, 5)))
            time.sleep(max(wait, 1.0))
        time.sleep(REQUEST_GAP_SECONDS)
        if response.is_error:
            raise RuntimeError(f"ClickUp {method} {path}: {response.status_code} {response.text[:500]}")
        if not response.content:
            return {}
        return response.json()


def task_name(task: dict[str, Any]) -> str:
    return f"[{task['priority']}] {task['code']} · {task['title']}"


def task_description(task: dict[str, Any]) -> str:
    refs = "\n".join(f"- [{label}]({url})" for label, url in task["refs"])
    deps = ", ".join(task["deps"]) if task["deps"] else "Nenhuma"
    return f"""## Resultado
{task['outcome']}

## Por que agora
{task['why']}

## Escopo 80/20
{task['scope']}

## Ferramentas e acessos
{task['tools']}

## Dependências
{deps}

## Critério de aceite
{task['acceptance']}

## Evidência obrigatória
{task['evidence']}

## Regra de execução multiagente
Antes de alterar qualquer superfície, comentar qual arquivo/configuração será tocado. Não executar em paralelo com outro agente na mesma superfície. Ao terminar, registrar mudança, teste, evidência e rollback antes de mover para revisão.

## Referências
{refs}
"""


def exact(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("name") == name), None)


def ensure_hierarchy(api: ClickUp) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    created: list[str] = []
    spaces = api.request("GET", f"/team/{WORKSPACE_ID}/space", params={"archived": "false"})["spaces"]
    space = exact(spaces, SPACE_NAME)
    if not space:
        space = api.request(
            "POST",
            f"/team/{WORKSPACE_ID}/space",
            json={"name": SPACE_NAME, "multiple_assignees": True, "features": {}},
        )
        created.append("space")

    folders = api.request("GET", f"/space/{space['id']}/folder", params={"archived": "false"})["folders"]
    folder = exact(folders, FOLDER_NAME)
    if not folder:
        folder = api.request("POST", f"/space/{space['id']}/folder", json={"name": FOLDER_NAME})
        created.append("folder")

    lists = api.request("GET", f"/folder/{folder['id']}/list", params={"archived": "false"})["lists"]
    list_obj = exact(lists, LIST_NAME)
    if not list_obj:
        list_obj = api.request(
            "POST",
            f"/folder/{folder['id']}/list",
            json={
                "name": LIST_NAME,
                "markdown_content": (
                    "# Missão\nOtimizar performance e monetização do Foco Genial pelo caminho crítico 80/20.\n\n"
                    "**Fonte da verdade:** esta lista. **Concluído:** somente após evidência e validação.\n\n"
                    "Compliance/consentimento já resolvidos ficam fora do escopo ativo, salvo regressão."
                ),
                "priority": 1,
                "status": "purple",
            },
        )
        created.append("list")
    return space, folder, list_obj, created


def ensure_tasks(api: ClickUp, list_id: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    response = api.request(
        "GET",
        f"/list/{list_id}/task",
        params={"include_closed": "true", "subtasks": "true", "include_markdown_description": "true"},
    )
    existing = {item["name"]: item for item in response.get("tasks", [])}
    by_code: dict[str, dict[str, Any]] = {}
    created: list[str] = []
    for task in TASKS:
        name = task_name(task)
        item = existing.get(name)
        if not item:
            item = api.request(
                "POST",
                f"/list/{list_id}/task",
                json={
                    "name": name,
                    "markdown_content": task_description(task),
                    "priority": 1 if task["priority"] == "P0" else 2,
                    "time_estimate": task["hours"] * 60 * 60 * 1000,
                    "notify_all": False,
                },
            )
            created.append(task["code"])
        by_code[task["code"]] = item
    return by_code, created


def ensure_checklists(api: ClickUp, by_code: dict[str, dict[str, Any]]) -> list[str]:
    changed: list[str] = []
    for spec in TASKS:
        task = api.request("GET", f"/task/{by_code[spec['code']]['id']}")
        checklist = next((c for c in task.get("checklists", []) if c.get("name") == "Execução e aceite"), None)
        if not checklist:
            response = api.request(
                "POST",
                f"/task/{task['id']}/checklist",
                json={"name": "Execução e aceite"},
            )
            checklist = response.get("checklist")
            if not checklist:
                refreshed = api.request("GET", f"/task/{task['id']}")
                checklist = next(c for c in refreshed.get("checklists", []) if c.get("name") == "Execução e aceite")
        existing_items = {item.get("name") for item in checklist.get("items", [])}
        task_changed = False
        for item_name in spec["checklist"]:
            if item_name not in existing_items:
                api.request(
                    "POST",
                    f"/checklist/{checklist['id']}/checklist_item",
                    json={"name": item_name},
                )
                task_changed = True
        if task_changed:
            changed.append(spec["code"])
    return changed


def ensure_dependencies(api: ClickUp, by_code: dict[str, dict[str, Any]]) -> list[str]:
    created: list[str] = []
    for spec in TASKS:
        if not spec["deps"]:
            continue
        task = api.request("GET", f"/task/{by_code[spec['code']]['id']}")
        current = {str(dep.get("depends_on")) for dep in task.get("dependencies", [])}
        for dependency_code in spec["deps"]:
            dependency_id = str(by_code[dependency_code]["id"])
            if dependency_id not in current:
                api.request(
                    "POST",
                    f"/task/{task['id']}/dependency",
                    json={"depends_on": dependency_id},
                )
                created.append(f"{spec['code']} <- {dependency_code}")
    return created


def main() -> int:
    token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
    if not token:
        print("CLICKUP_API_TOKEN ausente", file=sys.stderr)
        return 2

    api = ClickUp(token)
    space, folder, list_obj, hierarchy_created = ensure_hierarchy(api)
    by_code, tasks_created = ensure_tasks(api, str(list_obj["id"]))
    checklists_changed = ensure_checklists(api, by_code)
    dependencies_created = ensure_dependencies(api, by_code)

    print(
        json.dumps(
            {
                "workspace_id": WORKSPACE_ID,
                "space": {"id": space["id"], "name": space["name"]},
                "folder": {"id": folder["id"], "name": folder["name"]},
                "list": {"id": list_obj["id"], "name": list_obj["name"]},
                "hierarchy_created": hierarchy_created,
                "tasks_total": len(by_code),
                "tasks_created": tasks_created,
                "checklists_changed": checklists_changed,
                "dependencies_created": dependencies_created,
                "task_ids": {code: item["id"] for code, item in by_code.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
