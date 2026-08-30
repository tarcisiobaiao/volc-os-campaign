// @vitest-environment jsdom
/**
 * OPORTUNIDADES — o conteúdo embutível, e a língua que ele fala.
 *
 * Duas coisas estão travadas aqui, e as duas já estiveram quebradas:
 *
 *  1. **Isto é conteúdo, não página.** Sem `<Layout>`, sem `<h1>` e sem recuo
 *     de página. O Hub montava a página inteira dentro de uma aba, e o operador
 *     via duas molduras — e, por um tempo, dois `<h1>Tráfego</h1>`. Dois títulos
 *     de documento numa página só fazem a estrutura parar de dizer, a quem
 *     navega por leitor de tela, onde ele está.
 *
 *  2. **A tela fala a língua do operador.** Ela dizia "mutate atômico" e
 *     imprimia, cru, o texto que o servidor escreve para quem programa — com
 *     nome de função e nome de variável de ambiente dentro. O portão continua
 *     FECHADO exatamente como estava: o que mudou foi a palavra, não a regra, e
 *     esta prova cobra as duas coisas ao mesmo tempo.
 */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { EstadoDaTrava, QuadroDeTrafego } from '@/types/trafego';

const quadroDeTrafego = vi.hoisted(() => vi.fn());
const estadoDaTrava = vi.hoisted(() => vi.fn());

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { quadroDeTrafego, estadoDaTrava },
}));

import QuadroDeOportunidades from '@/components/trafego/oportunidades/QuadroDeOportunidades';
import {
  compacto,
  estadoDoCandidato,
  fraseDoPortao,
} from '@/components/trafego/oportunidades/linguagem';
import TrafegoPage from '@/pages/trafego/TrafegoPage';
import { veredito } from '@/components/trafego/hub/fixtureMulticanal';


// ── dados de prova, no formato do contrato ──────────────────────────────────

const pronto = {
  opportunity_id: 63,
  run_id: 7,
  titulo: 'Maquininha de cartão para MEI',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/maquininha/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 23,
  volume_total: 148_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 0,
  reconciliacao: veredito(63, 7, 'sem_campanha'),
};

const semCluster = {
  ...pronto,
  opportunity_id: 74,
  run_id: 9,
  titulo: 'FGTS saque-aniversário',
  tem_cluster: false,
  keywords_para_anuncio: 0,
  volume_total: null,
  servicos_declarados: [],
};

const jaNoAr = {
  ...pronto,
  opportunity_id: 81,
  run_id: 11,
  titulo: 'Consignado INSS',
  campanhas_lancadas: 2,
  reconciliacao: veredito(81, 11, 'vinculada'),
};

const quadro: QuadroDeTrafego = {
  prontos: [pronto, semCluster, jaNoAr],
  totais: { funis_publicados: 3, com_cluster: 2, keywords_disponiveis: 46 },
  sem_metrica: true,
  por_que: 'não existe camada de métrica no motor de anúncios.',
};

/** O portão como o servidor o descreve HOJE — texto de máquina incluído. */
const portaoFechado: EstadoDaTrava = {
  escrita_permitida: false,
  destravado_no_codigo: false,
  env_presente: false,
  motivo: '',
  explicacao:
    'A trava é de dois fatores: `destravar()` no código E FORGE_PERMITIR_ESCRITA=1 no ' +
    'ambiente. `validate_only` é isento — validar é leitura.',
};

function montar(no: React.ReactNode = <QuadroDeOportunidades />) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter>{no}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  quadroDeTrafego.mockResolvedValue(quadro);
  estadoDaTrava.mockResolvedValue(portaoFechado);
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ── 1 · conteúdo, não página ────────────────────────────────────────────────

describe('1 · isto é conteúdo embutível, não uma página dentro de outra', () => {
  it('não monta título de página nem moldura própria', async () => {
    montar();
    await screen.findByText('Maquininha de cartão para MEI');
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
    expect(screen.queryByText('compra de tráfego')).toBeNull();
    expect(document.querySelector('nav')).toBeNull();
  });

  it('a rota antiga é só um adaptador: ela renderiza o mesmo conteúdo', async () => {
    montar(<TrafegoPage />);
    await screen.findByText('Maquininha de cartão para MEI');
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
  });
});

