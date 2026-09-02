// @vitest-environment jsdom
/**
 * #10 · `smart_bidding_eligible` binário colapsava "não lido" em "não elegível".
 *
 *     valor={m.smart_bidding_eligible ? 'elegível' : 'não elegível'}
 *
 * Falha FECHADA — não é um falso verde —, mas emite um VEREDITO onde o servidor
 * pode não ter respondido nada. Fica fora de padrão com os sete estados de
 * `EstadoDeLeitura` que o resto do arquivo mantém, e com o próprio contrato:
 * `smart_bidding_ready` existe justamente porque "lemos e não há sinal" e "não
 * conseguimos ler" pedem coisas opostas (`types/trafego.ts`).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ContratoDeCanal, RespostaDosCanais } from '@/lib/trafego/canais';

const contratoDosCanais = vi.fn();
vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { contratoDosCanais: (...a: unknown[]) => contratoDosCanais(...a) },
  PautadorApiError: class extends Error {},
}));

const { PainelDeCanais } = await import('@/components/trafego/canais/PainelDeCanais');
const { textoDoLanceAutomatico } = await import('@/lib/trafego/canais');

/** `mensuracao` é frouxo de propósito: um dos casos provados é a CHAVE AUSENTE,
 *  que o tipo do contrato não sabe exprimir — e é exatamente o buraco. */
function canal(mensuracao: Record<string, unknown> = {}): ContratoDeCanal {
  const base: ContratoDeCanal = {
    plataforma: 'GOOGLE_ADS',
    canal: 'SEARCH',
    rotulo: 'Rede de Pesquisa',
    manifesto: {
      plataforma: 'GOOGLE_ADS', canal: 'SEARCH', rotulo: 'Rede de Pesquisa',
      hierarquia: ['campanha'], paineis: [], campos_do_pedido: [], capacidades: ['ler'],
      provas_obrigatorias: [], indisponibilidades: [], sabe_criar: true, sabe_provar: true,
    },
    portoes: [
      { nome: 'planejavel', estado: 'PERMITIDO', aberto: true, bloqueadores: [] },
      { nome: 'validavel', estado: 'PERMITIDO', aberto: true, bloqueadores: [] },
      { nome: 'criavel_pausada', estado: 'PERMITIDO', aberto: true, bloqueadores: [] },
      { nome: 'ativavel', estado: 'BLOQUEADO', aberto: false, bloqueadores: [] },
    ],
    assets: { estado: 'PERMITIDO', recursos: [], quantidade: 0, fonte: 'x', causa: null },
    mensuracao: {
      lida: true,
      conversion_goal_status: 'PRONTO',
      conversion_signal_status: 'PRONTO',
      signal_sources: ['gclid'],
      measurement_readiness: 'PRONTO',
      data_manager_status: 'PRONTO',
      observability_status: 'PRONTO',
      smart_bidding_eligible: true,
      plano: null,
      fonte: 'leitura viva da conta',
      notas: {},
    },
    observabilidade: {
      estado: 'PERMITIDO', coletor: 'varredura', causa: null,
      campanhas_no_espelho: 3, contagem_truncada: false,
    },
    operacional: {},
  };
  return {
    ...base,
    mensuracao: {
      ...base.mensuracao,
      ...mensuracao,
    } as unknown as ContratoDeCanal['mensuracao'],
  };
}

function resposta(canais: ContratoDeCanal[]): RespostaDosCanais {
  return {
    operador: {
      is_admin: true, lab_mode: false, google_read: true, google_validate_only: true,
      google_mutate: false, google_demand_gen_validate_only: false,
      porque_sem_mutacao: 'a permissão está fechada neste servidor.',
    },
    politica_canario: {},
    canais,
    fontes: { espelho_lido: true, leitura_viva_do_google: false, por_que_sem_leitura_viva: '.' },
  };
}

function montar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <PainelDeCanais />
    </QueryClientProvider>,
  );
}

beforeEach(() => contratoDosCanais.mockReset());
afterEach(cleanup);

describe('#10 · o lance automático tem três estados, não dois', () => {
  it('a tradução é pura e distingue os três', () => {
    expect(textoDoLanceAutomatico(true)).toBe('elegível');
    expect(textoDoLanceAutomatico(false)).toBe('não elegível');
    expect(textoDoLanceAutomatico(null)).toBe('não lido');
    expect(textoDoLanceAutomatico(undefined)).toBe('não lido');
  });

  it('campo ausente na resposta não vira "não elegível"', async () => {
    contratoDosCanais.mockResolvedValue(
      resposta([canal({ smart_bidding_eligible: undefined })]),
    );
    montar();
    await waitFor(() => screen.getByText('Rede de Pesquisa'));
    expect(screen.getByText('não lido')).toBeTruthy();
    expect(screen.queryByText('não elegível')).toBeNull();
  });

  it('`false` LIDO continua sendo o veredito "não elegível"', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal({ smart_bidding_eligible: false })]));
    montar();
    await waitFor(() => screen.getByText('Rede de Pesquisa'));
    expect(screen.getByText('não elegível')).toBeTruthy();
  });

  it('`true` continua sendo "elegível"', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Rede de Pesquisa'));
    expect(screen.getByText('elegível')).toBeTruthy();
  });
});
