// @vitest-environment jsdom
/**
 * Provas da Mesa de Lance.
 *
 * O que estes testes protegem não é layout — é a única coisa que a tela não
 * pode errar: dizer ao operador se o número que ele digitou vale alguma coisa.
 * Sob `maximize_conversions` a API aceita o CPC do ad group e o ignora na
 * veiculação; sob `manual_cpc` ele é o lance. Uma tela que troca essas duas
 * frases faz o operador gastar achando que controla.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MesaDeLance } from '../MesaDeLance';
import { DECORRE_DA_ESTRATEGIA } from '@/types/trafego';
import type { Cockpit } from '@/types/trafego';

afterEach(cleanup);

const cockpitCom = (extra: Record<string, unknown> = {}): Cockpit => ({
  origem: { nicho: 'FGTS', vertical: 'financeiro', url_final: 'https://a.com/x' },
  grupos: [],
  avisos: [],
  conta: {
    vinculada: true,
    customer_id: '8017851692',
    login_customer_id: '6016739364',
    nome: 'Crédito Up',
    moeda: 'BRL',
    fuso: 'America/Sao_Paulo',
    meta_conversao: {
      primaria: { id: '7466930854', nome: 'adViewInterstitial', categoria: 'PURCHASE' },
    },
    ...extra,
  },
} as unknown as Cockpit);

const montar = (props: Partial<React.ComponentProps<typeof MesaDeLance>> = {}) =>
  render(
    <MesaDeLance
      cockpit={cockpitCom()}
      estrategia="MANUAL_CPC" onEstrategia={vi.fn()}
      lance="0.38" onLance={vi.fn()}
      budget="30" onBudget={vi.fn()}
      graduacao={30} onGraduacao={vi.fn()}
      {...props}
    />,
  );

describe('MesaDeLance', () => {
  it('nasce em CPC manual — é como a casa opera', () => {
    montar();
    const manual = screen.getByRole('button', { name: /CPC manual/ });
    expect(manual.getAttribute('aria-pressed')).toBe('true');
  });

  it('mostra o que a escolha CAUSA, para o operador não descobrir depois', () => {
    montar();
    // O match type não é escolhido: decorre. E a tela diz qual saiu.
    expect(screen.getByText(/PHRASE/)).toBeTruthy();
    expect(screen.getByText(/1 conjunto/)).toBeTruthy();
  });

  it('a razão do phrase é de leilão, e está escrita na tela', () => {
    montar();
    expect(screen.getByText(/sinal que filtre a consulta/)).toBeTruthy();
    // E a regra vive num lugar só, para tela e engine nunca discordarem.
    expect(DECORRE_DA_ESTRATEGIA.MANUAL_CPC.match_type).toBe('PHRASE');
  });

  it('a graduação aparece no nascimento, com as quatro consequências', () => {
    montar();
    // "Maximizar conversões" aparece DUAS vezes de propósito: como escolha de
    // nascimento e como destino da graduação. `getByText` explodiria; o que
    // importa provar é que o destino está declarado, não quantas vezes.
    expect(screen.getAllByText(/Maximizar conversões/).length).toBeGreaterThan(1);
    expect(screen.getByText(/CPA real do dia anterior/)).toBeTruthy();
    expect(screen.getByText(/piso de BRL 30,00/)).toBeTruthy();
    expect(screen.getByText(/broad liberado/)).toBeTruthy();
  });

  it('diz que a graduação é REGISTRADA, não executada por esta tela', () => {
    montar();
    expect(screen.getByText(/não fica vigiando a conta/)).toBeTruthy();
  });

  it('sob lance automático não há para onde graduar, e some a regra', () => {
    montar({ estrategia: 'MAXIMIZE_CONVERSIONS' });
    expect(screen.getByText(/não há para onde graduar/)).toBeTruthy();
    expect(screen.queryByText(/CPA real do dia anterior/)).toBeNull();
  });

  it('avisa quando o lance passa do teto medido da casa (R$ 0,50)', () => {
    montar({ lance: '0.80' });
    expect(screen.getByText(/acima do teto da casa/)).toBeTruthy();
  });

  it('não inventa meta quando a conta não expõe — diz "não medido"', () => {
    montar({ cockpit: cockpitCom({ meta_conversao: undefined }) });
    expect(screen.getByText('não medido')).toBeTruthy();
  });

  it('avisa quando a verba de hoje é menor que o piso da graduação', () => {
    montar({ budget: '10' });
    expect(screen.getByText(/a verba sobe para o piso/)).toBeTruthy();
  });

  it('escolher automático troca a estratégia, não o lance', () => {
    const onEstrategia = vi.fn();
    const onLance = vi.fn();
    montar({ onEstrategia, onLance });
    fireEvent.click(screen.getByRole('button', { name: /Maximizar conversões/ }));
    expect(onEstrategia).toHaveBeenCalledWith('MAXIMIZE_CONVERSIONS');
    expect(onLance).not.toHaveBeenCalled();
  });

  it('o rótulo do número muda com a estratégia: lance vira CPA alvo', () => {
    const { unmount } = montar();
    expect(screen.getByText('lance por clique')).toBeTruthy();
    unmount();
    montar({ estrategia: 'MAXIMIZE_CONVERSIONS' });
    expect(screen.getByText('CPA alvo')).toBeTruthy();
  });
});

// ── a mudança de 17/08/2026 ─────────────────────────────────────────────────
//
// O Smart Bidding passou a CONVERGIR para a meta em campanhas limitadas por
// orçamento. Arbitragem é limitada por orçamento sempre. Sem este aviso, a
// linha "lance = CPA real de ontem" lê como teto de segurança — e ela virou
// autorização de gasto. Ver docs/SMART-BIDDING-2026-08-17.md.

describe('MesaDeLance · convergência de meta (17/08/2026)', () => {
  it('avisa que a meta da graduação é o que SERÁ GASTO, não um teto', () => {
    montar();
    expect(screen.getByText(/17\/08\/2026/)).toBeTruthy();
    expect(screen.getByText(/o que será gasto/)).toBeTruthy();
  });

  it('explica por que a meta sai do CPA real e não de número arredondado', () => {
    montar();
    expect(screen.getByText(/arredondado para cima/)).toBeTruthy();
  });

  it('o aviso some com a graduação desligada — não há meta futura a alertar', () => {
    montar({ graduacao: 0 });
    expect(screen.queryByText(/o que será gasto/)).toBeNull();
  });

  it('o aviso some sob lance automático, onde não há graduação', () => {
    montar({ estrategia: 'MAXIMIZE_CONVERSIONS' });
    expect(screen.queryByText(/17\/08\/2026/)).toBeNull();
  });
});
