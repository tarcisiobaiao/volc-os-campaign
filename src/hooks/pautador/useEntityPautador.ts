// ============================================
// PAUTADOR PRO — hook ENTITY-FIRST (useState/useEffect, padrão do repo).
// Persistência POR PAÍS: ao trocar o país no dropdown, recarrega os cards de
// entidade daquele país. Discovery ADICIONA (nunca apaga). Inteligência
// cultural/personas é refeita a cada run.
// ============================================

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useToast } from '@/hooks/use-toast';
import { pautadorService, MigrationPendingError } from '@/services/pautadorService';
import { pautadorEntityService } from '@/services/pautadorEntityService';
import { pautadorApi, PautadorApiError } from '@/lib/pautadorApi';
import type { MarketTier, OpportunityStatus, PautadorCountry } from '@/types/pautador';
import { entityKey } from '@/types/pautadorEntity';
import type { TesesResposta } from '@/types/pautadorOportunidade';
import type { EixoEmProgresso, ValidacaoRelatorio } from '@/types/pautadorValidacao';
import type {
  EntityCard,
  EntityFunnelResponse,
  EntityMineResponse,
  PautadorNiche,
} from '@/types/pautadorEntity';
import { PAUTADOR_COUNTRIES } from '@/data/pautadorCountries';

// Os 195 países soberanos vêm do dataset canônico (sempre disponível, sem
// depender de cadastro manual nem do Supabase para a lista).
const ALL_COUNTRIES: PautadorCountry[] = PAUTADOR_COUNTRIES.map((c) => ({
  country_code: c.country_code,
  country_name: c.country_name,
  native_language: c.native_language,
  market_tier: c.market_tier as MarketTier,
  flag_emoji: c.flag_emoji,
  is_active: true,
}));

export type DataSource = 'supabase' | 'ephemeral' | 'none';

