// @vitest-environment jsdom
/**
 * Provas do cartão de campanha ligada que não gasta.
 *
 * O que se prova aqui é o que ele NÃO faz: não inventa número, não sugere
 * lance, e não manda olhar o lance quando o problema é o anúncio.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import AlertaDeEntrega, { tempoLigada } from '@/components/trafego/AlertaDeEntrega';
import type { AlertaDeEntrega as Alerta } from '@/types/trafego';

afterEach(cleanup);

const base: Alerta = {
  customer_id: '8017851692',
  customer_name: 'Crédito Up',
  campaign_id: '24155134757',
  campaign_name: 'BR - Maquininha de Cartão',
  status: 'ENABLED',
  veiculacao: 'SERVING',
  horas_ligada: 26.4,
  impressoes: 1,
  cliques: 0,
  custo: 0,
  lance: 0.12,
  orcamento: 10,
  teto_de_cliques: 83,
  razoes: [],
  aprovacao_do_anuncio: 'APPROVED',
  sintoma: 'sem_impressao',
  revisar: ['o que o Google está dizendo', 'o lance do grupo', 'o orçamento diário'],
  alteracoes: [{
    quando: '2026-08-19 22:39',
    campo: 'lance',
    de: 'R$ 1.00',
    para: 'R$ 0.12',
    origem: 'GOOGLE_ADS_WEB_CLIENT',
    quem: 'tarcisio@agenciavolc.com.br',
    resumo: 'lance R$ 1.00 → R$ 0.12, no painel, 2026-08-19 22:39',
  }],
};

describe('AlertaDeEntrega', () => {
  it('mostra os fatos da conta', () => {
    render(<AlertaDeEntrega alerta={base} />);
    expect(screen.getByText('R$ 0,12')).toBeTruthy();
    expect(screen.getByText('R$ 10,00/dia')).toBeTruthy();
    expect(screen.getByText('83')).toBeTruthy();
    expect(screen.getByText(/ligada há 26,4h e não gastou nada/)).toBeTruthy();
    expect(screen.getByText('Crédito Up')).toBeTruthy();
  });

  it('abre a campanha na conta que veio colada ao alerta', () => {
    render(<AlertaDeEntrega alerta={base} />);
    const link = screen.getByRole('link', { name: /abrir no Google Ads/i });
    expect(link.getAttribute('href')).toContain('__c=8017851692');
  });

  it('⚠️ NÃO sugere lance nem cita CPC de mercado', () => {
    // A tentação era "R$ 0,12 contra mediana de R$ 10,54". É estimativa de
    // terceiro: infla, e no dia em que errar o operador para de confiar em
    // todos os outros alertas.
    const { container } = render(<AlertaDeEntrega alerta={base} />);
    const texto = container.textContent ?? '';
    for (const proibido of ['mediana', 'mercado', 'recomend', 'sugerimos', 'deveria']) {
      expect(texto.toLowerCase()).not.toContain(proibido);
    }
  });

  it('diz de onde vem o teto de cliques, para não parecer previsão', () => {
    render(<AlertaDeEntrega alerta={base} />);
    expect(screen.getByTitle(/orçamento ÷ lance/)).toBeTruthy();
  });

  it('mostra a alteração com origem — painel ou API', () => {
    render(<AlertaDeEntrega alerta={base} />);
    expect(screen.getByText(/no painel/)).toBeTruthy();
  });

  it('sem impressão manda olhar o leilão', () => {
    render(<AlertaDeEntrega alerta={base} />);
    expect(screen.getByText(/Não entrou no leilão/)).toBeTruthy();
  });

  it('com impressão manda olhar o anúncio, NÃO o lance', () => {
    // Subir lance aqui é pagar mais caro para continuar não sendo clicado.
    render(<AlertaDeEntrega alerta={{
      ...base, impressoes: 40, sintoma: 'sem_clique',
      revisar: ['o que o Google está dizendo', 'o texto do anúncio', 'a página de destino'],
    }} />);
    expect(screen.getByText(/Entrou no leilão e ninguém clicou/)).toBeTruthy();
    expect(screen.getByText('o texto do anúncio')).toBeTruthy();
    expect(screen.queryByText('o lance do grupo')).toBeNull();
  });

  it('sem observação do Google, diz isso em vez de deixar em branco', () => {
    render(<AlertaDeEntrega alerta={base} />);
    expect(screen.getByText(/nenhuma observação/)).toBeTruthy();
  });

  it('repete o texto do Google quando ele diz algo', () => {
    render(<AlertaDeEntrega alerta={{ ...base, razoes: ['LIMITED_BY_BUDGET'] }} />);
    expect(screen.getByText(/LIMITED_BY_BUDGET/)).toBeTruthy();
  });

  it('lance ausente vira travessão e não zero', () => {
    // "R$ 0,00" diria que o lance é zero; o que houve foi não conseguir ler.
    render(<AlertaDeEntrega alerta={{ ...base, lance: null, teto_de_cliques: null }} />);
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
  });
});

describe('tempoLigada', () => {
  it('usa horas abaixo de dois dias e dias acima', () => {
    expect(tempoLigada(26.4)).toBe('há 26,4h');
    expect(tempoLigada(72)).toBe('há 3 dias');
  });

  it('hora desconhecida é dita, não escondida', () => {
    expect(tempoLigada(null)).toBe('há tempo desconhecido');
  });
});
