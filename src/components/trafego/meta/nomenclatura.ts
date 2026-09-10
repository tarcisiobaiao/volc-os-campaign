import type { Draft } from './rascunho';

export type Naming = NonNullable<Draft['naming']>;
export const novaNomenclatura = (draft: Draft): Naming => ({ enabled: false,
  topic: draft.campaignName.replace(/^\d+\s*-\s*/, '').replace(/\s*\[[^\]]*\]/g, '').trim().slice(0, 200),
  site: siteDoDestino(draft.destinationUrl), landingType: tipoDoDestino(draft.destinationUrl), quiz: false, conversionLabel: '',
  topicSourceUrl: undefined,
  adsetNumbers: {}, adNumbers: {}, generated: {},
});
export function tipoDoDestino(url: string) {
  try { return new URL(url).pathname.split('/')[1] === 'r' ? 'LP_R' : ''; }
  catch { return ''; }
}
export function siteDoDestino(url: string) {
  try { return new URL(url).hostname.replace(/^www\./, '').replace(/\.(com\.br|com|org|net|br)$/, '').replace(/\./g, '_').toUpperCase().slice(0, 80); }
  catch { return ''; }
}
const limpo = (s: string) => s.replace(/[\[\]\r\n]/g, ' ').replace(/\s+/g, ' ').trim();
const tag = (s: string) => limpo(s) ? ` [${limpo(s).toUpperCase()}]` : '';
const num = (n: number, width: number) => String(n).padStart(width, '0');
const next = (numbers: Record<string, number>) => Math.max(0, ...Object.values(numbers)) + 1;

/** Stable keys, not row positions. Deleted numbers remain reserved in the draft. */
export function gerarNomenclatura(draft: Draft, naming: Naming, sizes: Record<string, string> = {}, conversionNames: Record<string, string> = {}) {
  const state: Naming = { ...naming, adsetNumbers: { ...naming.adsetNumbers }, adNumbers: { ...naming.adNumbers }, generated: { ...naming.generated } };
  const names: Record<string, string> = {};
  if (!state.campaignNumber || state.accountRef !== draft.accountRef || !state.topic.trim() || !state.site.trim()) return { naming: state, names };
  const cp = `CP${num(state.campaignNumber, 4)}`;
  names.campaign = `${num(state.campaignNumber, 4)} - ${limpo(state.topic).toUpperCase()}${tag(state.site)}${tag(draft.nivelDeOrcamento === 'CAMPAIGN' ? 'CBO' : 'ABO')}`;
  for (const set of draft.conjuntos) {
    state.adsetNumbers[set.key] ??= next(state.adsetNumbers);
    const cj = `${cp}_CJ${num(state.adsetNumbers[set.key], 3)}`;
    const ads = draft.variations.filter(a => a.adsetKey === set.key);
    const media = [...new Set(ads.map(a => a.midia === 'video' ? 'VIDEO' : 'IMG'))].join(' + ');
    const platforms = (set.posicionamentoModo === 'FACEBOOK_ONLY' ? ['facebook'] : set.posicionamentoValores)
      .map(p => ({ facebook: 'FB', instagram: 'IG', audience_network: 'AN', messenger: 'MESSENGER', threads: 'THREADS' }[p] || p)).join(' + ');
    const age = set.publico.idadeMin !== 18 || set.publico.idadeMax !== 65
      ? set.publico.idadeMin === 65 ? '65+' : `${set.publico.idadeMin}-${set.publico.idadeMax === 65 ? '65+' : set.publico.idadeMax}` : '';
    const conversion = set.mensuracao.proposito === 'OPTIMIZE'
      ? state.conversionLabel || (set.mensuracao.conversaoRef
        ? (conversionNames[set.mensuracao.conversaoRef]?.slice(0, 80) || 'CONVERSAO_PERSONALIZADA')
        : ({ CONTENT_VIEW: 'VIEW_CONTENT', PURCHASE: 'PURCHASE', LEAD: 'LEAD' }[set.mensuracao.eventoPadrao] || set.mensuracao.eventoPadrao))
      : draft.recipeId === 'TRAFFIC_WEBSITE_LPV_STATIC' ? 'LPV' : '';
    names[`set:${set.key}`] = `${cj}${tag(media)}${tag(platforms)}${tag(age)}${tag(state.landingType)}${state.quiz ? tag('QUIZ') : ''}${tag(conversion)}`;
    for (const ad of ads) {
      const key = `${set.key}:${ad.key}`;
      const localNumbers = Object.fromEntries(Object.entries(state.adNumbers).filter(([k]) => k.startsWith(`${set.key}:`)));
      state.adNumbers[key] ??= next(localNumbers);
      const an = state.adNumbers[key];
      names[`ad:${ad.key}`] = `${cj}_AN${num(an, 3)}${tag(ad.midia === 'video' ? 'VIDEO' : 'IMG')}${draft.creativeMode === 'flexible' ? tag('FLEX') : ''}`;
      // Full parent suffix prevents same An001/size in two sets from colliding.
      names[`creative:${ad.key}`] = `${limpo(state.topic)} - An${an} - ${sizes[ad.assetRef] || (ad.midia === 'video' ? 'VIDEO' : 'IMG')}${tag(cj)}`;
    }
  }
  return { naming: state, names };
}

/** Refresh generated values only. A manual edit is never silently overwritten. */
export function aplicarNomenclatura(draft: Draft, naming: Naming, sizes: Record<string, string> = {}, force = false, conversionNames: Record<string, string> = {}): Draft {
  const result = gerarNomenclatura(draft, naming, sizes, conversionNames);
  if (!Object.keys(result.names).length) return draft;
  const value = (key: string, current: string) => {
    if (force || !(key in naming.generated) || current === naming.generated[key]) {
      result.naming.generated[key] = result.names[key]; return result.names[key];
    }
    return current;
  };
  return { ...draft, campaignName: value('campaign', draft.campaignName),
    conjuntos: draft.conjuntos.map(c => ({ ...c, nome: value(`set:${c.key}`, c.nome) })),
    variations: draft.variations.map(a => ({ ...a, adName: value(`ad:${a.key}`, a.adName), creativeName: value(`creative:${a.key}`, a.creativeName) })),
    naming: { ...result.naming, enabled: true },
  };
}
