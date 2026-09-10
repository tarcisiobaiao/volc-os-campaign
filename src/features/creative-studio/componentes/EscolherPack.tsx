import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { listarPacks, type CreativePack } from '../api';
import { CapaPack, caminhoPack } from './PackVisual';
import { BuscaBiblioteca, useBuscaPaginada } from './BuscaBiblioteca';

/** Selection changes the draft only. The parent validates ownership and masters. */
export function EscolherPack({ selecionado, onEscolher, ocupado = false, acao = 'Usar este pack' }: {
  selecionado: string | null; onEscolher: (id: string) => void; ocupado?: boolean; acao?: string;
}) {
  const [packs, setPacks] = useState<CreativePack[]>([]);
  const { texto, setTexto, consulta, setConsulta } = useBuscaPaginada();
  const { offset, q } = consulta;
  const [mais, setMais] = useState(false);
  const [lendo, setLendo] = useState(true);
  const [erro, setErro] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    let vivo = true;
    setLendo(true); setErro(false);
    listarPacks(offset, q).then(r => {
      if (!vivo) return;
      setPacks(r.packs);
      setMais(r.has_more);
    }).catch(() => { if (vivo) setErro(true); })
      .finally(() => { if (vivo) setLendo(false); });
    return () => { vivo = false; };
  }, [offset, q, tentativa]);
  return <section aria-label="Escolher pack salvo" className="space-y-4">
    <p className="text-sm text-muted-foreground">Reaproveite as peças que você já gerou. Selecionar um pack não gera novas imagens nem publica anúncios.</p>
    <BuscaBiblioteca value={texto} onChange={setTexto} label="Buscar pack pelo nome" />
    {lendo && <p role="status">Carregando seus packs…</p>}
    {erro && <div role="alert">Não foi possível carregar os packs. <Button variant="outline" onClick={() => setTentativa(t => t + 1)}>Tentar novamente</Button></div>}
    {!lendo && !erro && !packs.length && <p>{q ? 'Nenhum pack encontrado para essa busca.' : 'Nenhum pack salvo. Crie suas imagens no assistente e salve a seleção em um pack.'}</p>}
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy={lendo}>
      {packs.map(pack => <li key={pack.id} className="overflow-hidden rounded-lg border border-border bg-card">
        <CapaPack item={pack.manifest.items[0]} nome={pack.nome} />
        <div className="space-y-3 p-4"><h3 className="font-semibold">{pack.nome}</h3>
          <p className="text-sm text-muted-foreground">{pack.manifest.items.length} peças · {pack.manifest.source === 'STUDIO' ? 'Estúdio' : 'Referências Meta'}</p>
          {pack.manifest.source === 'STUDIO' ? <Button type="button" disabled={ocupado || lendo || texto.trim() !== q} aria-pressed={selecionado === pack.id}
            onClick={() => onEscolher(pack.id)}>{selecionado === pack.id ? 'Pack selecionado' : acao}</Button>
            : <p className="text-sm">Este pack contém referências, não arquivos para envio.</p>}
          <Link className="block text-sm text-primary underline" to={caminhoPack(pack.id)} target="_blank" rel="noopener noreferrer">Ver peças e textos (nova aba)</Link>
        </div>
      </li>)}
    </ul>
    <div className="flex gap-2">{offset > 0 && <Button variant="outline" disabled={lendo} onClick={() => setConsulta(c => ({...c, offset: Math.max(0, c.offset - 20)}))}>Anterior</Button>}
    {mais && !erro && <Button variant="outline" disabled={lendo} onClick={() => setConsulta(c => ({...c, offset: c.offset + 20}))}>Próximos packs</Button>}</div>
  </section>;
}
