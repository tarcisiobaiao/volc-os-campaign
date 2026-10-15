// @vitest-environment jsdom
/**
 * Aprovação não nasce marcada. Um "Aprovado" pré-selecionado transforma pressa
 * em autorização: registrar sem escolher precisa ser recusado no campo.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
}));

import { FormularioDeDecisao } from '../aprovacoes/Decisao';

afterEach(cleanup);

describe('o formulário de decisão', () => {
  it('abre sem nenhuma decisão marcada', () => {
    render(<FormularioDeDecisao prefixo="t" aprovavel enviando={false} erro={null} aoDecidir={() => undefined} />);
    for (const radio of screen.getAllByRole('radio')) {
      expect((radio as HTMLInputElement).checked).toBe(false);
    }
  });

  it('registrar sem escolher não envia e diz o que falta', () => {
    const aoDecidir = vi.fn();
    render(<FormularioDeDecisao prefixo="t" aprovavel enviando={false} erro={null} aoDecidir={aoDecidir} />);
    fireEvent.change(screen.getByLabelText(/finalidade da decisão/i), { target: { value: 'display Q4' } });
    fireEvent.click(screen.getByRole('button', { name: /registrar decisão/i }));
    expect(aoDecidir).not.toHaveBeenCalled();
    expect(screen.getByText('Escolha a decisão.')).toBeTruthy();
  });

  it('com a decisão escolhida, envia', () => {
    const aoDecidir = vi.fn();
    render(<FormularioDeDecisao prefixo="t" aprovavel enviando={false} erro={null} aoDecidir={aoDecidir} />);
    fireEvent.click(screen.getAllByRole('radio')[0]);
    fireEvent.change(screen.getByLabelText(/finalidade da decisão/i), { target: { value: 'display Q4' } });
    fireEvent.click(screen.getByRole('button', { name: /registrar decisão/i }));
    expect(aoDecidir).toHaveBeenCalledTimes(1);
  });
});
