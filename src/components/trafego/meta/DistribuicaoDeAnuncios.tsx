import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { campo } from './primitivas';
import { type Draft, LIMITE_VARIACOES, variacoesEmitidas } from './rascunho';

export function DistribuicaoDeAnuncios({ draft, onAdicionar }: { draft: Draft; onAdicionar: (key: string) => void }) {
  const emitidas = variacoesEmitidas(draft);
  return <section aria-label="Distribuição dos anúncios por conjunto" className="space-y-3 rounded-lg border border-border bg-card p-4">
    <h3 className="font-semibold">Onde cada anúncio vai entrar</h3>
    <p className="max-w-[70ch] text-sm text-muted-foreground">Cada anúncio pertence a um conjunto e usa uma imagem e uma copy. Reutilizar a peça em outro conjunto cria outro anúncio, sem mover o original.</p>
    <ul className="divide-y divide-border">{draft.conjuntos.map(c => {
      const ads = emitidas.filter(v => v.adsetKey === c.key);
      const guardados = draft.variations.filter(v => v.adsetKey === c.key).length - ads.length;
      return <li key={c.key} className="flex flex-col items-stretch justify-between gap-3 py-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1"><p className="break-words font-medium">{c.nome || 'Conjunto sem nome'}</p>
          <p className="text-sm text-muted-foreground">{ads.length ? `${ads.length} anúncio(s): ${ads.map(v => v.adName).join(', ')}` : 'Sem anúncios. Adicione uma peça neste conjunto.'}</p>
          {guardados > 0 && <p className="text-sm text-warning">{guardados} anúncio(s) guardado(s), fora do modo atual.</p>}
        </div>
        <Button type="button" variant="outline" disabled={draft.variations.length >= LIMITE_VARIACOES || draft.creativeMode === 'flexible'}
          aria-label={`Adicionar anúncio em ${c.nome}`} onClick={() => onAdicionar(c.key)}>Adicionar neste conjunto</Button>
      </li>;
    })}</ul>
    {emitidas.some(v => !draft.conjuntos.some(c => c.key === v.adsetKey)) && <p role="alert" className="text-sm text-destructive">Há anúncio sem conjunto válido. Escolha o conjunto no anúncio antes de conferir o plano.</p>}
  </section>;
}

export function ReutilizarEmConjunto({ draft, origem, onDuplicar }: {
  draft: Draft; origem: string; onDuplicar: (destino: string) => void;
}) {
  const [destino, setDestino] = useState('');
  const anuncio = draft.variations.find(v => v.key === origem);
  const valido = draft.conjuntos.some(c => c.key === destino && c.key !== anuncio?.adsetKey);
  if (draft.conjuntos.length < 2) return null;
  return <div className="flex flex-wrap items-end gap-2 border-t border-border px-4 py-3">
    <label className="min-w-0 basis-60 flex-1 text-sm font-medium">Reutilizar este criativo em outro conjunto
      <select className={`${campo} mt-1`} value={valido ? destino : ''} onChange={e => setDestino(e.target.value)}>
        <option value="">Escolha o conjunto de destino</option>
        {draft.conjuntos.filter(c => c.key !== anuncio?.adsetKey).map(c => <option key={c.key} value={c.key}>{c.nome}</option>)}
      </select>
    </label>
    <Button type="button" variant="outline" className="h-auto min-h-10 max-w-full whitespace-normal" disabled={!valido || draft.variations.length >= LIMITE_VARIACOES}
      onClick={() => { onDuplicar(destino); setDestino(''); }}>Criar cópia no conjunto escolhido</Button>
    <p className="w-full text-xs text-muted-foreground">Mantém imagem e textos. O original fica onde está; a cópia exige nova revisão.</p>
  </div>;
}
