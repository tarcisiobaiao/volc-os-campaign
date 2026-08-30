import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, Loader2, Save, Server } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import {
  deriveConfig,
  deriveRouterFunctionUrl,
  DEFAULT_ENDPOINT_SUBDOMAIN,
  isValidDomain,
  isValidPixelId,
} from '@/lib/metaCapi/derive';
import { buildAllTemplates } from '@/lib/metaCapi/templates';
import type { MetaCapiSiteConfig } from '@/lib/metaCapi/types';
import { checkEndpoint, checkFunction, sendTestEvent, type CheckOutcome } from '@/lib/metaCapi/checks';
import type { MetaCapiSite, SaveSitePayload } from '@/hooks/useMetaCapiSites';
import { ChainDiagram, type ChainState } from './ChainDiagram';
import { StepRail, type StepDef } from './StepRail';
import { StepCloudflare, StepGtm, StepMeta, StepSite, StepSupabase } from './WizardSteps';

const ALL_STEPS: StepDef[] = [
  { id: 'site', title: 'Site e pixel', hint: 'domínio, pixel e token' },
  { id: 'supabase', title: 'Edge Function', hint: 'publicar a capi-router', onceOnly: true },
  { id: 'cloudflare', title: 'Worker e domínio', hint: 'endpoint no seu domínio' },
  { id: 'gtm', title: 'Tags no GTM', hint: 'pixel, interstitial e rewarded' },
  { id: 'meta', title: 'Meta e teste', hint: 'conversões e evento real' },
];

// No Supabase hosted a URL é https://<ref>.supabase.co e o identificador é o
// ref. No self-hosted (VOLC O.S. -> database.agenciavolc.com.br) não existe
// ref: o identificador é a própria URL base. deriveRouterFunctionUrl trata os
// dois formatos; aqui só decidimos qual passar.
const SUPABASE_URL = (import.meta.env.VITE_SUPABASE_URL || '').trim();
const PROJECT_REF =
  SUPABASE_URL.match(/https:\/\/([^.]+)\.supabase\.co/)?.[1] || SUPABASE_URL;

// A function é a MESMA para todos os sites: a URL sai só do projeto Supabase.
// Por isso a checagem não pode depender do formulário — foi esse acoplamento que
// fazia a etapa aparecer com o guia inteiro num site novo, mesmo já publicada.
const ROUTER_URL = deriveRouterFunctionUrl(PROJECT_REF);

export interface WizardForm {
  siteName: string;
  domain: string;
  pixelId: string;
  siteKey: string;
  endpointSubdomain: string;
  capiToken: string;
  testEventCode: string;
  events: { interstitial: boolean; rewarded: boolean };
}

const emptyForm: WizardForm = {
  siteName: '',
  domain: '',
  pixelId: '',
  siteKey: '',
  endpointSubdomain: DEFAULT_ENDPOINT_SUBDOMAIN,
  capiToken: '',
  testEventCode: '',
  events: { interstitial: true, rewarded: true },
};

function formFromSite(site: MetaCapiSite): WizardForm {
  return {
    siteName: site.site_name,
    domain: site.domain,
    pixelId: site.pixel_id,
    siteKey: site.site_key,
    endpointSubdomain: site.endpoint_url.split('://')[1]?.split('.')[0] || DEFAULT_ENDPOINT_SUBDOMAIN,
    capiToken: '',
    testEventCode: site.test_event_code || '',
    events: site.events || { interstitial: true, rewarded: true },
  };
}

interface MetaCapiWizardProps {
  /** Site existente = modo edição: os códigos já saem prontos e o token fica intocado. */
  site: MetaCapiSite | null;
  saving: boolean;
  onSave: (payload: SaveSitePayload) => Promise<MetaCapiSite | null>;
  onRecordCheck: (id: number, result: Record<string, unknown>) => Promise<void>;
  onExit: () => void;
}

