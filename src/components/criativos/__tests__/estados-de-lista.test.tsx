// @vitest-environment jsdom
/**
 * Vazio, vazio depois do filtro e erro de leitura precisam PARECER diferentes,
 * não só ter nomes diferentes no código.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  ErroDeLeitura,
  Carregando,
  SemArquivo,
  Vazio,
  VazioAposFiltro,
} from '@/components/criativos/comum/Estados';

afterEach(cleanup);

describe('os quatro estados de uma lista', () => {
  it('o vazio explica o que vai aparecer ali, sem número inventado', () => {
    render(
      <Vazio
        titulo="A biblioteca ainda está vazia"
        explicacao="Cada peça produzida é guardada aqui com procedência."
      />,
    );
    expect(screen.getByText('A biblioteca ainda está vazia')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('o vazio depois do filtro diz quantos existem e oferece limpar', () => {
    const limpar = vi.fn();
    render(<VazioAposFiltro universo={48} aoLimpar={limpar} />);
    expect(screen.getByText(/A biblioteca tem 48 ativos/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Limpar filtros' })).toBeTruthy();
    // Nunca afirma que a fonte está vazia.
    expect(screen.queryByText(/ainda está vazia/)).toBeNull();
  });

  it('o erro é um alerta e não pode ser confundido com vazio', () => {
    render(<ErroDeLeitura mensagem="A leitura falhou." codigo="ESTUDIO.sem_resposta" />);
    const alerta = screen.getByRole('alert');
    expect(alerta.textContent).toContain('A leitura não chegou');
    expect(alerta.textContent).toContain('A leitura falhou.');
    expect(alerta.textContent).toContain('ESTUDIO.sem_resposta');
  });

  it('o erro não expõe status bruto nem vocabulário de máquina', () => {
    render(<ErroDeLeitura mensagem="O Estúdio não conseguiu concluir esta operação." />);
    const alerta = screen.getByRole('alert');
    expect(alerta.textContent).not.toMatch(/\b(500|502|503|504|PostgREST|Traceback)\b/);
  });

  it('o carregando preserva o layout e se anuncia', () => {
    const { container } = render(<Carregando rotulo="Lendo a biblioteca" linhas={4} />);
    expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
    expect(screen.getByText('Lendo a biblioteca')).toBeTruthy();
  });

  it('arquivo indisponível é um quinto estado, e não é erro nem vazio', () => {
    render(<SemArquivo />);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText(/Arquivo indisponível/)).toBeTruthy();
  });
});
