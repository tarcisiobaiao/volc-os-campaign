import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface Connection { id: string; name: string; business_id: string; enabled: boolean; verified_at: string }
interface Listing { connections: Connection[]; selected_id: string | null; vault_ready: boolean; truncated: boolean }

export async function businessRequest(path = '', body?: unknown): Promise<any> {
  const base = (import.meta.env.VITE_PAUTADOR_API_URL || '').replace(/\/$/, '');
  if (!base) throw new Error('O endereço do backend não está configurado.');
  const { data } = await supabase.auth.getSession();
  if (!data.session) throw new Error('Entre novamente para configurar a integração.');
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 60000);
  try {
    const response = await fetch(`${base}/api/trafego/meta/business${path}`, {
      method: body === undefined ? 'GET' : 'POST', signal: abort.signal, cache: 'no-store',
      headers: { Authorization: `Bearer ${data.session.access_token}`, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) {
      // Never render the response body: gateways and validators may echo secrets.
      const messages: Record<number, string> = {
        401: 'Sua sessão expirou. Entre novamente.', 403: 'Apenas administradores podem configurar conexões.',
        409: 'A conexão precisa ser recadastrada antes do uso.',
        422: 'Não foi possível confirmar a conexão. Confira Business ID, token de usuário de sistema e permissão business_management.',
        503: 'O cofre oficial está indisponível. Tente novamente ou confira a configuração do servidor.',
      };
      throw new Error(messages[response.status] || 'Não foi possível concluir a operação. Tente novamente.');
    }
    try { return await response.json(); }
    catch { throw new Error('O servidor retornou uma resposta inválida. Atualize a lista antes de tentar novamente.'); }
  } catch (error) {
    if (error instanceof TypeError || (error instanceof Error && error.name === 'AbortError'))
      throw new Error('O backend não respondeu a tempo. Atualize a lista antes de tentar salvar novamente.');
    throw error;
  } finally { clearTimeout(timer); }
}

export function MetaBusinessConnections() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [name, setName] = useState('');
  const [business, setBusiness] = useState('');
  const [token, setToken] = useState('');
  async function refresh() { setListing(await businessRequest()); }
  useEffect(() => { let mounted = true; businessRequest().then(data => { if (mounted) setListing(data); })
    .catch(e => { if (mounted) setError(e.message); }).finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; }; }, []);
  async function action(work: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try { await work(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível concluir.'); }
    finally { setBusy(false); }
  }
  return <section aria-labelledby="meta-business-heading" className="space-y-6">
    <header className="space-y-2">
      <h2 id="meta-business-heading" className="text-xl font-semibold">Business Managers</h2>
      <p className="max-w-prose text-sm text-muted-foreground">Conecte um usuário de sistema e escolha o negócio usado para ler ativos e preparar campanhas. O token fica criptografado no servidor e não pode ser consultado pela interface.</p>
    </header>
    {error && <div role="alert" className="rounded-lg border border-destructive bg-card p-4 space-y-3"><p>{error}</p><Button variant="secondary" disabled={busy} onClick={() => void action(refresh)}>Atualizar lista</Button></div>}
    {notice && <p role="status" className="rounded-lg border border-success bg-card p-4">{notice}</p>}
    {loading ? <div role="status" className="h-32 rounded-lg bg-muted motion-safe:animate-pulse p-4">Carregando conexões…</div> :
      <div className="divide-y rounded-lg border bg-card">
        {!listing?.connections.length && <p className="p-5 text-sm">Nenhuma conexão cadastrada. Adicione o primeiro Business Manager abaixo.</p>}
        {listing?.connections.map(connection => <article key={connection.id} className="p-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1 min-w-0 space-y-1"><h3 className="font-semibold break-words">{connection.name}</h3>
            <p className="text-sm text-muted-foreground break-all">Business {connection.business_id}</p>
            <p className="text-sm">{!connection.enabled ? 'Desconectado no VOLC' : listing.selected_id === connection.id ? 'Selecionado para esta operação' : 'Disponível para seleção'}</p>
            <p className="text-xs text-muted-foreground">Usuário de sistema conferido em {new Date(connection.verified_at).toLocaleString('pt-BR')}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={busy || !connection.enabled} onClick={() => void action(async () => {
              await businessRequest(`/${connection.id}/select`, {}); setNotice('Conexão selecionada. Recarregue as contas no criador antes de continuar.');
            })}>{listing.selected_id === connection.id ? 'Conferir conexão' : 'Usar este negócio'}</Button>
            <Button variant="outline" disabled={busy || !connection.enabled} onClick={() => {
              if (window.confirm(`Desconectar ${connection.name} do VOLC? Isso não revoga o token na Meta nem pausa campanhas existentes.`))
                void action(async () => { await businessRequest(`/${connection.id}/disable`, {}); setNotice('Conexão desabilitada no VOLC. Para revogar o token, use as configurações da Meta.'); });
            }}>Desconectar</Button>
          </div>
        </article>)}
      </div>}
    {listing?.truncated && <p role="alert">Exibindo as primeiras 100 conexões. A lista está parcial.</p>}
    <form className="rounded-lg border bg-card p-5 sm:p-6 space-y-5" autoComplete="off" onSubmit={e => {
      e.preventDefault(); const submitted = token; setToken('');
      void action(async () => { await businessRequest('', { name: name.trim(), business_id: business.trim(), token: submitted });
        setName(''); setBusiness(''); setNotice('Token conferido e salvo. Selecione “Usar este negócio” para conectar o criador.'); });
    }}>
      <h3 className="text-lg font-semibold">Adicionar ou renovar conexão</h3>
      <p className="text-sm text-muted-foreground">Use o ID do portfólio empresarial, não o ID da conta de anúncios. Salvar para o mesmo Business substitui o token anterior.</p>
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="space-y-2"><Label htmlFor="meta-business-name">Nome para identificar o negócio</Label><Input id="meta-business-name" value={name} onChange={e => setName(e.target.value)} required maxLength={120} disabled={busy} /></div>
        <div className="space-y-2"><Label htmlFor="meta-business-id">Business Manager ID</Label><Input id="meta-business-id" value={business} onChange={e => setBusiness(e.target.value)} required pattern="[0-9]{5,30}" inputMode="numeric" disabled={busy} /></div>
      </div>
      <div className="space-y-2"><Label htmlFor="meta-business-token">Token de usuário de sistema</Label><Input id="meta-business-token" type="password" autoComplete="new-password" spellCheck={false} value={token} onChange={e => setToken(e.target.value)} required minLength={20} maxLength={4096} disabled={busy} aria-describedby="meta-token-help" />
        <p id="meta-token-help" className="text-sm text-muted-foreground">O backend consulta a Meta para confirmar o vínculo com este negócio. A conferência exige business_management; gerenciar anúncios também exige ads_management e acesso aos ativos. O token não volta na resposta.</p>
      </div>
      {listing && !listing.vault_ready && <p role="alert">O servidor ainda precisa da chave de criptografia. Nenhum token será salvo sem ela.</p>}
      <Button type="submit" disabled={busy || !listing?.vault_ready}>{busy ? 'Conferindo conexão…' : 'Conferir e salvar token'}</Button>
    </form>
    <footer className="flex flex-col sm:flex-row gap-4 sm:justify-between text-sm">
      <p className="max-w-prose text-muted-foreground">Os ativos são consultados quando você os solicita. Sincronização contínua exige um serviço em execução; salvar o token não ativa campanhas nem configura Meta CAPI.</p>
      <Button asChild variant="secondary"><Link to="/trafego/meta/nova">Preparar campanha pausada</Link></Button>
    </footer>
  </section>;
}
