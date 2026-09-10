import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { businessRequest } from '@/components/settings/MetaBusinessConnections';
import { pautadorApi, type ContaMetaLocal } from '@/lib/pautadorApi';
import { Button } from '@/components/ui/button';

type Business = { id: string; name: string; enabled: boolean };
/** Credential values never enter this component. Selection is owner-bound on the server. */
export function EscolherBusinessMeta({ demo, onAccounts, onChangeBusiness }: {
  demo: boolean; onAccounts: (accounts: ContaMetaLocal[]) => void; onChangeBusiness: () => void;
}) {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const callbacks = useRef({ onAccounts, onChangeBusiness });
  callbacks.current = { onAccounts, onChangeBusiness };
  async function load(connection?: string) {
    const ticket = ++sequence.current;
    setBusy(true); setError('');
    try {
      if (connection) {
        await businessRequest(`/${connection}/select`, {});
        if (ticket !== sequence.current) return;
        setSelected(connection);
        callbacks.current.onChangeBusiness();
        callbacks.current.onAccounts([]);
      } else {
        const listing = await businessRequest();
        if (ticket !== sequence.current) return;
        setBusinesses(listing.connections.filter((item: Business) => item.enabled));
        setSelected(listing.selected_id || '');
        if (!listing.selected_id) return;
      }
      const result = await pautadorApi.contasMetaLocal();
      if (ticket === sequence.current) callbacks.current.onAccounts(result.contas);
    } catch (e) {
      if (ticket === sequence.current) setError(e instanceof Error ? e.message : 'Não foi possível consultar as contas.');
    } finally { if (ticket === sequence.current) setBusy(false); }
  }
  useEffect(() => {
    if (!demo) void load();
    return () => { sequence.current++; };
  }, [demo]);
  if (demo) return <p className="text-sm text-muted-foreground">Demonstração: as conexões reais não são consultadas. Abra o criador sem modo=demo para usar suas contas.</p>;
  return <div className="space-y-2">
    <label htmlFor="meta-business" className="block text-sm font-medium">Portfólio empresarial (BM)</label>
    <select id="meta-business" value={selected} disabled={busy} onChange={e => { if (e.target.value) void load(e.target.value); }}
      className="min-h-11 w-full rounded-md border border-input bg-card px-3">
      <option value="">Selecione um portfólio</option>
      {businesses.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
    {busy && <p role="status" className="text-sm text-muted-foreground">Consultando as contas do portfólio…</p>}
    {error && <div role="alert"><p className="text-sm text-destructive">{error}</p><Button variant="outline" onClick={() => void load()}>Tentar novamente</Button></div>}
    {!busy && !error && !businesses.length && <Link className="text-sm text-primary underline" to="/settings/integrations">Cadastrar uma conexão Meta em Integrações</Link>}
  </div>;
}
