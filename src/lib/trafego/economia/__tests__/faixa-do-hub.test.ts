/**
 * A faixa econômica do Hub: a soma da carteira não pode mentir por omissão.
 *
 * Cada prova aqui é uma forma de a soma parecer maior, menor ou mais certa do
 * que a leitura permite: moeda misturada, campanha não medida somada como zero,
 * página incompleta tratada como carteira inteira, receita inventada.
 */
import { describe, expect, it } from 'vitest';

import { projetarFaixaDoHub } from '@/lib/trafego/economia/faixaDoHub';
import {
  inventarioComFalha,
  inventarioDeProva,
  inventarioSaudavel,
} from '@/components/trafego/inventario/fixtureDeProvas';
import type { CampanhaNoInventario, Inventario } from '@/types/trafego';

function campanhas(inv: Inventario): CampanhaNoInventario[] {
  return inv.contas.flatMap((c) => c.campanhas);
}

describe('projetarFaixaDoHub', () => {
  it('sem inventário não há faixa — nem zeros', () => {
    expect(projetarFaixaDoHub(null)).toBeNull();
  });

  it('soma só o medido, na moeda da conta, e diz quantas entraram', () => {
    const inv = inventarioSaudavel();
    const faixa = projetarFaixaDoHub(inv)!;
    const medidas = campanhas(inv).filter(
      (c) => c.estado_externo !== 'REMOVED' && c.entrega.leitura && c.entrega.custo_micros != null
        && c.entrega.cliques != null && c.entrega.impressoes != null,
    );
    const esperado = medidas.reduce((t, c) => t + (c.entrega.custo_micros ?? 0), 0) / 1_000_000;
    expect(faixa.custo.valor).toBeCloseTo(esperado, 6);
    expect(faixa.somadas).toBe(medidas.length);
  });

  it('campanha sem entrega medida fica FORA da soma e rebaixa a verdade para parcial', () => {
    const inv = inventarioDeProva();
    const faixa = projetarFaixaDoHub(inv)!;
    expect(faixa.somadas).toBeLessThan(faixa.operacionais);
    expect(faixa.custo.verdade).toBe('parcial');
    expect(faixa.custo.detalhe).toMatch(/sem entrega medida/);
  });

  it('conta que falhou rebaixa a verdade mesmo que todas as campanhas somadas estejam medidas', () => {
    const faixa = projetarFaixaDoHub(inventarioComFalha())!;
    expect(faixa.custo.verdade).toBe('parcial');
    expect(faixa.custo.detalhe).toMatch(/não pôde ser lida/);
  });

  it('página incompleta não é carteira inteira', () => {
    const inv = { ...inventarioSaudavel(), proximo_cursor: 'abc' };
    const faixa = projetarFaixaDoHub(inv)!;
    expect(faixa.custo.verdade).toBe('parcial');
    expect(faixa.custo.detalhe).toMatch(/nem todas as campanhas/);
  });

  it('não soma moedas diferentes: a outra moeda fica fora e é dita', () => {
    const inv = inventarioSaudavel();
    const conta = inv.contas.find((c) => c.campanhas.some((x) => x.entrega.custo_micros != null))!;
    const base = conta.campanhas.find((x) => x.entrega.custo_micros != null)!;
    const emDolar: CampanhaNoInventario = {
      ...base,
      volc_campaign_id: `${base.volc_campaign_id}_usd`,
      entrega: { ...base.entrega, moeda: 'USD', custo_micros: 1 },
    };
    conta.campanhas = [...conta.campanhas, emDolar];
    const antes = projetarFaixaDoHub(inventarioSaudavel())!;
    const faixa = projetarFaixaDoHub(inv)!;
    expect(faixa.moeda).toBe(antes.moeda);
    expect(faixa.custo.valor).toBe(antes.custo.valor);
    expect(faixa.custo.detalhe).toMatch(/outra moeda/);
  });

  it('sem moeda declarada não vira reais: fica fora e, sem nenhuma, o custo é indisponível', () => {
    // Cópia: a fixture devolve campanhas compartilhadas entre chamadas.
    const inv = structuredClone(inventarioSaudavel());
    for (const c of campanhas(inv)) c.entrega = { ...c.entrega, moeda: null };
    const faixa = projetarFaixaDoHub(inv)!;
    expect(faixa.moeda).toBeNull();
    expect(faixa.custo.valor).toBeNull();
    expect(faixa.custo.verdade).toBe('indisponivel');
    expect(faixa.custo.detalhe).toMatch(/sem moeda declarada/);
  });

  it('removida com gasto na janela fica fora e rebaixa a soma para parcial', () => {
    const inv = inventarioSaudavel();
    const conta = inv.contas.find((c) => c.campanhas.some((x) => x.entrega.custo_micros != null))!;
    const base = conta.campanhas.find((x) => x.entrega.custo_micros != null)!;
    const removida: CampanhaNoInventario = {
      ...base,
      volc_campaign_id: `${base.volc_campaign_id}_rm`,
      estado_externo: 'REMOVED',
      entrega: { ...base.entrega, custo_micros: 4_000_000_000 },
    };
    conta.campanhas = [...conta.campanhas, removida];
    const antes = projetarFaixaDoHub(inventarioSaudavel())!;
    const faixa = projetarFaixaDoHub(inv)!;
    expect(faixa.custo.valor).toBe(antes.custo.valor);
    expect(faixa.custo.verdade).toBe('parcial');
    expect(faixa.custo.detalhe).toMatch(/1 removida com gasto/);
  });

  it('nenhuma campanha medida: valor nulo e verdade desconhecida, nunca zero', () => {
    const inv = inventarioSaudavel();
    for (const c of campanhas(inv)) c.entrega = { ...c.entrega, leitura: null };
    const faixa = projetarFaixaDoHub(inv)!;
    expect(faixa.custo.valor).toBeNull();
    expect(faixa.custo.verdade).toBe('desconhecido');
    expect(faixa.cpc.valor).toBeNull();
  });

  it('receita e ROAS chegam indisponíveis, com motivo, e sem número', () => {
    const faixa = projetarFaixaDoHub(inventarioSaudavel())!;
    expect(faixa.receita).toMatchObject({ valor: null, verdade: 'indisponivel' });
    expect(faixa.roas).toMatchObject({ valor: null, verdade: 'indisponivel' });
    expect(faixa.receita.detalhe).toBeTruthy();
  });

  it('o frescor da soma é o da leitura mais antiga somada', () => {
    const inv = inventarioSaudavel();
    const leituras = campanhas(inv)
      .map((c) => c.entrega.leitura?.lido_em)
      .filter((l): l is string => Boolean(l))
      .sort();
    const faixa = projetarFaixaDoHub(inv)!;
    if (leituras.length > 0) expect(faixa.lidoEm).toBe(leituras[0]);
  });
});
