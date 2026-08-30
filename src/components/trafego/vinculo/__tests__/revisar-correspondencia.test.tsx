// @vitest-environment jsdom
/**
 * A superfície que faltava, e as três formas de ela mentir.
 *
 * O write-path de vínculo existia desde 26/08/2026 e `trafego_vinculo` seguia
 * com zero linhas, porque nenhuma tela chegava até ele. Ao construir a tela, as
 * maneiras de errar são conhecidas e caras:
 *
 *  1. apresentar correspondência provável como vínculo (contamina receita);
 *  2. transformar falha de leitura em "não associada" (o operador trata como
 *     órfã uma campanha que só não pôde ser comparada);
 *  3. desenhar "sem vínculo" como defeito (ensina que o sistema está quebrado
 *     quando ele está esperando uma decisão humana).
 *
 * Cada uma tem prova aqui.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RevisarCorrespondencia } from '@/components/trafego/vinculo/RevisarCorrespondencia';
import type { RevisaoDeCorrespondencia } from '@/types/trafego';

const api = vi.hoisted(() => ({
  correspondenciasDaCampanha: vi.fn(),
  confirmarVinculo: vi.fn(),
  desfazerVinculo: vi.fn(),
}));

vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));

const ID = 'gads-8017851692-24155134757';
/**
 * ⚠️ A forma NORMALIZADA, que é a que a API emite.
 *
 * `destino_comparavel` remove esquema, `www.`, query e barra final. A fixture
 * anterior usava a URL crua e afirmava ser "medida" — os dois campos que o
 * operador compara com o olho nunca tinham sido renderizados na forma real.
 */
const URL_MAQ = 'creditoup.com.br/r/maquininha-de-cartao-menor-taxa';

/** Os dados MEDIDOS em 27/08/2026 — não uma invenção plausível. */
const correspondenciaUnica: RevisaoDeCorrespondencia = {
  volc_campaign_id: ID,
  estado: 'correspondencia_unica',
  url_da_campanha: URL_MAQ,
  correspondencias: [
    {
      opportunity_id: 74,
      run_id: 7,
      project_id: 2,
      destinos: [URL_MAQ],
      sinais: [
        {
          regra: 'url_final_da_conta',
          forca: 'historica',
          evidencia: { url: URL_MAQ, lida_de: 'anuncio' },
        },
      ],
      estado_do_funil: 'correspondencia_provavel',
      outras_campanhas_presentes: 0,
      forca_maxima: 'historica',
    },
  ],
  sinais_ausentes: [],
  vinculo: null,
  exige_confirmacao_humana: true,
};

function montar(props: Partial<React.ComponentProps<typeof RevisarCorrespondencia>> = {}) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={cliente}>
      <RevisarCorrespondencia
        volcCampaignId={ID}
        nomeDaCampanha="BR - 20260819_131546 / Maquininha de Cartão"
        contaExterna="8017851692"
        idExterno="24155134757"
        estadoExterno="ENABLED"
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.correspondenciasDaCampanha.mockReset();
  api.confirmarVinculo.mockReset();
  api.desfazerVinculo.mockReset();
});
afterEach(cleanup);

describe('sugerir não é vincular', () => {
  it('não pré-seleciona a única candidata, e sem escolha não dá para confirmar', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(correspondenciaUnica);
    montar();

    await screen.findByText('funil 74', { exact: false });

    const confirmar = screen.getByRole('button', { name: /Confirmar associação/ });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);
    // E a tela DIZ por que está desabilitado, em vez de só ficar cinza.
    expect(screen.getByText(/a escolha é a decisão/)).toBeTruthy();
  });

  it('confirmar leva a regra derivada dos sinais, e nunca uma frase digitada', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(correspondenciaUnica);
    api.confirmarVinculo.mockResolvedValue({ vinculo: {} });
    montar();

    fireEvent.click(await screen.findByRole('button', { name: /funil 74/ }));
    fireEvent.click(screen.getByRole('button', { name: /Confirmar associação/ }));

    await waitFor(() => expect(api.confirmarVinculo).toHaveBeenCalledTimes(1));
    const pedido = api.confirmarVinculo.mock.calls[0][0];

    expect(pedido.volc_campaign_id).toBe(ID);
    expect(pedido.opportunity_id).toBe(74);
    expect(pedido.funnel_run_id).toBe(7);
    // A regra descreve o que de fato casou. O servidor recusa vínculo sem
    // regra, e uma regra genérica seria uma caixa-preta com nome bonito.
    expect(pedido.regra).toContain('url_final_da_conta');
    expect(pedido.regra).toContain('historica');
    // A evidência viaja inteira: é ela que permite reconstruir a decisão meses
    // depois sem depender da memória de ninguém.
    expect(pedido.evidencia.sinais).toHaveLength(1);
    expect(pedido.evidencia.destinos).toEqual([URL_MAQ]);
  });

  it('não manda quem confirmou — isso sai do token, no servidor', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(correspondenciaUnica);
    api.confirmarVinculo.mockResolvedValue({ vinculo: {} });
    montar();

    fireEvent.click(await screen.findByRole('button', { name: /funil 74/ }));
    fireEvent.click(screen.getByRole('button', { name: /Confirmar associação/ }));

    await waitFor(() => expect(api.confirmarVinculo).toHaveBeenCalled());
    const pedido = api.confirmarVinculo.mock.calls[0][0];
    expect(pedido).not.toHaveProperty('confirmado_por');
    expect(JSON.stringify(pedido)).not.toContain('@');
  });
});

