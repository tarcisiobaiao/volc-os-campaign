import { useCallback, useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';
import { useToast } from '@/hooks/use-toast';

// Mesma resolução do secureApi: dev aponta pro Express (:3001), produção usa as
// serverless da Vercel na mesma origem.
const envUrl = import.meta.env.VITE_API_URL || '';
const API_BASE_URL = envUrl === '/api' ? '' : envUrl;

export interface MetaCapiSite {
  id: number;
  site_key: string;
  site_name: string;
  domain: string;
  cookie_domain: string;
  endpoint_url: string;
  pixel_id: string;
  events: { interstitial: boolean; rewarded: boolean };
  is_active: boolean;
  test_event_code: string | null;
  /** O token NUNCA volta do servidor — só a informação de que existe. */
  has_token: boolean;
  last_check_at: string | null;
  last_check_result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface SaveSitePayload {
  id?: number;
  site_key: string;
  site_name: string;
  domain: string;
  cookie_domain: string;
  endpoint_url: string;
  pixel_id: string;
  events: { interstitial: boolean; rewarded: boolean };
  test_event_code?: string;
  /** Texto puro; trafega só na criação/troca e é cifrado no servidor. */
  capi_token?: string;
}

async function authedFetch(path: string, init: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  if (!token) {
    throw new Error('Sessão expirada. Entre novamente para continuar.');
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(init.headers || {}),
    },
  });

  const text = await resp.text();
  const body = text ? JSON.parse(text) : null;

  if (!resp.ok) {
    throw new Error(body?.error || `Falha na requisição (${resp.status}).`);
  }
  return body;
}

export function useMetaCapiSites() {
  const [sites, setSites] = useState<MetaCapiSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  /**
   * `silent` = recarga de fundo (depois de salvar/remover/testar). Sem isso, o
   * `loading` global piscaria e trocaria a tela que o operador está usando.
   */
  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      // A API devolve o array direto; o fallback aceita um envelope caso
      // o contrato ganhe metadados no futuro.
      const body = await authedFetch('/api/meta-capi/sites');
      setSites(Array.isArray(body) ? body : body?.sites || []);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao carregar os sites';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveSite = useCallback(
    async (payload: SaveSitePayload): Promise<MetaCapiSite | null> => {
      setSaving(true);
      try {
        const body = await authedFetch('/api/meta-capi/sites', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        await load({ silent: true });
        toast({ title: payload.id ? 'Site atualizado' : 'Site configurado ✅' });
        return (body?.id ? body : body?.site) || null;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Erro ao salvar o site';
        toast({ title: 'Não foi possível salvar', description: message, variant: 'destructive' });
        return null;
      } finally {
        setSaving(false);
      }
    },
    [load, toast],
  );

  const removeSite = useCallback(
    async (id: number) => {
      try {
        await authedFetch(`/api/meta-capi/sites?id=${id}`, { method: 'DELETE' });
        await load({ silent: true });
        toast({ title: 'Site removido' });
        return true;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Erro ao remover';
        toast({ title: 'Não foi possível remover', description: message, variant: 'destructive' });
        return false;
      }
    },
    [load, toast],
  );

  const recordCheck = useCallback(
    async (id: number, result: Record<string, unknown>) => {
      try {
        await authedFetch(`/api/meta-capi/sites?id=${id}&action=check`, {
          method: 'PATCH',
          body: JSON.stringify({ result }),
        });
        await load({ silent: true });
      } catch {
        // Falhar ao registrar o teste não pode atrapalhar o teste em si.
      }
    },
    [load],
  );

  return { sites, loading, saving, error, reload: load, saveSite, removeSite, recordCheck };
}