export const MetaCapiWizard: React.FC<MetaCapiWizardProps> = ({
  site,
  saving,
  onSave,
  onRecordCheck,
  onExit,
}) => {
  const { toast } = useToast();
  const [form, setForm] = useState<WizardForm>(site ? formFromSite(site) : emptyForm);
  const [stepId, setStepId] = useState<string>('site');
  const [done, setDone] = useState<Set<string>>(site ? new Set(['site']) : new Set());
  const [savedId, setSavedId] = useState<number | null>(site?.id ?? null);
  const [chain, setChain] = useState<ChainState>({
    gtm: 'idle',
    endpoint: 'idle',
    function: 'idle',
    meta: 'idle',
  });
  const [outcomes, setOutcomes] = useState<Record<string, CheckOutcome | undefined>>({});

  // Pergunta à function, ao abrir o wizard, se ela já está publicada.
  useEffect(() => {
    if (!ROUTER_URL) return;
    let cancelled = false;
    setChain((c) => ({ ...c, function: 'checking' }));
    void checkFunction(ROUTER_URL).then((out) => {
      if (cancelled) return;
      setOutcomes((o) => ({ ...o, function: out }));
      setChain((c) => ({ ...c, function: out.ok ? 'ok' : 'idle' }));
      if (out.ok) setDone((prev) => new Set(prev).add('supabase'));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const functionReady = outcomes.function?.ok === true;

  // Publicada => deixa de ser um passo e vira um fato. Se cair, volta ao fluxo
  // com o guia completo, que é quando ele realmente serve.
  const steps = useMemo(
    () => (functionReady ? ALL_STEPS.filter((s) => s.id !== 'supabase') : ALL_STEPS),
    [functionReady],
  );

  const patch = useCallback((next: Partial<WizardForm>) => {
    setForm((prev) => ({ ...prev, ...next }));
  }, []);

  // A config derivada é recalculada a cada tecla: o operador vê o cookie domain
  // e o endpoint se formarem enquanto digita, em vez de descobrir no fim.
  const config: MetaCapiSiteConfig | null = useMemo(() => {
    if (!isValidDomain(form.domain).valid || !form.siteName.trim()) return null;
    return deriveConfig({
      siteName: form.siteName.trim(),
      domain: form.domain,
      pixelId: form.pixelId,
      siteKey: form.siteKey || undefined,
      endpointSubdomain: form.endpointSubdomain,
      projectRef: PROJECT_REF,
      events: form.events,
    });
  }, [form]);

  const templates = useMemo(() => (config ? buildAllTemplates(config) : null), [config]);

  const canSave =
    !!config &&
    isValidPixelId(form.pixelId).valid &&
    (!!savedId || form.capiToken.trim().length > 10);

  // O passo aberto pode estar fora da trilha (Edge Function consultada pelo
  // link do topo). Nesse caso o rodapé oferece só a volta ao fluxo.
  const indexInRail = steps.findIndex((s) => s.id === stepId);
  const offRail = indexInRail === -1;

  const markDone = (id: string) => setDone((prev) => new Set(prev).add(id));

  const handleSave = async () => {
    if (!config) return;
    const saved = await onSave({
      id: savedId ?? undefined,
      site_key: config.siteKey,
      site_name: config.siteName,
      domain: config.domain,
      cookie_domain: config.cookieDomain,
      endpoint_url: config.endpointUrl,
      pixel_id: config.pixelId,
      events: config.events,
      test_event_code: form.testEventCode || undefined,
      capi_token: form.capiToken.trim() || undefined,
    });
    if (saved) {
      setSavedId(saved.id);
      patch({ capiToken: '' }); // não guarda o token em memória depois de salvo
      markDone('site');
      setStepId(steps[1]?.id ?? 'cloudflare');
    }
  };

  const runCheck = async (
    which: 'endpoint' | 'function' | 'meta',
    eventName: 'ViewContent' | 'RewardedAdView' = 'ViewContent',
  ) => {
    if (which === 'function') {
      setChain((c) => ({ ...c, function: 'checking' }));
      const out = await checkFunction(ROUTER_URL);
      setOutcomes((o) => ({ ...o, function: out }));
      setChain((c) => ({ ...c, function: out.ok ? 'ok' : 'fail' }));
      if (out.ok) markDone('supabase');
      return;
    }

    if (!config) return;

    if (which === 'endpoint') {
      setChain((c) => ({ ...c, endpoint: 'checking' }));
      const out = await checkEndpoint(config.endpointUrl);
      setOutcomes((o) => ({ ...o, endpoint: out }));
      setChain((c) => ({ ...c, endpoint: out.ok ? 'ok' : 'fail' }));
      if (out.ok) markDone('cloudflare');
      return;
    }

    if (!form.testEventCode.trim()) {
      toast({
        title: 'Falta o código de teste',
        description: 'Copie o test_event_code em Gerenciador de Eventos → Testar eventos.',
        variant: 'destructive',
      });
      return;
    }

    // Um teste por EVENTO: interstitial e rewarded percorrem o mesmo caminho,
    // mas com nome, slot e categoria diferentes — testar só um não prova o outro.
    setChain((c) => ({ ...c, meta: 'checking', gtm: 'ok' }));
    const out = await sendTestEvent({
      endpointUrl: config.endpointUrl,
      siteKey: config.siteKey,
      eventName,
      testEventCode: form.testEventCode.trim(),
      pageUrl: `https://${config.domain}/`,
    });
    setOutcomes((o) => ({ ...o, [`meta:${eventName}`]: out }));
    setChain((c) => ({ ...c, meta: out.ok ? 'ok' : 'fail' }));
    if (out.ok) markDone('meta');

    if (savedId) {
      await onRecordCheck(savedId, {
        event_name: eventName,
        ok: out.ok,
        layer: out.layer,
        message: out.message,
        status: out.status ?? null,
        at: new Date().toISOString(),
      });
    }
  };

  const stepProps = { form, patch, config, templates, outcomes, runCheck };

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <Button variant="ghost" size="sm" onClick={onExit} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> Sites configurados
        </Button>

        {functionReady && !offRail && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setStepId('supabase')}
            className="gap-1.5 text-xs text-muted-foreground"
          >
            <Server className="h-3.5 w-3.5" /> Edge Function
          </Button>
        )}
      </div>

      <ChainDiagram state={chain} />

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <Card className="shadow-card h-fit lg:sticky lg:top-4">
          <CardContent className="p-2">
            <StepRail steps={steps} currentId={stepId} done={done} onSelect={setStepId} />
          </CardContent>
        </Card>

        <Card className="shadow-card">
          <CardContent className="p-5 space-y-5">
            {stepId === 'site' && <StepSite {...stepProps} />}
            {stepId === 'supabase' && (
              <StepSupabase {...stepProps} alreadyPublished={functionReady} />
            )}
            {stepId === 'cloudflare' && <StepCloudflare {...stepProps} />}
            {stepId === 'gtm' && <StepGtm {...stepProps} onDone={() => markDone('gtm')} />}
            {stepId === 'meta' && <StepMeta {...stepProps} />}

            <div className="flex items-center justify-between gap-2 pt-4 border-t">
              {offRail ? (
                <Button variant="outline" size="sm" onClick={() => setStepId('site')} className="gap-1.5">
                  <ArrowLeft className="h-4 w-4" /> Voltar ao fluxo
                </Button>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setStepId(steps[Math.max(0, indexInRail - 1)].id)}
                    disabled={indexInRail === 0}
                    className="gap-1.5"
                  >
                    <ArrowLeft className="h-4 w-4" /> Voltar
                  </Button>

                  {stepId === 'site' ? (
                    <Button size="sm" onClick={handleSave} disabled={!canSave || saving} className="gap-1.5">
                      {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      {savedId ? 'Salvar alterações' : 'Salvar e continuar'}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() =>
                        setStepId(steps[Math.min(steps.length - 1, indexInRail + 1)].id)
                      }
                      disabled={indexInRail === steps.length - 1}
                      className="gap-1.5"
                    >
                      Avançar <ArrowRight className="h-4 w-4" />
                    </Button>
                  )}
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
