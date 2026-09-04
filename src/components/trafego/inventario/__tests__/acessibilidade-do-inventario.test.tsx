// @vitest-environment jsdom
/**
 * Acessibilidade MEDIDA — nenhuma prova aqui é "renderizou, então está ok".
 *
 * O operador desta tela decide gasto. Se ele navega por teclado, se o monitor
 * está mal calibrado, se ele tem deuteranopia ou se a tela está sendo
 * projetada numa reunião, o estado precisa continuar legível — e "precisa"
 * aqui é uma medida, não uma intenção.
 *
 * Por isso o contraste é CALCULADO a partir dos tokens reais de
 * `src/index.css`, e não conferido de olho: foi assim que apareceu o achado que
 * este arquivo trouxe junto — `--muted-foreground` só passa na AA quando o
 * fundo é o branco de `--card`; no canvas da página e nas caixas de aviso ele
 * reprova no tema claro, que é justamente a cena que decide este produto.
 *
 * ⚠️ Expansão de linha e alvo de toque NÃO são reprovados aqui de novo:
 * `inventario-campanhas.test.tsx` já os prova, e uma segunda cópia da mesma
 * asserção só duplica a manutenção. O que este arquivo cobre é o que ninguém
 * estava olhando: abas, hierarquia de títulos, nome acessível estável, estado
 * legível sem cor nenhuma, movimento reduzido e contraste nos dois temas.
 */
import { readFileSync } from 'node:fs';

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { computeAccessibleName } from 'dom-accessibility-api';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { Frescor, QuadroDeAlertas } from '@/types/trafego';

import HubDeTrafegoPage from '@/pages/trafego/HubDeTrafegoPage';
import {
  AvisoDeDadoAntigo,
  AvisoDeLeituraParcial,
  FalhaDoInventario,
  InventarioVazio,
} from '@/components/trafego/inventario/EstadosDoInventario';
import { SeloDeEstadoExterno, SeloDeFrescor } from '@/components/trafego/inventario/Selos';
import { descreverFalha } from '@/components/trafego/inventario/erros';
import { FRESCOR } from '@/components/trafego/inventario/formato';
import {
  inventarioDeProva,
  inventarioSaudavel,
  quadroDeAlertasDeProva,
} from '@/components/trafego/inventario/fixtureDeProvas';

// ── dublês ──────────────────────────────────────────────────────────────────

const leituraBase: LeituraDoInventario = {
  inventario: inventarioSaudavel(),
  carregando: false,
  atualizando: false,
  falhou: false,
  motivoDaFalha: null,
  temMais: false,
  carregandoMais: false,
  carregarMais: vi.fn(),
  recarregar: vi.fn(),
};

let leitura: LeituraDoInventario = leituraBase;

vi.mock('@/hooks/useInventario', async (original) => {
  const real = await original<typeof import('@/hooks/useInventario')>();
  return {
    ...real,
    useInventario: () => leitura,
    usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
  };
});

let notificacoes = {
  data: quadroDeAlertasDeProva() as QuadroDeAlertas | null,
  isLoading: false,
  isError: false,
  isFetching: false,
  error: null as unknown,
  refetch: vi.fn(),
};

// O painel dos canais tem prova própria em
// `src/components/trafego/canais/__tests__`. Aqui ele é dublado porque o objeto
// desta prova são as ABAS — e porque o painel real pede um `QueryClient`, que
// esta moldura não monta. Sem o dublê, ativar a aba derruba a árvore inteira e
// o teste passa a falhar por um motivo que não é o que ele investiga.
vi.mock('@/components/trafego/canais/PainelDeCanais', () => ({
  PainelDeCanais: () => 'painel dos canais',
  default: () => 'painel dos canais',
}));

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: () => notificacoes,
  INTERVALO_NOTIFICACOES_MS: 600000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/pages/trafego/TrafegoPage', () => ({
  default: () => <div>quadro de oportunidades</div>,
}));

function montarHub(endereco = '/trafego') {
  return render(
    <MemoryRouter initialEntries={[endereco]}>
      <HubDeTrafegoPage oportunidades={<div>quadro de oportunidades</div>} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  leitura = leituraBase;
  notificacoes = { ...notificacoes, data: quadroDeAlertasDeProva() };
});

afterEach(cleanup);

// ── 1 · hierarquia de títulos ───────────────────────────────────────────────

/** Os títulos, na ordem do documento, com o nível de cada um. */
function titulos(raiz: HTMLElement): { nivel: number; texto: string }[] {
  return [...raiz.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h) => ({
    nivel: Number(h.tagName[1]),
    texto: (h.textContent ?? '').trim(),
  }));
}

