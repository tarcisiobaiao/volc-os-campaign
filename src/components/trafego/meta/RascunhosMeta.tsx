import { useEffect, useRef, useState } from 'react';
import { FileEditIcon } from '@hugeicons/core-free-icons';
import { Icone } from '@/components/ui/icone';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { archiveMetaCampaignDraft, listMetaCampaignDrafts, type MetaDraftList, type MetaDraftSummary } from '@/lib/metaCampaignDraftApi';

export function RascunhosMeta({ currentRef, beforeResume, demo = false, onResume = ref => {
  // A draft's identity is initialized on mount. A fresh navigation prevents old
  // editor state from being written over the draft being resumed.
  window.location.assign(`/trafego/meta/nova?rascunho=${encodeURIComponent(ref)}`);
} }: { currentRef: string; beforeResume: () => Promise<boolean>; demo?: boolean; onResume?: (ref: string) => void }) {
  const [list, setList] = useState<MetaDraftList>();
  const [busy, setBusy] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<MetaDraftSummary>();
  const [notice, setNotice] = useState('');
  const sequence = useRef(0);
  const resumeLock = useRef(false);
  async function load(offset = 0) {
    if (demo) return;
    const id = ++sequence.current;
    setBusy(true); setError('');
    try {
      const page = await listMetaCampaignDrafts(offset);
      if (id === sequence.current) setList(previous => ({ ...page, items: offset && previous
        ? [...previous.items, ...page.items.filter(item => !previous.items.some(old => old.draft_ref === item.draft_ref))] : page.items }));
    } catch { if (id === sequence.current) setError('Não foi possível consultar seus rascunhos.'); }
    finally { if (id === sequence.current) setBusy(false); }
  }
  useEffect(() => { void load(); return () => { ++sequence.current; }; }, [demo]);
  async function resume(ref: string) {
    if (resumeLock.current) return;
    resumeLock.current = true; setResuming(true); setError('');
    try {
      if (!await beforeResume()) { setError('Não trocamos de rascunho: salve ou recupere a montagem atual antes de continuar.'); return; }
      onResume(ref);
    } catch { setError('Não foi possível salvar a montagem atual. Nada foi descartado.'); }
    finally { resumeLock.current = false; setResuming(false); }
  }
  async function remove(item: MetaDraftSummary) {
    if (resumeLock.current) return;
    resumeLock.current = true; setResuming(true); setError(''); setNotice('');
    try {
      // Flush an active save first. The version shown at confirmation remains
      // authoritative: if a save changed it, require a fresh confirmation.
      if (!await beforeResume()) throw new Error('Salve ou recupere a montagem atual antes de excluir.');
      await archiveMetaCampaignDraft(item.draft_ref, item.version);
      setDeleting(undefined);
      setList(previous => previous && ({ ...previous, items: previous.items.filter(d => d.draft_ref !== item.draft_ref) }));
      setNotice('Rascunho excluído. Imagens, packs e recibos foram preservados.');
      if (item.draft_ref === currentRef) window.location.assign('/trafego/meta/nova');
      else await load();
    } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível excluir o rascunho.'); setDeleting(undefined); }
    finally { resumeLock.current = false; setResuming(false); }
  }
  const count = list ? `${list.items.length}${list.has_more ? '+' : ''}` : '';
  return <Popover onOpenChange={open => { if (open) void load(); }}>
    <PopoverTrigger asChild>
      <Button type="button" variant="outline" className="min-h-11 gap-2" aria-label={`Rascunhos${error ? ': consulta indisponível' : count ? `: ${count} salvos` : ''}`}>
        <Icone icon={FileEditIcon} tamanho="sm" /> <span>Rascunhos</span>
        {(count || error) && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold tabular-nums text-primary">{error ? '!' : count}</span>}
      </Button>
    </PopoverTrigger>
    <PopoverContent align="end" className="w-[min(26rem,calc(100vw-2rem))] p-0 motion-reduce:animate-none" aria-label="Seus rascunhos de campanha">
      <div className="border-b p-4"><h2 className="font-display text-lg font-semibold">Continue de onde parou</h2>
        <p className="mt-1 text-sm text-muted-foreground">Montagens salvas na sua conta. Retomar não publica anúncios.</p></div>
      <div className="max-h-[55vh] overflow-y-auto p-4" aria-busy={busy || resuming}>
        {notice && <p role="status" className="mb-3 text-sm">{notice}</p>}
        {demo ? <p className="text-sm">Abra o criador fora da demonstração para consultar seus rascunhos reais.</p> : <>
          {error && <div role="alert" className="mb-3 text-sm text-destructive"><p>{error}</p>
            <Button variant="outline" className="mt-2 min-h-11" disabled={busy || resuming} onClick={() => void load()}>Consultar novamente</Button></div>}
          {busy && <p role="status" className="py-3 text-sm text-muted-foreground">Consultando rascunhos…</p>}
          {!busy && !error && list?.items.length === 0 && <p className="py-3 text-sm text-muted-foreground">Nenhum rascunho salvo ainda. Sua montagem aparecerá aqui após ser salva.</p>}
          <ul className="divide-y">{list?.items.map(item => <li key={item.draft_ref} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between gap-3"><div className="min-w-0">
              <p className="break-words font-semibold">{item.campaign_name.trim() || 'Campanha sem nome'}</p>
              <p className="mt-1 text-xs text-muted-foreground">{item.adset_count} conjuntos · {item.ad_count} anúncios</p>
              <time className="mt-1 block text-xs text-muted-foreground" dateTime={item.updated_at}>{new Date(item.updated_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</time>
            </div><Button variant="outline" className="min-h-11 shrink-0" disabled={resuming || currentRef === item.draft_ref}
              aria-label={`${currentRef === item.draft_ref ? 'Em edição' : 'Continuar'}: ${item.campaign_name || 'Campanha sem nome'}`}
              onClick={() => void resume(item.draft_ref)}>{currentRef === item.draft_ref ? 'Em edição' : 'Continuar'}</Button></div>
            {deleting?.draft_ref === item.draft_ref ? <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
              <p className="text-sm font-medium">Excluir este rascunho?</p>
              <p className="mt-1 text-sm text-muted-foreground">Sai da lista e perde a autorização de envio. Packs, imagens e campanhas existentes não serão apagados. A recuperação exige suporte.</p>
              <div className="mt-2 flex flex-wrap gap-2"><Button variant="destructive" className="min-h-11" disabled={resuming} onClick={() => void remove(deleting)}>Confirmar exclusão</Button>
                <Button variant="outline" className="min-h-11" disabled={resuming} onClick={() => setDeleting(undefined)}>Cancelar</Button></div>
            </div> : <Button variant="ghost" className="mt-1 min-h-11 text-destructive hover:text-destructive" disabled={resuming || busy}
              aria-label={`Excluir: ${item.campaign_name || 'Campanha sem nome'}`} onClick={() => {setDeleting(item); setNotice('');}}>Excluir</Button>}
          </li>)}</ul>
          {list?.has_more && <Button variant="ghost" className="mt-3 min-h-11 w-full" disabled={busy || resuming} onClick={() => void load(list.next_offset!)}>Carregar mais</Button>}
          {resuming && <p role="status" className="mt-3 text-sm">Salvando sua montagem antes de continuar…</p>}
        </>}
      </div>
    </PopoverContent>
  </Popover>;
}