// ── 2 · a língua do operador ────────────────────────────────────────────────

describe('2 · nenhuma palavra de máquina chega à tela', () => {
  const PROIBIDAS = [
    /mutate/i,
    /destravar/i,
    /FORGE_PERMITIR_ESCRITA/,
    /validate_only/i,
    /GAQL/i,
    /PostgREST/i,
    /snapshot/i,
    /payload/i,
    /trava/i,
  ];

  it('o texto cru do servidor não é repassado, nem por dentro do portão', async () => {
    montar();
    await screen.findByText('Maquininha de cartão para MEI');
    const texto = document.body.textContent ?? '';
    for (const proibida of PROIBIDAS) {
      expect(texto, `palavra de máquina na tela: ${proibida}`).not.toMatch(proibida);
    }
  });

  it('e o portão fechado é dito em operação, sem afrouxar nada', async () => {
    montar();
    // Esperar a PALAVRA, não a região: a região existe desde o primeiro quadro
    // e, antes da resposta, ela diz "permissão não verificada" — que é outro
    // estado, e de propósito.
    await screen.findByText('publicação temporariamente fechada');
    const secao = screen.getByRole('region', { name: 'permissão para criar campanha' });
    expect(within(secao).getByText('publicação temporariamente fechada')).toBeTruthy();
    expect(within(secao).getByText(/Você pode montar e mandar o Google conferir/)).toBeTruthy();
    expect(within(secao).getByText(/envio final permanece indisponível/)).toBeTruthy();
  });
});

describe('2b · as quatro respostas do portão, isoladas da tela', () => {
  it('fechado de todo: nada é criado, e a frase diz o que falta', () => {
    const f = fraseDoPortao(portaoFechado);
    expect(f.palavra).toBe('publicação temporariamente fechada');
    expect(f.explicacao).toMatch(/envio final permanece indisponível/);
  });

  it('env presente significa autorização durável; a confirmação fica no cockpit', () => {
    const f = fraseDoPortao({ ...portaoFechado, env_presente: true });
    expect(f.palavra).toBe('pronta para revisar e publicar');
    expect(f.explicacao).toMatch(/confirmação final cria a campanha PAUSADA/);
    expect(f.explicacao).not.toMatch(/FORGE|destravar/);
  });

  it('aberto avisa que o clique gasta de verdade, e avisa alto', () => {
    const f = fraseDoPortao({ ...portaoFechado, escrita_permitida: true, env_presente: true });
    expect(f.palavra).toBe('pronta para revisar e publicar');
    expect(f.explicacao).toMatch(/cria a campanha PAUSADA/);
    expect(f.tom).toBe('ruim');
  });

  it('⚠️ portão não consultado NÃO degrada para "fechado"', () => {
    // Ausência de resposta não pode virar permissão por precaução.
    const f = fraseDoPortao(null);
    expect(f.palavra).toBe('permissão não verificada');
    expect(f.explicacao).toMatch(/não avance para o envio/);
  });
});

// ── 3 · a funcionalidade preservada ─────────────────────────────────────────

