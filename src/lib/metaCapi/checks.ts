/**
 * Testes ao vivo da cadeia de conversões, direto do browser.
 *
 * Isso só é possível porque o Worker e a Edge Function respondem com
 * `Access-Control-Allow-Origin: *` — verificado contra o endpoint de produção.
 * Nenhuma credencial passa por aqui: quem fala com a Meta é a Edge Function,
 * que guarda o token do lado dela.
 */

export type CheckLayer = 'endpoint' | 'function' | 'meta';

export interface CheckOutcome {
  ok: boolean;
  layer: CheckLayer;
  /** Frase curta para o operador, em pt-BR. */
  message: string;
  /** Texto cru devolvido pela camada que falhou (ex.: o erro da Meta). */
  detail?: string;
  status?: number;
  durationMs: number;
}

const TIMEOUT_MS = 12_000;

async function timedFetch(url: string, init?: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const started = performance.now();
  try {
    const resp = await fetch(url, { ...init, signal: controller.signal });
    return { resp, durationMs: Math.round(performance.now() - started) };
  } finally {
    clearTimeout(timer);
  }
}

/** Erro de rede no browser é opaco por design — traduz para algo acionável. */
function networkMessage(layer: CheckLayer, url: string): string {
  const host = (() => {
    try {
      return new URL(url).host;
    } catch {
      return url;
    }
  })();
  if (layer === 'endpoint') {
    return `Não houve resposta de ${host}. Verifique se a rota de domínio customizado aponta para o Worker e se o DNS já propagou.`;
  }
  return `Não houve resposta de ${host}. Verifique se a function está publicada.`;
}

/** Camada 1 — o endpoint no seu domínio (Worker + DNS) está de pé? */
export async function checkEndpoint(endpointUrl: string): Promise<CheckOutcome> {
  try {
    const { resp, durationMs } = await timedFetch(endpointUrl, { method: 'GET' });
    if (resp.ok) {
      return { ok: true, layer: 'endpoint', message: 'Endpoint respondendo.', status: resp.status, durationMs };
    }
    return {
      ok: false,
      layer: 'endpoint',
      message: `O endpoint respondeu ${resp.status}. O esperado é 200.`,
      detail: (await resp.text()).slice(0, 400),
      status: resp.status,
      durationMs,
    };
  } catch {
    return { ok: false, layer: 'endpoint', message: networkMessage('endpoint', endpointUrl), durationMs: 0 };
  }
}

/** Camada 2 — a Edge Function está publicada? */
export async function checkFunction(routerFunctionUrl: string): Promise<CheckOutcome> {
  // Sem guarda, uma URL vazia faz o fetch resolver contra a própria página do
  // app, que responde 200 — e a checagem reportaria "publicada" sem nada
  // publicado. Acontecia em Supabase self-hosted, onde a derivação da URL
  // devolvia string vazia por não casar com o padrão *.supabase.co.
  if (!routerFunctionUrl || !/^https?:\/\//i.test(routerFunctionUrl)) {
    return {
      ok: false,
      layer: 'function',
      message:
        'URL da function não configurada. Defina VITE_SUPABASE_URL com o endpoint do seu Supabase (hosted ou self-hosted).',
      durationMs: 0,
    };
  }

  try {
    const { resp, durationMs } = await timedFetch(routerFunctionUrl, { method: 'GET' });
    if (resp.ok) {
      return { ok: true, layer: 'function', message: 'Function publicada e respondendo.', status: resp.status, durationMs };
    }
    return {
      ok: false,
      layer: 'function',
      message:
        resp.status === 401
          ? 'A function respondeu 401. Publique com a verificação de JWT desligada — o Worker chama sem Authorization.'
          : `A function respondeu ${resp.status}. O esperado é 200.`,
      detail: (await resp.text()).slice(0, 400),
      status: resp.status,
      durationMs,
    };
  } catch {
    return { ok: false, layer: 'function', message: networkMessage('function', routerFunctionUrl), durationMs: 0 };
  }
}

export interface TestEventInput {
  endpointUrl: string;
  siteKey: string;
  eventName: 'ViewContent' | 'RewardedAdView';
  testEventCode: string;
  pageUrl: string;
}

/**
 * Camada 3 — a cadeia inteira até a Meta.
 *
 * Vai pelo endpoint real (mesmo caminho do evento de verdade), com
 * `test_event_code` para cair em "Testar eventos" e não sujar os dados.
 */
export async function sendTestEvent(input: TestEventInput): Promise<CheckOutcome> {
  const payload = {
    site_key: input.siteKey,
    event_name: input.eventName,
    event_type: input.eventName === 'RewardedAdView' ? 'google_rewarded' : 'google_vignette',
    event_id: `wizard_test_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    event_source_url: input.pageUrl,
    referrer_url: '',
    fbc: '',
    fbp: '',
    external_id: `wizard_test_${Date.now()}`,
    slot_id: input.eventName === 'RewardedAdView' ? 'google_rewarded' : 'google_vignette_interstitial',
    test_event_code: input.testEventCode,
  };

  try {
    const { resp, durationMs } = await timedFetch(input.endpointUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify(payload),
    });

    if (resp.status === 204 || resp.ok) {
      return {
        ok: true,
        layer: 'meta',
        message: 'A Meta aceitou o evento. Confira em Testar eventos, no Gerenciador.',
        status: resp.status,
        durationMs,
      };
    }

    const raw = (await resp.text()).slice(0, 1200);

    // A function devolve o erro da Meta no corpo — é o diagnóstico mais valioso
    // que existe aqui, então é repassado inteiro em vez de virar "falhou".
    let message = `A cadeia respondeu ${resp.status}.`;
    try {
      const parsed = JSON.parse(raw);
      if (parsed?.error === 'site_not_found') {
        message = 'A function não encontrou este site na tabela. Salve o site antes de testar.';
      } else if (parsed?.error === 'site_inactive') {
        message = 'Este site está marcado como inativo.';
      } else if (parsed?.meta_status) {
        message = `A Meta recusou o evento (HTTP ${parsed.meta_status}).`;
      }
    } catch {
      /* corpo não-JSON: mantém a mensagem genérica com o detalhe cru */
    }

    return { ok: false, layer: 'meta', message, detail: raw, status: resp.status, durationMs };
  } catch {
    return { ok: false, layer: 'meta', message: networkMessage('endpoint', input.endpointUrl), durationMs: 0 };
  }
}
