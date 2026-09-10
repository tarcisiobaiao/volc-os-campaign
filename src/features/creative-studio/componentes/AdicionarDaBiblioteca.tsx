import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { criativosApi } from '@/lib/criativosApi';
import { adicionarAssetsAoPack, type CreativePack } from '../api';
import { BuscaBiblioteca, useBuscaPaginada } from './BuscaBiblioteca';

export function AdicionarDaBiblioteca({ pack, onSaved }: { pack: CreativePack; onSaved: (pack: CreativePack) => void }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const lock = useRef(false);
  const { texto, setTexto, consulta, setConsulta } = useBuscaPaginada();
  const assets = useQuery({ queryKey: ['pack-library-assets', pack.id, consulta],
    queryFn: () => criativosApi.assets({kind: 'imagem', busca: consulta.q, offset: consulta.offset, limite: 24}),
    enabled: open, gcTime: 0 });
  const existing = new Set(pack.manifest.items.map(item => item.master_ref));
  const remaining = Math.max(0, 10 - pack.manifest.items.length);
  async function save() {
    if (lock.current || !selected.length || selected.length > remaining) return;
    lock.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const updated = await adicionarAssetsAoPack(pack.id, selected, pack.manifest_sha256);
      onSaved(updated); setSelected([]); setOpen(false); setMessage('Peças adicionadas. As montagens anteriores continuam preservadas.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível salvar. Atualize o pack e tente novamente.'); }
    finally { lock.current = false; setBusy(false); }
  }
  if (pack.manifest.source !== 'STUDIO') return null;
  return <section aria-label="Adicionar peças ao pack" className="space-y-4 border-t border-border pt-5">
    <Button type="button" variant="outline" aria-expanded={open} disabled={busy || remaining === 0} onClick={() => setOpen(v => !v)}>Adicionar peças da biblioteca</Button>
    {!remaining && <p className="text-sm text-muted-foreground">Este pack atingiu o limite de 10 peças. Crie outro pack para organizar o próximo teste.</p>}
    {open && <>
      <p className="text-sm text-muted-foreground">Escolha até {remaining} peças. O que já está no pack permanece intacto.</p>
      <BuscaBiblioteca value={texto} onChange={setTexto} label="Buscar imagem pelo nome do projeto" />
      {assets.isFetching && <p role="status">Buscando imagens…</p>}
      {assets.isError && <p role="alert">Não foi possível consultar a biblioteca. <Button variant="ghost" onClick={() => void assets.refetch()}>Tentar novamente</Button></p>}
      <ul className="grid gap-4 grid-cols-2 md:grid-cols-4 lg:grid-cols-6">{assets.data?.assets.map(asset => {
        const included = existing.has(asset.id);
        return <li key={asset.id}><label className={`block overflow-hidden rounded-lg border p-2 ${selected.includes(asset.id) ? 'border-primary bg-primary/5' : 'border-border'}`}>
          {asset.previewUrl && <img src={asset.previewUrl} alt="" loading="lazy" className="aspect-square w-full object-contain" />}
          <span className="mt-2 flex items-start gap-2 text-sm"><input type="checkbox" checked={included || selected.includes(asset.id)}
            disabled={busy || included || assets.isFetching || (!selected.includes(asset.id) && selected.length >= remaining)}
            onChange={() => setSelected(s => s.includes(asset.id) ? s.filter(id => id !== asset.id) : [...s, asset.id])} className="mt-1 accent-primary" />
            <span className="min-w-0 break-words">{asset.projetoTitulo || asset.slot}{included && <span className="block text-xs text-muted-foreground">Já está neste pack</span>}</span></span>
        </label></li>;
      })}</ul>
      {!assets.isFetching && assets.data?.assets.length === 0 && <p>Nenhuma imagem encontrada. Tente outro nome.</p>}
      <div className="flex flex-wrap items-center gap-3">
        {consulta.offset > 0 && <Button variant="outline" disabled={assets.isFetching} onClick={() => setConsulta(c => ({...c, offset: Math.max(0, c.offset - 24)}))}>Anterior</Button>}
        {assets.data && consulta.offset + 24 < assets.data.total && <Button variant="outline" disabled={assets.isFetching} onClick={() => setConsulta(c => ({...c, offset: c.offset + 24}))}>Próximas imagens</Button>}
        <Button disabled={busy || !selected.length || selected.length > remaining} onClick={() => void save()}>{busy ? 'Salvando…' : `Adicionar ${selected.length} peças ao pack`}</Button>
      </div>
    </>}
    {message && <p role="status" className="text-sm">{message}</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </section>;
}
