import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookmarkPlus, FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { listarPacks, salvarPack, selecionarPack, type CreativePack } from '../api';
import { assistenteIntegrado } from '@/components/trafego/meta/ponteAssistente';

export function PacksDeCriativos({ masterRefs }: { masterRefs: string[] }) {
  const [nome, setNome] = useState('');
  const [packs, setPacks] = useState<CreativePack[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const trava = useRef(false);
  const [aviso, setAviso] = useState('');
  const [erro, setErro] = useState('');
  const [offset, setOffset] = useState(0);
  const [mais, setMais] = useState(false);
  async function executar(fn: () => Promise<void>) {
    if (trava.current) return;
    trava.current = true; setOcupado(true); setErro(''); setAviso('');
    try { await fn(); } catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível acessar o pack.'); }
    finally { trava.current = false; setOcupado(false); }
  }
  async function carregar(proximo = 0) {
    const r = await listarPacks(proximo);
    setPacks(proximo ? [...(packs ?? []), ...r.packs] : r.packs); setOffset(proximo); setMais(r.has_more);
  }
  return <section className="space-y-3 border-t border-border pt-5" aria-label="Packs reutilizáveis">
    <div><h3 className="font-display text-base font-semibold">Guarde as peças para o próximo teste</h3>
      <p className="mt-1 text-sm text-muted-foreground">Salve a seleção em um pack. As imagens e suas origens permanecem vinculadas, sem gerar ou pagar novamente.</p></div>
    <div className="flex flex-wrap items-end gap-2">
      <label className="min-w-48 flex-1 text-xs font-medium">Nome do pack<Input className="mt-1" value={nome} maxLength={120} onChange={e => setNome(e.target.value)} placeholder="Ex.: Encceja · primeira rodada" /></label>
      <Button variant="outline" disabled={ocupado || !nome.trim() || !masterRefs.length || masterRefs.length > 10} onClick={() => void executar(async () => {
        const r = await salvarPack(nome.trim(), masterRefs); await carregar();
        setAviso(`Pack “${r.nome}” salvo. A publicação continua separada.`);
      })}><BookmarkPlus className="h-4 w-4" aria-hidden />Salvar seleção ({masterRefs.length})</Button>
      <Button variant="ghost" disabled={ocupado} onClick={() => void executar(() => carregar())}><FolderOpen className="h-4 w-4" aria-hidden />Meus packs</Button>
    </div>
    {ocupado && <p role="status" className="text-sm text-muted-foreground">Acessando seus packs…</p>}
    {aviso && <p role="status" className="text-sm text-success">{aviso}</p>}
    {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
    {packs && <ul className="divide-y divide-border rounded-lg border border-border px-3">
      {!packs.length && <li className="py-4 text-sm text-muted-foreground">Nenhum pack salvo ainda. Selecione as imagens acima para começar.</li>}
      {packs.map(pack => <li key={pack.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
        <div><p className="text-sm font-medium">{pack.nome}</p><p className="text-xs text-muted-foreground">{pack.manifest.items.length} peça(s) · {pack.manifest.source === 'STUDIO' ? 'Arquivos do Estúdio' : 'Referências da Meta'} · revisão de uso pendente</p>
          {pack.manifest.items.some(i => i.copy_snapshot) && <details className="mt-2 max-w-prose text-sm"><summary className="cursor-pointer text-primary">Textos de origem</summary>{pack.manifest.items.map((i, index) => i.copy_snapshot && <div key={index} className="space-y-1 border-l border-border pl-3 pt-2"><p className="font-medium">{i.copy_snapshot.titulo}</p><p>{i.copy_snapshot.texto_principal}</p><p className="text-muted-foreground">{i.copy_snapshot.descricao}</p></div>)}<p className="mt-2 text-xs text-muted-foreground">Referência preservada, não aprovação para uma nova finalidade.</p></details>}
        </div>
        {pack.manifest.source === 'STUDIO' && (assistenteIntegrado()
          ? <Button size="sm" variant="outline" disabled={ocupado} onClick={() => void executar(async () => {
            const r = await selecionarPack(pack.id);
            window.parent.postMessage({ type: 'volc:creative-selection', masterRefs: r.master_refs }, window.location.origin);
            setAviso('Peças selecionadas no rascunho. Nada foi enviado à Meta.');
          })}>Usar nesta campanha</Button>
          : <Button asChild size="sm" variant="outline"><Link to={`/trafego/meta/nova?pack=${encodeURIComponent(pack.id)}`}>Preparar campanha</Link></Button>)}
      </li>)}
    </ul>}
    {mais && <Button variant="ghost" disabled={ocupado} onClick={() => void executar(() => carregar(offset + 20))}>Carregar mais packs</Button>}
    <p className="text-xs text-muted-foreground">Pack não é dark post: manter curtidas e comentários exige um post existente elegível. Os arquivos continuam no armazenamento atual do Estúdio.</p>
  </section>;
}
