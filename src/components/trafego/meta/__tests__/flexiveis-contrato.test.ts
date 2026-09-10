import { describe, expect, it } from 'vitest';
import {
  CAPACIDADES_FECHADAS, conjuntoInicial, paraPlanoV2, pendenciasDaVariacao,
  pendenciasDosTextosFlexiveis, prontidaoDasEtapas, textosFlexiveisDoConjunto,
  variacaoCompleta, variacaoEfetiva, variacaoInicial, type Draft, type TextosFlexiveisDraft,
} from '../rascunho';
import { duplicarParaTrocarImagem } from '../vinculos';

const pools = (prefixo: string): TextosFlexiveisDraft => ({
  primary_text: [`${prefixo}: principal A`, `${prefixo}: principal B`],
  headline: [`${prefixo}: título`], description: [],
});
function draftInicial(): Draft {
  return {
    recipeId: 'WEB_SALES_CONVERSION', accountRef: 'conta', pageRef: 'pagina', instagramActorRef: '',
    campaignName: 'Campanha', destinationUrl: 'https://example.test/', nivelDeOrcamento: 'ADSET',
    periodoDeOrcamento: 'DAILY', budgetBrl: '10,00', categoryConfirmed: true, creativeMode: 'flexible',
    conjuntos: ['A', 'B'].map(key => conjuntoInicial(key, `Conjunto ${key}`, '2026-10-01T10:00')),
    variations: ['A', 'B'].map((adsetKey, index) => ({
      ...variacaoInicial(`v${index}`, index + 1, adsetKey), assetRef: `asset-${adsetKey}`,
      message: `${adsetKey} texto legado`, headline: `${adsetKey} título legado`, description: `${adsetKey} descrição legada`,
      assetRightsConfirmed: true, thirdPartyIdentityCleared: true, assetPolicyConfirmedAt: '2026-10-01T09:00:00Z',
    })),
  };
}