describe('duas versões do mesmo funil são dois candidatos', () => {
  /**
   * ⚠️ O bug que esta prova fixa, achado em 27/08/2026 por revisão adversarial.
   *
   * A escolha era guardada por `opportunity_id`. Uma oportunidade pode ter mais
   * de um run — é o caso NORMAL quando o funil é reprocessado —, e os dois
   * chegam como candidatos separados, com destinos diferentes.
   *
   * Com a chave curta, clicar no segundo marcava os DOIS cartões e o pedido
   * saía com o run do PRIMEIRO. O vínculo ia para a versão errada do funil, em
   * silêncio, numa linha imutável que contamina atribuição de receita.
   *
   * `reconciliacao.chave_do_funil` já documentava exatamente esta armadilha do
   * lado do servidor.
   */
  const duasVersoes: RevisaoDeCorrespondencia = {
    ...correspondenciaUnica,
    estado: 'mais_de_uma_correspondencia',
    correspondencias: [
      { ...correspondenciaUnica.correspondencias[0], run_id: 7 },
      {
        ...correspondenciaUnica.correspondencias[0],
        run_id: 12,
        destinos: ['creditoup.com.br/r/maquininha-v2'],
      },
    ],
  };

  it('clicar na segunda versão marca só ela', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(duasVersoes);
    montar();

    const cartoes = await screen.findAllByRole('button', { name: /funil 74/ });
    expect(cartoes).toHaveLength(2);
    fireEvent.click(cartoes[1]);

    const marcados = cartoes.filter((b) => b.getAttribute('aria-pressed') === 'true');
    expect(marcados).toHaveLength(1);
    expect(marcados[0]).toBe(cartoes[1]);
  });

  it('confirma a versão que foi clicada, e não a primeira da lista', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(duasVersoes);
    api.confirmarVinculo.mockResolvedValue({ vinculo: {} });
    montar();

    const cartoes = await screen.findAllByRole('button', { name: /funil 74/ });
    fireEvent.click(cartoes[1]);
    fireEvent.click(screen.getByRole('button', { name: /Confirmar associação/ }));

    await waitFor(() => expect(api.confirmarVinculo).toHaveBeenCalledTimes(1));
    const pedido = api.confirmarVinculo.mock.calls[0][0];
    expect(pedido.funnel_run_id).toBe(12);
    // E a evidência gravada é a da versão escolhida, não a da outra.
    expect(pedido.evidencia.destinos).toEqual(['creditoup.com.br/r/maquininha-v2']);
  });
});

