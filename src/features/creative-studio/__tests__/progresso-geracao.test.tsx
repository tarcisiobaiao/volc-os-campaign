// @vitest-environment jsdom
import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GaleriaDeGeracoes, type PedidoNaGaleria } from '../componentes/GaleriaDeGeracoes';
import type { GeracaoRegistrada } from '../tipos';
import type { Rendition } from '@/types/criativos';

const api = vi.hoisted(() => ({ job: vi.fn() }));
vi.mock('@/lib/criativosApi', () => ({ criativosApi: api }));
vi.mock('../componentes/PacksDeCriativos', () => ({ PacksDeCriativos: () => null }));
const ponte = { job_id: 'job-a', creative_ref: 'creative-a', run_ref: 'run-a', geracao_ref: 'version-a', slots: ['4x5', '1x1'] } as GeracaoRegistrada;
const pedido: PedidoNaGaleria = { runRef: 'run-a', geracaoRef: 'version-a', briefings: ['4x5', '1x1'].map(formato_slot => ({ creative_ref: 'creative-a', formato_slot, texto_na_arte: 'Descubra', direcao_visual: 'Cena' })) };
const renderDe = (slot: string, pronta: boolean): Rendition => ({ id: `render-${slot}`, slot, rotulo: slot, estado: pronta ? 'pronta' : 'gerando', larguraPedida: 1080, alturaPedida: slot === '4x5' ? 1350 : 1080, previewUrl: pronta ? `https://example.invalid/${slot}.png` : null }) as Rendition;
const flush = async () => { await act(async () => { await Promise.resolve(); }); };
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); });

describe('progresso real da geração', () => {
  it('mostra reservas imediatamente e cada arquivo antes de a geração inteira terminar', async () => {
    vi.useFakeTimers();
    const concluiu = vi.fn();
    const { rerender } = render(<GaleriaDeGeracoes geracoes={[]} pedido={pedido} onComecar={vi.fn()} onConcluida={concluiu} />);
    expect(screen.getAllByText('Preparando imagem')).toHaveLength(2);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByText('Seu próximo criativo começa aqui')).toBeNull();
    api.job.mockResolvedValue({ id: 'job-a', estado: 'running', renditions: [renderDe('4x5', true), renderDe('1x1', false)] });
    rerender(<GaleriaDeGeracoes geracoes={[ponte]} pedido={pedido} onComecar={vi.fn()} onConcluida={concluiu} />);
    await flush();
    expect(screen.getAllByRole('img')).toHaveLength(1);
    expect(screen.getByText('Gerando imagem')).toBeTruthy();
    expect(screen.getByText('1 de 2 prontas · 1 em produção')).toBeTruthy();
    expect(concluiu).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar 4x5' }));
    api.job.mockResolvedValue({ id: 'job-a', estado: 'succeeded', renditions: [renderDe('4x5', true), renderDe('1x1', true)] });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.getAllByRole('img')).toHaveLength(2);
    expect(screen.getByRole('checkbox', { name: 'Selecionar 4x5' })).toHaveProperty('checked', true);
    expect(screen.getByText('Suas imagens estão prontas')).toBeTruthy();
    expect(concluiu).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(concluiu).toHaveBeenCalledTimes(1);
    expect(api.job).toHaveBeenCalledTimes(2);
  });

  it('preserva miniatura e seleção se a próxima leitura falhar; tenta de novo sem gerar', async () => {
    vi.useFakeTimers();
    api.job.mockResolvedValueOnce({ id: 'job-a', estado: 'running', renditions: [renderDe('4x5', true), renderDe('1x1', false)] })
      .mockRejectedValueOnce(new Error('rede'))
      .mockResolvedValue({ id: 'job-a', estado: 'partial', renditions: [renderDe('4x5', true), { ...renderDe('1x1', false), estado: 'falhou', erro: { mensagem: 'Falha no provedor.' } }] });
    const concluiu = vi.fn();
    render(<GaleriaDeGeracoes geracoes={[ponte]} onComecar={vi.fn()} onConcluida={concluiu} />);
    await flush();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar 4x5' }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.getAllByRole('img')).toHaveLength(1);
    expect(screen.getByRole('checkbox', { name: 'Selecionar 4x5' })).toHaveProperty('checked', true);
    expect(screen.getByRole('alert')).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('Geração encerrada com pendências')).toBeTruthy();
    expect(screen.getByText('1 de 2 prontas · 1 com falha')).toBeTruthy();
    expect(concluiu).toHaveBeenCalledTimes(1);
  });

  it('não confunde arquivos de versão anterior com o pedido novo', async () => {
    api.job.mockResolvedValue({ id: 'job-a', estado: 'succeeded', renditions: [renderDe('4x5', true), renderDe('1x1', true)] });
    const concluiu = vi.fn();
    render(<GaleriaDeGeracoes geracoes={[{ ...ponte, geracao_ref: 'old-version' }]} pedido={pedido} onComecar={vi.fn()} onConcluida={concluiu} />);
    await flush();
    expect(screen.getAllByRole('img')).toHaveLength(2);
    expect(screen.getAllByText('Preparando imagem')).toHaveLength(2);
    expect(concluiu).not.toHaveBeenCalled();
  });
});
