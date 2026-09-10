import type { CreativePack, DraftPackSelection } from '@/features/creative-studio/api';
import type { RegistroMidiaMeta } from '@/lib/pautadorApi';
import { type Draft, LIMITE_VARIACOES, nomeUnico, proximaChave, variacaoInicial, variacoesEmitidas } from './rascunho';

export function packMaterializado(draft: Draft, selection: DraftPackSelection): boolean {
  return selection.master_refs.length > 0 && selection.master_refs.every(master =>
    variacoesEmitidas(draft).some(v => v.adsetKey === selection.adset_key && !!v.assetRef
      && v.packOrigin?.masterRef === master && v.packOrigin.accountRef === draft.accountRef
      && v.packOrigin.packId === selection.pack_id && v.packOrigin.manifestHash === selection.manifest_sha256
      && v.packOrigin.selectionVersion === selection.version));
}

/** Attach by explicit parent and master identity, never by array position. */
export function materializarPack(draft: Draft, selection: DraftPackSelection, pack: CreativePack,
  accountRef: string, receipt: RegistroMidiaMeta, preferredVariationKey?: string): Draft {
  if (!accountRef || draft.accountRef !== accountRef || !draft.conjuntos.some(c => c.key === selection.adset_key))
    throw new Error('A conta ou o conjunto mudou. Revise o destino antes de vincular.');
  if (pack.id !== selection.pack_id || pack.manifest_sha256 !== selection.manifest_sha256)
    throw new Error('A versão do pack mudou. Selecione novamente.');
  const refs = selection.master_refs;
  if (!refs.length || new Set(refs).size !== refs.length || !receipt.ok
    || receipt.resultados.length !== refs.length || new Set(receipt.resultados.map(r => r.master_ref)).size !== refs.length
    || refs.some(ref => !receipt.resultados.some(r => r.master_ref === ref && r.asset_ref
      && ['REGISTERED', 'ALREADY_REGISTERED'].includes(r.estado))))
    throw new Error('O registro não confirmou todas as peças. Nenhum anúncio foi anexado.');
  const additions = refs.filter(ref => !draft.variations.some(v => v.adsetKey === selection.adset_key
    && v.packOrigin?.masterRef === ref && v.packOrigin.packId === pack.id
    && v.packOrigin.selectionVersion === selection.version && v.packOrigin.accountRef === accountRef));
  /** Um pack preenche primeiro os slots de mídia vazios do conjunto. Isto é o
   * que faz “Duplicar e trocar imagem” preservar copy e identidade do anúncio,
   * em vez de deixar o duplicado vazio e criar uma terceira linha. */
  const empty = draft.variations.filter(v => v.adsetKey === selection.adset_key
    && !v.assetRef && !v.videoRef && !v.existingPostRef && !v.packOrigin)
    .sort((a, b) => a.key === preferredVariationKey ? -1 : b.key === preferredVariationKey ? 1 : 0);
  const slots = empty.slice(0, additions.length);
  const remainingAdditions = additions.slice(slots.length);
  if (draft.variations.length + remainingAdditions.length > LIMITE_VARIACOES)
    throw new Error(`O lote ultrapassa ${LIMITE_VARIACOES} anúncios. Retire anúncios não utilizados antes de anexar.`);
  let variations = draft.variations.map(v => {
    const slotIndex = slots.findIndex(slot => slot.key === v.key);
    if (slotIndex < 0) return v;
    const ref = additions[slotIndex];
    const item = pack.manifest.items.find(i => i.master_ref === ref);
    if (!item) throw new Error('Uma peça selecionada não existe neste pack.');
    const copy = item.copy_snapshot;
    return { ...v, midia: 'image' as const,
      assetRef: receipt.resultados.find(r => r.master_ref === ref)!.asset_ref!, videoRef: '', existingPostRef: undefined,
      message: v.message || copy?.texto_principal || '', headline: v.headline || copy?.titulo || '',
      description: v.description || copy?.descricao || '', cta: v.cta || copy?.cta_nativa || 'LEARN_MORE',
      assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
      packOrigin: {packId: pack.id, manifestHash: pack.manifest_sha256, masterRef: ref, accountRef, selectionVersion: selection.version},
    };
  });
  for (const ref of remainingAdditions) {
    const item = pack.manifest.items.find(i => i.master_ref === ref);
    if (!item) throw new Error('Uma peça selecionada não existe neste pack.');
    const key = proximaChave(variations.map(v => v.key), 'variation');
    const copy = item.copy_snapshot;
    variations.push({ ...variacaoInicial(key, variations.length + 1, selection.adset_key),
      assetRef: receipt.resultados.find(r => r.master_ref === ref)!.asset_ref!,
      adName: nomeUnico(item.nome || pack.nome, variations.map(v => v.adName)),
      creativeName: nomeUnico(item.nome || pack.nome, variations.map(v => v.creativeName)),
      message: copy?.texto_principal || '', headline: copy?.titulo || '', description: copy?.descricao || '',
      cta: copy?.cta_nativa || 'LEARN_MORE',
      assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
      packOrigin: {packId: pack.id, manifestHash: pack.manifest_sha256, masterRef: ref, accountRef, selectionVersion: selection.version},
    });
  }
  return {...draft, variations, creativeMode: draft.creativeMode === 'flexible' ? 'flexible' : variations.length > 1 ? 'batch' : 'single'};
}