describe('hierarquia de títulos', () => {
  it.each([
    ['com inventário lido', () => leituraBase],
    ['sem conta nenhuma', () => ({
      ...leituraBase,
      inventario: inventarioDeProva({ contas: [], parcial: false, faltou: [] }),
    })],
    ['com a leitura falhada', () => ({
      ...leituraBase,
      inventario: null,
      falhou: true,
      motivoDaFalha: 'texto que não é do vocabulário',
    })],
  ])('não pula nível na aba Campanhas — %s', (_nome, montar) => {
    leitura = montar() as LeituraDoInventario;
    const { container } = montarHub();
    const encontrados = titulos(container);

    // Um `h1` só: dois títulos de página numa página só desfaz a estrutura do
    // documento para quem navega por títulos.
    expect(encontrados.filter((t) => t.nivel === 1).length).toBe(1);
    expect(encontrados[0].nivel).toBe(1);

    // ⚠️ Os estados do inventário eram `h3` debaixo de um `h1`. Pular o `h2`
    // não quebra nada visualmente e quebra tudo no atalho mais usado de leitor
    // de tela: quem pula de título em título ouve "nível 3" e procura o nível 2
    // que nunca existiu.
    for (let i = 1; i < encontrados.length; i += 1) {
      expect(encontrados[i].nivel - encontrados[i - 1].nivel).toBeLessThanOrEqual(1);
    }
  });
});

// ── 2 · abas ────────────────────────────────────────────────────────────────

describe('as cinco abas', () => {
  it('são tablist/tab/tabpanel de verdade, e cada aba aponta para o painel dela', () => {
    montarHub();
    const lista = screen.getByRole('tablist');
    expect(lista.getAttribute('aria-label')).toBe('seções do tráfego');

    const abas = screen.getAllByRole('tab');
    // ⚠️ Quatro desde 03/09/2026: `Canais` foi consolidada em `criar`. As duas
    // respondiam à mesma pergunta de fontes diferentes — o veredito do servidor
    // e uma derivação no cliente que nunca consultava a janela do canário —, e
    // a divergência aparecia como simetria falsa em Display.
    expect(abas.length).toBe(4);

    const painel = screen.getByRole('tabpanel');
    const ativa = abas.find((a) => a.getAttribute('aria-selected') === 'true');
    expect(ativa).toBeTruthy();
    // `aria-controls` sem alvo é pior que nenhum: o leitor de tela anuncia um
    // caminho que não leva a lugar nenhum.
    expect(document.getElementById(ativa!.getAttribute('aria-controls') as string)).toBe(painel);
    expect(painel.getAttribute('aria-labelledby')).toBe(ativa!.id);
  });

  it('a barra de abas é UMA parada de Tab, não três', () => {
    montarHub();
    const lista = screen.getByRole('tablist');
    const abas = screen.getAllByRole('tab');
    // Foco rotativo: a barra inteira vale uma parada de Tab e as abas se
    // alcançam pelas setas. Três paradas obrigariam quem usa teclado a
    // atravessar a navegação inteira para chegar ao conteúdo — em toda visita.
    const paradas = [lista, ...abas].filter((e) => e.getAttribute('tabindex') === '0');
    expect(paradas.length).toBe(1);
    expect(abas.every((a) => a.getAttribute('tabindex') === '-1')).toBe(true);
  });

  it('a seta para a direita muda de aba', async () => {
    montarHub();
    const abas = screen.getAllByRole('tab');
    expect(abas[0].getAttribute('aria-selected')).toBe('true');

    abas[0].focus();
    fireEvent.keyDown(abas[0], { key: 'ArrowRight' });

    // O foco viaja num `setTimeout` (a biblioteca de foco rotativo agenda para
    // depois do `preventDefault`), então a asserção síncrona olharia para o
    // estado anterior e passaria a impressão de que o teclado não funciona.
    await waitFor(() => expect(abas[1].getAttribute('aria-selected')).toBe('true'));
  });

  it('o contador vive no rótulo da aba — e ausência não vira zero', () => {
    leitura = { ...leituraBase, inventario: null };
    montarHub();
    const campanhas = screen.getAllByRole('tab')[0];
    // Enquanto a leitura não chega, `0` seria uma AFIRMAÇÃO — "não há nada" —
    // sobre o que ainda não se sabe.
    expect(campanhas.textContent).not.toMatch(/\d/);
  });
});

// ── 3 · nomes acessíveis ────────────────────────────────────────────────────

