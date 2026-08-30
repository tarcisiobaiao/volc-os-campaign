// @vitest-environment jsdom
/**
 * A ESCADA NA TELA.
 *
 * O que esta superfície precisa provar, além de renderizar:
 *
 *  - um degrau não apurado NUNCA aparece como "sem impedimento";
 *  - os degraus acima do corte continuam visíveis, sob a frase que diz que são
 *    leitura suspensa — esconder perderia informação, exibir como conclusão
 *    afirmaria o que não se provou;
 *  - valor `null` aparece como travessão, jamais como `0`;
 *  - todo estado é glifo + palavra + descrição, e a descrição chega ao leitor
 *    de tela.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { derivarDiagnostico } from '@/lib/diagnostico/derivar';
import { evidenciaDeProva, ID_FGTS, ID_MAQUININHA } from '@/lib/diagnostico/fixtureDeEvidencia';
import { EscadaDeEntrega } from '../EscadaDeEntrega';

const AGORA = new Date('2026-08-26T18:10:11.000Z');
const diagnostico = (id: string, opcoes = {}) =>
  derivarDiagnostico(evidenciaDeProva(opcoes), id, { agora: AGORA });

afterEach(cleanup);

describe('o veredito é uma frase, não um número grande', () => {
  it('a Maquininha pausada abre dizendo onde a escada parou', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_MAQUININHA)} />);
    expect(
      screen.getByRole('heading', { name: /Não entrega — impedida em campanha/i }),
    ).toBeTruthy();
    expect(screen.getByText(/resolver este degrau vem antes/i)).toBeTruthy();
  });

  it('a FGTS limitada pela verba diz que nada impede e algo segura', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} />);
    expect(
      screen.getByRole('heading', { name: /Entrega abaixo do possível — orçamento/i }),
    ).toBeTruthy();
  });

  it('todo número da tela vem com a idade da leitura ao lado', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} />);
    expect(screen.getByText(/^lido /)).toBeTruthy();
    expect(screen.getByText(/moeda BRL/)).toBeTruthy();
  });

  it('moeda não declarada é dita, e não assumida como real', () => {
    const d = { ...diagnostico(ID_FGTS), moeda: null };
    render(<EscadaDeEntrega diagnostico={d} />);
    expect(screen.getByText(/moeda não declarada/)).toBeTruthy();
  });
});

describe('⚠️ não apurado nunca vira boa notícia', () => {
  it('com a cobrança caída, o título diz que não foi possível apurar', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS, { derrubar: ['faturamento'] })} />);
    expect(
      screen.getByRole('heading', { name: /Não foi possível apurar — parou em conta/i }),
    ).toBeTruthy();
    expect(screen.queryByText(/Nenhum impedimento medido/)).toBeNull();
  });

  it('os degraus acima do corte ficam visíveis, sob a frase de leitura suspensa', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS, { derrubar: ['faturamento'] })} />);
    const nota = screen.getByRole('note');
    expect(nota.textContent).toContain('A leitura para aqui');
    expect(nota.textContent).toContain('inclusive');
    // A campanha continua na tela, e não como conclusão.
    expect(screen.getByRole('button', { name: /Campanha/ })).toBeTruthy();
  });

  it('o motivo literal da falha de leitura aparece na linha do degrau', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS, { derrubar: ['faturamento'] })} />);
    expect(screen.getByText(/motivo da falha de leitura: .*PERMISSION_DENIED/)).toBeTruthy();
  });
});

describe('glifo + palavra + descrição', () => {
  it('a descrição de cada estado chega ao leitor de tela, não só ao mouse', () => {
    const { container } = render(<EscadaDeEntrega diagnostico={diagnostico(ID_MAQUININHA)} />);
    const invisiveis = [...container.querySelectorAll('.sr-only')].map((n) => n.textContent ?? '');
    expect(
      invisiveis.some((t) => t.includes('este degrau impede a entrega')),
    ).toBe(true);
  });

  it('nenhum estado depende de cor: a palavra existe em texto', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} />);
    expect(screen.getAllByText('sem impedimento').length).toBeGreaterThan(0);
    expect(screen.getAllByText('limita').length).toBeGreaterThan(0);
  });
});

describe('a evidência abre no lugar, sem modal', () => {
  it('o degrau expande inline, com `aria-expanded` e painel associado', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} />);
    const botao = screen.getByRole('button', { name: /Orçamento/ });
    expect(botao.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(botao);
    expect(botao.getAttribute('aria-expanded')).toBe('true');

    const painel = document.getElementById(botao.getAttribute('aria-controls')!)!;
    expect(within(painel).getByText(/a verba está segurando a entrega\?/)).toBeTruthy();
    expect(within(painel).getByText('leilões perdidos por verba')).toBeTruthy();
  });

  it('a origem de cada evidência é declarada — lido na conta não é declarado por nós', () => {
    render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} eixoAberto="orcamento" />);
    expect(screen.getAllByText('lido na conta').length).toBeGreaterThan(0);
  });

  it('⚠️ evidência sem valor aparece como travessão, nunca como zero', () => {
    const d = diagnostico(ID_FGTS);
    const orcamento = d.degraus.find((x) => x.eixo === 'orcamento')!;
    orcamento.evidencias = orcamento.evidencias.map((e) => ({ ...e, valor: null }));
    render(<EscadaDeEntrega diagnostico={d} eixoAberto="orcamento" />);

    const painel = document.getElementById('degrau-orcamento')!;
    expect(within(painel).getAllByText('—').length).toBe(orcamento.evidencias.length);
    expect(within(painel).queryByText('0')).toBeNull();
  });

  it('degrau sem evidência nenhuma diz que a conclusão vem da ausência de leitura', () => {
    render(
      <EscadaDeEntrega
        diagnostico={diagnostico(ID_FGTS, { derrubar: ['faturamento'] })}
        eixoAberto="conta"
      />,
    );
    expect(
      screen.getByText(/A conclusão acima vem da ausência da leitura, não de um valor lido/),
    ).toBeTruthy();
  });
});

describe('estrutura do documento', () => {
  it('a escada é lista ordenada — a ordem causal é a informação principal', () => {
    const { container } = render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} />);
    expect(container.querySelectorAll('ol').length).toBeGreaterThan(0);
    // Nove degraus, sempre. Nenhum some por falta de dado.
    expect(container.querySelectorAll('li').length).toBe(9);
  });

  it('todo alvo de toque tem 44px de altura mínima', () => {
    const { container } = render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} />);
    for (const b of container.querySelectorAll('li > button')) {
      expect(b.className).toContain('min-h-11');
    }
  });

  it('o foco é sempre visível — nenhum `outline-none` sem anel de substituição', () => {
    const { container } = render(<EscadaDeEntrega diagnostico={diagnostico(ID_FGTS)} />);
    for (const b of container.querySelectorAll('button')) {
      if (b.className.includes('focus-visible:outline-none')) {
        expect(b.className).toContain('focus-visible:ring-2');
      }
    }
  });
});
