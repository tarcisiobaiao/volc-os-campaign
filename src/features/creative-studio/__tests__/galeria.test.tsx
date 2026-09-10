// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GaleriaDeAssets } from '../componentes/GaleriaDeGeracoes';
import type { Rendition } from '@/types/criativos';
import * as ponte from '@/components/trafego/meta/ponteAssistente';

vi.mock('../componentes/PacksDeCriativos', () => ({ PacksDeCriativos: () => null }));

afterEach(cleanup);
afterEach(() => vi.restoreAllMocks());
const peca = { id: 'asset_teste', slot: '4x5', rotulo: 'Retrato de teste', estado: 'pronta', largura: 1080, altura: 1350, larguraPedida: 1080, alturaPedida: 1350, previewUrl: 'https://example.invalid/fixture.png', mime: 'image/png' } as Rendition;

describe('galeria do estúdio', () => {
  it('no assistente integrado envia somente masters selecionados, não URLs nem geração', () => {
    vi.spyOn(ponte, 'assistenteIntegrado').mockReturnValue(true);
    const enviar = vi.spyOn(window.parent, 'postMessage').mockImplementation(() => {});
    render(<GaleriaDeAssets pecas={[{ ...peca, masterId: 'master_asset_teste' }]} onComecar={vi.fn()} />);
    const selecionar = screen.getByRole('button', { name: 'Selecionar para esta campanha' });
    expect(selecionar).toHaveProperty('disabled', true);
    fireEvent.click(screen.getByRole('checkbox', { name: /selecionar/i }));
    fireEvent.click(selecionar);
    expect(enviar).toHaveBeenCalledExactlyOnceWith({ type: 'volc:creative-selection', masterRefs: ['master_asset_teste'] }, window.location.origin);
  });
  it('não oferece vinculação à campanha quando a imagem não tem master persistido', () => {
    vi.spyOn(ponte, 'assistenteIntegrado').mockReturnValue(true);
    render(<GaleriaDeAssets pecas={[peca]} onComecar={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /selecionar/i }));
    expect(screen.getByRole('button', { name: 'Selecionar para esta campanha' })).toHaveProperty('disabled', true);
  });
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
    expect(screen.getByText('Gerando imagem')).toBeTruthy();
  });
  it('exclusão é explícita, confirmada e arquiva o master sem apagar o recibo', async () => {
    dublê.arquivarAsset.mockResolvedValue({
      assetId: 'master_asset_teste', estado: 'arquivado', historicoPreservado: true,
    });
    const atualizou = vi.fn();
    render(<GaleriaDeAssets pecas={[{ ...peca, masterId: 'master_asset_teste' }]} onComecar={vi.fn()} onArquivada={atualizou} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /selecionar/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Excluir selecionados' }));
    expect(screen.getByRole('alertdialog')).toBeTruthy();
    expect(screen.getByText(/arquivo, a geração e o recibo são preservados/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Excluir da biblioteca' }));
    await waitFor(() => expect(dublê.arquivarAsset).toHaveBeenCalledWith('master_asset_teste'));
    expect(atualizou).toHaveBeenCalledOnce();
  });
  it('arquiva uma única vez quando duas proporções pertencem ao mesmo master', async () => {
    dublê.arquivarAsset.mockClear();
    dublê.arquivarAsset.mockResolvedValue({
      assetId: 'master_asset_teste', estado: 'arquivado', historicoPreservado: true,
    });
    render(<GaleriaDeAssets pecas={[
      { ...peca, id: 'rendition-4x5', masterId: 'master_asset_teste' },
      { ...peca, id: 'rendition-1x1', slot: '1x1', rotulo: 'Quadrado', masterId: 'master_asset_teste' },
    ]} onComecar={vi.fn()} />);
    screen.getAllByRole('checkbox').forEach(item => fireEvent.click(item));
    fireEvent.click(screen.getByRole('button', { name: 'Excluir selecionados' }));
    expect(screen.getByText('Excluir 1 peça(s) da biblioteca?')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Excluir da biblioteca' }));
    await waitFor(() => expect(dublê.arquivarAsset).toHaveBeenCalledTimes(1));
    expect(dublê.arquivarAsset).toHaveBeenCalledWith('master_asset_teste');
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
const dublê = vi.hoisted(() => ({ job: vi.fn(), arquivarAsset: vi.fn() }));
vi.mock('@/lib/criativosApi', () => ({ criativosApi: dublê }));

describe('a galeria sobrevive à leitura parcial', () => {
  it('mostra o que chegou e declara o que faltou, sem virar acervo vazio', async () => {
    dublê.job.mockImplementation(async (id: string) => {
      if (id === 'job-ruim') throw new Error('não foi possível ler este trabalho');
      return {
        id: 'job-ok',
        estado: 'succeeded',
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