describe('nome acessível', () => {
  it('os botões destas caixas são nomeados pelo conteúdo, sem aria-label por cima', () => {
    render(<FalhaDoInventario ocorrencia={descreverFalha({ status: 503 }, 'inventario')} aoTentarDeNovo={vi.fn()} />);
    for (const botao of screen.getAllByRole('button')) {
      // ⚠️ `aria-label` SUBSTITUI o nome calculado a partir do conteúdo. Quando
      // o conteúdo já diz melhor — e "copiar código" diz —, o rótulo só cria um
      // segundo texto para manter em dia, e é o segundo que envelhece.
      expect(botao.hasAttribute('aria-label')).toBe(false);
      expect(computeAccessibleName(botao)).toBe((botao.textContent ?? '').trim());
    }
  });

  it('⚠️ copiar não renomeia o botão — o controle não muda de identidade sob a mão', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    render(<FalhaDoInventario ocorrencia={descreverFalha({ status: 503 }, 'inventario')} />);
    const botao = screen.getByRole('button', { name: 'copiar código' });
    const antes = computeAccessibleName(botao);

    fireEvent.click(botao);
    await screen.findByText(/Código copiado/);

    // O padrão comum é trocar o texto para "copiado!". Quem está com o foco no
    // botão ouve o controle virar outro; a confirmação pertence à região viva.
    expect(computeAccessibleName(botao)).toBe(antes);
  });

  it('o código fica legível na tela, não só dentro da área de transferência', () => {
    const oc = descreverFalha({ status: 503 }, 'inventario', { id: 'VOLC-ABC234' });
    render(<FalhaDoInventario ocorrencia={oc} />);
    expect(screen.getByText('VOLC-ABC234')).toBeTruthy();
  });
});

// ── 4 · foco ────────────────────────────────────────────────────────────────

describe('foco', () => {
  it('todo controle destas caixas recebe foco e mostra que recebeu', () => {
    render(<FalhaDoInventario ocorrencia={descreverFalha({ status: 503 }, 'inventario')} aoTentarDeNovo={vi.fn()} />);
    const botoes = screen.getAllByRole('button');
    expect(botoes.length).toBeGreaterThan(1);
    for (const botao of botoes) {
      expect(botao.tagName).toBe('BUTTON');
      expect(botao.getAttribute('tabindex')).not.toBe('-1');
      botao.focus();
      expect(document.activeElement).toBe(botao);
      // `outline: none` sem substituto apaga o único sinal de onde o teclado
      // está. Aqui o substituto é o anel de 2px em `--ring`.
      expect(botao.className).toContain('focus-visible:ring-2');
    }
  });
});

// ── 5 · estado sem cor nenhuma ──────────────────────────────────────────────

const FRESCORES = Object.keys(FRESCOR) as Frescor[];

describe('estado legível sem cor', () => {
  it('os seis frescores mais o desconhecido se distinguem só pelo texto', () => {
    const lidos = new Set<string>();
    for (const frescor of [...FRESCORES, 'algo_novo_do_servidor' as Frescor]) {
      const { container, unmount } = render(
        <SeloDeFrescor frescor={frescor} leitura={{ lido_em: null, idade_s: 372 }} />,
      );
      const texto = (container.textContent ?? '').trim();
      expect(texto.length).toBeGreaterThan(10);
      lidos.add(texto);
      unmount();
    }
    // Sete estados, sete textos. Se dois colidissem, a diferença entre eles
    // estaria viajando só na cor — e é essa diferença que decide se o operador
    // pede leitura, espera, ou não faz nada.
    expect(lidos.size).toBe(7);
  });

  it('o glifo é enfeite redundante, e a palavra não é pintada com a cor do estado', () => {
    const { container } = render(
      <SeloDeFrescor frescor="falhou" leitura={null} ultimaLeituraBoa={{ lido_em: null, idade_s: 26400 }} />,
    );
    for (const svg of container.querySelectorAll('svg')) {
      // Glifo que carrega significado sozinho some para quem usa leitor de tela.
      expect(svg.getAttribute('aria-hidden')).toBe('true');
    }
    const chip = container.querySelector('span > span') as HTMLElement;
    const raiz = chip.parentElement as HTMLElement;
    // `--warning` no claro mede ~2,4:1 contra o branco: pintar a PALAVRA com a
    // cor do estado é o jeito mais comum de tornar ilegível justamente o rótulo
    // que precisa ser lido.
    expect(raiz.className).not.toMatch(/text-(warning|destructive|success|info)\b/);
  });

  it('frescor sem data DIZ que não tem data — não fica em branco', () => {
    const { container } = render(<SeloDeFrescor frescor="velho" leitura={null} />);
    expect(container.textContent).toContain('sem data de leitura');
  });

  it('estado da conta de anúncio que a tela não conhece não vira palavra de máquina', () => {
    const { container } = render(<SeloDeEstadoExterno estado="UNSPECIFIED" />);
    // `UNSPECIFIED` como estado da campanha põe vocabulário de máquina onde o
    // operador procura a resposta — e uma palavra que ele não vai achar no
    // painel do Google para conferir.
    expect(container.textContent).toContain('estado não reconhecido');
    expect(container.textContent).toContain('UNSPECIFIED');
    const palavra = container.querySelector('span > span') as HTMLElement;
    expect(palavra.textContent).not.toBe('UNSPECIFIED');
  });
});

