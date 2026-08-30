// @vitest-environment jsdom
/**
 * A tela do trabalho: sem barra inventada, sem peça boa apagada por uma irmã
 * falhada, e sem nenhuma chamada de rede saindo do render.
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// O cliente HTTP do Estúdio importa a sessão do Supabase, que exige variáveis
// de ambiente. O teste não fala com rede nenhuma; o duplo existe só para o
// módulo poder ser importado.
vi.mock('@/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
}));

import { PainelDeFase, PecaDoJob } from '@/components/criativos/job/Acompanhamento';
import type { CreativeJob, EventoDoJob, Rendition } from '@/types/criativos';

const job: CreativeJob = {
  id: 'j1',
  briefingId: 'b1',
  projetoId: 'p1',
  projetoTitulo: 'Campanha de agosto',
  tipo: 'imagem',
  modo: 'full_llm',
  motor: 'motor',
  motorVersao: '1',
  estado: 'running',
  tentativa: 1,
  procedenciaExecucao: 'volc_os',
  origemExterna: null,
  custoEstimadoUsd: null,
  custoRealUsd: null,
  iniciadoEm: null,
  terminadoEm: null,
  canceladoPedidoEm: null,
  canceladoEm: null,
  criadoEm: '2026-08-27T12:00:00Z',
  falha: null,
  renditions: [],
  cursorEventos: 0,
};

const evento = (over: Partial<EventoDoJob>): EventoDoJob => ({
  seq: 1,
  fase: 'gerando',
  mensagem: null,
  percentual: null,
  slot: null,
  em: '2026-08-27T12:00:00Z',
  ...over,
});

const peca = (over: Partial<Rendition>): Rendition => ({
  id: 'r1',
  slot: '1x1',
  rotulo: 'Quadrado',
  estado: 'pronta',
  larguraPedida: 1080,
  alturaPedida: 1080,
  nativoLargura: null,
  nativoAltura: null,
  largura: null,
  altura: null,
  bytesTotais: null,
  mime: null,
  contentHash: null,
  enquadramento: null,
  masterId: null,
  previewUrl: null,
  erro: null,
  custoUsd: null,
  concluidaEm: null,
  ...over,
});

let chamadasDeRede = 0;

beforeEach(() => {
  chamadasDeRede = 0;
  vi.stubGlobal('fetch', (...args: unknown[]) => {
    chamadasDeRede += 1;
    return Promise.reject(new Error(`render não pode chamar rede: ${String(args[0])}`));
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('acompanhamento sem percentual inventado', () => {
  it('percentual nulo não desenha barra: desenha a etapa', () => {
    render(
      <PainelDeFase
        job={job}
        eventos={[evento({ fase: 'chamando_motor' })]}
        conexao="aberta"
        falhaDoFluxo={null}
      />,
    );
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.getByText('Chamando o motor de geração.')).toBeTruthy();
    expect(screen.getByText(/não informa progresso em percentual/)).toBeTruthy();
  });

  it('percentual real desenha a barra com os valores medidos', () => {
    render(
      <PainelDeFase
        job={job}
        eventos={[evento({ percentual: 40 })]}
        conexao="aberta"
        falhaDoFluxo={null}
      />,
    );
    const barra = screen.getByRole('progressbar');
    expect(barra.getAttribute('aria-valuenow')).toBe('40');
    expect(barra.getAttribute('aria-valuemax')).toBe('100');
  });

  it('a mudança de estado é anunciada numa região viva dedicada', () => {
    const { container } = render(
      <PainelDeFase job={job} eventos={[evento({})]} conexao="aberta" falhaDoFluxo={null} />,
    );
    const viva = container.querySelector('[aria-live="polite"]');
    expect(viva).toBeTruthy();
    expect(viva?.textContent).toContain('Em execução');
  });

  it('nenhuma chamada de rede sai do render', () => {
    render(<PainelDeFase job={job} eventos={[evento({})]} conexao="aberta" falhaDoFluxo={null} />);
    expect(chamadasDeRede).toBe(0);
  });
});

describe('falha parcial preserva as peças boas', () => {
  const renditions = [
    peca({ id: 'a', slot: '1x1', rotulo: 'Quadrado', estado: 'pronta', previewUrl: 'blob:a', largura: 1080, altura: 1080 }),
    peca({
      id: 'c',
      slot: '9x16',
      rotulo: 'Vertical',
      estado: 'falhou',
      erro: {
        codigo: 'motor.politica',
        mensagem: 'O motor recusou a mensagem por política de conteúdo.',
        permanente: true,
        em: '2026-08-27T12:00:00Z',
      },
    }),
  ];

  it('a peça pronta continua com prévia mesmo com a irmã falhada na tela', () => {
    render(
      <MemoryRouter>
        <ul>
          {renditions.map((p) => (
            <PecaDoJob key={p.id} peca={p} />
          ))}
        </ul>
      </MemoryRouter>,
    );
    const itens = screen.getAllByRole('listitem');
    expect(itens).toHaveLength(2);
    expect(within(itens[0]).getByRole('img')).toBeTruthy();
    expect(within(itens[0]).getByText('Pronta')).toBeTruthy();
  });

  it('a peça falhada mostra o motivo sanitizado e o remédio certo', () => {
    render(
      <MemoryRouter>
        <ul>
          <PecaDoJob peca={renditions[1]} />
        </ul>
      </MemoryRouter>,
    );
    expect(screen.getByText('O motor recusou a mensagem por política de conteúdo.')).toBeTruthy();
    expect(screen.getByText(/Falha permanente/)).toBeTruthy();
  });

  it('medida ausente aparece como não medida, nunca como zero', () => {
    render(
      <MemoryRouter>
        <ul>
          <PecaDoJob peca={peca({ estado: 'pronta', previewUrl: 'blob:a' })} />
        </ul>
      </MemoryRouter>,
    );
    expect(screen.getAllByText('não medido').length).toBeGreaterThan(0);
    expect(screen.queryByText('0 x 0 px')).toBeNull();
  });

  it('renderizar peças não dispara rede', () => {
    render(
      <MemoryRouter>
        <ul>
          {renditions.map((p) => (
            <PecaDoJob key={p.id} peca={p} />
          ))}
        </ul>
      </MemoryRouter>,
    );
    expect(chamadasDeRede).toBe(0);
  });
});
