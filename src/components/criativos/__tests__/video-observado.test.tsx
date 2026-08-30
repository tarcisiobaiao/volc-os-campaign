// @vitest-environment jsdom
/**
 * A leitura de vídeo é obrigada a dizer que o VOLC O.S. NÃO produziu o build.
 *
 * É a mentira mais fácil de cometer nesta fatia: player, contrato resolvido,
 * beats e gates de QA lado a lado convidam a conclusão de que a casa renderizou
 * o vídeo. A declaração de origem existe para fechar essa porta por afirmação,
 * não por omissão.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
}));

import { LeituraDeVideo } from '@/components/criativos/video/LeituraDeVideo';
import type { AssetMaster, CreativeJob, VideoObservado } from '@/types/criativos';

const job: CreativeJob = {
  id: 'j1',
  briefingId: 'b1',
  projetoId: 'p1',
  projetoTitulo: 'Short da Odete',
  tipo: 'video',
  modo: 'observado',
  motor: 'fabrica-externa',
  motorVersao: 'desconhecida',
  estado: 'succeeded',
  tentativa: 1,
  procedenciaExecucao: 'observado',
  origemExterna: {
    fabrica: 'volc-factory',
    identificadorDoBuild: 'short_odete',
    hashDoArtefato: 'sha256:abcdef0123456789abcdef',
    congeladoEm: '2026-08-20T10:00:00Z',
    motorVersaoConhecida: null,
    observadoEm: '2026-08-27T09:00:00Z',
  },
  custoEstimadoUsd: null,
  custoRealUsd: null,
  iniciadoEm: null,
  terminadoEm: null,
  canceladoPedidoEm: null,
  canceladoEm: null,
  criadoEm: '2026-08-27T09:00:00Z',
  falha: null,
  renditions: [],
  cursorEventos: 0,
};

const master: AssetMaster = {
  id: 'm1',
  jobId: 'j1',
  projetoId: 'p1',
  projetoTitulo: 'Short da Odete',
  slot: '9x16',
  kind: 'video',
  mime: 'video/mp4',
  largura: 1080,
  altura: 1920,
  bytesTotais: null,
  duracaoMs: null,
  contentHash: 'sha256:0011223344556677',
  versao: 1,
  raizId: null,
  substituiId: null,
  procedencia: {
    motor: 'fabrica-externa',
    motorVersao: 'desconhecida',
    insumoHash: 'sha256:aaaa',
    brandPackId: null,
    brandPackVersao: null,
    criadoEm: '2026-08-20T10:00:00Z',
    custoUsd: null,
    licenca: null,
    credito: null,
    disclosure: null,
    sintetico: true,
  },
  procedenciaExecucao: 'observado',
  previewUrl: null,
  posterUrl: null,
  aprovacaoVigente: null,
  usos: [],
  usoApurado: false,
  criadoEm: '2026-08-20T10:00:00Z',
  arquivadoEm: null,
};

const leitura = (over: Partial<VideoObservado> = {}): VideoObservado => ({
  job,
  master,
  contrato: {
    tema: 'aposentadoria',
    nicho: null,
    skin: null,
    titulo: 'Short da Odete',
    badge: null,
    duracaoS: 45,
    fps: 30,
    largura: 1080,
    altura: 1920,
    hook: null,
    voz: null,
    beats: [
      {
        indice: 1,
        papel: 'Hook',
        copy: 'Você sabia disto?',
        visual: null,
        assetArquivo: null,
        duracaoFrames: null,
        duracaoS: 3,
        inicioS: 0,
      },
    ],
    elementosDeRetencao: [],
    cta: null,
    fatos: [],
  },
  ledger: [],
  qa: {
    vereditoTecnico: 'PASS',
    vereditoVisual: null,
    gatesTecnicos: [],
    gatesVisuais: [],
    custoQaUsd: null,
  },
  videoUrl: 'blob:video',
  posterUrl: null,
  limitacaoDeclarada:
    'O render de vídeo ainda depende da isolação do runtime externo (C-01).',
  ...over,
});

afterEach(cleanup);

describe('a leitura declara a procedência antes de tudo', () => {
  it('afirma que o build foi observado e nomeia a fábrica', () => {
    render(<LeituraDeVideo leitura={leitura()} />);
    expect(screen.getByText('Este build foi observado, não produzido aqui')).toBeTruthy();
    expect(screen.getByText(/A fábrica volc-factory produziu e congelou/)).toBeTruthy();
    expect(screen.getByText(/não renderizou nada deste build/)).toBeTruthy();
  });

  it('mostra a limitação com o texto do servidor, sem inventar o motivo', () => {
    render(<LeituraDeVideo leitura={leitura()} />);
    expect(
      screen.getByText('O render de vídeo ainda depende da isolação do runtime externo (C-01).'),
    ).toBeTruthy();
  });

  it('versão de motor não gravada é declarada, não preenchida', () => {
    render(<LeituraDeVideo leitura={leitura()} />);
    expect(screen.getByText(/não gravada pela fábrica/)).toBeTruthy();
  });

  it('o estado do job fica fora das abas, sempre visível', () => {
    render(<LeituraDeVideo leitura={leitura()} />);
    expect(screen.getAllByText('Concluído').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Observado').length).toBeGreaterThan(0);
  });
});

describe('o player não toca sozinho', () => {
  it('não tem autoplay, não tem som automático e não pré-carrega', () => {
    const { container } = render(<LeituraDeVideo leitura={leitura()} />);
    const video = container.querySelector('video');
    expect(video).toBeTruthy();
    expect(video?.hasAttribute('autoplay')).toBe(false);
    expect(video?.getAttribute('preload')).toBe('none');
    expect(video?.hasAttribute('controls')).toBe(true);
  });

  it('arquivo ausente declara indisponibilidade, não erro', () => {
    const { container } = render(<LeituraDeVideo leitura={leitura({ videoUrl: null })} />);
    expect(container.querySelector('video')).toBeNull();
    expect(screen.getByText(/não está disponível nesta leitura/)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('ausência de registro não vira ausência de fato', () => {
  it('QA não executado é dito como não executado, não como reprovação', () => {
    render(<LeituraDeVideo leitura={leitura()} />);
    expect(screen.getAllByText('Não executado').length).toBeGreaterThan(0);
    expect(screen.getByText(/Ausência de validação não é reprovação/)).toBeTruthy();
  });

  it('lista de fatos vazia diz que ninguém registrou, não que não há afirmações', () => {
    render(<LeituraDeVideo leitura={leitura()} />);
    expect(screen.getByText(/significa que ninguém as registrou aqui/)).toBeTruthy();
  });

  it('as cenas funcionam por teclado, sem depender de arraste', () => {
    render(<LeituraDeVideo leitura={leitura()} />);
    const beat = screen.getByRole('button', { name: /Hook/ });
    expect(beat.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(beat);
    expect(beat.getAttribute('aria-expanded')).toBe('true');
  });
});
