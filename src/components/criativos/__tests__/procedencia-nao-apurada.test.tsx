// @vitest-environment jsdom
/**
 * Contraprovas da auditoria P17, na camada que RENDERIZA
 * (`docs/architecture/UI-ESTADOS-HONESTOS-P17.md`).
 *
 * ## Por que estes casos não eram pegos pelo compilador
 *
 * `tsconfig.app.json` tem `"strict": false`, então `strictNullChecks` está
 * desligado e todo `T | null` do contrato é, para o `tsc`, apenas `T`. Passar
 * `procedenciaExecucao: null` para uma prop tipada `ProcedenciaDeExecucao`
 * compila em silêncio — e a tela imprime "Produzido aqui" para um ativo cuja
 * autoria ninguém apurou. Nesta área, ausência é obrigação de runtime e de
 * teste; o compilador não ajuda.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

// `@/lib/supabase` lança no import sem `VITE_SUPABASE_*`. O dublê corta a
// dependência sem trazer credencial nenhuma para a worktree.
vi.mock('@/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
}));

import { SeloDeProcedencia } from '@/components/criativos/comum/Selo';
import { VazioAposFiltro } from '@/components/criativos/comum/Estados';
import { PainelDeFase, PecaDoJob } from '@/components/criativos/job/Acompanhamento';
import type { CreativeJob, EstadoDoJob, Rendition } from '@/types/criativos';

afterEach(cleanup);

const job = (over: Partial<CreativeJob> = {}): CreativeJob => ({
  id: 'j1',
  briefingId: 'b1',
  projetoId: 'p1',
  projetoTitulo: 'Campanha',
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
  ...over,
});

const peca = (over: Partial<Rendition> = {}): Rendition => ({
  id: 'r1',
  slot: '1x1',
  rotulo: 'Quadrado',
  estado: 'pronta',
  larguraPedida: 1080,
  alturaPedida: 1080,
  nativoLargura: null,
  nativoAltura: null,
  largura: 1080,
  altura: 1080,
  bytesTotais: null,
  mime: null,
  contentHash: null,
  enquadramento: 'nativo',
  masterId: null,
  previewUrl: null,
  erro: null,
  custoUsd: null,
  concluidaEm: null,
  ...over,
});

// ─────────────────────────────────────────────────────────────────────────────
// D1 — procedência não apurada
// ─────────────────────────────────────────────────────────────────────────────

describe('D1: procedência ausente não vira afirmação de autoria', () => {
  it('`null` não é "Produzido aqui"', () => {
    // Mutante: `procedencia === 'observado' ? A : B`. Com `null` caindo no
    // `else`, o selo dizia "Produzido aqui" e a ficha do ativo dizia
    // "Produzida pelo motor do VOLC O.S." — a frase exata que o comentário de
    // `AssetMaster.procedenciaExecucao` existe para impedir.
    render(<SeloDeProcedencia procedencia={null} />);
    expect(screen.queryByText('Produzido aqui')).toBeNull();
    expect(screen.getByText(/não apurada/i)).toBeTruthy();
  });

  it('a descrição do selo nulo nega explicitamente as duas afirmações', () => {
    const { container } = render(<SeloDeProcedencia procedencia={null} />);
    const texto = container.textContent ?? '';
    expect(texto).toMatch(/não apurada/i);
    // Nem autoria nem observação: o servidor simplesmente não disse.
    expect(texto).not.toMatch(/O motor do VOLC O\.S\. executou/);
    expect(texto).not.toMatch(/fábrica externa/);
  });

  it('os dois valores declarados continuam ditos como antes', () => {
    const { unmount } = render(<SeloDeProcedencia procedencia="observado" />);
    expect(screen.getByText('Observado')).toBeTruthy();
    unmount();
    render(<SeloDeProcedencia procedencia="volc_os" />);
    expect(screen.getByText('Produzido aqui')).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D3 — estado desconhecido não pode apagar a tela
// ─────────────────────────────────────────────────────────────────────────────

describe('D3: um estado que esta versão não conhece não derruba o acompanhamento', () => {
  it('renderiza e declara o desconhecimento em vez de lançar', () => {
    // Mutante: `const rotulo = ROTULO_DO_JOB[job.estado]` cru, seguido de
    // `rotulo.palavra`. Um oitavo estado no servidor lançava TypeError e
    // trocava a tela de acompanhamento por tela branca — a pior representação
    // possível de "não sei".
    expect(() =>
      render(
        <PainelDeFase
          job={job({ estado: 'reprocessando' as EstadoDoJob })}
          eventos={[]}
          conexao="inativa"
          falhaDoFluxo={null}
        />,
      ),
    ).not.toThrow();
    expect(screen.getByRole('status').textContent).toMatch(/não reconhecido/i);
  });

  it('estado conhecido continua sendo anunciado pela palavra dele', () => {
    render(
      <PainelDeFase job={job({ estado: 'running' })} eventos={[]} conexao="inativa" falhaDoFluxo={null} />,
    );
    expect(screen.getByRole('status').textContent).toContain('Em execução');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D4 — MISMATCH visível na peça
// ─────────────────────────────────────────────────────────────────────────────

describe('D4: a peça que saiu fora da dimensão pedida diz isso em palavra', () => {
  it('dimensão medida diferente da pedida vira frase, não três números soltos', () => {
    // Mutante: as três linhas do `<dl>` sem nenhuma frase de divergência.
    // Comparar "Pedido 1080 x 1080" com "Medido no arquivo 1024 x 1024" era
    // trabalho do operador, e ninguém faz esse trabalho em uma lista de quatro.
    const { container } = render(<PecaDoJob peca={peca({ largura: 1024, altura: 1024 })} />);
    expect(container.textContent).toMatch(/não bate|fora da dimensão|diferente da pedida/i);
  });

  it('peça na dimensão pedida não recebe aviso nenhum', () => {
    const { container } = render(<PecaDoJob peca={peca()} />);
    expect(container.textContent).not.toMatch(/não bate|fora da dimensão|diferente da pedida/i);
  });

  it('peça sem medida não é acusada de divergir', () => {
    const { container } = render(<PecaDoJob peca={peca({ largura: null, altura: null })} />);
    expect(container.textContent).not.toMatch(/não bate|fora da dimensão|diferente da pedida/i);
    expect(container.textContent).toContain('não medido');
  });

  it('`nao_normalizado` aparece como enquadramento conhecido', () => {
    const { container } = render(
      <PecaDoJob peca={peca({ enquadramento: 'nao_normalizado', largura: 1024, altura: 1024 })} />,
    );
    expect(container.textContent).not.toContain('nao_normalizado');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D5 — universo desconhecido não é "a biblioteca tem 0 ativos"
// ─────────────────────────────────────────────────────────────────────────────

describe('D5: o vazio depois do filtro não inventa o tamanho da biblioteca', () => {
  it('universo desconhecido não afirma zero', () => {
    // Mutante: `universo={universo ?? 0}`. A caixa dizia "A biblioteca tem 0
    // ativos. O filtro atual é que não alcança nenhum deles." — duas
    // afirmações que se contradizem, e a primeira falsa.
    const { container } = render(<VazioAposFiltro universo={null} aoLimpar={() => {}} />);
    expect(container.textContent).not.toMatch(/A biblioteca tem 0 ativos/);
    expect(container.textContent).toMatch(/não informou|não foi informado/i);
  });

  it('universo conhecido continua sendo dito com o número', () => {
    const { container } = render(<VazioAposFiltro universo={48} aoLimpar={() => {}} />);
    expect(container.textContent).toMatch(/A biblioteca tem 48 ativos/);
  });
});
