// @vitest-environment jsdom
/**
 * A bancada Criar desenha o que o registro declara — não sete etapas genéricas.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { EstudioMulticanal } from '@/components/trafego/estudio/EstudioMulticanal';
import type { CapacidadesDoOperador, ManifestoDeCanal } from '@/types/trafego';

const manifesto = (over: Partial<ManifestoDeCanal> = {}): ManifestoDeCanal => ({
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo'],
  paineis: [],
  campos_do_pedido: ['url_final', 'verba_diaria', 'copy'],
  capacidades: ['ler', 'propor', 'escrever'],
  provas_obrigatorias: ['politica', 'duplicidade', 'selo'],
  indisponibilidades: [],
  sabe_provar: true,
  sabe_criar: true,
  ...over,
});

const capacidades: CapacidadesDoOperador = {
  is_admin: true,
  lab_mode: false,
  google_read: true,
  google_validate_only: true,
  google_demand_gen_validate_only: true,
  google_mutate: false,
  porque_sem_mutacao: 'a permissão operacional para escrever nas contas está fechada neste servidor.',
};

const manifestos: ManifestoDeCanal[] = [
  manifesto(),
  manifesto({
    canal: 'DISPLAY',
    rotulo: 'Display',
    sabe_criar: true,
    indisponibilidades: ['a primeira fatia de Display não monta segmentação'],
  }),
  manifesto({
    canal: 'DEMAND_GEN',
    rotulo: 'Demand Gen',
    sabe_provar: true,
    sabe_criar: false,
    campos_do_pedido: ['upgraded_targeting', 'audiencias', 'intencoes', 'exclusoes_de_audiencia'],
    indisponibilidades: ['criação real continua recusada em /subir'],
  }),
  manifesto({
    canal: 'PERFORMANCE_MAX',
    rotulo: 'Performance Max',
    sabe_provar: false,
    sabe_criar: false,
    campos_do_pedido: [],
    hierarquia: ['campanha', 'asset_group', 'asset'],
    indisponibilidades: ['não há construtor de campanha para Performance Max'],
  }),
];

function montar(canal: string | null = 'SEARCH') {
  return render(
    <MemoryRouter>
      <EstudioMulticanal
        manifestos={manifestos}
        capacidades={capacidades}
        canal={canal}
      />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe('a bancada mostra os seis canais com o papel visível', () => {
  it('o seletor lista Search até Shopping, cada um com o estado de capacidade', () => {
    montar();
    const grupo = screen.getByRole('group', { name: 'canal do estúdio' });
    expect(within(grupo).getByRole('button', { name: /Search/ })).toBeTruthy();
    expect(within(grupo).getByRole('button', { name: /Display/ })).toBeTruthy();
    expect(within(grupo).getByRole('button', { name: /Demand Gen/ })).toBeTruthy();
    expect(within(grupo).getByRole('button', { name: /Performance Max/ })).toBeTruthy();
    expect(within(grupo).getByRole('button', { name: /Vídeo/ })).toBeTruthy();
    expect(within(grupo).getByRole('button', { name: /Shopping/ })).toBeTruthy();
    expect(within(grupo).getByText('operacional')).toBeTruthy();
    expect(within(grupo).getByText('somente leitura pela API')).toBeTruthy();
    expect(within(grupo).getByText('depende de Merchant Center')).toBeTruthy();
  });

  it('enquanto o vocabulário não chegou, não inventa os seis canais', () => {
    render(
      <MemoryRouter>
        <EstudioMulticanal manifestos={[]} capacidades={null} lido={false} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('status').textContent).toMatch(/leitura do vocabulário que não chegou/);
    expect(screen.queryByRole('group', { name: 'canal do estúdio' })).toBeNull();
  });
});

describe('Search abre o cockpit real', () => {
  it('o CTA dominante aponta para Preparar e a etapa se chama Anúncio e recursos', () => {
    montar('SEARCH');
    const cta = screen.getByRole('link', { name: 'Começar campanha' });
    expect(cta.getAttribute('href')).toBe('/trafego?aba=preparar');
    expect(screen.getByText('Anúncio e recursos')).toBeTruthy();
    expect(screen.getByText(/pelo menos 3 headlines/)).toBeTruthy();
    expect(screen.queryByText('Criativos')).toBeNull();
    expect(screen.queryByText(/imagens e vídeos/)).toBeNull();
  });
});

describe('os outros canais não copiam o Search', () => {
  it('Display mostra o contrato visual do RDA', () => {
    montar('DISPLAY');
    expect(screen.getByText('Anúncio responsivo de display')).toBeTruthy();
    expect(screen.getByText('imagens de marketing')).toBeTruthy();
    expect(screen.getByText('long headline')).toBeTruthy();
    // ⚠️ Este caso fixava `'Começar campanha'` para Display, e com isso fixava
    // uma PROMESSA FALSA (achado da revisão adversarial, lente 4). A porta é uma
    // só e ela monta Search: `NovaCampanhaPage` envia `canal: 'SEARCH'` fixo.
    // Display responde `sabe_criar: true` no manifesto — o que é verdade sobre o
    // CANAL — e o convite fazia o operador atravessar a porta para montar outro
    // canal, descobrindo a troca dentro de um formulário que pede keywords.
    expect(screen.getByRole('link', { name: 'Preparar por Search' })).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Começar campanha' })).toBeNull();
  });

  it('só Search é convidado a "Começar campanha"; os outros dizem a porta real', () => {
    // Contraprova do mesmo achado, feita canal a canal em vez de num só.
    for (const canal of ['DISPLAY', 'DEMAND_GEN', 'PERFORMANCE_MAX'] as const) {
      cleanup();
      montar(canal);
      expect(
        screen.queryByRole('link', { name: 'Começar campanha' }),
        `${canal} não pode convidar a começar campanha: o cockpit monta Search`,
      ).toBeNull();
    }
    cleanup();
    montar('SEARCH');
    expect(screen.getByRole('link', { name: 'Começar campanha' })).toBeTruthy();
  });

  it('Demand Gen separa as superfícies e declara somente a porta HTTP de prova', () => {
    montar('DEMAND_GEN');
    expect(screen.getByText(/não é Display/)).toBeTruthy();
    expect(screen.getByText('Audiência')).toBeTruthy();
    expect(screen.getByText('Intenção')).toBeTruthy();
    expect(screen.getByText('Exclusões de audiência')).toBeTruthy();
    expect(screen.getByText('Controles de canal')).toBeTruthy();
    expect(screen.getByText('Anúncio multi-asset pausado')).toBeTruthy();
    expect(screen.getByText(/budget → campanha PAUSED/)).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Começar campanha' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Montar e provar' })).toBeNull();
    expect(screen.getByText('Prova HTTP habilitada')).toBeTruthy();
    expect(screen.getByText(/não redireciona para o cockpit de Search/)).toBeTruthy();
  });

  it('Performance Max fala de asset groups, não de keywords', () => {
    montar('PERFORMANCE_MAX');
    expect(screen.getByText('Asset groups')).toBeTruthy();
    expect(screen.queryByText('Keywords, correspondências e negativas')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Começar campanha' })).toBeNull();
  });

  it('Shopping é pré-requisito de Merchant Center', () => {
    montar('SHOPPING');
    fireEvent.click(screen.getByRole('button', { name: /Shopping/ }));
    expect(screen.getByText(/pré-requisito ausente/)).toBeTruthy();
    expect(screen.getByText('Merchant Center')).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Começar campanha' })).toBeNull();
  });

  it('Vídeo observa e não oferece criar pela API', () => {
    montar('VIDEO');
    fireEvent.click(screen.getByRole('button', { name: /Vídeo/ }));
    const observar = screen.getByRole('link', { name: 'Observar e analisar' });
    expect(observar.getAttribute('href')).toBe('/trafego?aba=campanhas&canal=VIDEO');
    expect(screen.queryByText(/Criar campanha Video pela API/i)).toBeNull();
    expect(screen.queryByRole('link', { name: 'Começar campanha' })).toBeNull();
    expect(screen.getByText(/Rotas programáticas de vídeo/)).toBeTruthy();
  });
});
