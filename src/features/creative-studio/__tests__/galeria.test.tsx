// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GaleriaDeAssets } from '../componentes/GaleriaDeGeracoes';
import type { Rendition } from '@/types/criativos';

afterEach(cleanup);
const peca = { id: 'asset_teste', slot: '4x5', rotulo: 'Retrato de teste', estado: 'pronta', largura: 1080, altura: 1350, larguraPedida: 1080, alturaPedida: 1350, previewUrl: 'https://example.invalid/fixture.png', mime: 'image/png' } as Rendition;

describe('galeria do estúdio', () => {
  it('não inventa assets no vazio e oferece briefing', () => {
    const comecar = vi.fn();
    render(<GaleriaDeAssets pecas={[]} onComecar={comecar} />);
    expect(screen.queryByRole('img')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Preparar um briefing' }));
    expect(comecar).toHaveBeenCalledOnce();
  });
  it('oferece preview, zoom acessível e ZIP por seleção, sem geração', () => {
    render(<GaleriaDeAssets pecas={[peca]} onComecar={vi.fn()} />);
    expect(screen.getByRole('img').getAttribute('src')).toBe(peca.previewUrl);
    const zip = screen.getByRole('button', { name: /baixar selecionados/i }) as HTMLButtonElement;
    expect(zip.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: /selecionar/i }));
    expect(zip.disabled).toBe(false);
    expect(screen.getByRole('button', { name: 'Baixar Retrato de teste' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Ampliar Retrato de teste' }));
    expect(screen.getByRole('dialog')).toBeTruthy();
  });
  it('não permite selecionar arquivo que ainda não está pronto', () => {
    render(<GaleriaDeAssets pecas={[{ ...peca, estado: 'gerando', previewUrl: null }]} onComecar={vi.fn()} />);
    expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText('Aguardando arquivo')).toBeTruthy();
  });
});

/**
 * Leitura parcial: o defeito mais caro desta galeria.
 *
 * O laço usava `Promise.all`. UM id que falhasse rejeitava tudo e descartava as
 * leituras que tinham dado certo, então um 404 transitório num job apagava da
 * tela os formatos que já estavam prontos em outro — exatamente o oposto de
 * "falha em um formato não apaga os formatos concluídos". Pior: o `catch`
 * matava o timer, e a galeria parava de acompanhar para sempre.
 */
const dublê = vi.hoisted(() => ({ job: vi.fn() }));
vi.mock('@/lib/criativosApi', () => ({ criativosApi: dublê }));

describe('a galeria sobrevive à leitura parcial', () => {
  it('mostra o que chegou e declara o que faltou, sem virar acervo vazio', async () => {
    dublê.job.mockImplementation(async (id: string) => {
      if (id === 'job-ruim') throw new Error('não foi possível ler este trabalho');
      return {
        id: 'job-ok',
        estado: 'concluido',
        renditions: [{ ...peca, id: 'asset_ok', rotulo: 'Formato pronto' }],
      };
    });

    const { GaleriaDeGeracoes } = await import('../componentes/GaleriaDeGeracoes');
    render(
      <GaleriaDeGeracoes
        geracoes={[{ job_id: 'job-ok' }, { job_id: 'job-ruim' }] as never}
        onComecar={vi.fn()}
      />,
    );

    // O formato que ficou pronto continua na tela…
    expect(await screen.findByRole('img')).toBeTruthy();
    // …a falha do outro é dita, não escondida…
    expect(
      await screen.findByText(/1 de 2 trabalho\(s\) não puderam ser lidos/i),
    ).toBeTruthy();
    // …e não é confundida com acervo vazio.
    expect(screen.queryByRole('button', { name: 'Preparar um briefing' })).toBeNull();
  });
});