describe('confirmar acontece uma vez', () => {
  /**
   * ⚠️ Segundo bug achado por revisão adversarial em 27/08/2026.
   *
   * Depois do sucesso o botão continuava clicável, e um segundo clique
   * disparava um SEGUNDO pedido. O servidor recusa o duplicado com 409 pela
   * unicidade — a linha não duplica —, mas a tela passava a mostrar um erro
   * logo depois de um sucesso, e o operador não tem como saber qual das duas
   * respostas vale sobre uma decisão que não pode ser corrigida.
   */
  it('um segundo clique depois do sucesso não dispara outro pedido', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(correspondenciaUnica);
    api.confirmarVinculo.mockResolvedValue({ vinculo: {} });
    montar();

    fireEvent.click(await screen.findByRole('button', { name: /funil 74/ }));
    const botao = screen.getByRole('button', { name: /Confirmar associação/ });
    fireEvent.click(botao);

    await waitFor(() => expect(api.confirmarVinculo).toHaveBeenCalledTimes(1));
    await screen.findByText('Associação registrada.');

    fireEvent.click(botao);
    fireEvent.click(botao);
    expect(api.confirmarVinculo).toHaveBeenCalledTimes(1);
    expect((botao as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('a força do sinal não é inflada', () => {
  it('URL da conta sem carimbo é dita "observado, sem data" — nunca "forte"', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(correspondenciaUnica);
    montar();

    await screen.findByText('funil 74', { exact: false });
    expect(screen.getAllByText(/observado, sem data/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/observado agora/)).toBeNull();
    // A ressalva é explicada, e não escondida atrás de uma palavra.
    expect(
      screen.getAllByText(/não guarda quando ela foi lida/).length,
    ).toBeGreaterThan(0);
  });

  it('disputa pelo mesmo funil aparece antes de o operador confirmar', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue({
      ...correspondenciaUnica,
      correspondencias: [
        {
          ...correspondenciaUnica.correspondencias[0],
          estado_do_funil: 'conflito',
          outras_campanhas_presentes: 1,
        },
      ],
    });
    montar();

    expect(await screen.findByText(/disputado por \+1/)).toBeTruthy();
  });
});

describe('as três formas de não saber', () => {
  it('falha de leitura NÃO vira "não associada"', async () => {
    api.correspondenciasDaCampanha.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 503 }),
    );
    montar();

    const alerta = await screen.findByRole('alert');
    expect(alerta.textContent).toContain('não');
    // O ponto: a tela recusa a conclusão barata.
    expect(screen.getByText(/não consegui comparar|não pôde ser feita/)).toBeTruthy();
    expect(screen.queryByText('não associada ao VOLC')).toBeNull();
    expect(screen.getByRole('button', { name: /Tentar de novo/ })).toBeTruthy();
  });

  it('"não associada" é dita como estado normal, não como defeito', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue({
      ...correspondenciaUnica,
      estado: 'sem_correspondencia',
      correspondencias: [],
      exige_confirmacao_humana: false,
    });
    montar();

    expect(await screen.findByText('não associada ao VOLC')).toBeTruthy();
    expect(screen.getByText(/Nada precisa ser feito agora/)).toBeTruthy();
    // Não existe botão de confirmar quando não há o que confirmar.
    expect(screen.queryByRole('button', { name: /Confirmar associação/ })).toBeNull();
  });

  it('"não apurada" diz o que impediu, e é diferente de não ter achado', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue({
      ...correspondenciaUnica,
      estado: 'nao_apurada',
      correspondencias: [],
      exige_confirmacao_humana: false,
      sinais_ausentes: [
        {
          regra: 'conta_da_campanha',
          motivo: 'esta campanha não tem conta de anúncio identificada',
          impede_prova: true,
        },
      ],
    });
    montar();

    expect(await screen.findByText('não foi possível apurar')).toBeTruthy();
    expect(screen.getByText(/O que impediu de comparar/)).toBeTruthy();
    expect(
      screen.getByText(/não tem conta de anúncio identificada/, { exact: false }),
    ).toBeTruthy();
  });
});

describe('já associada', () => {
  it('oferece desfazer e explica que o registro não é apagado', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue({
      ...correspondenciaUnica,
      estado: 'associada',
      correspondencias: [],
      exige_confirmacao_humana: false,
      vinculo: {
        vinculo_id: '11111111-1111-1111-1111-111111111111',
        opportunity_id: 74,
        run_id: 7,
      },
    });
    api.desfazerVinculo.mockResolvedValue({ vinculo: {} });
    montar();

    expect(await screen.findByText('associada')).toBeTruthy();
    expect(screen.getByText(/não apaga o registro/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Desfazer associação/ }));
    await waitFor(() => expect(api.desfazerVinculo).toHaveBeenCalledTimes(1));
    expect(api.desfazerVinculo.mock.calls[0][0]).toBe(
      '11111111-1111-1111-1111-111111111111',
    );
  });
});

describe('nada de vocabulário de backend na tela', () => {
  it('não expõe nome de coluna, tabela, rota nem GAQL', async () => {
    api.correspondenciasDaCampanha.mockResolvedValue(correspondenciaUnica);
    const { container } = montar();

    await screen.findByText('funil 74', { exact: false });
    const texto = container.textContent ?? '';

    for (const vazamento of [
      'volc_campaign_id',
      'opportunity_id',
      'funnel_run_id',
      'trafego_vinculo',
      'PostgREST',
      'SELECT',
      '/api/',
    ]) {
      expect(texto).not.toContain(vazamento);
    }
  });
});
