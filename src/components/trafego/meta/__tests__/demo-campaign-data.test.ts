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
});