// ── 6 · movimento reduzido ──────────────────────────────────────────────────

const MEUS_ARQUIVOS = [
  'src/components/trafego/inventario/EstadosDoInventario.tsx',
  'src/components/trafego/inventario/Selos.tsx',
  'src/components/trafego/inventario/formato.tsx',
  'src/components/trafego/inventario/erros.ts',
  'src/hooks/useInventario.ts',
];

describe('movimento reduzido', () => {
  it('nenhuma animação destes arquivos ignora quem pediu menos movimento', () => {
    for (const caminho of MEUS_ARQUIVOS) {
      const linhas = readFileSync(caminho, 'utf8').split('\n');
      linhas.forEach((linha, i) => {
        if (!/\banimate-(?!none)/.test(linha)) return;
        expect(
          linha.includes('motion-reduce:animate-none'),
          `${caminho}:${i + 1} anima sem desligar em prefers-reduced-motion`,
        ).toBe(true);
      });
    }
  });

  it('a confirmação de cópia é palavra, não movimento nem cor', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    render(<FalhaDoInventario ocorrencia={descreverFalha({ status: 503 }, 'inventario')} />);
    fireEvent.click(screen.getByRole('button', { name: 'copiar código' }));
    const regiao = await screen.findByText(/Código copiado/);
    expect(regiao.closest('[role="status"]')).toBeTruthy();
  });
});

// ── 7 · contraste, nos dois temas ───────────────────────────────────────────

type HSL = [number, number, number];
type RGB = [number, number, number];

/** Os tokens como estão em `src/index.css` — a fonte canônica, não o hex do doc. */
function tokensDe(regiao: RegExp): Record<string, HSL> {
  const css = readFileSync('src/index.css', 'utf8');
  const bloco = css.match(regiao);
  if (!bloco) throw new Error('bloco de tokens não encontrado em src/index.css');
  const saida: Record<string, HSL> = {};
  for (const [, nome, h, s, l] of bloco[1].matchAll(
    /--([a-z-]+):\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*;/g,
  )) {
    saida[nome] = [Number(h), Number(s) / 100, Number(l) / 100];
  }
  return saida;
}

function paraRgb([h, s, l]: HSL): RGB {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hh = h / 60;
  const x = c * (1 - Math.abs((hh % 2) - 1));
  const m = l - c / 2;
  const base: RGB =
    hh < 1 ? [c, x, 0] : hh < 2 ? [x, c, 0] : hh < 3 ? [0, c, x]
      : hh < 4 ? [0, x, c] : hh < 5 ? [x, 0, c] : [c, 0, x];
  return base.map((v) => (v + m) * 255) as RGB;
}

const linear = (v: number): number => {
  const c = v / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};

const luminancia = (p: RGB): number =>
  0.2126 * linear(p[0]) + 0.7152 * linear(p[1]) + 0.0722 * linear(p[2]);

