import React, { useState } from 'react';
import {
  AlertTriangle, CheckCircle2, ExternalLink, Info, KeyRound, Loader2, PlayCircle, RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { CodeBlock } from '@/components/ui/code-block';
import { cn } from '@/lib/utils';
import { isValidDomain, isValidPixelId, sanitizeSiteKey } from '@/lib/metaCapi/derive';
import { TEMPLATE_META } from '@/lib/metaCapi/templates';
import type { MetaCapiSiteConfig, TemplateId } from '@/lib/metaCapi/types';
import type { CheckOutcome } from '@/lib/metaCapi/checks';
import type { WizardForm } from './MetaCapiWizard';
import { CopyField } from './CopyField';

// O código exibido é o MESMO arquivo versionado no repositório: importar por
// ?raw elimina a chance de o wizard mostrar uma versão e a gente publicar outra.
import capiRouterSource from '../../../../supabase/functions/capi-router/index.ts?raw';

/**
 * Nome sugerido do Worker. Genérico DE PROPÓSITO: um Worker atende todos os
 * sites, então batizá-lo com o nome de um site (o modelo antigo, um relay por
 * site) induziria a criar um por domínio de novo.
 */
export const RELAY_WORKER_NAME = 'capi-relay';

export interface StepProps {
  form: WizardForm;
  patch: (next: Partial<WizardForm>) => void;
  config: MetaCapiSiteConfig | null;
  templates: Record<TemplateId, string> | null;
  outcomes: Record<string, CheckOutcome | undefined>;
  runCheck: (
    which: 'endpoint' | 'function' | 'meta',
    eventName?: 'ViewContent' | 'RewardedAdView',
  ) => Promise<void>;
}

// ---------------------------------------------------------------- utilitários

const StepHeader: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="space-y-1">
    <h2 className="text-lg font-semibold">{title}</h2>
    <p className="text-sm text-muted-foreground">{children}</p>
  </div>
);

const Hint: React.FC<{ children: React.ReactNode; tone?: 'info' | 'warn' }> = ({
  children,
  tone = 'info',
}) => (
  <div
    className={cn(
      'flex items-start gap-2 rounded-lg border p-3 text-xs',
      tone === 'warn'
        ? 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200'
        : 'border-border bg-muted/40 text-muted-foreground',
    )}
  >
    {tone === 'warn' ? (
      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
    ) : (
      <Info className="h-4 w-4 shrink-0 mt-0.5" />
    )}
    <div className="space-y-1">{children}</div>
  </div>
);

