// @vitest-environment jsdom
/**
 * As sete regras do acompanhamento, provadas.
 *
 * Polling é onde mais se erra em silêncio: a tela parece funcionar e por baixo
 * empilha consultas, apaga o último estado bom quando a rede pisca, ou continua
 * perguntando para sempre sobre um job que já terminou.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ⚠️ `@/lib/supabase` lança no import quando `VITE_SUPABASE_*` não existe, e a
// worktree isolada não tem `.env` — copiar segredo para `/private/tmp` é proibido
// pelo envelope. O dublê corta a dependência sem trazer nenhuma credencial.
vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'token-de-teste' } } }),
    },
  },
}));

import { ehTerminal } from '@/hooks/useTrabalhoDaBancada';
import type { EstadoDoTrabalho } from '@/types/parqueCriativo';

describe('estados terminais', () => {
  it('rendered, failed e cancelled encerram o acompanhamento', () => {
    for (const e of ['rendered', 'failed', 'cancelled'] as EstadoDoTrabalho[]) {
      expect(ehTerminal(e)).toBe(true);
    }
  });

  it('queued, claimed, running e validating continuam', () => {
    for (const e of ['queued', 'claimed', 'running', 'validating'] as EstadoDoTrabalho[]) {
      expect(ehTerminal(e)).toBe(false);
    }
  });

  it('estado indefinido NÃO é terminal', () => {
    // ⚠️ "Ainda não sei" não pode encerrar o acompanhamento: seria parar de
    // perguntar exatamente quando ainda não há resposta.
    expect(ehTerminal(undefined)).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// O hook, com relógio e visibilidade controlados
// ─────────────────────────────────────────────────────────────────────────────

import { cleanup, renderHook, act, waitFor } from '@testing-library/react';

import { criativosApi } from '@/lib/criativosApi';
import { useTrabalhoDaBancada } from '@/hooks/useTrabalhoDaBancada';
import type { TrabalhoDaBancada } from '@/types/parqueCriativo';

function trabalho(estado: EstadoDoTrabalho, extra: Partial<TrabalhoDaBancada> = {}) {
  return {
    id: 'job-1', estado, tentativa: 1, maxTentativas: 3, operario: 'op-1',
    leaseAte: null, batimentoEm: null, vivo: true, falha: null, recibo: null,
    retomaDe: null, retomadaN: 0, canceladoPor: null, canceladoMotivo: null,
    criadoEm: null, podeRetomar: false, podeCancelar: true,
    ...extra,
  } as TrabalhoDaBancada;
}

let visibilidade: DocumentVisibilityState = 'visible';

beforeEach(() => {
  visibilidade = 'visible';
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => visibilidade,
  });
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  // ⚠️ `vitest.config.ts` não usa `globals: true`, então o auto-cleanup do
  // Testing Library NÃO roda sozinho — os outros arquivos de teste deste módulo
  // chamam `cleanup` na mão pelo mesmo motivo. Sem isto, um hook montado num
  // teste continua pollando dentro do teste seguinte e incrementa o spy DELE:
  // a contagem de chamadas de um teste passa a depender de quem rodou antes.
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('acompanhamento', () => {
  it('para de perguntar quando o trabalho termina', async () => {
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockResolvedValueOnce(trabalho('running'))
      .mockResolvedValueOnce(trabalho('rendered'))
      .mockResolvedValue(trabalho('rendered'));

    const { result } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(result.current.trabalho?.estado).toBe('running'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });
    await waitFor(() => expect(result.current.encerrado).toBe(true));

    const chamadasAoTerminar = ler.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(ler.mock.calls.length).toBe(chamadasAoTerminar);
  });

  it('uma falha de leitura NÃO apaga o último estado bom', async () => {
    vi.spyOn(criativosApi, 'trabalhoDaBancada')
      .mockResolvedValueOnce(trabalho('running'))
      .mockRejectedValue(new Error('a rede piscou'));

    const { result } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(result.current.trabalho?.estado).toBe('running'));
    const lidoAntes = result.current.lidoEm;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    await waitFor(() => expect(result.current.leituraFalhou).toBeTruthy());

    // O estado bom sobrevive, e o carimbo de frescor NÃO avança.
    expect(result.current.trabalho?.estado).toBe('running');
    expect(result.current.lidoEm).toBe(lidoAntes);
  });

  it('não empilha consultas: uma resposta lenta não gera duas em voo', async () => {
    let liberar: ((v: TrabalhoDaBancada) => void) | null = null;
    const ler = vi.spyOn(criativosApi, 'trabalhoDaBancada').mockImplementation(
      () => new Promise((r) => { liberar = r; }),
    );

    renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));

    // O tempo passa muito, e a primeira consulta segue pendurada.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(ler).toHaveBeenCalledTimes(1);

    await act(async () => {
      liberar?.(trabalho('rendered'));
      await vi.advanceTimersByTimeAsync(0);
    });
  });

  it('aba escondida pausa, e voltar retoma imediatamente', async () => {
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockResolvedValue(trabalho('running'));

    const { result } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(result.current.trabalho?.estado).toBe('running'));

    visibilidade = 'hidden';
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(30_000);
    });
    const escondida = ler.mock.calls.length;
    await waitFor(() => expect(result.current.pausado).toBe(true));

    visibilidade = 'visible';
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });
    await waitFor(() => expect(ler.mock.calls.length).toBeGreaterThan(escondida));
    expect(result.current.pausado).toBe(false);
  });

  it('desmontar cancela o timer e não deixa consulta em voo escrever', async () => {
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockResolvedValue(trabalho('running'));

    const { unmount } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalled());
    const antes = ler.mock.calls.length;

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(ler.mock.calls.length).toBe(antes);
  });

  it('sem id não consulta nada', async () => {
    const ler = vi.spyOn(criativosApi, 'trabalhoDaBancada');
    const { result } = renderHook(() => useTrabalhoDaBancada(null));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(ler).not.toHaveBeenCalled();
    // ⚠️ Ausência não vira fila vazia: sem id, `carregando` é falso E `trabalho`
    // é nulo, e a tela precisa distinguir isso de "consultei e não achei".
    expect(result.current.carregando).toBe(false);
    expect(result.current.trabalho).toBeNull();
  });

  it('o intervalo cresce em vez de martelar o servidor', async () => {
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockResolvedValue(trabalho('running'));

    renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    // Com intervalo fixo de 1s seriam ~10 chamadas; com backoff, bem menos.
    expect(ler.mock.calls.length).toBeLessThan(8);
    expect(ler.mock.calls.length).toBeGreaterThan(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Achado #15 — resposta antiga não pode contaminar o trabalho novo
//
// O caminho real é a RETOMADA: `Producao.tsx` faz `setTrabalhoId(novo.id)` no
// `onSuccess` de `retomarNaBancada`. A consulta do trabalho velho continua em
// voo, e a única coisa que a separava da tela nova era a ref `vivo` — que o
// efeito seguinte devolve para `true`. Sem geração, a resposta de A escreve na
// tela de B: peça de A, estado de A, e `terminou` de A parando o polling de B.
// ─────────────────────────────────────────────────────────────────────────────

/** Promessa que este teste resolve na hora que quiser. Zero relógio real. */
function adiavel<T>() {
  let resolver!: (v: T) => void;
  let rejeitar!: (e: unknown) => void;
  const promessa = new Promise<T>((res, rej) => {
    resolver = res;
    rejeitar = rej;
  });
  // A promessa só é observada depois; sem catch aqui o Node reclamaria antes.
  promessa.catch(() => undefined);
  return { promessa, resolver, rejeitar };
}

