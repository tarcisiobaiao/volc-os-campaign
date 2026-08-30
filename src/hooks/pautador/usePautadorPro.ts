// ============================================
// PAUTADOR PRO — hook principal (useState/useEffect/useCallback, padrão do repo)
// Modo duplo:
//  - Supabase persistido (migração v7 aplicada + backend com service-role)
//  - Efêmero/demo (backend em modo dry ou sem Supabase) — claramente sinalizado
// ============================================

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useToast } from '@/hooks/use-toast';
import {
  pautadorService,
  MigrationPendingError,
} from '@/services/pautadorService';
import { pautadorApi, PautadorApiError } from '@/lib/pautadorApi';
import {
  countryExists,
  normalizeCountryInput,
  normKey,
  toCountryRow,
} from '@/lib/pautadorCountries';
import type {
  CulturalIntelligence,
  DiscoveryResponse,
  FunnelPage,
  FunnelResult,
  Insights,
  KeywordCluster,
  MineResult,
  Opportunity,
  OpportunityStatus,
  PautadorCountry,
  PautadorRun,
  Persona,
  RunStats,
} from '@/types/pautador';

const FALLBACK_COUNTRIES: PautadorCountry[] = [
  { country_code: 'GB', country_name: 'Reino Unido', native_language: 'en-GB', market_tier: 'high_value', flag_emoji: '🇬🇧' },
  { country_code: 'PT', country_name: 'Portugal', native_language: 'pt-PT', market_tier: 'medium_value', flag_emoji: '🇵🇹' },
  { country_code: 'GT', country_name: 'Guatemala', native_language: 'es-GT', market_tier: 'volume_play', flag_emoji: '🇬🇹' },
  { country_code: 'US', country_name: 'Estados Unidos', native_language: 'en-US', market_tier: 'high_value', flag_emoji: '🇺🇸' },
  { country_code: 'BR', country_name: 'Brasil', native_language: 'pt-BR', market_tier: 'medium_value', flag_emoji: '🇧🇷' },
  { country_code: 'DE', country_name: 'Alemanha', native_language: 'de-DE', market_tier: 'high_value', flag_emoji: '🇩🇪' },
];

export type DataSource = 'supabase' | 'ephemeral' | 'none';

export function oppKey(o: Opportunity): string {
  return o.id ? `db-${o.id}` : `seed-${o.seed_id || o.keyword}`;
}