/** Resultado de um teste: o valor está no detalhe, então ele aparece por inteiro. */
const CheckResult: React.FC<{ outcome?: CheckOutcome }> = ({ outcome }) => {
  if (!outcome) return null;
  return (
    <div
      className={cn(
        'rounded-lg border p-3 text-xs space-y-2',
        outcome.ok
          ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/30'
          : 'border-destructive/40 bg-destructive/5',
      )}
    >
      <p className={cn('font-medium flex items-center gap-1.5', outcome.ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-destructive')}>
        {outcome.ok ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        {outcome.message}
      </p>
      {outcome.detail && (
        <pre className="overflow-x-auto rounded bg-background/60 p-2 text-[10px] font-mono whitespace-pre-wrap break-all">
          {outcome.detail}
        </pre>
      )}
      {outcome.durationMs > 0 && (
        <p className="text-muted-foreground">respondeu em {outcome.durationMs} ms</p>
      )}
    </div>
  );
};

const OrderedList: React.FC<{ items: React.ReactNode[] }> = ({ items }) => (
  <ol className="space-y-2 text-sm">
    {items.map((item, i) => (
      <li key={i} className="flex gap-2.5">
        <span className="mt-0.5 h-5 w-5 shrink-0 rounded-full bg-muted text-[11px] font-semibold flex items-center justify-center">
          {i + 1}
        </span>
        <span className="text-muted-foreground leading-relaxed">{item}</span>
      </li>
    ))}
  </ol>
);

const DerivedRow: React.FC<{ label: string; value?: string }> = ({ label, value }) => (
  <div className="flex items-baseline justify-between gap-3 py-1 border-b border-dashed last:border-0">
    <span className="text-[11px] text-muted-foreground shrink-0">{label}</span>
    <code className="text-[11px] font-mono text-right break-all">{value || '—'}</code>
  </div>
);

// ------------------------------------------------------------------ passo 1

export const StepSite: React.FC<StepProps> = ({ form, patch, config }) => {
  const domainCheck = form.domain ? isValidDomain(form.domain) : null;
  const pixelCheck = form.pixelId ? isValidPixelId(form.pixelId) : null;

  return (
    <div className="space-y-5">
      <StepHeader title="Site e pixel">
        Duas informações bastam. O resto — cookie, endpoint e chave do site — é derivado
        e aparece abaixo enquanto você digita.
      </StepHeader>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="siteName">Nome do site</Label>
          <Input
            id="siteName"
            value={form.siteName}
            onChange={(e) => patch({ siteName: e.target.value })}
            placeholder="Apps TechNews"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="domain">Domínio</Label>
          <Input
            id="domain"
            value={form.domain}
            onChange={(e) => patch({ domain: e.target.value.trim() })}
            placeholder="apps.technewsbrasil.com.br"
            aria-invalid={domainCheck ? !domainCheck.valid : undefined}
          />
          {domainCheck && !domainCheck.valid && (
            <p className="text-[11px] text-destructive">{domainCheck.error}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="pixelId">ID do pixel</Label>
          <Input
            id="pixelId"
            value={form.pixelId}
            onChange={(e) => patch({ pixelId: e.target.value.trim() })}
            placeholder="940750053457681"
            inputMode="numeric"
            aria-invalid={pixelCheck ? !pixelCheck.valid : undefined}
          />
          {pixelCheck && !pixelCheck.valid && (
            <p className="text-[11px] text-destructive">{pixelCheck.error}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="siteKey">Chave do site</Label>
          <Input
            id="siteKey"
            value={form.siteKey || config?.siteKey || ''}
            onChange={(e) => patch({ siteKey: sanitizeSiteKey(e.target.value) })}
            placeholder="apps-technews"
          />
          <p className="text-[11px] text-muted-foreground">
            Identifica o site nos eventos. Só mude se quiser algo mais curto.
          </p>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="capiToken" className="flex items-center gap-1.5">
          <KeyRound className="h-3.5 w-3.5" /> Token da API de Conversões
        </Label>
        <Input
          id="capiToken"
          type="password"
          value={form.capiToken}
          onChange={(e) => patch({ capiToken: e.target.value })}
          placeholder="EAAG…"
          autoComplete="off"
        />
        <p className="text-[11px] text-muted-foreground">
          Cifrado antes de tocar o banco e nunca devolvido pela API. Ao editar um site,
          deixe em branco para manter o token atual.
        </p>
      </div>

      <div className="space-y-2">
        <Label>Eventos deste site</Label>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Checkbox
              checked={form.events.interstitial}
              onCheckedChange={(v) =>
                patch({ events: { ...form.events, interstitial: v === true } })
              }
            />
            Interstitial <span className="text-muted-foreground">(ViewContent)</span>
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Checkbox
              checked={form.events.rewarded}
              onCheckedChange={(v) => patch({ events: { ...form.events, rewarded: v === true } })}
            />
            Rewarded <span className="text-muted-foreground">(RewardedAdView)</span>
          </label>
        </div>
      </div>

      {config && (
        <div className="rounded-lg border bg-muted/30 p-3">
          <p className="text-[11px] font-semibold mb-1.5">Derivado automaticamente</p>
          <DerivedRow label="Cookie compartilhado" value={config.cookieDomain} />
          <DerivedRow label="Endpoint" value={config.endpointUrl} />
          <DerivedRow label="Function" value={config.routerFunctionUrl} />
          {config.domain !== config.cookieDomain.slice(1) && (
            <p className="text-[11px] text-muted-foreground mt-2">
              O cookie usa o domínio raiz, não <code>{config.domain}</code> — é o que permite
              reconhecer o mesmo visitante entre os subdomínios.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

// ------------------------------------------------------------------ passo 2

function generateMasterKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes));
}

export const StepSupabase: React.FC<StepProps & { alreadyPublished?: boolean }> = ({
  config, outcomes, runCheck, alreadyPublished,
}) => {
  const [checking, setChecking] = useState(false);
  const [masterKey, setMasterKey] = useState('');
  // Já publicada: o guia some do caminho, mas continua a um clique — é o que
  // resolve troca de chave, ambiente novo ou alguém repetindo o setup do zero.
  const [showGuide, setShowGuide] = useState(!alreadyPublished);

  if (alreadyPublished && !showGuide) {
    return (
      <div className="space-y-4">
        <StepHeader title="Edge Function">
          Esta etapa é de conta, não de site — e já está pronta.
        </StepHeader>

        <div className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900/50 dark:bg-emerald-950/30">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
          <div className="space-y-1 min-w-0">
            <p className="text-sm font-medium text-emerald-900 dark:text-emerald-200">
              capi-router publicada e respondendo
            </p>
            <p className="text-xs text-muted-foreground break-all">{config?.routerFunctionUrl}</p>
            <p className="text-xs text-muted-foreground">
              Sites novos não exigem deploy nem secret: entram como uma linha na tabela.
            </p>
          </div>
        </div>

        <Button variant="ghost" size="sm" onClick={() => setShowGuide(true)} className="gap-1.5 text-xs">
          <RefreshCw className="h-3.5 w-3.5" /> Ver o código e as instruções mesmo assim
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <StepHeader title="Publicar a Edge Function">
        <Badge variant="secondary" className="mr-1.5">uma vez só</Badge>
        Uma única function atende todos os seus sites. Depois desta etapa, site novo
        não exige deploy nem secret novo.
      </StepHeader>

      {alreadyPublished && (
        <Hint>
          <p>
            A function já está no ar. Siga aqui só se for trocar a chave mestra ou
            configurar outro ambiente — republicar com uma chave diferente torna
            ilegíveis os tokens já salvos.
          </p>
        </Hint>
      )}

      <OrderedList
        items={[
          <>
            No painel do Supabase, vá em <strong>Edge Functions → Deploy a new function</strong>,
            nomeie como <code className="font-mono">capi-router</code> e cole o código abaixo.
          </>,
          <>
            Desligue <strong>Verify JWT</strong>. O Worker chama sem cabeçalho de autorização —
            com a verificação ligada, tudo volta 401.
          </>,
          <>
            Em <strong>Project Settings → Edge Functions → Secrets</strong>, crie
            <code className="font-mono mx-1">CAPI_MASTER_KEY</code> com a chave abaixo.
          </>,
          <>
            Cole a <strong>mesma</strong> chave em <code className="font-mono">CAPI_MASTER_KEY</code> no
            ambiente do servidor (<code className="font-mono">.env.server</code> no local, variáveis
            de ambiente na Vercel).
          </>,
        ]}
      />

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <Label>Chave mestra</Label>
          <Button variant="outline" size="sm" onClick={() => setMasterKey(generateMasterKey())} className="gap-1.5 h-7 text-xs">
            <RefreshCw className="h-3.5 w-3.5" /> Gerar
          </Button>
        </div>
        {masterKey ? (
          <CodeBlock code={masterKey} title="CAPI_MASTER_KEY" language="base64, 32 bytes" />
        ) : (
          <Hint tone="warn">
            <p>
              Gere a chave <strong>uma única vez</strong> e guarde. Ela cifra os tokens de todos
              os sites: trocá-la depois torna ilegível tudo que já foi salvo.
            </p>
            <p>Se você já configurou isso antes, use a chave existente em vez de gerar outra.</p>
          </Hint>
        )}
      </div>

      <CodeBlock
        code={capiRouterSource}
        title="capi-router / index.ts"
        language="TypeScript · Deno"
      />

      <div className="space-y-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!config || checking}
          onClick={async () => {
            setChecking(true);
            await runCheck('function');
            setChecking(false);
          }}
          className="gap-1.5"
        >
          {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
          Testar a function
        </Button>
        <CheckResult outcome={outcomes.function} />
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ passo 3

export const StepCloudflare: React.FC<StepProps> = ({ config, templates, outcomes, runCheck }) => {
  const [checking, setChecking] = useState(false);
  const [modo, setModo] = useState<'novo' | 'existente'>('novo');

  // Host do domínio customizado: o endpoint sem o https:// e sem o /capi.
  const customDomain =
    config?.endpointUrl.replace(/^https?:\/\//, '').replace(/\/capi$/, '') || 'ev.seudominio.com.br';

  return (
    <div className="space-y-5">
      <StepHeader title="Worker e domínio">
        O Worker dá ao evento um endereço no seu próprio domínio e repassa o IP e o
        navegador reais do visitante — é o que sustenta a qualidade do match na Meta.
      </StepHeader>

      <Hint>
        <p>
          <strong>Um Worker atende todos os seus sites.</strong> O código não tem nada
          específico de site: quem identifica o site é a chave que vai no evento. Site novo
          significa apenas mais um domínio apontando para o mesmo Worker.
        </p>
      </Hint>

      <div className="flex gap-2">
        <Button
          variant={modo === 'novo' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setModo('novo')}
          className="text-xs"
        >
          Criar o Worker
        </Button>
        <Button
          variant={modo === 'existente' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setModo('existente')}
          className="text-xs"
        >
          Já tenho um Worker
        </Button>
      </div>

      {modo === 'novo' ? (
        <>
          <OrderedList
            items={[
              <>
                No painel da Cloudflare, abra <strong>Workers &amp; Pages</strong> e clique em{' '}
                <strong>Criar aplicativo</strong>.
              </>,
              <>
                Na tela <em>“Ship something new”</em>, escolha{' '}
                <strong>“Comece com Hello World!”</strong>. As outras opções (GitHub, GitLab,
                modelos, upload) criam projeto com estrutura de arquivos — aqui a gente quer
                um Worker em branco, de arquivo único.
              </>,
              <>
                No campo de nome, use exatamente este valor — ele vale para todos os seus sites:
                <div className="mt-2">
                  <CopyField value={RELAY_WORKER_NAME} />
                </div>
              </>,
              <>
                Conclua a criação (<strong>Deploy</strong>). A Cloudflare publica um Worker de
                exemplo que responde “Hello World” — é normal, vamos substituir agora.
              </>,
              <>
                Abra o editor do Worker (<strong>Edit code</strong> / <strong>Editar código</strong>),{' '}
                <strong>apague todo o conteúdo</strong>, cole o código abaixo e publique de novo.
              </>,
              <>
                No Worker, vá em <strong>Settings → Domains &amp; Routes → Add → Custom domain</strong>{' '}
                e informe:
                <div className="mt-2">
                  <CopyField
                    value={customDomain}
                    hint="Este subdomínio precisa estar num domínio que já está na sua conta Cloudflare."
                  />
                </div>
              </>,
              <>
                O certificado sai em segundos, às vezes poucos minutos. O teste no fim desta
                página diz a hora em que ficou pronto.
              </>,
            ]}
          />
        </>
      ) : (
        <>
          <OrderedList
            items={[
              <>
                Abra o Worker que você já usa para conversões e entre no editor de código.
              </>,
              <>
                Substitua o conteúdo pelo código abaixo. Na prática muda uma linha: a{' '}
                <code className="font-mono">SUPABASE_CAPI_URL</code> passa a apontar para a{' '}
                <code className="font-mono">capi-router</code>, que atende todos os sites.
              </>,
              <>
                Em <strong>Settings → Domains &amp; Routes → Add → Custom domain</strong>, acrescente
                o domínio deste site (os domínios que já existem continuam funcionando):
                <div className="mt-2">
                  <CopyField value={customDomain} />
                </div>
              </>,
            ]}
          />

          <Hint tone="warn">
            <p>
              Ao trocar a URL de um Worker que já está em produção, os sites que passam por ele
              começam a depender da tabela de sites. Confirme que cada domínio atendido por esse
              Worker já está cadastrado aqui antes de publicar — ou crie um Worker novo e migre
              um site por vez.
            </p>
          </Hint>
        </>
      )}

      {templates && config && (
        <CodeBlock
          code={templates.worker}
          title={TEMPLATE_META.worker.title}
          language="JavaScript · Cloudflare Worker"
          highlights={[config.routerFunctionUrl]}
        />
      )}

      <div className="space-y-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!config || checking}
          onClick={async () => {
            setChecking(true);
            await runCheck('endpoint');
            setChecking(false);
          }}
          className="gap-1.5"
        >
          {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
          Testar o endpoint
        </Button>
        <CheckResult outcome={outcomes.endpoint} />
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ passo 4

export const StepGtm: React.FC<StepProps & { onDone: () => void }> = ({
  form, config, templates, onDone,
}) => {
  const tags: TemplateId[] = ['pixelBase'];
  if (form.events.interstitial) tags.push('interstitial');
  if (form.events.rewarded) tags.push('rewarded');

  return (
    <div className="space-y-5">
      <StepHeader title="Tags no Google Tag Manager">
        Três tags de HTML personalizado, todas com o acionador
        <strong> Inicialização — todas as páginas</strong>. As tags de anúncio já garantem os
        cookies antes de o anúncio abrir.
      </StepHeader>

      {templates && config && (
        <div className="space-y-4">
          {tags.map((id) => (
            <div key={id} className="space-y-1.5">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-semibold">{TEMPLATE_META[id].title}</h3>
                <Badge variant="outline" className="text-[10px]">{TEMPLATE_META[id].gtmTrigger}</Badge>
              </div>
              <p className="text-xs text-muted-foreground">{TEMPLATE_META[id].description}</p>
              <CodeBlock
                code={templates[id]}
                language={TEMPLATE_META[id].gtmTagType}
                highlights={[config.pixelId, config.endpointUrl, config.cookieDomain, config.siteKey]}
              />
            </div>
          ))}
        </div>
      )}

      <Hint>
        <p>
          Os trechos destacados são o que o assistente preencheu: confira o pixel e o domínio
          num relance antes de publicar o container.
        </p>
      </Hint>

      <Button variant="outline" size="sm" onClick={onDone} className="gap-1.5">
        <CheckCircle2 className="h-4 w-4" /> Publiquei o container
      </Button>
    </div>
  );
};

// ------------------------------------------------------------------ passo 5

const EVENTOS = [
  { name: 'ViewContent' as const, flag: 'interstitial' as const, label: 'interstitial' },
  { name: 'RewardedAdView' as const, flag: 'rewarded' as const, label: 'rewarded' },
];

export const StepMeta: React.FC<StepProps> = ({ form, patch, config, outcomes, runCheck }) => {
  const [testing, setTesting] = useState<'ViewContent' | 'RewardedAdView' | null>(null);

  return (
    <div className="space-y-5">
      <StepHeader title="Conversões na Meta e teste real">
        Por último, as conversões personalizadas — e um evento de verdade percorrendo a
        cadeia inteira, para você não sair daqui no escuro.
      </StepHeader>

      <div className="rounded-lg border p-3 space-y-2">
        <p className="text-xs font-semibold">Conversões personalizadas a criar</p>
        <div className="space-y-2 text-sm">
          {form.events.interstitial && (
            <div className="flex items-start gap-2">
              <Badge variant="secondary" className="mt-0.5 shrink-0">interstitial</Badge>
              <p className="text-muted-foreground text-xs">
                Regra sobre o evento padrão <code className="font-mono">ViewContent</code>.
              </p>
            </div>
          )}
          {form.events.rewarded && (
            <div className="flex items-start gap-2">
              <Badge variant="secondary" className="mt-0.5 shrink-0">rewarded</Badge>
              <p className="text-muted-foreground text-xs">
                Regra sobre o evento personalizado <code className="font-mono">RewardedAdView</code>.
              </p>
            </div>
          )}
        </div>
        <a
          href="https://business.facebook.com/events_manager2"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          Abrir o Gerenciador de Eventos <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="testCode">Código de teste</Label>
        <Input
          id="testCode"
          value={form.testEventCode}
          onChange={(e) => patch({ testEventCode: e.target.value.trim() })}
          placeholder="TEST12345"
          className="max-w-xs font-mono"
        />
        <p className="text-[11px] text-muted-foreground">
          Em <strong>Testar eventos</strong>, no Gerenciador. Com esse código o evento aparece
          no painel de testes e não entra nos seus dados.
        </p>
      </div>

      {/* Um disparo por evento: interstitial e rewarded viajam pelo mesmo
          caminho, mas com nome, slot e categoria diferentes na Meta — testar um
          não prova o outro. */}
      <div className="space-y-3">
        {EVENTOS.filter((ev) => form.events[ev.flag]).map((ev) => {
          const outcome = outcomes[`meta:${ev.name}`];
          return (
            <div key={ev.name} className="space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <Button
                  size="sm"
                  variant={outcome?.ok ? 'outline' : 'default'}
                  disabled={!config || testing !== null || !form.testEventCode.trim()}
                  onClick={async () => {
                    setTesting(ev.name);
                    await runCheck('meta', ev.name);
                    setTesting(null);
                  }}
                  className="gap-1.5"
                >
                  {testing === ev.name ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : outcome?.ok ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  ) : (
                    <PlayCircle className="h-4 w-4" />
                  )}
                  {outcome?.ok ? `Testar ${ev.label} de novo` : `Testar ${ev.label}`}
                </Button>
                <code className="text-[10px] text-muted-foreground font-mono">{ev.name}</code>
              </div>
              <CheckResult outcome={outcome} />
            </div>
          );
        })}
      </div>

      {EVENTOS.some((ev) => form.events[ev.flag] && outcomes[`meta:${ev.name}`]?.ok) && (
        <Hint>
          <p>
            Abra <strong>Testar eventos</strong> no Gerenciador: o evento aparece em segundos.
            Confira o <code className="font-mono">content_category</code> — é ele que separa{' '}
            <code className="font-mono">interstitial</code> de{' '}
            <code className="font-mono">rewarded</code> nas suas conversões personalizadas.
          </p>
          <p>
            No teste, <code className="font-mono">fbc</code> e <code className="font-mono">fbp</code>{' '}
            vão vazios — não existe clique nem cookie aqui. Nos eventos reais do site eles são
            preenchidos pela tag, e a correspondência na Meta fica melhor.
          </p>
        </Hint>
      )}
    </div>
  );
};
