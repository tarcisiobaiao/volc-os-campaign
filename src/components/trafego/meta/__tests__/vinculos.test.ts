import { describe, expect, it } from 'vitest';
import { adicionarAnuncioNoConjunto, duplicarParaTrocarImagem, removerConjuntoSemAnuncios } from '../vinculos';
import { type Draft, conjuntoInicial, variacaoInicial, paraPlanoV2, contratoDoPlano, variacoesEmitidas } from '../rascunho';

function draft(): Draft {
  return { recipeId: 'TRAFFIC_WEBSITE_LPV_STATIC', accountRef: 'conta', pageRef: 'pagina', instagramActorRef: '',
    campaignName: 'Teste', destinationUrl: 'https://example.com', categoryConfirmed: true,
    nivelDeOrcamento: 'ADSET', periodoDeOrcamento: 'DAILY', budgetBrl: '10,00', creativeMode: 'single',
    conjuntos: ['a', 'b'].map(k => conjuntoInicial(k, k, '2026-10-01T10:00', '10,00')),
    variations: [{ ...variacaoInicial('variation-001', 1, 'a'), assetRef: 'image1',
      assetRightsConfirmed: true, thirdPartyIdentityCleared: true, assetPolicyConfirmedAt: '2026-09-08T10:00:00Z' }],
  };
}
describe('vínculo explícito anúncio → conjunto', () => {
  it('modo flexível transporta cada grupo, sua copy e o conjunto explicitamente no V2', () => {
    const d = {...adicionarAnuncioNoConjunto(draft(), 'b', 'variation-001'), creativeMode:'flexible' as const};
    expect(contratoDoPlano(d).contrato).toBe('V2');
    expect(variacoesEmitidas(d)).toHaveLength(2);
    expect(paraPlanoV2(d).creative_mode).toBe('FLEXIBLE_IMAGES');
    expect(paraPlanoV2(d).ads.map(a => a.adset_key)).toEqual(['a', 'b']);
  });
  it('duplicar e trocar imagem preserva copy e pai, mas limpa post, mídia, pack e aprovação', () => {
    const original = draft();
    original.variations[0].existingPostRef = 'metapost_original';
    original.variations[0].message = 'Texto validado em ABO';
    const next = duplicarParaTrocarImagem(original, original.variations[0].key);
    expect(next.variations[0]).toEqual(original.variations[0]);
    expect(next.variations[1]).toMatchObject({adsetKey: 'a', message: 'Texto validado em ABO', assetRef: '', videoRef: '', assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: ''});
    expect(next.variations[1].existingPostRef).toBeUndefined();
    expect(next.variations[1].packOrigin).toBeUndefined();
    expect(next.variations[1].key).not.toBe(original.variations[0].key);
    expect(paraPlanoV2(next).ads).toHaveLength(2);
  });
  it('adicionar ao segundo conjunto não escolhe o primeiro nem copia mídia silenciosamente', () => {
    const r = adicionarAnuncioNoConjunto(draft(), 'b');
    expect(r.variations[1].adsetKey).toBe('b');
    expect(r.variations[1].assetRef).toBe('');
    expect(r.creativeMode).toBe('batch');
  });
  it('duplicar em outro conjunto preserva original e mídia, mas não aprovação', () => {
    const original = draft();
    const r = adicionarAnuncioNoConjunto(original, 'b', 'variation-001');
    expect(r.variations[0]).toEqual(original.variations[0]);
    expect(r.variations[1]).toMatchObject({ adsetKey: 'b', assetRef: 'image1', assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '' });
    expect(r.variations[1].key).not.toBe(r.variations[0].key);
    expect(r.variations[1].adName).not.toBe(r.variations[0].adName);
    expect(paraPlanoV2(r).ads.map(a => a.adset_key)).toEqual(['a', 'b']);
  });
  it('recusa destino ausente e origem inexistente sem fallback', () => {
    const d = draft();
    expect(adicionarAnuncioNoConjunto(d, '')).toBe(d);
    expect(adicionarAnuncioNoConjunto(d, 'missing')).toBe(d);
    expect(adicionarAnuncioNoConjunto(d, 'b', 'missing')).toBe(d);
  });
  it('não remove conjunto com anúncio oculto pelo modo individual', () => {
    const d = { ...adicionarAnuncioNoConjunto(draft(), 'b'), creativeMode: 'single' as const };
    expect(removerConjuntoSemAnuncios(d, 'b')).toBe(d);
  });
  it('reordenar conjuntos não altera vínculo ao reutilizar peça', () => {
    const d = draft(); d.conjuntos.reverse();
    expect(adicionarAnuncioNoConjunto(d, 'b', 'variation-001').variations.map(v => v.adsetKey)).toEqual(['a', 'b']);
  });
});
