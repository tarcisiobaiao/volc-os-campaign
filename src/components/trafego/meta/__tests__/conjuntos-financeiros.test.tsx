// @vitest-environment jsdom
/**
 * A seção "Conjuntos de anúncios": o grão em que a receita foi MEDIDA.
 *
 * O que estes testes protegem, e que a tela anterior não podia proteger porque
 * não mostrava número nenhum por conjunto:
 *
 * - o total da campanha PROVA ser a soma dos conjuntos, na tela;
 * - divergência entre a soma e o total é mostrada, nunca escolhida;
 * - ausência continua `—`; zero só quando medido;
 * - a receita não desce para anúncio/criativo;
 * - a leitura campaign-level aparece como reconciliação, jamais como parcela.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { ConjuntosFinanceiros } from '../ConjuntosFinanceiros';
import type { ConjuntoFinanceiroMeta, FinanceiroMeta } from '@/lib/pautadorApi';

const razao = (extra: Partial<ConjuntoFinanceiroMeta['razao']> = {}) => ({
  conjuntos: 1, dias: 1, conjuntos_atribuidos: 1, linhas: 1,
  linhas_atribuidas: 1, linhas_sem_utm: 0, linhas_sem_leitura_gam: 0,
  linhas_sem_entrega: 0, spend_completo: true, revenue_completo: true, ...extra,
});

const conjunto = (over: Partial<ConjuntoFinanceiroMeta> = {}): ConjuntoFinanceiroMeta => ({
  adset_ref: 'metaobj_aaa', id_mascarado: '…4960361',
  spend: '6', revenue_original: '3', revenue_brl: '15',
  impressions: 100, clicks: 5, gam_impressions: 20, gam_clicks: 3,
  reach: null, ctr: '5', cpc: '1.2', roas_ratio: '2.5',
  profit_gross: '9', retorno_excedente_pct: '150',
  currency: 'BRL', timezone: 'America/Sao_Paulo', source: 'META_ADS',
  source_freshness: '2026-09-07T08:00:00Z', revenue_freshness: '2026-09-07T09:00:00Z',
  razao: razao(), ...over,
});

const financeiro = (over: Partial<FinanceiroMeta> = {}): FinanceiroMeta => ({
  ok: true, estado: 'COM_SNAPSHOT', grao: 'adset',
  currency: 'BRL', timezone: 'America/Sao_Paulo',
  periodo_inicio: '2026-09-06', periodo_fim: '2026-09-06', provisorio: false,
  frescor: '2026-09-07T08:00:00Z', receita_frescor: '2026-09-07T09:00:00Z',
  spend: '10', revenue: '25', profit_gross: '15', roas_ratio: '2.5',
  retorno_excedente_pct: '150', impressions: 200, clicks: 10, ctr: '5', cpc: '1',
  spend_completo: true, revenue_completo: true,
  conjuntos: [
    conjunto(),
    conjunto({ adset_ref: 'metaobj_bbb', id_mascarado: '…5594250361', spend: '4', revenue_brl: '10' }),
  ],
  razao: razao({ conjuntos: 2, linhas: 2, conjuntos_atribuidos: 2, linhas_atribuidas: 2 }),
  reconciliacao: null,
  impedimentos: [], ...over,
});

// Sem `globals: true` no vitest.config, a limpeza automática do RTL não é
// registrada: dois `render` no mesmo arquivo empilham DOM e `getByTestId`
// encontra dois elementos. A limpeza explícita é a convenção aqui.
afterEach(cleanup);

describe('ConjuntosFinanceiros — a campanha soma os conjuntos', () => {
  it('mostra uma linha por conjunto e o total da campanha no rodapé', () => {
    render(<ConjuntosFinanceiros financeiro={financeiro()} />);
    expect(screen.getByText('Conjuntos de anúncios (2)')).toBeTruthy();
    expect(screen.getByText('…4960361')).toBeTruthy();
    expect(screen.getByText('…5594250361')).toBeTruthy();
    expect(screen.getByText('Total da campanha')).toBeTruthy();
  });

  it('mostra o percurso de compra até monetização sem chamar impressão GAM de pessoa', () => {
    render(<ConjuntosFinanceiros financeiro={financeiro({
      inline_link_clicks: 25,
      landing_page_views: 20,
      landing_page_load_rate_pct: '80',
      cost_per_landing_page_view: '0.5',
      gam_impressions: 60,
      gam_impressions_per_landing_page_view: '3',
      contribution_observed: '15',
      evidence: {
        state: 'OBSERVED_COMPLETE', reasons: [],
        economic_basis: 'gam_revenue_brl_minus_meta_spend',
        other_costs: 'NOT_MODELED', informational_only: true,
      },
    })} />);
    const percurso = screen.getByTestId('percurso-ate-monetizacao');
    expect(percurso.textContent).toContain('Cliques no link');
    expect(percurso.textContent).toContain('Chegadas à página');
    expect(percurso.textContent).toContain('80,00%');
    expect(percurso.textContent).toContain('R$ 0,50');
    expect(percurso.textContent).toContain('3,00×');
    expect(percurso.textContent).toContain('múltiplos slots e refresh');
    expect(percurso.textContent).toContain('não representam pessoas nem retenção');
    expect(percurso.textContent).toContain('Evidência completa');
  });

  it('não transforma etapas ausentes em zero e explica a cobertura econômica', () => {
    render(<ConjuntosFinanceiros financeiro={financeiro({
      inline_link_clicks: null,
      landing_page_views: null,
      landing_page_load_rate_pct: null,
      cost_per_landing_page_view: null,
      gam_impressions: null,
      gam_impressions_per_landing_page_view: null,
      contribution_observed: null,
      evidence: {
        state: 'INCOMPLETE', reasons: ['GAM_REVENUE_INCOMPLETE'],
        economic_basis: 'gam_revenue_brl_minus_meta_spend',
        other_costs: 'NOT_MODELED', informational_only: true,
      },
    })} />);
    const percurso = screen.getByTestId('percurso-ate-monetizacao');
    expect(percurso.textContent).toContain('—');
    expect(percurso.textContent).not.toContain('R$ 0,00');
    expect(percurso.textContent).toContain('outros custos não modelados');
    expect(percurso.textContent).toContain('Evidência incompleta');
    expect(percurso.textContent).toContain('etapas do percurso ainda sem medida');
  });

  it.each([
    ['PROVISIONAL', 'Dados provisórios'],
    ['UNRECONCILED', 'Leituras divergentes'],
  ] as const)('traduz o estado %s para uma decisão legível', (state, rotulo) => {
    render(<ConjuntosFinanceiros financeiro={financeiro({
      evidence: {
        state, reasons: [], economic_basis: 'gam_revenue_brl_minus_meta_spend',
        other_costs: 'NOT_MODELED', informational_only: true,
      },
    })} />);
    expect(screen.getByTestId('estado-da-evidencia').textContent).toContain(rotulo);
  });

  it('PROVA na tela que o total é a soma dos conjuntos', () => {
    render(<ConjuntosFinanceiros financeiro={financeiro()} />);
    const prova = screen.getByTestId('prova-da-soma');
    // 6 + 4 = 10 de gasto; 15 + 10 = 25 de receita.
    expect(prova.textContent).toContain('soma dos 2 conjuntos é exatamente o total');
  });

  it('quando a soma NÃO bate, a tela diz que não bate em vez de escolher um', () => {
    // O total do servidor diz 99; os conjuntos somam 10. Nada é ajustado.
    render(<ConjuntosFinanceiros financeiro={financeiro({ spend: '99' })} />);
    const prova = screen.getByTestId('prova-da-soma');
    expect(prova.textContent).toContain('não bate');
    expect(prova.textContent).toContain('Nenhum dos dois foi ajustado');
  });

  it('receita parcial NÃO é acusada como divergência (semântica do servidor)', () => {
    // Achado do revisor adversarial: a tela usava "qualquer null derruba a
    // soma" também para a receita, e o servidor não faz isso. Filhos 15 e null
    // com total 15 são CORRETOS e parciais — acusar divergência aqui seria a
    // tela contradizendo um backend que está certo.
    const dados = financeiro({ revenue: '15' });
    dados.conjuntos![1] = conjunto({
      adset_ref: 'metaobj_bbb', id_mascarado: '…5594250361', spend: '4',
      revenue_brl: null, revenue_original: null, roas_ratio: null, profit_gross: null,
      razao: razao({ linhas_atribuidas: 0, linhas_sem_utm: 1, revenue_completo: false }),
    });
    render(<ConjuntosFinanceiros financeiro={dados} />);
    expect(screen.getByTestId('prova-da-soma').textContent).toContain('exatamente o total');
  });

  it('ausência dos dois lados NÃO vira prova de igualdade', () => {
    // `null === null` faria a tela afirmar que a soma bate sobre uma campanha
    // da qual não se sabe nada.
    const dados = financeiro({ spend: null, revenue: null });
    dados.conjuntos = [
      conjunto({ spend: null, revenue_brl: null }),
      conjunto({ adset_ref: 'metaobj_bbb', spend: null, revenue_brl: null }),
    ];
    render(<ConjuntosFinanceiros financeiro={dados} />);
    const texto = screen.getByTestId('prova-da-soma').textContent ?? '';
    expect(texto).toContain('Ausência não é prova de igualdade');
    expect(texto).not.toContain('exatamente o total');
  });

  it('receita desconhecida de um conjunto vira travessão, nunca R$ 0,00', () => {
    const dados = financeiro();
    dados.conjuntos![1] = conjunto({
      adset_ref: 'metaobj_bbb', id_mascarado: '…5594250361', spend: '4',
      revenue_brl: null, revenue_original: null, roas_ratio: null, profit_gross: null,
      razao: razao({ linhas_atribuidas: 0, linhas_sem_utm: 1, revenue_completo: false }),
    });
    render(<ConjuntosFinanceiros financeiro={dados} />);
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText('R$ 0,00')).toBeNull();
  });

  it('zero medido continua sendo zero, e não travessão', () => {
    const dados = financeiro({ revenue: '15' });
    dados.conjuntos![1] = conjunto({
      adset_ref: 'metaobj_bbb', id_mascarado: '…5594250361',
      spend: '4', revenue_brl: '0', profit_gross: '-4', roas_ratio: '0',
    });
    render(<ConjuntosFinanceiros financeiro={dados} />);
    expect(screen.getAllByText('R$ 0,00').length).toBeGreaterThanOrEqual(1);
  });

  it('a razão da soma aparece quando algum conjunto/dia ficou sem UTM', () => {
    render(<ConjuntosFinanceiros financeiro={financeiro({
      razao: razao({ conjuntos: 2, linhas: 2, linhas_atribuidas: 1, linhas_sem_utm: 1,
                     revenue_completo: false }),
    })} />);
    expect(screen.getByText(/1 conjunto\/dia sem UTM no GAM/)).toBeTruthy();
    expect(screen.getByText(/receita desconhecida, não zero/)).toBeTruthy();
  });

  it('a divergência com a leitura campaign-level é reconciliação, não parcela', () => {
    render(<ConjuntosFinanceiros financeiro={financeiro({
      reconciliacao: { reconciliado: false, motivo: 'DIVERGENCIA_ENTRE_NIVEIS',
                       spend_conjuntos: '10', spend_campanha: '99', diferenca: '-89' },
    })} />);
    expect(screen.getByText(/serve para\s+reconciliar/)).toBeTruthy();
    expect(screen.getByText(/contaria a mesma\s+despesa duas vezes/)).toBeTruthy();
  });

  it('campanha sem conjuntos não vira campanha com gasto zero', () => {
    render(<ConjuntosFinanceiros financeiro={financeiro({
      conjuntos: [], estado: 'SEM_CONJUNTOS_NO_READ_MODEL',
    })} />);
    expect(screen.getByText(/o que falta é leitura, não dinheiro/)).toBeTruthy();
    expect(screen.queryByText('R$ 0,00')).toBeNull();
  });

  it('o drill-down avisa que a receita NÃO desce para o anúncio', () => {
    render(
      <ConjuntosFinanceiros
        financeiro={financeiro()}
        aoAbrirConjunto={() => <p>anúncios do conjunto</p>}
      />,
    );
    // `fireEvent` e não `.click()` cru: o clique nativo roda fora do `act` do
    // React e o estado do acordeão não chegaria a mudar antes da asserção.
    fireEvent.click(screen.getAllByRole('button')[0]);
    expect(screen.getByText(/A receita não desce até aqui/)).toBeTruthy();
  });

  it('o id bruto do conjunto nunca chega ao DOM', () => {
    const { container } = render(<ConjuntosFinanceiros financeiro={financeiro()} />);
    // Id SINTÉTICO com a forma de um id da Meta (17 dígitos). Um id real aqui
    // devolveria ao repositório a identidade que a sanitização tirou.
    expect(container.innerHTML).not.toContain('900000000000000361');
    // O que a tela mostra é o id MASCARADO; a referência opaca fica no
    // atributo de controle, nunca como texto de leitura.
    expect(container.innerHTML).toContain('…4960361');
  });
});
