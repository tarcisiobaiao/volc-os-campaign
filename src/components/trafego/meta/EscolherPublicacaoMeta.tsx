import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { pautadorApi, type PublicacaoExistenteMeta } from '@/lib/pautadorApi';
import { BuscaBiblioteca, useBuscaPaginada } from '@/features/creative-studio/componentes/BuscaBiblioteca';

export function EscolherPublicacaoMeta({ accountRef, pageRef, selected, onSelect, onClear, demo, disabled }: {
  accountRef: string; pageRef: string; selected?: string; onSelect: (item: PublicacaoExistenteMeta) => void;
  onClear: () => void; demo: boolean; disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<PublicacaoExistenteMeta[]>([]);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const { texto, setTexto, consulta, setConsulta } = useBuscaPaginada();
  useEffect(() => {
    setOpen(false); setItems([]); setMore(false); setLoading(false); setError('');
    setTexto(''); setConsulta({ q: '', offset: 0 });
  }, [accountRef, pageRef, demo, setTexto, setConsulta]);
  useEffect(() => {
    let active = true;
    if (!open || demo || !accountRef || !pageRef) return;
    setLoading(true); setError(''); setItems([]);
    pautadorApi.postsExistentesMeta(accountRef, pageRef, consulta.q, consulta.offset).then(result => {
      if (!active) return;
      if (!result.complete) throw new Error('A consulta não foi concluída. Atualize antes de escolher uma publicação.');
      setItems(result.items); setMore(result.has_more);
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'Não foi possível consultar os posts.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, demo, accountRef, pageRef, consulta, retry]);
  return <section className="space-y-3 md:col-span-2" aria-label="Reutilizar publicação existente">
    <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" disabled={disabled || !accountRef || !pageRef || demo}
      aria-expanded={open} onClick={() => setOpen(v => !v)}>{selected ? 'Trocar publicação existente' : 'Buscar anúncio existente / Dark Post'}</Button>
      {selected && <Button type="button" variant="ghost" disabled={disabled} onClick={onClear}>Voltar a criar um post novo</Button>}</div>
    {selected && <p role="status" className="text-sm font-medium">Publicação original selecionada e bloqueada. A Meta reutilizará o ID do post — mídia, textos, destino e engajamento permanecem no post; somente o anúncio e o conjunto serão novos.</p>}
    {open && <div className="space-y-3 border-y border-border py-4">
      <p className="max-w-prose text-sm text-muted-foreground">Busque pelo nome do anúncio ou criativo que você já testou em ABO. Mostramos posts de imagem elegíveis desta conta e Página, inclusive de anúncios pausados. Usar um post não transfere os resultados históricos do anúncio.</p>
      <BuscaBiblioteca value={texto} onChange={setTexto} label="Buscar anúncio ou Dark Post pelo nome" />
      {loading && <p role="status">Buscando publicações na conta…</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error} <Button variant="ghost" onClick={() => setRetry(v => v + 1)}>Tentar novamente</Button></p>}
      {!loading && !error && !items.length && <p className="text-sm">Nenhuma publicação de imagem reutilizável foi encontrada nesta Página. Confira a Página ou tente outro nome. Vídeos e posts sem um único destino HTTPS ainda não entram nesta seleção.</p>}
      <ul className="divide-y divide-border">{items.map(item => <li key={item.post_ref} className="flex flex-wrap items-center gap-3 py-3">
        {item.preview_url && <img src={item.preview_url} alt="" loading="lazy" className="h-16 w-16 rounded object-contain" />}
        <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-medium break-words">{item.label}</p>{item.is_flexible && <span className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">Múltiplos assets · {item.image_variants || 1} imagens · {item.text_variants || 1} textos</span>}</div><p className="text-xs text-muted-foreground break-words">{item.source_ad_names.join(' · ')}</p><p className="mt-1 break-all text-xs">{item.destination_url}</p>{item.is_flexible && <p className="mt-1 text-xs text-muted-foreground">{item.reuse_reason || 'Reuso por ID do post não comprovado para este formato. Monte um novo anúncio flexível para escolher as variações.'}</p>}
          {item.copy_variants && <details className="mt-2 text-sm"><summary className="cursor-pointer">Ver textos de referência</summary>{item.copy_variants.messages.map((text, i) => <p key={i} className="mt-2">{text}</p>)}</details>}
        </div>
        <Button type="button" variant="outline" disabled={loading || disabled || item.is_flexible || item.reuse_supported === false || texto.trim() !== consulta.q} onClick={() => { onSelect(item); setOpen(false); }}>{item.is_flexible ? 'Somente referência' : 'Usar este post'}</Button>
      </li>)}</ul>
      <div className="flex gap-2">{consulta.offset > 0 && <Button variant="outline" disabled={loading} onClick={() => setConsulta(c => ({...c, offset: Math.max(0, c.offset - 24)}))}>Anterior</Button>}
      {more && <Button variant="outline" disabled={loading} onClick={() => setConsulta(c => ({...c, offset: c.offset + 24}))}>Próximas publicações</Button>}</div>
    </div>}
  </section>;
}