function razao(a: RGB, b: RGB): number {
  const [x, y] = [luminancia(a), luminancia(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

/** Tinta translúcida sobre um fundo — é o que `bg-warning/[0.06]` faz. */
const sobre = (frente: RGB, alfa: number, fundo: RGB): RGB =>
  frente.map((v, i) => v * alfa + fundo[i] * (1 - alfa)) as RGB;

const TEMAS = {
  claro: tokensDe(/:root\s*\{([\s\S]*?)\n\s*\}/),
  escuro: tokensDe(/\.dark\s*\{([\s\S]*?)\n\s*\}/),
};

describe('contraste no tema claro E no escuro', () => {
  it.each(Object.entries(TEMAS))('as caixas de estado passam na AA — tema %s', (_tema, t) => {
    const fg = paraRgb(t.foreground);
    const mf = paraRgb(t['muted-foreground']);
    const card = paraRgb(t.card);
    const fundo = paraRgb(t.background);

    // Os fundos exatos que estes componentes desenham.
    const painelDeFalha = sobre(paraRgb(t.destructive), 0.05, fundo);
    const avisoParcial = sobre(paraRgb(t.warning), 0.06, fundo);
    const avisoAntigo = sobre(paraRgb(t.muted), 0.4, fundo);
    /**
     * ⚠️ CORRIGIDO APÓS REVISÃO ADVERSARIAL.
     *
     * Estes casos usavam `secundaria()`, que calculava `--foreground/75` — a
     * tinta COMPENSATÓRIA que `EstadosDoInventario` usava enquanto
     * `--muted-foreground` reprovava. A compensação foi revertida no lote que
     * corrigiu o token, mas a função ficou: a prova continuava verde medindo
     * uma cor que o componente não renderiza mais. Guardava o passado.
     *
     * Agora todos os casos usam `mf`, que é o `--muted-foreground` DO TEMA
     * sendo testado — e os leitos tingidos (painel de falha, aviso parcial,
     * aviso de dado antigo) são justamente os piores do produto.
     */

    const casos: [string, RGB, RGB][] = [
      // `InventarioVazio` — a única destas caixas que fica sobre `--card`, e a
      // única onde `--muted-foreground` alcança a AA.
      ['vazio: corpo sobre card', mf, card],
      ['falha: frase principal', fg, painelDeFalha],
      ['falha: próximo passo', mf, painelDeFalha],
      ['falha: rótulo do código', mf, painelDeFalha],
      ['falha: código', fg, sobre(paraRgb(t.muted), 0.5, painelDeFalha)],
      ['parcial: título', fg, avisoParcial],
      ['parcial: lista do que faltou', mf, avisoParcial],
      ['dado antigo: corpo', mf, avisoAntigo],
    ];

    for (const [rotulo, tinta, atras] of casos) {
      const medida = razao(tinta, atras);
      expect(medida, `${rotulo}: ${medida.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('--muted-foreground alcança a AA em TODO leito de estado, nos dois temas', () => {
    // Esta prova era o marcador do defeito: ela afirmava que
    // `--muted-foreground` REPROVAVA fora do card e existia para falhar no dia
    // em que o token fosse corrigido, sinalizando que a compensação
    // (`--foreground/75` em EstadosDoInventario) podia sair.
    //
    // Esse dia chegou: o token foi de 45% para 40% de luminosidade. A prova
    // inverteu de sentido e agora guarda o invariante em vez do defeito — se
    // alguém clarear o token de novo, isto acusa antes de chegar ao operador.
    for (const nome of ['claro', 'escuro'] as const) {
      const t = TEMAS[nome];
      const mf = paraRgb(t['muted-foreground']);

      for (const [leito, cor] of [
        ['card', paraRgb(t.card)],
        ['background', paraRgb(t.background)],
        ['muted', paraRgb(t.muted)],
      ] as const) {
        const medida = razao(mf, cor);
        expect(medida, `${nome}: muted-foreground sobre ${leito} = ${medida.toFixed(2)}:1`)
          .toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});

// ── 8 · as caixas todas, de uma vez ─────────────────────────────────────────

describe('as caixas de estado não são becos sem saída', () => {
  it('o vazio ensina o que aquilo mostraria', () => {
    const { container } = render(<InventarioVazio />);
    expect(within(container).getByRole('heading', { level: 2 })).toBeTruthy();
    expect(container.textContent).toContain('não significa que as contas estejam vazias');
  });

  it('a leitura parcial nomeia o que faltou, e não só o adjetivo', () => {
    render(
      <AvisoDeLeituraParcial
        faltou={[{ customer_id: '8017851692', escopo: 'campanhas', motivo: 'a conta não respondeu' }]}
      />,
    );
    expect(screen.getByRole('status').textContent).toContain('8017851692');
    expect(screen.getByRole('status').textContent).toContain('Nada foi apagado');
  });

  it('o dado antigo declara a idade — e diz quando não sabe qual é', () => {
    const { container, rerender } = render(<AvisoDeDadoAntigo idadeSegundos={26400} />);
    expect(container.textContent).toContain('há 7 h');
    rerender(<AvisoDeDadoAntigo idadeSegundos={null} aAtualizacaoFalhou />);
    expect(container.textContent).toContain('A atualização mais recente falhou');
    expect(container.textContent).not.toMatch(/há \d/);
  });
});
