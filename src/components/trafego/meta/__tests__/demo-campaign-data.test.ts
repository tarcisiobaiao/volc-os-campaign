import { describe, expect, it } from 'vitest';
import { CONTA_DEMO_META, criarDadosDemoCampanha } from '../demoCampaignData';

describe('demo scoped data', () => {
  const id = 'campanha-descoberta-01';
  it('sums children exactly, preserves the fixture on proposals, and filters days', async () => {
    const api = criarDadosDemoCampanha(id)!;
    const f = await api.financeiroMeta(id, CONTA_DEMO_META);
    expect(f.spend).toBeCloseTo(684.2, 2);
    expect(f.revenue).toBeCloseTo(1110, 2);
    expect(f.conjuntos).toHaveLength(2);
    expect(f.conjuntos!.reduce((s,c)=>s+Number(c.spend),0)).toBe(f.spend);
    expect(f.conjuntos!.reduce((s,c)=>s+Number(c.revenue_brl),0)).toBe(f.revenue);
    const dia = await api.financeiroMeta(id,CONTA_DEMO_META,'2026-08-29','2026-08-29');
    expect(dia.spend).toBe(82.4);
    const before = await api.detalheMetaReadModel('conjuntos','conjunto-aberto-01',CONTA_DEMO_META);
    await api.planejarGestaoMeta({conta_ref:CONTA_DEMO_META,campanha_ref:id,entidade:'conjunto',referencia:'conjunto-aberto-01',acao:'PAUSAR'});
    expect(await api.detalheMetaReadModel('conjuntos','conjunto-aberto-01',CONTA_DEMO_META)).toEqual(before);
  });
  it('refuses unknown scope without production fallback', async () => {
    expect(criarDadosDemoCampanha('real-object')).toBeNull();
    await expect(criarDadosDemoCampanha(id)!.financeiroMeta(id,'real-account')).rejects.toThrow('Escopo fora');
  });
  it('has distinct ad observations in the same period without copying revenue', async () => {
    const api = criarDadosDemoCampanha(id)!;
    const f = await api.financeiroMeta(id, CONTA_DEMO_META);
    expect(f.anuncios).toHaveLength(4);
    expect(f.anuncios_completo).toBe(true);
    for (const conjunto of f.conjuntos!) {
      const ads = f.anuncios!.filter(a => a.adset_ref === conjunto.adset_ref);
      expect(ads.reduce((sum,a)=>sum + Number(a.spend),0)).toBeCloseTo(Number(conjunto.spend),2);
      expect(ads.reduce((sum,a)=>sum + Number(a.impressions),0)).toBe(conjunto.impressions);
      expect(ads.reduce((sum,a)=>sum + Number(a.clicks),0)).toBe(conjunto.clicks);
      expect(ads[0].spend).not.toBe(ads[1].spend);
      for (const ad of ads) {
        expect(ad).not.toHaveProperty('revenue');
        expect(ad).not.toHaveProperty('roas_ratio');
        expect(Number(ad.ctr)).toBeCloseTo(Number(ad.clicks)/Number(ad.impressions)*100,5);
      }
    }
    const day = await api.financeiroMeta(id,CONTA_DEMO_META,'2026-08-29','2026-08-29');
    expect(day.anuncios!.reduce((s,a)=>s+Number(a.spend),0)).toBeCloseTo(Number(day.spend),2);
    const absent = await api.financeiroMeta(id,CONTA_DEMO_META,'2027-01-01','2027-01-02');
    expect(absent.anuncios_completo).toBe(false);
    expect(absent.anuncios!.every(a=>a.spend === null && a.clicks === null && !a.completo)).toBe(true);
  });
  it('reuses one creative across adsets and exposes only local illustrative previews', async () => {
    const api = criarDadosDemoCampanha(id)!;
    const creative = await api.inventarioMetaReadModel('criativos',CONTA_DEMO_META);
    const links = await api.inventarioMetaReadModel('vinculos',CONTA_DEMO_META);
    const ads = await api.inventarioMetaReadModel('anuncios',CONTA_DEMO_META);
    expect(creative.items).toHaveLength(3);
    expect(creative.items.every(c=>String(c.thumbnail_url).startsWith('/meta-demo/'))).toBe(true);
    const used = links.items.filter(l=>l.meta_creative_id === creative.items[0].meta_creative_id);
    expect(used).toHaveLength(2);
    expect(new Set(used.map(l=>ads.items.find(a=>a.meta_ad_id === l.meta_ad_id)!.meta_adset_id)).size).toBe(2);
  });
});
