// @vitest-environment jsdom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ImportarCopyDoAssistente } from '../ImportarCopyDoAssistente';
import { lerSelecaoDeCopy } from '../ponteAssistente';
import { lerCopyDeCampanha } from '@/features/creative-studio/api';
vi.mock('@/features/creative-studio/api', () => ({ lerCopyDeCampanha: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const selecao = { projectRef: `crproj_${'a'.repeat(24)}`, runRef: `crrun_${'b'.repeat(24)}`, creativeRef: 'creative_abc' };
const copy = { project_ref: selecao.projectRef, run_ref: selecao.runRef, creative_ref: selecao.creativeRef,
  copy_ref: 'copy_abc', copy_sha256: 'c'.repeat(64), snapshot_sha256: 'd'.repeat(64),
  message: 'Mensagem externa aprovada', headline: 'Título aprovado', description: 'Descrição', cta: 'LEARN_MORE',
  scope: 'DRAFT_COPY_ONLY' as const, launch_authorized: false as const, media_registered: false as const };

describe('ponte da copy', () => {
  it('recebe somente referências e ignora texto fornecido pelo iframe', () => {
    expect(lerSelecaoDeCopy({ type: 'volc:creative-copy', ...selecao, message: 'não confiar' })).toEqual(selecao);
    expect(lerSelecaoDeCopy({ type: 'volc:creative-copy', ...selecao, projectRef: 'https://fora' })).toBeNull();
  });
  it('só substitui o anúncio escolhido após nova leitura da aprovação', async () => {
    vi.mocked(lerCopyDeCampanha).mockResolvedValue(copy);
    const aplicar = vi.fn();
    render(<ImportarCopyDoAssistente selecao={selecao} anuncios={[{ key: 'v1', adName: 'Anúncio 1' }]}
      onAplicar={aplicar} onCancelar={() => {}} />);
    await screen.findByText('Título aprovado');
    expect((screen.getByText('Substituir texto deste anúncio') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Em qual anúncio?'), { target: { value: 'v1' } });
    fireEvent.click(screen.getByText('Substituir texto deste anúncio'));
    await waitFor(() => expect(aplicar).toHaveBeenCalledWith('v1', copy));
    expect(lerCopyDeCampanha).toHaveBeenCalledTimes(2);
  });
  it('recusa aprovação revogada depois de abrir a prévia', async () => {
    vi.mocked(lerCopyDeCampanha).mockResolvedValueOnce(copy).mockRejectedValueOnce(new Error('Aprovação revogada'));
    const aplicar = vi.fn();
    render(<ImportarCopyDoAssistente selecao={selecao} anuncios={[{ key: 'v1', adName: 'Anúncio 1' }]}
      onAplicar={aplicar} onCancelar={() => {}} />);
    await screen.findByText('Título aprovado');
    fireEvent.change(screen.getByLabelText('Em qual anúncio?'), { target: { value: 'v1' } });
    fireEvent.click(screen.getByText('Substituir texto deste anúncio'));
    expect((await screen.findByRole('alert')).textContent).toContain('Aprovação revogada');
    expect(aplicar).not.toHaveBeenCalled();
  });
});
