// @vitest-environment jsdom
/**
 * A ordem das campanhas é a do servidor. O browser não reordena fatias.
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import { mesclarPaginas } from '@/hooks/useInventario';
import type { CampanhaNoInventario } from '@/types/trafego';

import { InventarioDeCampanhas } from '@/components/trafego/inventario/InventarioDeCampanhas';
import { creditoUp, inventarioDeProva, maquininha } from '@/components/trafego/inventario/fixtureDeProvas';

function campanha(nome: string, extra: Partial<CampanhaNoInventario> = {}): CampanhaNoInventario {
  return {
    ...maquininha,
    volc_campaign_id: `vc_${nome.replace(/\s+/g, '_')}`,
    nome,
    externa: { ...maquininha.externa, campaign_id: nome },
    ...extra,
  };
}

const zebraPausada = campanha('BR - Zebra pausada', { estado_externo: 'PAUSED', veiculacao: 'PAUSED' });
const alphaLigada = campanha('BR - Alpha ligada', { estado_externo: 'ENABLED', veiculacao: 'SERVING' });
const charlie = campanha('BR - Charlie depois');

const leituraBase: LeituraDoInventario = {
  inventario: null,
  carregando: false,
  atualizando: false,
  falhou: false,
  motivoDaFalha: null,
  temMais: false,
  carregandoMais: false,
  carregarMais: vi.fn(),
  recarregar: vi.fn(),
};

let leitura: LeituraDoInventario = leituraBase;

vi.mock('@/hooks/useInventario', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/hooks/useInventario')>();
  return {
    ...real,
    useInventario: () => leitura,
    usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
  };
});

function nomesNaTela(): string[] {
  return ['BR - Zebra pausada', 'BR - Alpha ligada', 'BR - Charlie depois']
    .filter((nome) => screen.queryByText(nome))
    .sort((a, b) => {
      const na = screen.getByText(a);
      const nb = screen.getByText(b);
      return na.compareDocumentPosition(nb) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });
}

function envelope(campanhas: CampanhaNoInventario[]) {
  return inventarioDeProva({
    frescor: 'recente',
    parcial: false,
    faltou: [],
    contas: [{ ...creditoUp, quantidade: campanhas.length, campanhas }],
    totais: {
      contas: 1,
      operacionais: campanhas.length,
      historicas: 0,
      geral: campanhas.length,
      atencao: 0,
    },
  });
}

beforeEach(() => {
  leitura = {
    ...leituraBase,
    inventario: envelope([zebraPausada, alphaLigada]),
    carregarMais: vi.fn(),
  };
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
});
afterEach(cleanup);

describe('nenhuma ordenação local', () => {
  it('ordenarCampanhas.ts saiu, e o grupo não reordena', () => {
    const raiz = join(process.cwd(), 'src/components/trafego');
    expect(existsSync(join(raiz, 'hub/ordenarCampanhas.ts'))).toBe(false);
    const grupo = readFileSync(join(raiz, 'inventario/GrupoDeConta.tsx'), 'utf8');
    expect(grupo).not.toMatch(/ordenarCampanhas/);
    expect(grupo).not.toMatch(/localeCompare/);
    expect(grupo).not.toMatch(/\.sort\(/);
  });

  it('a tela preserva a ordem recebida, mesmo contra o alfabeto e contra ligadas-primeiro', () => {
    render(<InventarioDeCampanhas />);
    expect(nomesNaTela()).toEqual(['BR - Zebra pausada', 'BR - Alpha ligada']);
  });

  it('carregar mais concatena na ordem do servidor, sem reordenar o que já estava', () => {
    const pagina1 = envelope([zebraPausada]);
    const pagina2 = envelope([alphaLigada, charlie]);
    const junto = mesclarPaginas([pagina1, pagina2]);
    expect(junto?.contas[0].campanhas.map((c) => c.nome)).toEqual([
      'BR - Zebra pausada',
      'BR - Alpha ligada',
      'BR - Charlie depois',
    ]);

    leitura = {
      ...leituraBase,
      inventario: junto,
      temMais: false,
      carregarMais: vi.fn(),
    };
    render(<InventarioDeCampanhas />);
    expect(nomesNaTela()).toEqual([
      'BR - Zebra pausada',
      'BR - Alpha ligada',
      'BR - Charlie depois',
    ]);
  });

  it('o botão de carregar mais não reordena a fatia já visível', () => {
    const carregarMais = vi.fn(() => {
      leitura = {
        ...leitura,
        inventario: envelope([zebraPausada, alphaLigada, charlie]),
        temMais: false,
      };
    });
    leitura = {
      ...leituraBase,
      inventario: envelope([zebraPausada, alphaLigada]),
      temMais: true,
      carregarMais,
    };
    const { rerender } = render(<InventarioDeCampanhas />);
    expect(nomesNaTela()).toEqual(['BR - Zebra pausada', 'BR - Alpha ligada']);
    fireEvent.click(screen.getByRole('button', { name: 'Carregar mais' }));
    expect(carregarMais).toHaveBeenCalledTimes(1);
    rerender(<InventarioDeCampanhas />);
    expect(nomesNaTela()).toEqual([
      'BR - Zebra pausada',
      'BR - Alpha ligada',
      'BR - Charlie depois',
    ]);
  });
});
