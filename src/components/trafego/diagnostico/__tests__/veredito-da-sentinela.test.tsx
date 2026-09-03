// @vitest-environment jsdom
/**
 * As contraprovas de tela da sentinela.
 *
 * A regra que todas defendem: **nada aqui pode ser lido como boa notícia sem
 * prova completa.** O incidente que originou esta lane chegou ao operador como
 * "Não foi possível apurar — parou em conta", porque o backend nunca preenchia
 * o degrau `conta` e o veredito era derivado no cliente sobre essa escada.
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import {
  VereditoDaSentinela,
  haQuantoTempo,
} from '@/components/trafego/diagnostico/VereditoDaSentinela';
import {
  fraseDasRecomendacoes,
  leituraDoStatus,
  podeSerLidoComoBom,
  tomDoVeredito,
} from '@/lib/diagnostico/sentinela';
import type {
  CausaDaSentinela,
  VeredictoDaSentinela as Veredito,
} from '@/types/diagnostico';

afterEach(cleanup);

const AGORA = Date.parse('2026-09-03T12:00:00Z');
const LIDO_EM = '2026-09-03T11:00:00Z';

function causa(over: Partial<CausaDaSentinela> = {}): CausaDaSentinela {
  return {
    status: 'ACCOUNT_BLOCKED',
    escopo: 'account',
    severidade: 'critica',
    frase: 'A conta de anúncio está SUSPENDED.',
    evidencias: [
      {
        rotulo: 'estado da conta',
        campo: 'customer.status',
        valor: 'SUSPENDED',
        observado_em: LIDO_EM,
        origem: 'conta',
      },
    ],
    motivo_da_conta: [],
    denominador: null,
    proximo_ato: 'tratar a conta no painel do Google',
    ...over,
  };
}

function veredito(over: Partial<Veredito> = {}): Veredito {
  return {
    versao: 1,
    customer_id: '9990001111',
    volc_campaign_id: 'cmp.search:prova',
    escopo: 'account',
    status: 'ACCOUNT_BLOCKED',
    severidade: 'critica',
    incidente: true,
    observado_em: LIDO_EM,
    janela_inicio: '2026-08-27',
    janela_fim: '2026-09-03',
    janela_do_guardiao: 'apos_72h',
    frescor: 'recente',
    estado_da_evidencia: 'parcial',
    causa_primaria: causa(),
    causas_secundarias: [],
    desconhecidos: [],
    recomendacoes: {
      estado_da_coleta: 'vazio_confirmado',
      apurado: true,
      itens: [],
      quantidade: 0,
      impedimento: null,
    },
    proximo_ato: 'tratar a conta no painel do Google antes de qualquer ajuste',
    chave: 'abc123',
    mutacao_externa: false,
    ...over,
  };
}

describe('o veredito responde as oito perguntas do incidente', () => {
  it('diz o que aconteceu, em que nível e com que evidência', () => {
    render(<VereditoDaSentinela veredito={veredito()} agora={AGORA} />);

    expect(screen.getByRole('heading', { name: /conta de anúncio bloqueada/i }))
      .toBeTruthy();
    expect(screen.getByText(/no nível da/i).textContent).toContain('conta de anúncio');
    expect(screen.getByText('SUSPENDED')).toBeTruthy();
    expect(screen.getByText(/customer\.status|estado da conta/i)).toBeTruthy();
  });

  it('diz há quanto tempo, e o frescor da prova', () => {
    render(<VereditoDaSentinela veredito={veredito()} agora={AGORA} />);
    expect(screen.getByText(/lido há 60 minutos/i)).toBeTruthy();
    expect(screen.getByText(/leitura recente/i)).toBeTruthy();
  });

  it('diz o próximo ato', () => {
    render(<VereditoDaSentinela veredito={veredito()} agora={AGORA} />);
    expect(screen.getByText(/próximo ato/i)).toBeTruthy();
    expect(
      screen.getByText(/tratar a conta no painel do Google antes de qualquer ajuste/i),
    ).toBeTruthy();
  });

  it('mostra a causa secundária COM denominador, sem promovê-la a veredito', () => {
    render(
      <VereditoDaSentinela
        agora={AGORA}
        veredito={veredito({
          causas_secundarias: [
            causa({
              status: 'LIMITED_BY_RANK',
              escopo: 'keyword',
              severidade: 'media',
              frase: '2 de 2 keywords com lance abaixo da estimativa',
              denominador: {
                rotulo: 'com lance abaixo da estimativa de primeira página',
                quantos: 2,
                de_quantos: 2,
                fora_da_conta: 1,
                unidade: 'keywords',
                proporcao: null,
                frase:
                  '2 de 2 keywords com lance abaixo da estimativa de primeira ' +
                  'página; 1 sem dado suficiente, fora desta conta',
              },
            }),
          ],
        })}
      />,
    );

    // o título principal continua sendo o da conta
    expect(screen.getByRole('heading', { name: /conta de anúncio bloqueada/i }))
      .toBeTruthy();

    const secundarias = screen.getByRole('list', { name: /causas secundárias/i });
    expect(within(secundarias).getByText(/limitada por classificação/i)).toBeTruthy();
    // ⚠️ O denominador viaja com o número. Percentual sem denominador é proibido.
    // ⚠️ `getAllBy`: a frase da causa E a linha do denominador dizem o mesmo
    // número, de propósito — a frase explica, o denominador prova.
    expect(within(secundarias).getAllByText(/2 de 2 keywords/i).length)
      .toBeGreaterThanOrEqual(1);
    expect(within(secundarias).getByText(/fora desta conta/i)).toBeTruthy();
  });

  it('mostra o que permanece desconhecido, em vez de escondê-lo', () => {
    render(
      <VereditoDaSentinela
        agora={AGORA}
        veredito={veredito({
          desconhecidos: [
            'recibo de destino pago: não consultado por esta leitura',
            'recomendações do Google: coleta em falhou',
          ],
        })}
      />,
    );
    const lista = screen.getByRole('list', { name: /desconhecidos/i });
    expect(within(lista).getAllByRole('listitem')).toHaveLength(2);
    expect(within(lista).getByText(/não consultado por esta leitura/i)).toBeTruthy();
  });

  it('declara na tela que nenhuma alteração foi aplicada', () => {
    render(<VereditoDaSentinela veredito={veredito()} agora={AGORA} />);
    const declaracao = screen.getByTestId('declaracao-de-nao-mutacao');
    expect(declaracao.textContent).toContain('Nenhuma alteração foi aplicada');
    expect(declaracao.textContent).toContain('não muda lance, verba, anúncio nem keyword');
  });
});

describe('nenhum verde sem prova', () => {
  it('HEALTHY com prova completa é a ÚNICA leitura boa', () => {
    const bom = veredito({
      status: 'HEALTHY',
      severidade: 'informativa',
      incidente: false,
      estado_da_evidencia: 'apurada',
      causa_primaria: null,
    });
    expect(podeSerLidoComoBom(bom)).toBe(true);
    expect(tomDoVeredito(bom)).toBe('bom');
  });

  it('HEALTHY com prova parcial NÃO é verde, e a ressalva é texto', () => {
    const duvidoso = veredito({
      status: 'HEALTHY',
      severidade: 'informativa',
      incidente: false,
      estado_da_evidencia: 'parcial',
      causa_primaria: null,
    });
    expect(podeSerLidoComoBom(duvidoso)).toBe(false);
    expect(tomDoVeredito(duvidoso)).not.toBe('bom');

    render(<VereditoDaSentinela veredito={duvidoso} agora={AGORA} />);
    expect(screen.getByRole('status').textContent).toContain(
      'Isto não é o mesmo que "está tudo bem"',
    );
    // O selo diz "prova parcial" e a ressalva em texto repete a palavra: a
    // regra do projeto é glifo + palavra + descrição, e a descrição não pode
    // viver só num `title`.
    expect(screen.getAllByText(/prova parcial/i).length).toBeGreaterThanOrEqual(2);
  });

  it('status desconhecido nunca degrada para bom', () => {
    const futuro = veredito({
      status: 'ALGUM_ESTADO_DE_2031',
      estado_da_evidencia: 'apurada',
    });
    expect(leituraDoStatus('ALGUM_ESTADO_DE_2031').tom).toBe('atencao');
    expect(leituraDoStatus('ALGUM_ESTADO_DE_2031').pedeAlguem).toBe(true);
    expect(podeSerLidoComoBom(futuro)).toBe(false);
    expect(tomDoVeredito(futuro)).toBe('atencao');

    render(<VereditoDaSentinela veredito={futuro} agora={AGORA} />);
    expect(screen.getByRole('heading', { name: /estado não reconhecido/i }))
      .toBeTruthy();
    expect(screen.getAllByText(/não afirma que a campanha esteja bem/i).length)
      .toBeGreaterThanOrEqual(1);
  });

  it('CAMPAIGN_OFF não é alarme e não é verde', () => {
    const off = veredito({
      status: 'CAMPAIGN_OFF',
      severidade: 'informativa',
      incidente: false,
      escopo: 'campaign',
      causa_primaria: causa({
        status: 'CAMPAIGN_OFF',
        escopo: 'campaign',
        severidade: 'informativa',
        frase: 'A campanha está PAUSED.',
        evidencias: [],
      }),
    });
    expect(tomDoVeredito(off)).toBe('neutro');
    expect(leituraDoStatus('CAMPAIGN_OFF').pedeAlguem).toBe(false);
    render(<VereditoDaSentinela veredito={off} agora={AGORA} />);
    expect(screen.getByRole('heading', { name: /campanha desligada/i })).toBeTruthy();
  });
});

describe('recomendações: coletar não é concordar, e falha não é zero', () => {
  it('coleta falhada NÃO é lida como zero recomendações', () => {
    const frase = fraseDasRecomendacoes({
      estado_da_coleta: 'falhou',
      apurado: false,
      itens: null,
      quantidade: null,
      impedimento: 'a chamada não retornou',
    });
    expect(frase).toMatch(/não foi possível apurar/i);
    expect(frase).toMatch(/NÃO significa que não haja nenhuma/i);
    expect(frase).not.toMatch(/^0 /);
  });

  it('vazio confirmado é dito como vazio confirmado', () => {
    expect(
      fraseDasRecomendacoes({
        estado_da_coleta: 'vazio_confirmado',
        apurado: true,
        itens: [],
        quantidade: 0,
        impedimento: null,
      }),
    ).toMatch(/não sugeriu nada/i);
  });

  it('a recomendação aparece adjudicada e marcada como não aplicada', () => {
    render(
      <VereditoDaSentinela
        agora={AGORA}
        veredito={veredito({
          recomendacoes: {
            estado_da_coleta: 'com_dados',
            apurado: true,
            quantidade: 1,
            impedimento: null,
            itens: [
              {
                tipo: 'KEYWORD',
                alvo: 'customers/999/recommendations/x',
                impacto_informado: '+12 cliques/semana (informado pelo Google)',
                observado_em: LIDO_EM,
                frescor: 'recente',
                evidencia: [],
                adjudicacao: 'nova',
                confianca: 'baixa',
                proximo_ato: 'revisar antes de qualquer ato',
                aplicada: false,
              },
            ],
          },
        })}
      />,
    );
    const lista = screen.getByRole('list', { name: /recomendações/i });
    expect(within(lista).getByText('KEYWORD')).toBeTruthy();
    expect(within(lista).getByText('nova')).toBeTruthy();
    expect(within(lista).getByText(/informado pelo Google/i)).toBeTruthy();
    expect(screen.getByText(/1 recomendação registrada, nenhuma aplicada/i))
      .toBeTruthy();
  });
});

describe('a janela do guardião', () => {
  it('idade desconhecida NÃO é lida como recém-criada', () => {
    render(
      <VereditoDaSentinela
        agora={AGORA}
        veredito={veredito({
          status: 'OBSERVING',
          janela_do_guardiao: 'indeterminada',
          incidente: false,
          severidade: 'informativa',
          causa_primaria: null,
        })}
      />,
    );
    const chip = screen.getByTitle(/não sabemos desde quando está ligada/i);
    expect(chip.textContent).toContain('idade desconhecida');
  });

  it('nomeia as quatro fases da vida da campanha', () => {
    for (const [janela, esperado] of [
      ['nascimento', /nascendo/i],
      ['ate_24h', /primeiras 24 horas/i],
      ['24_72h', /24 a 72 horas/i],
      ['apos_72h', /operação contínua/i],
    ] as const) {
      const { unmount } = render(
        <VereditoDaSentinela
          agora={AGORA}
          veredito={veredito({ janela_do_guardiao: janela })}
        />,
      );
      expect(screen.getByText(esperado)).toBeTruthy();
      unmount();
    }
  });
});

describe('haQuantoTempo', () => {
  it('sem carimbo devolve null — e a tela diz "sem carimbo de leitura"', () => {
    expect(haQuantoTempo(null)).toBeNull();
    expect(haQuantoTempo('não é uma data')).toBeNull();
    render(
      <VereditoDaSentinela agora={AGORA} veredito={veredito({ observado_em: null })} />,
    );
    expect(screen.getByText(/sem carimbo de leitura/i)).toBeTruthy();
  });

  it('conta em minutos, horas e dias', () => {
    expect(haQuantoTempo('2026-09-03T11:59:30Z', AGORA)).toMatch(/menos de dois minutos/);
    expect(haQuantoTempo('2026-09-03T11:00:00Z', AGORA)).toBe('há 60 minutos');
    expect(haQuantoTempo('2026-09-03T02:00:00Z', AGORA)).toBe('há 10 horas');
    expect(haQuantoTempo('2026-08-29T12:00:00Z', AGORA)).toBe('há 5 dias');
  });
});