describe('pools de texto por conjunto flexível', () => {
  it('emite arrays independentes das imagens e não mistura conjuntos reordenados', () => {
    const draft = draftInicial();
    draft.conjuntos[0].flexibleTexts = pools('A');
    draft.conjuntos[1].flexibleTexts = pools('B');
    draft.conjuntos.reverse();
    const plano = paraPlanoV2(draft);
    expect(plano.creative_mode).toBe('FLEXIBLE_IMAGES');
    expect(plano.adsets.map(s => [s.adset_key, s.flexible_texts])).toEqual([['B', pools('B')], ['A', pools('A')]]);
    expect(plano.ads.map(ad => [ad.adset_key, ad.message, ad.headline, ad.description])).toEqual([
      ['A', pools('A').primary_text[0], pools('A').headline[0], ''],
      ['B', pools('B').primary_text[0], pools('B').headline[0], ''],
    ]);
    expect(plano.ads).toHaveLength(2); // Textos adicionais não inventam imagens/anúncios.
  });

  it('deriva legado por pai com trim e unique sem alterar a origem', () => {
    const draft = draftInicial();
    draft.variations.push({ ...draft.variations[0], key: 'repetido', message: ` ${draft.variations[0].message} ` });
    draft.variations.push({ ...draft.variations[0], key: 'outro', message: 'Outro argumento', description: '' });
    const antes = JSON.stringify(draft);
    expect(textosFlexiveisDoConjunto(draft, 'A')).toEqual({
      primary_text: ['A texto legado', 'Outro argumento'], headline: ['A título legado'], description: ['A descrição legada'],
    });
    expect(textosFlexiveisDoConjunto(draft, 'B').primary_text).toEqual(['B texto legado']);
    expect(JSON.stringify(draft)).toBe(antes);
    expect(paraPlanoV2(draft).adsets.every(set => set.flexible_texts)).toBe(true);
  });

  it('não corta pools derivados ou explícitos acima de cinco e sinaliza a pendência', () => {
    const draft = draftInicial();
    draft.variations = Array.from({ length: 6 }, (_, index) => ({
      ...draft.variations[0], key: `v${index}`, message: `Argumento ${index}`,
    }));
    const derivados = textosFlexiveisDoConjunto(draft, 'A');
    expect(derivados.primary_text).toHaveLength(6);
    expect(pendenciasDosTextosFlexiveis(derivados)).toContain('Use no máximo 5 textos principais por conjunto.');
    draft.conjuntos[0].flexibleTexts = derivados;
    expect(paraPlanoV2(draft).adsets[0].flexible_texts?.primary_text).toHaveLength(6);
    expect(variacaoCompleta(draft.variations[0], draft)).toBe(false);
  });

  it('listas explicitamente vazias não são preenchidas silenciosamente com os textos legados', () => {
    const draft = draftInicial();
    draft.conjuntos[0].flexibleTexts = { primary_text: [], headline: [], description: [] };
    expect(textosFlexiveisDoConjunto(draft, 'A')).toEqual(draft.conjuntos[0].flexibleTexts);
    expect(pendenciasDosTextosFlexiveis(textosFlexiveisDoConjunto(draft, 'A'))).toHaveLength(2);
    expect(variacaoCompleta(draft.variations[0], draft)).toBe(false);
    expect(paraPlanoV2(draft).ads[0].message).toBe('');
  });

  it('valida todos os tipos, inclusive entradas vazias e limites de caracteres', () => {
    expect(pendenciasDosTextosFlexiveis(pools('A'))).toEqual([]);
    expect(pendenciasDosTextosFlexiveis({ primary_text: ['p'.repeat(2200)], headline: ['t'.repeat(255)], description: ['d'.repeat(255)] })).toEqual([]);
    expect(pendenciasDosTextosFlexiveis({ primary_text: ['p'], headline: ['🙂'.repeat(255)], description: [] })).toEqual([]);
    expect(pendenciasDosTextosFlexiveis({ primary_text: ['p'.repeat(2201)], headline: ['t'.repeat(256)], description: ['d'.repeat(256)] })).toHaveLength(3);
    expect(pendenciasDosTextosFlexiveis({ primary_text: [' '], headline: ['t'], description: [''] })).toHaveLength(2);
    expect(pendenciasDosTextosFlexiveis({ primary_text: ['p'], headline: Array(6).fill('t'), description: Array(6).fill('d') })).toHaveLength(2);
  });

  it('pools válidos substituem campos legados invisíveis sem dispensar direitos da mídia', () => {
    const draft = draftInicial();
    draft.conjuntos.forEach(set => { set.flexibleTexts = pools(set.key); });
    draft.variations.forEach(ad => { ad.message = ''; ad.headline = ''; ad.description = ''; });
    expect(pendenciasDaVariacao(draft.variations[0], draft)).toEqual([]);
    const contexto = { capacidades: { ...CAPACIDADES_FECHADAS, flexivel: true }, compilado: false, validado: false };
    expect(prontidaoDasEtapas(draft, contexto).criativo).toBe('pronto');
    draft.variations[0].assetRightsConfirmed = false;
    expect(pendenciasDaVariacao(draft.variations[0], draft)).toContain('Confirme os direitos de uso da imagem.');
    expect(prontidaoDasEtapas(draft, contexto).criativo).toBe('pendente');
  });

  it('STATIC omite pools e mantém cópia e validação legadas mesmo com arrays salvos', () => {
    const draft = draftInicial();
    draft.creativeMode = 'batch';
    draft.conjuntos[0].flexibleTexts = pools('Inativo');
    const plano = paraPlanoV2(draft);
    expect(plano).not.toHaveProperty('creative_mode');
    expect(plano.adsets.every(set => !('flexible_texts' in set))).toBe(true);
    expect(plano.ads[0].message).toBe('A texto legado');
    expect(variacaoEfetiva(draft, draft.variations[0])).toBe(draft.variations[0]);
    draft.variations[0].description = '';
    expect(pendenciasDaVariacao(draft.variations[0], draft)).toContain('Preencha a descrição.');
  });

  it('retorno e payload não compartilham arrays mutáveis com o rascunho', () => {
    const draft = draftInicial();
    draft.conjuntos[0].flexibleTexts = pools('A');
    textosFlexiveisDoConjunto(draft, 'A').headline.push('Não persistir');
    paraPlanoV2(draft).adsets[0].flexible_texts?.primary_text.push('Também não');
    expect(draft.conjuntos[0].flexibleTexts).toEqual(pools('A'));
  });

  it('preserva arrays em roundtrip de persistência e duplicação para trocar imagem', () => {
    const draft = draftInicial();
    draft.conjuntos[0].flexibleTexts = pools('A');
    const recuperado = JSON.parse(JSON.stringify(draft)) as Draft;
    expect(paraPlanoV2(recuperado)).toEqual(paraPlanoV2(draft));
    const duplicado = duplicarParaTrocarImagem(recuperado, 'v0');
    expect(duplicado.creativeMode).toBe('flexible');
    expect(duplicado.conjuntos[0].flexibleTexts).toEqual(pools('A'));
    expect(variacaoEfetiva(duplicado, duplicado.variations.at(-1)!).message).toBe(pools('A').primary_text[0]);
    expect(duplicado.variations.at(-1)?.assetRightsConfirmed).toBe(false);
  });

  it('mover uma imagem usa o pool do novo pai sem modificar os pools nem herdar outro escopo', () => {
    const draft = draftInicial();
    draft.conjuntos.forEach(set => { set.flexibleTexts = pools(set.key); });
    const before = JSON.stringify(draft.conjuntos);
    draft.variations[0] = { ...draft.variations[0], adsetKey: 'B' };
    expect(paraPlanoV2(draft).ads[0].message).toBe(pools('B').primary_text[0]);
    expect(JSON.stringify(draft.conjuntos)).toBe(before);
    expect(textosFlexiveisDoConjunto(draft, 'inexistente')).toEqual({ primary_text: [], headline: [], description: [] });
  });

  it('editar pools muda o payload assinado sem mutar a versão anterior', () => {
    const draft = draftInicial();
    draft.conjuntos[0].flexibleTexts = pools('A');
    const original = JSON.stringify(paraPlanoV2(draft));
    draft.conjuntos[0].flexibleTexts.primary_text[1] = 'Novo argumento aprovado';
    expect(JSON.stringify(paraPlanoV2(draft))).not.toBe(original);
    expect(original).toContain('A: principal B');
  });
});
