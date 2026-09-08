import { useEffect, useRef, useState } from 'react';
import { BookmarkPlus, Copy, Pause } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { useMetaCampaignApi, useMetaCampaignDemo } from './MetaCampaignData';
import { salvarPackMeta } from '@/features/creative-studio/api';
import type { PropostaGestaoMeta } from '@/types/metaOperacao';

export interface EscopoDaHierarquia { contaRef: string; campanhaRef: string }
export function AcoesDaHierarquia({ contaRef, campanhaRef, referencia, nome, entidade }: EscopoDaHierarquia & {
  referencia: string; nome: string; entidade: 'conjunto' | 'anuncio';
}) {
  const api = useMetaCampaignApi(); const demo = useMetaCampaignDemo();
  const [acao, setAcao] = useState<'pausar' | 'duplicar' | 'pack' | null>(null);
  const [novoNome, setNovoNome] = useState('');
  const [proposta, setProposta] = useState<PropostaGestaoMeta | null>(null);
  const [aviso, setAviso] = useState(''); const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false); const trava = useRef(false);
  const vivo = useRef(true);
  useEffect(() => { vivo.current = true; return () => { vivo.current = false; }; }, []);
  function abrir(a: typeof acao) { setProposta(null); setErro(''); setAviso(''); setNovoNome(`${nome} · ${a === 'pack' ? 'pack' : 'cópia'}`.slice(0, 120)); setAcao(a); }
  async function conferir() {
    if (trava.current || !acao) return;
    trava.current = true; setOcupado(true); setErro('');
    try {
      if (acao === 'pack') {
        if (demo) {
          const blob = new Blob([JSON.stringify({ demonstracao: true, nome: novoNome, contaRef, campanhaRef, referencia, entidade, launch_authorized: false }, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'pack-demonstrativo-nao-publicavel.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
          if (vivo.current) setAviso('Exemplo baixado. Dados fictícios não foram gravados no banco.');
        } else {
          await salvarPackMeta({ conta_ref: contaRef, campanha_ref: campanhaRef, entidade, referencia, nome: novoNome.trim() });
          if (vivo.current) setAviso('Pack salvo em Meus packs no Assistente Criativo. Nenhum anúncio foi alterado.');
        }
      } else {
        const r = await api.planejarGestaoMeta({ conta_ref: contaRef, campanha_ref: campanhaRef, entidade, referencia,
          acao: acao === 'pausar' ? 'PAUSAR' : entidade === 'conjunto' ? 'DUPLICAR_CONJUNTO' : 'DUPLICAR_ANUNCIO',
          ...(acao === 'duplicar' ? { nome: novoNome.trim() } : {}) });
        if (vivo.current) setProposta(r);
      }
    } catch (e) { if (vivo.current) setErro(e instanceof Error ? e.message : 'Não foi possível conferir este item.'); }
    finally { trava.current = false; if (vivo.current) setOcupado(false); }
  }
  return <div className="mt-2 flex items-center gap-1" aria-label={`Ações de ${nome}`}>
    <Button size="sm" variant="ghost" aria-label={`Preparar pausa: ${nome}`} title="Preparar pausa" onClick={() => abrir('pausar')}><Pause className="h-4 w-4" aria-hidden /><span className="sr-only">Pausar</span></Button>
    <Button size="sm" variant="ghost" aria-label={`Preparar duplicação: ${nome}`} title="Preparar duplicação" onClick={() => abrir('duplicar')}><Copy className="h-4 w-4" aria-hidden /><span className="sr-only">Duplicar</span></Button>
    <Button size="sm" variant="ghost" aria-label={`Salvar pack: ${nome}`} title="Salvar em pack" onClick={() => abrir('pack')}><BookmarkPlus className="h-4 w-4" aria-hidden /><span className="sr-only">Salvar pack</span></Button>
    <Dialog open={acao !== null} onOpenChange={open => { if (!open && !ocupado) setAcao(null); }}><DialogContent>
      <DialogTitle>{acao === 'pack' ? 'Salvar em pack' : acao === 'pausar' ? 'Preparar pausa' : 'Preparar duplicação'}</DialogTitle>
      <DialogDescription>{nome} · {entidade === 'conjunto' ? 'Conjunto de anúncios' : 'Anúncio'}</DialogDescription>
      {demo && <p className="text-sm text-warning">Demonstração: apenas dados fictícios, sem chamadas reais.</p>}
      {acao !== 'pausar' && <label className="text-sm font-medium">{acao === 'pack' ? 'Nome do pack' : 'Nome da cópia'}<Input className="mt-1" maxLength={120} value={novoNome} disabled={ocupado} onChange={e => { setNovoNome(e.target.value); setProposta(null); setAviso(''); }} /></label>}
      <p className="text-sm text-muted-foreground">{acao === 'pack'
        ? 'Guarda a origem: conta, campanha, conjunto, anúncio e referência do criativo. Não copia dinheiro nem autoriza reuso de um dark post.'
        : 'Confira a proposta antes de qualquer alteração. O executor de pausa e duplicação ainda não está conectado; esta ação não modifica a Meta.'}</p>
      {!proposta && !aviso && <Button disabled={ocupado || (acao !== 'pausar' && !novoNome.trim())} onClick={() => void conferir()}>{ocupado ? 'Conferindo…' : acao === 'pack' ? demo ? 'Baixar pack demonstrativo' : 'Salvar pack' : 'Conferir proposta'}</Button>}
      {proposta && <div role="status" className="space-y-2 border-t border-border pt-3"><h4 className="font-semibold">Proposta pronta · não aplicada</h4><p className="text-sm">{proposta.efeito_proposto}</p><p className="text-xs text-muted-foreground">{proposta.receita}</p><details><summary className="cursor-pointer text-sm">O que falta para executar</summary><ul className="list-disc pl-5 text-sm text-muted-foreground">{proposta.requisitos_para_executar.map(r => <li key={r}>{r}</li>)}</ul></details></div>}
      {aviso && <p role="status" className="text-sm text-success">{aviso}</p>}
      {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
    </DialogContent></Dialog>
  </div>;
}