describe('troca de trabalho em voo (achado #15)', () => {
  it('a resposta de A, chegando atrasada, não preenche a tela de B', async () => {
    const a = adiavel<TrabalhoDaBancada>();
    const b = adiavel<TrabalhoDaBancada>();
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockImplementation((id: string) => (id === 'job-A' ? a.promessa : b.promessa));

    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useTrabalhoDaBancada(id),
      { initialProps: { id: 'job-A' as string | null } },
    );
    await waitFor(() => expect(ler).toHaveBeenCalledWith('job-A'));

    // A troca acontece com A ainda pendurada — exatamente o que a retomada faz.
    rerender({ id: 'job-B' });

    // B PRECISA ser consultado. Com a trava `emVoo` compartilhada, esta é a
    // asserção que fica vermelha: B nunca chega a ser perguntado.
    await waitFor(() => expect(ler).toHaveBeenCalledWith('job-B'));

    // Agora A responde tarde, terminal, com peça própria.
    await act(async () => {
      a.resolver(trabalho('rendered', { id: 'job-A' }));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.trabalho?.id).not.toBe('job-A');
    expect(result.current.trabalho).toBeNull();
    // O terminal de A não pode encerrar o acompanhamento de B.
    expect(result.current.encerrado).toBe(false);

    await act(async () => {
      b.resolver(trabalho('running', { id: 'job-B' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.trabalho?.id).toBe('job-B');
    expect(result.current.trabalho?.estado).toBe('running');
  });

  it('nenhum render intermediário mostra a peça de A sob o id de B', async () => {
    // ⚠️ Zerar no efeito não bastava: o efeito roda DEPOIS do commit, então o
    // primeiro render com o id novo devolvia a peça anterior. Medido antes da
    // correção, a sequência de ids renderizados após a troca era ["job-A", null]
    // — um frame inteiro com a peça de A rotulada como B, que é o sintoma do
    // achado #15 sem depender de nenhuma resposta atrasada.
    vi.spyOn(criativosApi, 'trabalhoDaBancada').mockImplementation(async (id: string) =>
      trabalho(id === 'job-A' ? 'rendered' : 'running', { id }),
    );
    const vistos: Array<string | null | undefined> = [];
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => {
        const leitura = useTrabalhoDaBancada(id);
        vistos.push(leitura.trabalho?.id ?? null);
        return leitura;
      },
      { initialProps: { id: 'job-A' as string | null } },
    );
    await waitFor(() => expect(result.current.trabalho?.id).toBe('job-A'));

    vistos.length = 0;
    rerender({ id: 'job-B' });
    expect(vistos).not.toContain('job-A');
    // E o estado honesto enquanto B não respondeu é "ainda não sei".
    expect(result.current.carregando).toBe(true);
    expect(result.current.encerrado).toBe(false);
  });

  it('a falha de A, chegando atrasada, não marca erro em B', async () => {
    const a = adiavel<TrabalhoDaBancada>();
    const b = adiavel<TrabalhoDaBancada>();
    vi.spyOn(criativosApi, 'trabalhoDaBancada').mockImplementation((id: string) =>
      id === 'job-A' ? a.promessa : b.promessa,
    );

    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useTrabalhoDaBancada(id),
      { initialProps: { id: 'job-A' as string | null } },
    );
    await waitFor(() => expect(result.current.carregando).toBe(true));
    rerender({ id: 'job-B' });

    await act(async () => {
      a.rejeitar(new Error('a rede de A piscou'));
      await vi.advanceTimersByTimeAsync(0);
    });
    // O erro pertence a A. B ainda está carregando e não tem falha nenhuma.
    expect(result.current.leituraFalhou).toBeNull();

    await act(async () => {
      b.resolver(trabalho('running', { id: 'job-B' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.leituraFalhou).toBeNull();
    expect(result.current.trabalho?.id).toBe('job-B');
  });

  it('troca rápida A → B → C: só C vence', async () => {
    const a = adiavel<TrabalhoDaBancada>();
    const b = adiavel<TrabalhoDaBancada>();
    const c = adiavel<TrabalhoDaBancada>();
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockImplementation((id: string) =>
        id === 'job-A' ? a.promessa : id === 'job-B' ? b.promessa : c.promessa,
      );

    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useTrabalhoDaBancada(id),
      { initialProps: { id: 'job-A' as string | null } },
    );
    await waitFor(() => expect(ler).toHaveBeenCalledWith('job-A'));
    rerender({ id: 'job-B' });
    rerender({ id: 'job-C' });
    await waitFor(() => expect(ler).toHaveBeenCalledWith('job-C'));

    // As duas antigas respondem depois, e em ordem trocada.
    await act(async () => {
      b.resolver(trabalho('failed', { id: 'job-B' }));
      a.resolver(trabalho('rendered', { id: 'job-A' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.trabalho).toBeNull();
    expect(result.current.encerrado).toBe(false);
    expect(result.current.leituraFalhou).toBeNull();

    await act(async () => {
      c.resolver(trabalho('running', { id: 'job-C' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.trabalho?.id).toBe('job-C');
  });

  it('desmontar com consulta em voo: a resposta tardia não escreve nada', async () => {
    const a = adiavel<TrabalhoDaBancada>();
    vi.spyOn(criativosApi, 'trabalhoDaBancada').mockReturnValue(a.promessa);

    const { unmount } = renderHook(() => useTrabalhoDaBancada('job-A'));
    await waitFor(() => expect(criativosApi.trabalhoDaBancada).toHaveBeenCalled());
    unmount();

    const avisos = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await act(async () => {
      a.resolver(trabalho('rendered', { id: 'job-A' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(avisos).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Achado #16 — `recarregar()` em voo não pode virar no-op
//
// O caminho real é o CANCELAMENTO: `Producao.tsx` chama `recarregar()` no
// `onSuccess` de `cancelarNaBancada`. Se havia uma consulta em voo — iniciada
// ANTES do cancelamento —, o pedido de releitura era descartado e a tela ficava
// mostrando "running" até o próximo backoff, com o backend já em "cancelled".
// ─────────────────────────────────────────────────────────────────────────────

describe('refresh durante consulta em voo (achado #16)', () => {
  it('o refresh pedido durante a consulta é executado assim que ela responde', async () => {
    const primeira = adiavel<TrabalhoDaBancada>();
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockImplementationOnce(() => primeira.promessa)
      .mockResolvedValue(trabalho('cancelled', { id: 'job-1' }));

    const { result } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));

    // O operador cancelou; o servidor confirmou; a tela pede releitura.
    act(() => result.current.recarregar());

    // A consulta velha (anterior ao cancelamento) responde "running".
    await act(async () => {
      primeira.resolver(trabalho('running', { id: 'job-1' }));
      await vi.advanceTimersByTimeAsync(0);
    });

    // A releitura tem de sair AGORA, sem esperar backoff.
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.trabalho?.estado).toBe('cancelled'));
  });

  it('três refreshes seguidos coalescem em uma releitura, não três', async () => {
    const primeira = adiavel<TrabalhoDaBancada>();
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockImplementationOnce(() => primeira.promessa)
      .mockResolvedValue(trabalho('cancelled', { id: 'job-1' }));

    const { result } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.recarregar();
      result.current.recarregar();
      result.current.recarregar();
    });

    await act(async () => {
      primeira.resolver(trabalho('running', { id: 'job-1' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    await waitFor(() => expect(result.current.trabalho?.estado).toBe('cancelled'));
    // Uma releitura, não uma por clique: coalescência.
    expect(ler).toHaveBeenCalledTimes(2);
  });

  it('a falha da consulta em voo não engole o refresh pendente', async () => {
    const primeira = adiavel<TrabalhoDaBancada>();
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockImplementationOnce(() => primeira.promessa)
      .mockResolvedValue(trabalho('cancelled', { id: 'job-1' }));

    const { result } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));

    act(() => result.current.recarregar());
    await act(async () => {
      primeira.rejeitar(new Error('a rede piscou'));
      await vi.advanceTimersByTimeAsync(0);
    });

    await waitFor(() => expect(ler).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.trabalho?.estado).toBe('cancelled'));
    // A releitura boa limpa a falha anterior.
    expect(result.current.leituraFalhou).toBeNull();
  });

  it('voltar para a aba durante uma consulta em voo também relê', async () => {
    const primeira = adiavel<TrabalhoDaBancada>();
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockImplementationOnce(() => primeira.promessa)
      .mockResolvedValue(trabalho('rendered', { id: 'job-1' }));

    renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));

    visibilidade = 'hidden';
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    visibilidade = 'visible';
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await act(async () => {
      primeira.resolver(trabalho('running', { id: 'job-1' }));
      await vi.advanceTimersByTimeAsync(0);
    });
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(2));
  });

  it('um trabalho terminal não volta a pollar por causa de refresh pendente', async () => {
    const primeira = adiavel<TrabalhoDaBancada>();
    const ler = vi
      .spyOn(criativosApi, 'trabalhoDaBancada')
      .mockImplementationOnce(() => primeira.promessa)
      .mockResolvedValue(trabalho('rendered', { id: 'job-1' }));

    const { result } = renderHook(() => useTrabalhoDaBancada('job-1'));
    await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));

    act(() => result.current.recarregar());
    await act(async () => {
      primeira.resolver(trabalho('rendered', { id: 'job-1' }));
      await vi.advanceTimersByTimeAsync(0);
    });

    // O refresh pendente é honrado UMA vez (o operador pediu), e aí para.
    await waitFor(() => expect(result.current.encerrado).toBe(true));
    const aoTerminar = ler.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(ler.mock.calls.length).toBe(aoTerminar);
    expect(aoTerminar).toBeLessThanOrEqual(2);
  });
});
