import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { adicionarAssetsAoPack, lerPack } from '../api';
import { EscolherPack } from './EscolherPack';
import { caminhoPack } from './PackVisual';

export function AdicionarSelecaoAoPack({ masterRefs }: { masterRefs: string[] }) {
  const [aberto, setAberto] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [salvo, setSalvo] = useState<{ id: string; nome: string } | null>(null);
  const trava = useRef(false);
  async function adicionar(id: string) {
    if (trava.current || !masterRefs.length || masterRefs.length > 10) return;
    trava.current = true; setBusy(true); setErro(''); setSalvo(null);
    const refs = [...new Set(masterRefs)];
    try {
      const pack = await lerPack(id);
      const updated = await adicionarAssetsAoPack(id, refs, pack.manifest_sha256);
      setSalvo(updated); setAberto(false);
    } catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível adicionar as peças. Sua seleção continua aqui.'); }
    finally { trava.current = false; setBusy(false); }
  }
  return <div className="space-y-4">
    <Button type="button" variant="outline" disabled={busy || !masterRefs.length || masterRefs.length > 10}
      aria-expanded={aberto} onClick={() => { setAberto(a => !a); setSalvo(null); }}>Adicionar seleção a um pack existente ({masterRefs.length})</Button>
    {aberto && <><p className="text-sm text-muted-foreground">Escolha onde guardar estas peças. Imagens repetidas não serão duplicadas; campanhas e seleções já confirmadas permanecem como estavam.</p>
      <EscolherPack selecionado={null} ocupado={busy} acao="Adicionar neste pack" onEscolher={id => void adicionar(id)} /></>}
    {busy && <p role="status">Adicionando as peças ao pack…</p>}
    {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
    {salvo && <p role="status" className="text-sm">Seleção adicionada a “{salvo.nome}”. <Link className="text-primary underline" to={caminhoPack(salvo.id)}>Abrir pack atualizado</Link></p>}
  </div>;
}