describe('3 · tudo que a tela fazia, ela continua fazendo', () => {
  it('lista os funis publicados com keywords, volume e procedência da mineração', async () => {
    montar();
    await screen.findByText('Maquininha de cartão para MEI');
    expect(screen.getAllByText(/funis publicados/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/keywords triadas para anúncio/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/minerado por n8n:dataforseo/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('148,0k').length).toBe(2);
    expect(screen.getAllByText('23').length).toBe(2);
    // O funil sem cluster não tem volume medido: travessão, nunca zero.
    expect(screen.getAllByText('—').length).toBe(2);
  });

  it('leva a /trafego/nova/:opportunityId com o run no endereço', async () => {
    montar();
    await screen.findByText('Maquininha de cartão para MEI');
    const link = screen.getByRole('link', { name: /montar campanha/ });
    expect(link.getAttribute('href')).toBe('/trafego/nova/63?run=7');
  });

  it('funil que já tem campanha no ar não é convidado a lançar outra igual', async () => {
    // Doutrina P7: um termo, uma campanha. Duas competem no mesmo leilão e
    // encarecem uma à outra — o quadro convidava porque não sabia.
    montar();
    await screen.findByText('Consignado INSS');
    const link = screen.getByRole('link', { name: /abrir o que existe/ });
    expect(link.getAttribute('href')).toBe('/trafego/nova/81?run=11');
    expect(screen.getByText('2 campanhas no ar')).toBeTruthy();
  });

  it('sem cluster não vira "0 keywords": vira ausência de triagem', async () => {
    montar();
    await screen.findByText('FGTS saque-aniversário');
    expect(screen.getByText('sem keywords mineradas')).toBeTruthy();
    expect(screen.getByText('minerar no Pautador antes')).toBeTruthy();
    expect(estadoDoCandidato(semCluster).pronto).toBe(false);
  });

  it('declara que não há performance aqui, com o motivo do servidor', async () => {
    montar();
    await screen.findByText(/não existe camada de métrica/);
  });
});

// ── 4 · as regras da casa ───────────────────────────────────────────────────

describe('4 · ausência é travessão, e todo número herda frescor', () => {
  it('volume não medido aparece como travessão, nunca como zero', () => {
    expect(compacto(null)).toBe('—');
    expect(compacto(0)).toBe('0');
    expect(compacto(1_500_000)).toBe('1,5M');
    expect(compacto(148_000)).toBe('148,0k');
  });

  it('a idade da leitura acompanha a lista', async () => {
    montar();
    await screen.findByText('Maquininha de cartão para MEI');
    expect(screen.getByText(/^lido /)).toBeTruthy();
  });

  it('comparação é em colunas alinhadas, não numa grade de cartões', async () => {
    montar();
    await screen.findByText('Maquininha de cartão para MEI');
    const tabela = screen.getByRole('table');
    const colunas = within(tabela).getAllByRole('columnheader').map((c) => c.textContent);
    expect(colunas).toEqual([
      'funil',
      'keywords',
      'volume/mês',
      'procedência da mineração',
      'estado',
      'ação',
    ]);
  });
});

// ── 5 · o vazio e a falha ───────────────────────────────────────────────────

describe('5 · o vazio ensina e a falha tem código copiável', () => {
  it('sem funil publicado, diz o que apareceria ali e o que fazer', async () => {
    quadroDeTrafego.mockResolvedValue({ ...quadro, prontos: [] });
    montar();
    expect(await screen.findByText('Nenhum funil publicado ainda')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Redator' })).toBeTruthy();
    expect(screen.getByText(/não significa que não há\s+trabalho em andamento/)).toBeTruthy();
  });

  it('falha traz frase de operação, próximo passo e um código para citar', async () => {
    quadroDeTrafego.mockRejectedValue(new Error('boom'));
    montar();
    // Espera folgada de propósito: a leitura tenta de novo uma vez antes de
    // desistir, e é DEPOIS dessa segunda tentativa que a falha é declarada.
    expect(
      await screen.findByText('Não consegui ler os funis prontos', {}, { timeout: 5000 }),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: /copiar código/i })).toBeTruthy();
    // "deu erro" sozinho é um beco: ninguém acha a ocorrência no log depois.
    expect(screen.getByText(/^VOLC-/)).toBeTruthy();
    // E nada do erro cru chega à tela.
    expect(document.body.textContent).not.toMatch(/boom/);
  });

  it('a falha do portão não derruba a lista de funis', async () => {
    estadoDaTrava.mockRejectedValue(new Error('sem portão'));
    montar();
    await waitFor(() => expect(screen.getByText('Maquininha de cartão para MEI')).toBeTruthy());
    expect(screen.getByText('permissão não verificada')).toBeTruthy();
  });
});
