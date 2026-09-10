import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, Copy, Download, ImageIcon, ZoomIn } from 'lucide-react';
import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { lerPack, listarPacks } from '@/features/creative-studio/api';
import { CapaPack, caminhoPack, useImagemPack } from '@/features/creative-studio/componentes/PackVisual';
import { AdicionarDaBiblioteca } from '@/features/creative-studio/componentes/AdicionarDaBiblioteca';
import { BuscaBiblioteca, useBuscaPaginada } from '@/features/creative-studio/componentes/BuscaBiblioteca';

export default function CreativePackPage() {
  const { packId } = useParams();
  const [index, setIndex] = useState(0);
  const { texto, setTexto, consulta, setConsulta } = useBuscaPaginada();
  const { offset, q } = consulta;
  const setOffset = (fn: (value: number) => number) => setConsulta(c => ({...c, offset: fn(c.offset)}));
  const [zoom, setZoom] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { setIndex(0); setMessage(''); setZoom(false); }, [packId]);
  const pack = useQuery({ queryKey: ['creative-pack', packId], queryFn: () => lerPack(packId!), enabled: Boolean(packId), gcTime: 0 });
  const list = useQuery({ queryKey: ['creative-packs', offset, q], queryFn: () => listarPacks(offset, q), enabled: !packId, gcTime: 0 });
  const item = pack.data?.manifest.items[index];
  const image = useImagemPack(item);
  const copy = item?.copy_snapshot;
  async function copiar() {
    try { await navigator.clipboard.writeText([copy?.texto_principal, copy?.titulo, copy?.descricao].filter(Boolean).join('\n\n')); setMessage('Copy copiada.'); }
    catch { setMessage('Não foi possível copiar. Selecione o texto para copiar manualmente.'); }
  }
  async function baixar() {
    if (!image.data?.previewUrl || busy) return;
    setBusy(true); setMessage('');
    try {
      const response = await fetch(image.data.previewUrl, { credentials: 'omit', redirect: 'error' });
      if (!response.ok) throw new Error();
      const blob = await response.blob();
      if (!['image/png', 'image/jpeg', 'image/webp'].includes(blob.type) || blob.size > 25 * 1024 * 1024) throw new Error();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url;
      a.download = `criativo-${index + 1}.${blob.type === 'image/jpeg' ? 'jpg' : blob.type === 'image/webp' ? 'webp' : 'png'}`;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setMessage('Não foi possível baixar. Atualize a imagem e tente novamente.'); }
    finally { setBusy(false); }
  }
  const request = packId ? pack : list;
  return <Layout><div className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-8">
    <Link className="inline-flex min-h-11 items-center gap-2 text-sm text-primary hover:underline" to={packId ? '/trafego/meta/packs' : '/trafego/meta/assistente-criativo'}><ArrowLeft className="h-4 w-4" aria-hidden />{packId ? 'Todos os packs' : 'Assistente Criativo'}</Link>
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-medium text-primary">Biblioteca criativa</p><h1 className="mt-2 font-display text-3xl font-bold tracking-tight">{packId ? pack.data?.nome ?? 'Seu pack' : 'Meus packs'}</h1><p className="mt-2 text-sm text-muted-foreground">{packId ? `${pack.data?.manifest.items.length ?? '…'} peças para explorar, conferir e reutilizar.` : 'Suas melhores ideias, prontas para o próximo teste.'}</p></div>
    {pack.data?.manifest.source === 'STUDIO' && <Button asChild><Link to={`/trafego/meta/nova?pack=${encodeURIComponent(packId!)}`}>Preparar campanha<ArrowRight className="h-4 w-4" aria-hidden /></Link></Button>}</header>
    {request.isLoading && <div role="status" className="h-80 animate-pulse rounded-2xl bg-muted motion-reduce:animate-none"><span className="sr-only">Carregando pack…</span></div>}
    {request.isError && <div role="alert" className="rounded-xl border border-destructive/40 p-6"><p>Não foi possível carregar seus packs.</p><Button className="mt-3" variant="outline" onClick={() => void request.refetch()}>Tentar novamente</Button></div>}
    {!packId && <BuscaBiblioteca value={texto} onChange={setTexto} label="Buscar pack pelo nome" />}
    {pack.data && <AdicionarDaBiblioteca key={pack.data.id} pack={pack.data} onSaved={() => { void pack.refetch(); setMessage('Pack atualizado.'); }} />}
    {!packId && list.data && <><div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{list.data.packs.map(p => <Link key={p.id} to={caminhoPack(p.id)} className="group overflow-hidden rounded-xl border border-border bg-card shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"><CapaPack item={p.manifest.items[0]} nome={p.nome} /><div className="p-4"><h2 className="font-semibold">{p.nome}</h2><p className="mt-1 text-sm text-muted-foreground">{p.manifest.items.length} peças</p><span className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-primary">Explorar pack<ArrowRight className="h-4 w-4" aria-hidden /></span></div></Link>)}</div>{!list.data.packs.length && <p>{consulta.q ? 'Nenhum pack encontrado para essa busca.' : 'Você ainda não salvou um pack. Selecione imagens na galeria do Assistente para começar.'}</p>}<div className="flex gap-3">{offset > 0 && <Button variant="outline" onClick={() => setOffset(n => n - 20)}>Anterior</Button>}{list.data.has_more && <Button variant="outline" onClick={() => setOffset(n => n + 20)}>Próximos packs</Button>}</div></>}
    {pack.data && <>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
        <section aria-label="Imagem selecionada" className="space-y-4"><div className="flex min-h-80 items-center justify-center overflow-hidden rounded-2xl bg-muted p-4 sm:p-6">
          {image.data?.previewUrl ? <img src={image.data.previewUrl} alt={`Peça ${index + 1} do pack ${pack.data.nome}`} className="max-h-[65vh] w-full object-contain" /> : <div className="py-24 text-center text-muted-foreground"><ImageIcon className="mx-auto mb-3 h-10 w-10" aria-hidden /><p>{image.isFetching ? 'Carregando imagem…' : 'Esta imagem não está disponível para prévia.'}</p><Button variant="ghost" disabled={!item?.job_id} onClick={() => void image.refetch()}>Atualizar imagem</Button></div>}
        </div><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm tabular-nums text-muted-foreground">Peça {index + 1}{item?.largura && item?.altura ? ` • ${item.largura} × ${item.altura} px` : ''}</p><div className="flex gap-2"><Button variant="outline" disabled={!image.data} onClick={() => setZoom(true)}><ZoomIn className="h-4 w-4" aria-hidden />Ampliar</Button><Button variant="outline" disabled={!image.data || busy} onClick={() => void baixar()}><Download className="h-4 w-4" aria-hidden />{busy ? 'Baixando…' : 'Baixar imagem'}</Button></div></div></section>
        <section aria-label="Prévia do anúncio" className="space-y-5"><div><h2 className="text-xl font-semibold">Como seu anúncio pode aparecer</h2><p className="mt-1 text-sm text-muted-foreground">Prévia ilustrativa. A Página e o destino serão escolhidos na campanha.</p></div>
          <article className="overflow-hidden rounded-xl border border-border bg-card shadow-sm"><div className="flex items-center gap-3 p-4"><span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary"><ImageIcon className="h-5 w-5" aria-hidden /></span><div><p className="text-sm font-semibold">Sua Página</p><p className="text-xs text-muted-foreground">Patrocinado · Prévia</p></div></div><p className="whitespace-pre-wrap px-4 pb-4 text-sm leading-relaxed">{copy?.texto_principal || 'Esta peça ainda não tem uma copy vinculada.'}</p>{image.data?.previewUrl && <img src={image.data.previewUrl} alt="Composição do anúncio" className="max-h-80 w-full bg-muted object-contain" />}<div className="flex items-center justify-between gap-3 bg-muted/50 p-4"><div><h3 className="text-sm font-semibold">{copy?.titulo || pack.data.nome}</h3><p className="mt-1 text-xs text-muted-foreground">{copy?.descricao}</p></div><span className="shrink-0 rounded-md border border-border px-3 py-2 text-xs font-semibold">{({ LEARN_MORE: 'Saiba mais', SIGN_UP: 'Cadastre-se', SHOP_NOW: 'Comprar agora', CONTACT_US: 'Fale conosco', DOWNLOAD: 'Baixar' } as Record<string,string>)[copy?.cta_nativa ?? ''] ?? copy?.cta_nativa ?? 'Saiba mais'}</span></div></article>
          <Button variant="outline" disabled={!copy} onClick={() => void copiar()}><Copy className="h-4 w-4" aria-hidden />Copiar texto do anúncio</Button><p className="text-xs leading-relaxed text-muted-foreground">Copy preservada da estratégia original. Confira a adequação à próxima campanha antes de publicar.</p>
        </section>
      </div>
      <section aria-label="Peças do pack"><h2 className="mb-4 text-xl font-semibold">Explore as peças</h2><div className="flex gap-4 overflow-x-auto pb-4">{pack.data.manifest.items.map((p, i) => <button key={p.master_ref ?? i} type="button" aria-label={`Ver peça ${i + 1}`} aria-pressed={index === i} onClick={() => { setIndex(i); setMessage(''); }} className={`group w-40 shrink-0 overflow-hidden rounded-xl border-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${index === i ? 'border-primary bg-primary/5' : 'border-border bg-card'}`}><CapaPack item={p} nome={`${pack.data!.nome}, peça ${i + 1}`} /><span className="block p-3 text-sm font-medium">Peça {i + 1}</span></button>)}</div></section>
      <p className="text-xs text-muted-foreground">Salvar um pack preserva arquivos e textos. Curtidas e comentários dependem do reuso de um post elegível na Meta.</p>
    </>}
    {message && <p role="status" className="text-sm">{message}</p>}
    <Dialog open={zoom} onOpenChange={setZoom}><DialogContent className="max-w-4xl"><DialogTitle>{pack.data?.nome}, peça {index + 1}</DialogTitle><DialogDescription>Imagem na proporção original.</DialogDescription>{image.data?.previewUrl && <img src={image.data.previewUrl} alt="Peça ampliada" className="max-h-[75vh] w-full object-contain" />}</DialogContent></Dialog>
  </div></Layout>;
}
