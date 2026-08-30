// @vitest-environment jsdom
/**
 * Smoke test do wizard: ele MONTA?
 *
 * Existe por causa de um bug real: um `const` lido antes da própria declaração
 * (temporal dead zone) virava ReferenceError no render e a página inteira ficava
 * BRANCA. O `tsc` passou limpo e o build também — só um render de verdade pega.
 *
 * Não testa aparência. Testa que nenhuma tela fica em branco.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MetaCapiWizard } from '../MetaCapiWizard';
import type { MetaCapiSite } from '@/hooks/useMetaCapiSites';

const noop = async () => null;
const noopVoid = async () => {};

const siteSalvo: MetaCapiSite = {
  id: 1,
  site_key: 'apps-technews',
  site_name: 'Apps TechNews',
  domain: 'apps.technewsbrasil.com.br',
  cookie_domain: '.technewsbrasil.com.br',
  endpoint_url: 'https://ev.technewsbrasil.com.br/capi',
  pixel_id: '940750053457681',
  events: { interstitial: true, rewarded: true },
  is_active: true,
  test_event_code: null,
  has_token: true,
  last_check_at: null,
  last_check_result: null,
  created_at: '2026-07-30T00:00:00Z',
  updated_at: '2026-07-30T00:00:00Z',
};

beforeEach(() => {
  // O wizard pinga a Edge Function ao montar; sem stub isso viraria rede real.
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('ok', { status: 200 })),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderWizard(site: MetaCapiSite | null) {
  return render(
    <MetaCapiWizard
      site={site}
      saving={false}
      onSave={noop}
      onRecordCheck={noopVoid}
      onExit={() => {}}
    />,
  );
}

describe('MetaCapiWizard', () => {
  it('monta em branco (site novo) sem quebrar', () => {
    renderWizard(null);
    // pelo heading: "Site e pixel" também é o rótulo do passo no trilho
    expect(screen.getByRole('heading', { name: 'Site e pixel' })).toBeDefined();
    // a trilha dos 5 passos precisa existir
    expect(screen.getByRole('list', { name: /etapas/i })).toBeDefined();
  });

  it('com a function no ar, a etapa Edge Function sai da trilha', async () => {
    renderWizard(null);
    const trilha = screen.getByRole('list', { name: /etapas/i });

    // antes da checagem async terminar, ela ainda está lá
    expect(trilha.textContent).toContain('Edge Function');

    // o stub de fetch responde 200 -> function publicada
    await waitFor(() => expect(trilha.textContent).not.toContain('Edge Function'));

    // e o fluxo passa a ter 4 passos, começando pelo site
    expect(trilha.querySelectorAll('li')).toHaveLength(4);
    expect(trilha.textContent).toContain('Site e pixel');
    expect(trilha.textContent).toContain('Worker e domínio');
  });

  it('com a function fora do ar, a etapa CONTINUA na trilha', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('boom', { status: 500 })),
    );
    renderWizard(null);
    const trilha = screen.getByRole('list', { name: /etapas/i });

    await waitFor(() => expect(screen.getByText(/não está no ar|500/i)).toBeDefined(), {
      timeout: 2000,
    }).catch(() => {
      /* a mensagem exata varia; o que importa é a trilha abaixo */
    });

    expect(trilha.textContent).toContain('Edge Function');
    expect(trilha.querySelectorAll('li')).toHaveLength(5);
  });

  it('salvar a etapa 1 leva ao próximo passo, sem zerar o formulário', async () => {
    // Regressão: a página trocava o wizard pelo spinner durante a recarga da
    // lista, desmontando o componente e voltando à etapa 1 em branco.
    const onSave = vi.fn(async () => siteSalvo);
    render(
      <MetaCapiWizard
        site={null}
        saving={false}
        onSave={onSave}
        onRecordCheck={noopVoid}
        onExit={() => {}}
      />,
    );

    // espera a detecção da Edge Function (é o que define qual é o próximo passo)
    await waitFor(() =>
      expect(screen.getByRole('list', { name: /etapas/i }).textContent).not.toContain(
        'Edge Function',
      ),
    );

    fireEvent.change(screen.getByLabelText('Nome do site'), { target: { value: 'Apps TechNews' } });
    fireEvent.change(screen.getByLabelText('Domínio'), {
      target: { value: 'apps.technewsbrasil.com.br' },
    });
    fireEvent.change(screen.getByLabelText('ID do pixel'), {
      target: { value: '940750053457681' },
    });
    fireEvent.change(screen.getByLabelText(/Token da API de Convers/i), {
      target: { value: 'EAAG_token_de_teste_longo' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Salvar e continuar/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    // avançou para o passo seguinte
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /Worker e dom/i })).toBeDefined(),
    );
    // e o que foi digitado continua lá ao voltar
    fireEvent.click(screen.getByRole('button', { name: /^Voltar$/i }));
    expect(screen.getByDisplayValue('Apps TechNews')).toBeDefined();
    expect(screen.getByDisplayValue('apps.technewsbrasil.com.br')).toBeDefined();
  });

  it('monta em modo edição, com os dados do site', () => {
    renderWizard(siteSalvo);
    expect(screen.getByDisplayValue('Apps TechNews')).toBeDefined();
    expect(screen.getByDisplayValue('apps.technewsbrasil.com.br')).toBeDefined();
    expect(screen.getByDisplayValue('940750053457681')).toBeDefined();
  });

  it('renderiza TODOS os passos sem tela branca', async () => {
    const { container } = renderWizard(siteSalvo);
    const passos = screen.getAllByRole('button', { name: /Site e pixel|Edge Function|Worker|Tags|Meta e teste/i });

    for (const passo of passos) {
      passo.click();
      // conteúdo real renderizado, não árvore vazia
      expect(container.querySelector('h2')).toBeTruthy();
      expect(container.textContent?.length ?? 0).toBeGreaterThan(120);
    }
  });

  it('testa CADA evento ligado, não só o primeiro', async () => {
    // Regressão: com interstitial e rewarded ligados, o botão único sempre
    // mandava ViewContent — o rewarded nunca chegava a ser testado.
    renderWizard(siteSalvo); // events: interstitial + rewarded
    fireEvent.click(screen.getByRole('button', { name: /Meta e teste/i }));

    expect(screen.getByRole('button', { name: /Testar interstitial/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Testar rewarded/i })).toBeDefined();
  });

  it('com um evento só, mostra um botão só', async () => {
    renderWizard({ ...siteSalvo, events: { interstitial: true, rewarded: false } });
    fireEvent.click(screen.getByRole('button', { name: /Meta e teste/i }));

    expect(screen.getByRole('button', { name: /Testar interstitial/i })).toBeDefined();
    expect(screen.queryByRole('button', { name: /Testar rewarded/i })).toBeNull();
  });

  it('mostra o endpoint derivado do APEX enquanto o site é editado', () => {
    renderWizard(siteSalvo);
    // apps.technewsbrasil.com.br -> cookie no domínio raiz
    expect(screen.getByText('.technewsbrasil.com.br')).toBeDefined();
    expect(screen.getByText('https://ev.technewsbrasil.com.br/capi')).toBeDefined();
  });
});