export function usePautadorPro() {
  const { toast } = useToast();

  const [countries, setCountries] = useState<PautadorCountry[]>(FALLBACK_COUNTRIES);
  const [selectedCountry, setSelectedCountry] = useState<string>('Reino Unido');

  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [source, setSource] = useState<DataSource>('none');
  const [migrationPending, setMigrationPending] = useState(false);

  const [run, setRun] = useState<PautadorRun | null>(null);
  const [cultural, setCultural] = useState<CulturalIntelligence | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [stats, setStats] = useState<RunStats | null>(null);

  const [clusters, setClusters] = useState<Record<string, KeywordCluster>>({});
  const [funnels, setFunnels] = useState<Record<string, FunnelPage[]>>({});
  // full rich pipeline outputs (Fase 2 / Fase 3) keyed by oppKey
  const [mineResults, setMineResults] = useState<Record<string, MineResult>>({});
  const [funnelResults, setFunnelResults] = useState<Record<string, FunnelResult>>({});

  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [addingCountry, setAddingCountry] = useState(false);
  // Set so concurrent mine/funnel ops each keep their own spinner.
  const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set());
  const addBusy = useCallback((k: string) => setBusyKeys((p) => { const n = new Set(p); n.add(k); return n; }), []);
  const removeBusy = useCallback((k: string) => setBusyKeys((p) => { const n = new Set(p); n.delete(k); return n; }), []);

  // --- initial load ---
  const loadInitial = useCallback(async () => {
    setLoading(true);
    // countries: supabase -> backend -> fallback
    try {
      const cs = await pautadorService.fetchCountries();
      if (cs.length) setCountries(cs);
    } catch (err) {
      if (err instanceof MigrationPendingError) {
        setMigrationPending(true);
      }
      try {
        const res = await pautadorApi.countries();
        if (res.countries?.length) setCountries(res.countries);
      } catch {
        /* keep fallback */
      }
    }
    // latest run + opportunities
    try {
      const latest = await pautadorService.fetchLatestRun();
      if (latest) {
        setRun(latest);
        setCultural(latest.cultural_intelligence || null);
        setPersonas(latest.personas || []);
        setInsights(latest.insights || null);
        const opps = await pautadorService.fetchOpportunities(latest.id);
        // Don't wipe in-memory ephemeral cards when the DB has none (refresh in demo mode).
        setOpportunities((prev) => (opps.length || !prev.some((o) => o._ephemeral) ? opps : prev));
        setSource((prev) => (opps.length ? 'supabase' : prev === 'ephemeral' ? 'ephemeral' : 'none'));
        if (latest.country) setSelectedCountry(latest.country);
      } else {
        setSource('none');
      }
      setMigrationPending(false);
    } catch (err) {
      if (err instanceof MigrationPendingError) {
        setMigrationPending(true);
        setSource('none');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  const applyDiscovery = useCallback(
    async (resp: DiscoveryResponse) => {
      setCultural(resp.cultural_intelligence);
      setPersonas(resp.personas);
      setInsights(resp.insights);
      setStats(resp.stats);
      setRun(resp.run);
      if (resp.persisted && resp.run.id) {
        const opps = await pautadorService.fetchOpportunities(resp.run.id);
        setOpportunities(opps);
        setSource('supabase');
        setMigrationPending(false);
      } else {
        setOpportunities(resp.opportunities.map((o) => ({ ...o, _ephemeral: true })));
        setSource('ephemeral');
      }
    },
    [],
  );

  const runDiscovery = useCallback(
    async (countryName?: string) => {
      const country = countryName || selectedCountry;
      const meta = countries.find((c) => c.country_name === country);
      setDiscovering(true);
      try {
        const resp = await pautadorApi.discovery({
          country,
          country_code: meta?.country_code,
          native_language: meta?.native_language,
          count: 40,
        });
        await applyDiscovery(resp);
        const mode = resp.persisted ? 'persistida no Supabase' : 'em modo demo (não persistida)';
        toast({
          title: `Descoberta concluída — ${resp.opportunities.length} oportunidades`,
          description: `Motor: ${resp.meta.engine} · ${mode}.${resp.warnings.length ? ' ' + resp.warnings.join(' ') : ''}`,
        });
      } catch (err) {
        const message = err instanceof PautadorApiError ? err.message : 'Erro ao disparar descoberta';
        toast({ title: 'Falha na descoberta', description: message, variant: 'destructive' });
      } finally {
        setDiscovering(false);
      }
    },
    [selectedCountry, countries, applyDiscovery, toast],
  );

  const patchLocalStatus = useCallback((key: string, status: OpportunityStatus) => {
    setOpportunities((prev) =>
      prev.map((o) => (oppKey(o) === key ? { ...o, status } : o)),
    );
  }, []);

  const mineOpportunity = useCallback(
    async (opp: Opportunity) => {
      const key = oppKey(opp);
      addBusy(key);
      try {
        const res = await pautadorApi.mine(opp.id ?? 0, opp._ephemeral ? opp : undefined);
        setMineResults((prev) => ({ ...prev, [key]: res }));
        setClusters((prev) => ({ ...prev, [key]: res.cluster }));
        patchLocalStatus(key, 'mining');
        const ads = res.production_ads_queue?.length ?? 0;
        const seo = res.content_seo_queue?.length ?? 0;
        const live = (res.services_used || []).some((s) => s.endsWith(':live'));
        toast({
          title: 'Mineração concluída',
          description:
            `${ads} keywords de ADS · ${seo} de conteúdo · ${res.funis_sugeridos?.length ?? 0} funis. ` +
            `Fonte: ${live ? 'APIs reais' : 'mock'}.${res.warnings?.length ? ' ⚠ ' + res.warnings.join(' ') : ''}`,
        });
        return res;
      } catch (err) {
        const message = err instanceof PautadorApiError ? err.message : 'Erro ao minerar';
        toast({ title: 'Falha na mineração', description: message, variant: 'destructive' });
        return null;
      } finally {
        removeBusy(key);
      }
    },
    [patchLocalStatus, toast, addBusy, removeBusy],
  );

  const buildFunnel = useCallback(
    async (opp: Opportunity) => {
      const key = oppKey(opp);
      // For an ephemeral (dry) card, the backend has no DB cluster to read, so
      // pass the freshly-mined result inline. For a DB card, the backend reads
      // the persisted cluster and returns 409 if mining is missing.
      const inlineCluster = opp._ephemeral ? mineResults[key] : undefined;
      if (opp._ephemeral && !inlineCluster) {
        toast({
          title: 'Minere antes de gerar o funil',
          description: 'Clique em Minerar primeiro para gerar as keywords de suporte.',
          variant: 'destructive',
        });
        return null;
      }
      addBusy(key);
      try {
        const res = await pautadorApi.funnel(
          opp.id ?? 0,
          opp._ephemeral ? opp : undefined,
          inlineCluster,
        );
        setFunnelResults((prev) => ({ ...prev, [key]: res }));
        setFunnels((prev) => ({ ...prev, [key]: res.funnel.pages }));
        patchLocalStatus(key, 'funnel');
        toast({
          title: 'Funil construído',
          description:
            `${res.funnel.pages.length} páginas · ${res.writing_jobs?.length ?? 0} briefings.` +
            `${res.warnings?.length ? ' ⚠ ' + res.warnings.join(' ') : ''}`,
        });
        return res;
      } catch (err) {
        const message = err instanceof PautadorApiError ? err.message : 'Erro ao construir funil';
        toast({ title: 'Falha no funil', description: message, variant: 'destructive' });
        return null;
      } finally {
        removeBusy(key);
      }
    },
    [patchLocalStatus, toast, addBusy, removeBusy, mineResults],
  );

  const moveOpportunity = useCallback(
    async (opp: Opportunity, newStatus: OpportunityStatus) => {
      if (newStatus === opp.status) return;
      const key = oppKey(opp);
      // Phase triggers
      if (newStatus === 'mining') return void mineOpportunity(opp);
      if (newStatus === 'funnel') return void buildFunnel(opp);

      // simple move
      patchLocalStatus(key, newStatus); // optimistic
      if (opp._ephemeral || !opp.id) return;
      try {
        await pautadorService.updateOpportunityStatus(opp.id, newStatus);
      } catch (err) {
        patchLocalStatus(key, opp.status); // revert
        toast({ title: 'Erro ao mover card', variant: 'destructive' });
      }
    },
    [mineOpportunity, buildFunnel, patchLocalStatus, toast],
  );

  const addOpportunity = useCallback(
    async (opp: Opportunity) => {
      // Persist via the backend when we have a run to attach to (opportunities.run_id is NOT NULL).
      if (run?.id && pautadorApi.configured) {
        try {
          const res = await pautadorApi.addOpportunity({ ...opp, run_id: run.id });
          const saved = (res.opportunity as Opportunity) || opp;
          setOpportunities((prev) => [{ ...saved, _ephemeral: !res.persisted }, ...prev]);
          toast({
            title: res.persisted ? 'Oportunidade adicionada' : 'Oportunidade adicionada (local)',
            description: opp.keyword,
          });
          return;
        } catch (err) {
          const message = err instanceof PautadorApiError ? err.message : 'Erro ao adicionar';
          toast({ title: 'Não persistida — mantida localmente', description: message, variant: 'destructive' });
        }
      }
      setOpportunities((prev) => [{ ...opp, _ephemeral: true }, ...prev]);
    },
    [run, toast],
  );

  // Add a new country (typed by the admin). Normalizes deterministically,
  // dedupes (accent/case-insensitive), persists via Supabase (admin RLS),
  // and falls back to a local/ephemeral entry if the table is missing or denied.
  const addCountry = useCallback(
    async (rawInput: string) => {
      const input = rawInput.trim();
      if (!input) return null;
      const canon = normalizeCountryInput(input);
      const row = toCountryRow(canon);

      const existing = countryExists(countries, row);
      if (existing) {
        setSelectedCountry(existing.country_name);
        toast({ title: 'País já existe', description: existing.country_name });
        return existing;
      }

      setAddingCountry(true);
      try {
        const created = await pautadorService.createCountry(row);
        setCountries((prev) =>
          [...prev, created].sort((a, b) => a.country_name.localeCompare(b.country_name)),
        );
        setSelectedCountry(created.country_name);
        toast({ title: 'País adicionado', description: `${created.flag_emoji || ''} ${created.country_name}`.trim() });
        return created;
      } catch (err: any) {
        // Fallback: keep it locally so the admin can still run a discovery for it.
        const local = { ...row } as PautadorCountry;
        setCountries((prev) =>
          prev.some((c) => normKey(c.country_name) === normKey(row.country_name))
            ? prev
            : [...prev, local].sort((a, b) => a.country_name.localeCompare(b.country_name)),
        );
        setSelectedCountry(local.country_name);
        let reason = 'Adicionado localmente (não persistido).';
        let destructive = true;
        if (err instanceof MigrationPendingError) {
          reason = 'Tabelas ausentes — adicionado localmente. Aplique a migração para salvar.';
        } else if (err?.code === '23505') {
          reason = 'Já existia no banco (código duplicado).';
          destructive = false;
        } else if (err?.code === '42501' || /permission|rls|policy/i.test(err?.message || '')) {
          reason = 'Sem permissão (apenas ADMIN salva) — adicionado localmente.';
        }
        toast({ title: 'País adicionado (local)', description: reason, variant: destructive ? 'destructive' : undefined });
        return local;
      } finally {
        setAddingCountry(false);
      }
    },
    [countries, toast],
  );

  // --- KPIs ---
  const kpis = useMemo(() => {
    const total = opportunities.length;
    const gold = opportunities.filter((o) => o.tier === 'S').length;
    const aTier = opportunities.filter((o) => o.tier === 'A').length;
    const ready = opportunities.filter((o) => o.status === 'ready').length;
    const scores = opportunities.map((o) => o.arbitrage_score || 0);
    const avg = scores.length ? Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100) / 100 : 0;
    return { total, gold, aTier, ready, avg };
  }, [opportunities]);

  return {
    // data
    countries,
    selectedCountry,
    setSelectedCountry,
    opportunities,
    source,
    migrationPending,
    run,
    cultural,
    personas,
    insights,
    stats,
    clusters,
    funnels,
    mineResults,
    funnelResults,
    kpis,
    // states
    loading,
    discovering,
    addingCountry,
    busyKeys,
    apiConfigured: pautadorApi.configured,
    // actions
    refresh: loadInitial,
    runDiscovery,
    moveOpportunity,
    mineOpportunity,
    buildFunnel,
    addOpportunity,
    addCountry,
  };
}