export function useEntityPautador() {
  const { toast } = useToast();

  const [countries] = useState<PautadorCountry[]>(ALL_COUNTRIES);
  // Brasil é o padrão porque é onde a operação de fato roda: um site
  // (creditoup.com.br) e as campanhas ativas. Abrir num mercado onde ainda não
  // se opera custa um clique toda vez e, pior, faz a coluna parecer vazia.
  // A string é o `country_name` — o lookup em `countries` é por ele, não pelo
  // código ISO, e grafia errada aqui devolve `undefined` em silêncio.
  const [selectedCountry, setSelectedCountry] = useState<string>('Brasil');

  // Nicho + sazonalidade (R1/R2): direcionam a descoberta. Seleção vazia /
  // null = SEM filtro — comportamento diversificado de hoje, backward-compatible.
  const [niches, setNiches] = useState<PautadorNiche[]>([]);
  const [selectedNiches, setSelectedNiches] = useState<string[]>([]);
  const [seasonality, setSeasonality] = useState<'evergreen' | 'seasonal' | null>(null);

  const reloadNiches = useCallback(async () => {
    try {
      const resp = await pautadorApi.niches();
      setNiches(resp.niches || []);
    } catch {
      // silencioso: o multiselect só fica vazio; não bloqueia o resto da página
    }
  }, []);

  useEffect(() => {
    reloadNiches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [cards, setCards] = useState<EntityCard[]>([]);
  const [source, setSource] = useState<DataSource>('none');
  const [migrationPending, setMigrationPending] = useState(false);

  const [cultural, setCultural] = useState<Record<string, unknown> | null>(null);
  const [personas, setPersonas] = useState<Array<Record<string, unknown>>>([]);
  const [insights, setInsights] = useState<Record<string, unknown> | null>(null);

  const [mineResults, setMineResults] = useState<Record<string, EntityMineResponse>>({});
  const [funnelResults, setFunnelResults] = useState<Record<string, EntityFunnelResponse>>({});
  // v7_17 · card cujo arraste p/ "Em validação" está aguardando a escolha de
  // PERGUNTA. O modal NÃO trava o arraste — ele só antecede o movimento.
  const [medindo, setMedindo] = useState<Set<string>>(new Set());
  const [medindoLote, setMedindoLote] = useState(false);
  // As TESES da coluna. Leitura pura e barata (nenhuma medição, nenhum custo),
  // então pode ser recarregada sempre que a lista muda.
  const [teses, setTeses] = useState<TesesResposta | null>(null);
  const [tesesCarregando, setTesesCarregando] = useState(false);
  const [tesesErro, setTesesErro] = useState<string | null>(null);
  const [ultimoLote, setUltimoLote] = useState<ValidacaoRelatorio | null>(null);
  const [progresso, setProgresso] = useState<Record<string, EixoEmProgresso[]>>({});

  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  // descoberta ON no país selecionado (persistido em pautador_runs.status='running'):
  // sobrevive à navegação — o Kanban anima enquanto a run está rodando.
  const [discoveryRunning, setDiscoveryRunning] = useState(false);
  const discoveryPollRef = useRef(false);
  const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set());
  const addBusy = useCallback((k: string) => setBusyKeys((p) => { const n = new Set(p); n.add(k); return n; }), []);
  const removeBusy = useCallback((k: string) => setBusyKeys((p) => { const n = new Set(p); n.delete(k); return n; }), []);
  // cards minerando no n8n (async) — animação + auto-poll até o resultado chegar
  const [miningKeys, setMiningKeys] = useState<Set<string>>(new Set());
  const addMining = useCallback((k: string) => setMiningKeys((p) => { const n = new Set(p); n.add(k); return n; }), []);
  const removeMining = useCallback((k: string) => setMiningKeys((p) => { const n = new Set(p); n.delete(k); return n; }), []);
  // cards arquitetando o funil — mesma UX do mining, mas na coluna "Em funil"
  const [buildingKeys, setBuildingKeys] = useState<Set<string>>(new Set());
  const addBuilding = useCallback((k: string) => setBuildingKeys((p) => { const n = new Set(p); n.add(k); return n; }), []);
  const removeBuilding = useCallback((k: string) => setBuildingKeys((p) => { const n = new Set(p); n.delete(k); return n; }), []);
  // cards que ACABARAM de concluir uma etapa — check verde transitório no card
  const [doneKeys, setDoneKeys] = useState<Set<string>>(new Set());

  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  // As teses acompanham a coluna de validação. É leitura pura e barata — sem
  // medição, sem custo —, então recarregar a cada mudança da lista é honesto:
  // o operador vê a comparação atualizada assim que uma medição termina.
  const idsValidando = useMemo(
    () => cards.filter((c) => c.status === 'validating' && c.id)
               .map((c) => c.id).join(','),
    [cards],
  );
  useEffect(() => {
    void carregarTeses(cards.filter((c) => c.status === 'validating'));
    // `idsValidando` é a chave estável: recarrega quando a COMPOSIÇÃO da
    // coluna muda, não a cada renderização de um card.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsValidando]);
  const currentCodeRef = useRef<string | undefined>(undefined);

  const countryMeta = useMemo(
    () => countries.find((c) => c.country_name === selectedCountry),
    [countries, selectedCountry],
  );
  currentCodeRef.current = countryMeta?.country_code;

  // "Etapa concluída ✅" no card: mostra um check verde e o remove após ~12s (some
  // sozinho, sem hard refresh). Detectado ao vivo (poll do mining / retorno do funil).
  const markDone = useCallback((key: string) => {
    setDoneKeys((p) => { const n = new Set(p); n.add(key); return n; });
    setTimeout(() => {
      if (mountedRef.current) setDoneKeys((p) => { const n = new Set(p); n.delete(key); return n; });
    }, 12000);
  }, []);

  // Poll: enquanto o n8n minera (async), detecta a conclusão pelo CLUSTER persistido
  // (pautador_keyword_clusters — sempre gravado; sem o índice único que pode rejeitar
  // o lote de seed_queries). Confiável independente de colisão de keyword.
  const pollMining = useCallback((key: string, code: string, opportunityId: number, baseline: number) => {
    const MAX = 60; // ~5 min
    const INTERVAL = 5000;
    const tick = async (attempt: number) => {
      if (!mountedRef.current) return;
      if (attempt >= MAX) {
        removeMining(key);
        toast({ title: 'Mineração ainda em andamento', description: 'O n8n pode estar demorando. Clique em Atualizar mais tarde.' });
        return;
      }
      try {
        const clusters = await pautadorService.fetchClusters(opportunityId);
        if (clusters.length > baseline) {
          // pronto: recarrega os cards do país e avisa
          const rows = await pautadorEntityService.fetchEntityCards(code).catch(() => null);
          if (rows && mountedRef.current && currentCodeRef.current === code) setCards(rows);
          removeMining(key);
          markDone(key); // ✅ check verde no card, ao vivo
          const cl = clusters[0] as unknown as { production_ads_queue?: unknown[]; keywords?: unknown[] };
          const n = cl?.production_ads_queue?.length ?? cl?.keywords?.length ?? 0;
          toast({ title: 'Mineração concluída ✅', description: `${n} keywords mineradas pelo n8n. Abra o card → aba Keywords.` });
          return;
        }
      } catch { /* segue tentando */ }
      setTimeout(() => tick(attempt + 1), INTERVAL);
    };
    setTimeout(() => tick(0), INTERVAL);
  }, [removeMining, markDone, toast]);

  // Poll: enquanto a DESCOBERTA está 'running' (pautador_runs), mantém a animação
  // e, ao concluir, recarrega cards + inteligência. É o que faz a UX sobreviver à
  // navegação: qualquer montagem do país detecta a run em andamento e reanima.
  const pollDiscovery = useCallback((code: string, name: string) => {
    if (discoveryPollRef.current) return;
    discoveryPollRef.current = true;
    const INTERVAL = 5000;
    const MAX = 180; // ~15 min de guarda
    const stop = () => { discoveryPollRef.current = false; };
    const tick = async (attempt: number) => {
      if (!mountedRef.current || currentCodeRef.current !== code) return stop();
      if (attempt >= MAX) { stop(); setDiscoveryRunning(false); return; }
      try {
        const run = await pautadorService.fetchLatestRun(name);
        const running = run?.status === 'running' && isRunFresh(run);
        if (!running) {
          stop();
          setDiscoveryRunning(false);
          if (run?.status === 'completed') {
            const rows = await pautadorEntityService.fetchEntityCards(code).catch(() => null);
            if (rows && mountedRef.current && currentCodeRef.current === code) {
              setCards(rows);
              setSource(rows.length ? 'supabase' : 'none');
            }
            setCultural((run?.cultural_intelligence as unknown as Record<string, unknown>) || null);
            setInsights((run?.insights as unknown as Record<string, unknown>) || null);
            toast({ title: 'Descoberta concluída ✅', description: `${name}: ${run?.produced_count ?? 0} entidades. Kanban atualizado.` });
          }
          return;
        }
      } catch { /* segue tentando */ }
      setTimeout(() => tick(attempt + 1), INTERVAL);
    };
    setTimeout(() => tick(0), INTERVAL);
  }, [toast]);

  // --- persistence per country: reload cards + cultural intel on country change ---
  const loadCards = useCallback(async (code?: string, name?: string) => {
    if (!code) { setLoading(false); return; }
    setLoading(true);
    try {
      const rows = await pautadorEntityService.fetchEntityCards(code);
      setCards(rows);
      setSource(rows.length ? 'supabase' : 'none');
      setMigrationPending(false);
    } catch (err) {
      if (err instanceof MigrationPendingError) {
        setMigrationPending(true);
        setCards([]);
        setSource('none');
      } else {
        // keep whatever we have
      }
    } finally {
      setLoading(false);
    }
    // reload the PERSISTED cultural intelligence/insights for this country
    // (latest run) so the panel survives refresh + country switch.
    if (name) {
      try {
        const latest = await pautadorService.fetchLatestRun(name);
        setCultural((latest?.cultural_intelligence as unknown as Record<string, unknown>) || null);
        setInsights((latest?.insights as unknown as Record<string, unknown>) || null);
        // há uma descoberta ON neste país? (persistente — reanima após navegar)
        const running = latest?.status === 'running' && isRunFresh(latest);
        setDiscoveryRunning(running);
        if (running && code) pollDiscovery(code, name);
      } catch {
        setCultural(null);
        setInsights(null);
        setDiscoveryRunning(false);
      }
    } else {
      setCultural(null);
      setInsights(null);
      setDiscoveryRunning(false);
    }
  }, [pollDiscovery]);

  useEffect(() => {
    // when switching countries, show that country's persisted cards + intel
    loadCards(countryMeta?.country_code, countryMeta?.country_name);
  }, [countryMeta?.country_code, countryMeta?.country_name, loadCards]);

  const patchLocal = useCallback((key: string, patch: Partial<EntityCard>) => {
    setCards((prev) => prev.map((c) => (entityKey(c) === key ? { ...c, ...patch } : c)));
  }, []);

  const runDiscovery = useCallback(async () => {
    const meta = countryMeta;
    setDiscovering(true);
    setDiscoveryRunning(true); // anima o Kanban já no clique
    try {
      const resp = await pautadorApi.entityDiscovery({
        country: selectedCountry,
        country_code: meta?.country_code,
        native_language: meta?.native_language,
        count: 20,
        niches: selectedNiches,
        seasonality: seasonality ?? undefined,
      });
      // só aplica o resultado se o usuário ainda estiver no MESMO país (evita
      // contaminar o país atual com o resultado de outro, se navegou no meio).
      const sameCountry = currentCodeRef.current === meta?.country_code;
      if (sameCountry) {
        setCultural(resp.cultural_intelligence || null);
        setPersonas(resp.personas || []);
        setInsights(resp.insights || null);
        if (resp.persisted) {
          // persisted: resp.items is the FULL reload of the country's cards
          // (created + merged + pre-existing) — authoritative, replace is correct.
          setCards(resp.items);
        } else {
          // demo/ephemeral: resp.items are only the new run's entities — ADD them
          // (dedup by entity key) so prior demo cards are never wiped ("runs ADD").
          setCards((prev) => {
            const seen = new Set(prev.map(entityKey));
            return [...prev, ...resp.items.filter((c) => !seen.has(entityKey(c)))];
          });
        }
        setSource(resp.persisted ? 'supabase' : 'ephemeral');
        setMigrationPending(false);
      }
      const mode = resp.persisted ? 'persistida' : 'modo demo (não persistida)';
      toast({
        title: `Descoberta concluída — ${resp.items.length} entidades`,
        description: `Motor: ${resp.engine} · ${mode}. +${resp.created_count} novas, ${resp.merged_count} já existentes.${resp.warnings.length ? ' ⚠ ' + resp.warnings.slice(0, 2).join(' ') : ''}`,
      });
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao disparar descoberta';
      toast({ title: 'Falha na descoberta', description: message, variant: 'destructive' });
    } finally {
      setDiscovering(false);
      setDiscoveryRunning(false);
    }
  }, [selectedCountry, countryMeta, toast, selectedNiches, seasonality]);

  const mineEntity = useCallback(async (card: EntityCard) => {
    const key = entityKey(card);
    addBusy(key);
    try {
      const res = await pautadorApi.mineEntity(card.entity_id ?? 0, card.ephemeral ? card.entity : undefined);
      setMineResults((prev) => ({ ...prev, [key]: res }));
      if (res.dispatched) {
        // o flow n8n minera e grava no Supabase de forma assíncrona — anima + auto-poll
        patchLocal(key, { status: 'mining' });
        addMining(key);
        // baseline = clusters atuais da oportunidade; o poll detecta quando o n8n grava um novo
        const baseline = card.id
          ? (await pautadorService.fetchClusters(card.id).catch(() => [])).length
          : 0;
        pollMining(key, card.country_code, card.id ?? 0, baseline);
        toast({
          title: 'Mineração disparada no n8n ⛏️',
          description: 'O fluxo externo está minerando. O card mostra o progresso e atualiza sozinho quando ficar pronto.',
        });
      } else {
        // append new pains/queries locally (dedup by name/query)
        patchLocal(key, {
          status: 'mining',
          pains: mergeBy(card.pains, res.pains, 'pain_name'),
          seed_queries: mergeBy(card.seed_queries, res.seed_queries, 'query'),
        });
        markDone(key); // ✅ check verde (mineração interna síncrona)
        toast({ title: 'Mineração concluída', description: `${res.pains.length} dores · ${res.seed_queries.length} queries. (${res.engine})` });
      }
      return res;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao minerar';
      toast({ title: 'Falha na mineração', description: message, variant: 'destructive' });
      return null;
    } finally {
      removeBusy(key);
    }
  }, [patchLocal, toast, addBusy, removeBusy, addMining, pollMining, markDone]);

  const buildFunnel = useCallback(async (card: EntityCard) => {
    const key = entityKey(card);
    const prevStatus = card.status;
    addBusy(key);
    // move o card JÁ pra "Em funil" e liga a animação (igual ao mining) — ele fica
    // na coluna enquanto o arquiteto roda, em vez de preso na etapa anterior.
    patchLocal(key, { status: 'funnel' });
    addBuilding(key);
    try {
      const res = await pautadorApi.entityFunnel(card.id ?? 0, card.ephemeral ? card.entity : undefined);
      setFunnelResults((prev) => ({ ...prev, [key]: res }));
      patchLocal(key, {
        status: 'funnel',
        funnel_hypotheses: [...(card.funnel_hypotheses || []), ...res.funnel_hypotheses],
      });
      markDone(key); // ✅ check verde no card quando o funil fica pronto
      toast({
        title: 'Funil arquitetado',
        description: `${res.pages?.length ?? 0} páginas · ${res.writing_jobs?.length ?? 0} briefings de redação. (${res.engine})`,
      });
      return res;
    } catch (err) {
      patchLocal(key, { status: prevStatus }); // reverte se o arquiteto falhar
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao gerar funil';
      toast({ title: 'Falha no funil', description: message, variant: 'destructive' });
      return null;
    } finally {
      removeBusy(key);
      removeBuilding(key);
    }
  }, [patchLocal, toast, addBusy, removeBusy, addBuilding, removeBuilding, markDone]);

  const applyMove = useCallback(async (card: EntityCard, newStatus: OpportunityStatus) => {
    if (newStatus === card.status) return;
    const key = entityKey(card);
    const prevStatus = card.status;
    if (newStatus === 'mining') return void mineEntity(card);
    if (newStatus === 'funnel') return void buildFunnel(card);
    patchLocal(key, { status: newStatus }); // optimistic
    if (card.ephemeral || !card.id) return;
    try {
      // "Pronto" não dispara mais nada além de mudar o status. O bloco de
      // ClickUp que morava aqui saiu junto com a integração — e ele não era
      // inerte: sem o backend devolvendo `clickup`, caía no último ramo e
      // chamava `setClickupConfirm` para um diálogo que não existe mais.
      await pautadorApi.updateEntityStatus(card.id, newStatus);
    } catch (err) {
      patchLocal(key, { status: prevStatus }); // revert
      toast({ title: 'Erro ao mover card', variant: 'destructive' });
    }
  }, [mineEntity, buildFunnel, patchLocal, toast]);

  // ── A MEDIÇÃO ────────────────────────────────────────────────────────────
  //
  // Ela roda SÓ quando o card entra em "Em validação" — nunca ao abrir o
  // drawer, nunca em background. Medir custa dinheiro e quem manda é quem paga.
  //
  // O POST responde no fim (~30s), mas a gravação é incremental: cada eixo vai
  // para o banco assim que é medido. Enquanto o POST não volta, o hook lê os
  // eixos que já caíram e a tela os revela um a um. É progresso REAL — o mesmo
  // mecanismo que faz re-arrastar refazer só o que falta.
  const medirCard = useCallback(async (card: EntityCard, opts?: { silencioso?: boolean }) => {
    if (!card.id || card.ephemeral) return;
    // ⚠️ `entityKey`, e NÃO `String(card.id)`.
    //
    // Até `b2af81f0` esta linha era a única das 19 do hook que usava
    // `String(card.id)`. O board lê com `entityKey(card)` (`ent-<id>`), então
    // `medindoKeys.has(key)` era SEMPRE falso: o selo de medição e o progresso
    // por eixo nunca apareciam no card durante os ~2 minutos da run. Só o
    // drawer via, porque ele copiava a convenção errada.
    const key = entityKey(card);
    setMedindo((s) => new Set(s).add(key));
    setProgresso((p) => ({ ...p, [key]: [] }));

    // O AVISO DE PARTIDA, que a mineração tinha e a medição não.
    //
    // Medir leva ~2 minutos e o único sinal era o drawer — quem arrastava e
    // fechava o card não tinha como saber se algo estava acontecendo. O aviso
    // diz o que vai custar, porque medir gasta dinheiro e quem paga tem de
    // saber que começou.
    if (!opts?.silencioso) {
      toast({
        title: 'Medindo o card 📐',
        description: 'SERP, histórico e a leitura das perguntas. Leva ~2 min — dá para fechar o card, o progresso continua.',
      });
    }

    let vivo = true;
    const sondar = async () => {
      while (vivo) {
        try {
          const { eixos } = await pautadorApi.entityAxes(card.id!);
          if (!vivo) return;
          setProgresso((p) => ({ ...p, [key]: eixos }));
        } catch { /* uma sonda perdida não derruba a medição */ }
        await new Promise((r) => setTimeout(r, 1500));
      }
    };
    void sondar();

    try {
      const resp = await pautadorApi.validateEntity(card.id, undefined);
      const medido = resp.validacao?.resultados?.[0];
      if (medido) patchLocal(key, { validacao: medido as EntityCard['validacao'] });
      if (!opts?.silencioso) {
        // O CUSTO SAIU DA TELA, e a decisão é do operador.
        //
        // Cifrão em toast de sucesso não ajuda a decidir nada — a decisão de
        // gastar já foi tomada no arraste — e transforma cada medição num
        // lembrete de fatura. O número continua GRAVADO (`custo_usd` em
        // `pautador_validation_runs`), então a auditoria não perde nada; o que
        // sai é a exibição.
        const r = resp.validacao;
        toast({
          title: 'Card medido ✓',
          description: r ? `Concluído em ${Math.round((r.duracao_ms ?? 0) / 1000)}s. Abra o card para ver os eixos.`
                         : 'Abra o card para ver os eixos.',
        });
      }
    } catch {
      toast({ title: 'A medição falhou', description: 'O card foi movido; os eixos ficam como estavam.', variant: 'destructive' });
    } finally {
      vivo = false;
      setMedindo((s) => { const n = new Set(s); n.delete(key); return n; });
      setProgresso((p) => { const n = { ...p }; delete n[key]; return n; });
      void loadCards(countryMeta?.country_code, countryMeta?.country_name);
    }
  }, [patchLocal, toast, loadCards, countryMeta]);

  /** Lê as teses já deriváveis. NÃO mede e NÃO gasta: deriva do `validacao`
   *  que o Validador gravou. Falhar aqui não apaga o que está na tela — a
   *  comparação some, o card continua. */
  const carregarTeses = useCallback(async (cards: EntityCard[]) => {
    const ids = cards.map((c) => c.id).filter((x): x is number => !!x);
    if (!ids.length) { setTeses(null); setTesesErro(null); return; }
    setTesesCarregando(true);
    setTesesErro(null);
    try {
      setTeses(await pautadorApi.entityTeses({ opportunity_ids: ids }));
    } catch (e) {
      setTesesErro(e instanceof Error ? e.message : 'falha ao ler as teses');
    } finally {
      setTesesCarregando(false);
    }
  }, []);

  /** A coluna inteira. É o caminho PADRÃO — o lote paga a base uma vez. */
  const medirColuna = useCallback(async (cards: EntityCard[]) => {
    const ids = cards.map((c) => c.id).filter((x): x is number => !!x);
    if (!ids.length) return;
    setMedindoLote(true);
    try {
      const { validacao } = await pautadorApi.validateBatch({ opportunity_ids: ids });
      setUltimoLote(validacao);
      toast({
        title: `${validacao.cards} cards medidos ✓`,
        description: 'A coluna inteira foi medida. Abra os cards para ver os eixos.',
      });
      await loadCards(countryMeta?.country_code, countryMeta?.country_name);
    } catch {
      toast({ title: 'A medição da coluna falhou', variant: 'destructive' });
    } finally {
      setMedindoLote(false);
    }
  }, [toast, loadCards, countryMeta]);


  /** Arraste para "Em validação": move e MEDE. Sem intermediários.
   *
   * ## O diálogo de escolha de pergunta saiu, e o motivo é o motor
   *
   * Aqui havia uma interceptação (v7_17) que abria um modal pedindo para
   * ESCOLHER UMA pergunta que o funil responderia. Ela nasceu quando a entidade
   * era julgada por uma pergunta só — e essa premissa foi derrubada por medição.
   *
   * `DIRPF` congelado em "Quando libera a declaração de 2026?" devolve uma DATA,
   * dispara o portão e mata a entidade mais rica do lote. A contagem estava
   * certa; o objeto é que era outro. Desde então `agregar()` lê TODAS as
   * perguntas do PAA e carrega a distribuição, e `formatos_da_entidade()` diz o
   * formato de CADA uma — o funil tem cinco páginas e cada uma responde a sua.
   *
   * Pedir uma pergunta ao humano, hoje, é pedir que ele desfaça à mão o que o
   * motor passou seis rodadas aprendendo a não fazer.
   *
   * ⚠️ O GATILHO DA MEDIÇÃO MOROU DENTRO DAQUELE MODAL. Ele veio para cá junto,
   * e essa é a parte que não pode se perder no caminho: sem ela o card entraria
   * na coluna e ficaria parado, sem medir, em silêncio.
   */
  const moveEntity = useCallback(async (card: EntityCard, newStatus: OpportunityStatus) => {
    const entrando = newStatus === 'validating' && card.status !== 'validating';
    const r = await applyMove(card, newStatus);
    // O ARRASTE é o gatilho da medição, e o único. Não mede ao abrir a aba, não
    // mede em background, não remede o que já tem — `refazer` é explícito.
    if (entrando && !card.ephemeral && !card.validacao) void medirCard(card);
    return r;
  }, [applyMove, medirCard]);

  const validateEntity = useCallback((card: EntityCard) => moveEntity(card, 'validating'), [moveEntity]);
  // "Rodar novamente": destrava um card preso em mineração/funil (erro no n8n ou
  // no backend) limpando o estado local e re-disparando a etapa correspondente.
  const rerunEntity = useCallback(async (card: EntityCard) => {
    const key = entityKey(card);
    removeMining(key); // limpa a animação/estado preso de mineração
    if (card.status === 'funnel') return void buildFunnel(card);
    return void mineEntity(card); // mining (ou qualquer travado) → re-dispara mineração
  }, [mineEntity, buildFunnel, removeMining]);

  // Exclusão manual (aba Rejeitado): remove o card do país (cascade no backend).
  const deleteEntity = useCallback(async (card: EntityCard) => {
    const key = entityKey(card);
    if (card.ephemeral || !card.id) {
      setCards((prev) => prev.filter((c) => entityKey(c) !== key));
      return true;
    }
    addBusy(key);
    try {
      await pautadorApi.deleteEntityOpportunity(card.id);
      setCards((prev) => prev.filter((c) => entityKey(c) !== key));
      removeMining(key);
      toast({ title: 'Card excluído', description: `${card.entity.canonical_name} foi removido.` });
      return true;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao excluir card';
      toast({ title: 'Falha ao excluir', description: message, variant: 'destructive' });
      return false;
    } finally {
      removeBusy(key);
    }
  }, [toast, addBusy, removeBusy, removeMining]);

  // Insights livres do usuário (aba Insights) — persistidos por card.
  const saveInsights = useCallback(async (card: EntityCard, text: string) => {
    const key = entityKey(card);
    if (card.ephemeral || !card.id) {
      patchLocal(key, { insights: text });
      toast({ title: 'Insights salvos localmente', description: 'Card ainda não persistido (demo).' });
      return true;
    }
    addBusy(key);
    try {
      await pautadorApi.saveEntityInsights(card.id, text);
      patchLocal(key, { insights: text });
      toast({ title: 'Insights salvos ✅' });
      return true;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao salvar insights';
      toast({ title: 'Falha ao salvar insights', description: message, variant: 'destructive' });
      return false;
    } finally {
      removeBusy(key);
    }
  }, [patchLocal, toast, addBusy, removeBusy]);

  // Descrição da tarefa. ⚠️ ÓRFÃ desde a saída do ClickUp: era o corpo da task
  // e hoje nada a lê. Continua salva e editável; o destino dela é decisão. NÃO se confunde com
  // o insights, que é direcionamento do agente de funil.
  const saveTaskDescription = useCallback(async (card: EntityCard, text: string) => {
    const key = entityKey(card);
    if (card.ephemeral || !card.id) {
      patchLocal(key, { task_description: text });
      toast({ title: 'Descrição salva localmente', description: 'Card ainda não persistido (demo).' });
      return true;
    }
    addBusy(key);
    try {
      await pautadorApi.saveEntityTaskDescription(card.id, text);
      patchLocal(key, { task_description: text });
      toast({ title: 'Descrição da tarefa salva ✅' });
      return true;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao salvar a descrição';
      toast({ title: 'Falha ao salvar', description: message, variant: 'destructive' });
      return false;
    } finally {
      removeBusy(key);
    }
  }, [patchLocal, toast, addBusy, removeBusy]);

  // Nome de exibição do CARD (não da entidade) — diferencia cópias da mesma
  // entidade rodando em sites diferentes.
  const saveDisplayTitle = useCallback(async (card: EntityCard, text: string) => {
    const key = entityKey(card);
    const value = text.trim();
    if (card.ephemeral || !card.id) {
      patchLocal(key, { display_title: value || null });
      return true;
    }
    addBusy(key);
    try {
      await pautadorApi.saveEntityDisplayTitle(card.id, value);
      patchLocal(key, { display_title: value || null });
      toast({ title: value ? 'Card renomeado ✅' : 'Nome de exibição removido' });
      return true;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao renomear o card';
      toast({ title: 'Falha ao renomear', description: message, variant: 'destructive' });
      return false;
    } finally {
      removeBusy(key);
    }
  }, [patchLocal, toast, addBusy, removeBusy]);

  // Duplicar: mesma entidade, outro site. A cópia reaproveita a mineração já paga
  // (dores + seed queries) e cai em "Em mineração" pronta pra seguir pro funil.
  const duplicateCard = useCallback(async (card: EntityCard, displayTitle: string) => {
    if (card.ephemeral || !card.id) {
      toast({
        title: 'Card não persistido',
        description: 'Só dá pra duplicar cards salvos no Supabase (este é demo).',
        variant: 'destructive',
      });
      return false;
    }
    const key = entityKey(card);
    addBusy(key);
    try {
      const { card: copy, warnings } = await pautadorApi.duplicateEntityCard(card.id, displayTitle);
      // a cópia entra no board sem recarregar o país inteiro
      setCards((prev) => (prev.some((c) => entityKey(c) === entityKey(copy)) ? prev : [...prev, copy]));
      toast({
        title: 'Card duplicado ✅',
        description: `${copy.display_title || copy.entity.canonical_name} está em "Em mineração" com ${copy.pains?.length ?? 0} dores e ${copy.seed_queries?.length ?? 0} queries.${warnings?.length ? ' ⚠ ' + warnings.join(' ') : ''}`,
      });
      return true;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao duplicar o card';
      toast({ title: 'Falha ao duplicar', description: message, variant: 'destructive' });
      return false;
    } finally {
      removeBusy(key);
    }
  }, [toast, addBusy, removeBusy]);

  // "Dar baixa": marca que o funil foi criado pelo redator (oculta o card em Pronto).
  const toggleFunnelCompleted = useCallback(async (card: EntityCard, completed: boolean) => {
    const key = entityKey(card);
    if (card.ephemeral || !card.id) {
      patchLocal(key, { funnel_completed: completed });
      return true;
    }
    patchLocal(key, { funnel_completed: completed }); // optimistic
    try {
      await pautadorApi.setFunnelCompleted(card.id, completed);
      if (completed) toast({ title: 'Baixa dada ✅', description: `${card.entity.canonical_name}: funil marcado como criado.` });
      return true;
    } catch (err) {
      patchLocal(key, { funnel_completed: !completed }); // revert
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao dar baixa';
      toast({ title: 'Falha ao dar baixa', description: message, variant: 'destructive' });
      return false;
    }
  }, [patchLocal, toast]);

  // Criação MANUAL de entidade (default direto em Pronto) — NÃO dispara ClickUp.
  const createManualEntity = useCallback(async (fields: {
    canonical_name: string; full_name?: string; official_source?: string;
    entity_category?: string; description?: string; aliases?: string[];
  }) => {
    const meta = countryMeta;
    if (!fields.canonical_name?.trim()) {
      toast({ title: 'Informe o nome da entidade', variant: 'destructive' });
      return false;
    }
    try {
      const resp = await pautadorApi.createManualEntity({
        country: selectedCountry,
        country_code: meta?.country_code || '',
        native_language: meta?.native_language,
        canonical_name: fields.canonical_name.trim(),
        full_name: fields.full_name?.trim() || undefined,
        official_source: fields.official_source?.trim() || undefined,
        entity_category: fields.entity_category?.trim() || undefined,
        description: fields.description?.trim() || undefined,
        aliases: (fields.aliases || []).map((a) => a.trim()).filter(Boolean),
        status: 'ready',
      });
      setCards((prev) => {
        const key = entityKey(resp.card);
        return prev.some((c) => entityKey(c) === key)
          ? prev.map((c) => (entityKey(c) === key ? resp.card : c))
          : [resp.card, ...prev];
      });
      setSource('supabase');
      toast({
        title: resp.already_existed ? 'Entidade já existia — atualizada em Pronto' : 'Entidade criada em Pronto ✅',
        description: `${resp.card.entity.canonical_name} · sem disparo de ClickUp.`,
      });
      return true;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao criar entidade';
      toast({ title: 'Falha ao criar entidade', description: message, variant: 'destructive' });
      return false;
    }
  }, [selectedCountry, countryMeta, toast]);

  // Input manual em Descobertas -> agente secundário enriquece e cria o card em 'discovered'.
  const enrichEntity = useCallback(async (canonicalName: string) => {
    const meta = countryMeta;
    const name = (canonicalName || '').trim();
    if (!name) { toast({ title: 'Informe o nome da entidade', variant: 'destructive' }); return false; }
    try {
      const resp = await pautadorApi.enrichEntity({
        country: selectedCountry,
        country_code: meta?.country_code || '',
        native_language: meta?.native_language,
        canonical_name: name,
      });
      setCards((prev) => {
        const k = entityKey(resp.card);
        return prev.some((c) => entityKey(c) === k)
          ? prev.map((c) => (entityKey(c) === k ? resp.card : c))
          : [resp.card, ...prev];
      });
      setSource('supabase');
      toast({
        title: resp.already_existed ? 'Entidade já existia — atualizada' : 'Entidade enriquecida ✅',
        description: `${resp.card.entity.canonical_name} entrou em Descobertas. (${resp.engine || 'agente'})`,
      });
      return true;
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao enriquecer entidade';
      toast({ title: 'Falha ao enriquecer', description: message, variant: 'destructive' });
      return false;
    }
  }, [selectedCountry, countryMeta, toast]);

  const kpis = useMemo(() => {
    const total = cards.length;
    const gold = cards.filter((c) => c.gold_tier === 'S').length;
    const aTier = cards.filter((c) => c.gold_tier === 'A').length;
    const ready = cards.filter((c) => c.status === 'ready').length;
    const scores = cards.map((c) => c.score || 0);
    const avg = scores.length ? Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100) / 100 : 0;
    return { total, gold, aTier, ready, avg };
  }, [cards]);

  return {
    countries, selectedCountry, setSelectedCountry,
    cards, source, migrationPending, cultural, personas, insights,
    mineResults, funnelResults, kpis,
    loading, discovering, discoveryRunning, busyKeys, miningKeys, buildingKeys, doneKeys, apiConfigured: pautadorApi.configured,
    niches, selectedNiches, setSelectedNiches, seasonality, setSeasonality, reloadNiches,
    refresh: () => loadCards(countryMeta?.country_code, countryMeta?.country_name),
    runDiscovery, moveEntity, mineEntity, buildFunnel, validateEntity,
    rerunEntity, deleteEntity, saveInsights, saveTaskDescription, saveDisplayTitle, duplicateCard,
    toggleFunnelCompleted, createManualEntity,
    enrichEntity,
    medirCard, medirColuna, medindo, medindoLote, ultimoLote, progresso,
    teses, tesesCarregando, tesesErro, carregarTeses,
  };
}

// Uma run 'running' só conta como ativa se for recente (evita run travada por
// restart do backend deixar a animação presa pra sempre).
function isRunFresh(run?: { created_at?: string } | null): boolean {
  const ts = run?.created_at;
  if (!ts) return false;
  const t = new Date(ts).getTime();
  return Number.isFinite(t) && Date.now() - t < 12 * 60 * 1000; // 12 min
}

function mergeBy<T extends Record<string, any>>(a: T[], b: T[], key: string): T[] {
  const seen = new Set((a || []).map((x) => String(x[key]).toLowerCase().trim()));
  const out = [...(a || [])];
  for (const item of b || []) {
    const k = String(item[key]).toLowerCase().trim();
    if (!seen.has(k)) { seen.add(k); out.push(item); }
  }
  return out;
}
