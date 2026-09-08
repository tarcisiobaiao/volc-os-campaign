import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { lerCopyDeCampanha, type CopyDeCampanha } from '@/features/creative-studio/api';
import type { SelecaoDeCopy } from './ponteAssistente';

/** An explicit replacement of one draft's text, never of its media or approval. */
export function ImportarCopyDoAssistente({ selecao, anuncios, onAplicar, onCancelar }: {
  selecao: SelecaoDeCopy;
  anuncios: { key: string; adName: string }[];
  onAplicar: (key: string, copy: CopyDeCampanha) => void;
  onCancelar: () => void;
}) {
  const [copy, setCopy] = useState<CopyDeCampanha | null>(null);
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [alvo, setAlvo] = useState('');
  const confirmacao = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setCopy(null); setErro(''); setAlvo('');
    lerCopyDeCampanha(selecao, controller.signal).then(setCopy).catch(exc => {
      if (!controller.signal.aborted) setErro(exc instanceof Error ? exc.message : 'Não foi possível conferir o texto.');
    });
    return () => { controller.abort(); confirmacao.current?.abort(); };
  }, [selecao]);
  async function aplicar() {
    if (!copy || ocupado || !anuncios.some(a => a.key === alvo)) return;
    setOcupado(true); setErro('');
    const controller = new AbortController();
    confirmacao.current = controller;
    try {
      const atual = await lerCopyDeCampanha(selecao, controller.signal);
      if (controller.signal.aborted) return;
      if (atual.snapshot_sha256 !== copy.snapshot_sha256) {
        setCopy(atual);
        setErro('O texto mudou. Confira a nova versão antes de substituir.');
        return;
      }
      onAplicar(alvo, atual);
    } catch (exc) {
      if (!controller.signal.aborted) setErro(exc instanceof Error ? exc.message : 'Não foi possível conferir a aprovação.');
    } finally { setOcupado(false); }
  }
  return <section className="space-y-4 rounded-lg border border-border bg-card p-5" aria-label="Texto do assistente para a campanha">
    <div><h3 className="font-semibold">Usar o texto aprovado</h3>
      <p className="mt-1 text-sm text-muted-foreground">Substitui somente o texto de um anúncio. Imagem, público e orçamento continuam iguais.</p></div>
    {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
    {!copy && !erro && <p role="status" className="text-sm text-muted-foreground">Conferindo a aprovação…</p>}
    {copy && <>
      <div className="space-y-2 border-y border-border py-4 text-sm break-words">
        <strong>{copy.headline}</strong><p className="whitespace-pre-wrap">{copy.message}</p>
        <p className="text-muted-foreground">{copy.description}</p><p>Botão: {copy.cta}</p>
      </div>
      <div className="space-y-2"><Label htmlFor="copy-anuncio-alvo">Em qual anúncio?</Label>
        <select id="copy-anuncio-alvo" value={alvo} disabled={ocupado}
          onChange={e => setAlvo(e.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
          <option value="">Escolha o anúncio que receberá o texto</option>
          {anuncios.map(a => <option key={a.key} value={a.key}>{a.adName}</option>)}
        </select></div>
      <p className="text-sm text-muted-foreground">Confira a combinação final com a imagem. O plano anterior precisará ser validado novamente.</p>
    </>}
    <div className="flex flex-wrap gap-2"><Button type="button" disabled={!copy || ocupado || !anuncios.some(a => a.key === alvo)} onClick={aplicar}>
      {ocupado ? 'Conferindo…' : 'Substituir texto deste anúncio'}
    </Button><Button type="button" variant="ghost" disabled={ocupado} onClick={onCancelar}>Cancelar</Button></div>
  </section>;
}
