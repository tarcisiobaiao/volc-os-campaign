import { type Draft, LIMITE_VARIACOES, nomeUnico, proximaChave, variacaoInicial, textosFlexiveisDoConjunto } from './rascunho';

/** Explicit parent, immutable identities, and no inherited approval on reuse. */
export function adicionarAnuncioNoConjunto(draft: Draft, destino: string, origem?: string): Draft {
  if (!draft.conjuntos.some(c => c.key === destino) || draft.variations.length >= LIMITE_VARIACOES) return draft;
  const anterior = origem ? draft.variations.find(v => v.key === origem) : undefined;
  if (origem && !anterior) return draft;
  const key = proximaChave(draft.variations.map(v => v.key), 'variation');
  const base = anterior ?? variacaoInicial(key, draft.variations.length + 1, destino);
  return { ...draft, creativeMode: draft.creativeMode === 'flexible' ? 'flexible' : 'batch',
    conjuntos: draft.creativeMode === 'flexible' ? draft.conjuntos.map(c => ({ ...c,
      flexibleTexts: textosFlexiveisDoConjunto(draft, c.key),
    })) : draft.conjuntos,
    variations: [...draft.variations, {
    ...base, key, adsetKey: destino,
    creativeName: nomeUnico(base.creativeName, draft.variations.map(v => v.creativeName)),
    adName: nomeUnico(base.adName, draft.variations.map(v => v.adName)),
    assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
  }] };
}

export function removerConjuntoSemAnuncios(draft: Draft, key: string): Draft {
  // Includes drafts hidden by single mode. Never silently reparent them.
  if (draft.conjuntos.length <= 1 || draft.variations.some(v => v.adsetKey === key)) return draft;
  return { ...draft, conjuntos: draft.conjuntos.filter(c => c.key !== key) };
}

/** Copy is reusable; post identity, media and its approval are not inherited. */
export function duplicarParaTrocarImagem(draft: Draft, origem: string): Draft {
  const source = draft.variations.find(item => item.key === origem);
  if (!source) return draft;
  const next = adicionarAnuncioNoConjunto(draft, source.adsetKey, origem);
  if (next === draft) return draft;
  const key = next.variations.at(-1)!.key;
  return { ...next, creativeMode: draft.creativeMode === 'flexible' ? 'flexible' : 'batch',
    variations: next.variations.map(item => item.key !== key ? item : {
      ...item, midia: 'image', assetRef: '', videoRef: '', existingPostRef: undefined,
      packOrigin: undefined,
    }) };
}
