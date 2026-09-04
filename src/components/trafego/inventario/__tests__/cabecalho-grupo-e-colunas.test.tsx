// @vitest-environment jsdom
/**
 * Provas da frente B1: a moldura, o cabeçalho, o grupo de conta e as colunas.
 *
 * Três coisas se provam aqui, e nenhuma delas é aparência:
 *
 *  1. o cabeçalho responde "quando isso foi lido?" e "como está a leitura?"
 *     ANTES de qualquer número, e a única ação da moldura declara o que faz e o
 *     que não faz;
 *  2. nada da moldura se mexe ao trocar de aba — cabeçalho, abas e o recuo do
 *     conteúdo ficam onde estavam;
 *  3. a tabela do monitor é comparativa de verdade: estado e canal em coluna
 *     própria, a idade da medida em coluna própria, e o identificador da conta
 *     mascarado no resumo com o completo guardado na expansão.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { QuadroDeAlertas } from '@/types/trafego';

import HubDeTrafegoPage, { fraseDaSituacao } from '@/pages/trafego/HubDeTrafegoPage';
import { InventarioDeCampanhas } from '@/components/trafego/inventario/InventarioDeCampanhas';
import { mascararConta } from '@/components/trafego/inventario/GrupoDeConta';
import { tetoDaCampanha } from '@/components/trafego/inventario/LinhaDeCampanha';
import { densidadeDaLargura } from '@/components/trafego/inventario/densidade';
import {
  creditoUp,
  fgts,
  fgtsDeTeste,
  inventarioDeProva,
  inventarioRenderavel,
  inventarioVelho,
  maquininha,
  quadroDeAlertasDeProva,
} from '@/components/trafego/inventario/fixtureDeProvas';

// ── dublês ──────────────────────────────────────────────────────────────────

const leituraBase: LeituraDoInventario = {
  inventario: inventarioRenderavel(),
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

interface DubleDeNotificacoes {
  data: QuadroDeAlertas | null;
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => void;
}

let notificacoes: DubleDeNotificacoes;

vi.mock('@/hooks/useInventario', () => ({
  useInventario: () => leitura,
  usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
}));

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: () => notificacoes,
  INTERVALO_NOTIFICACOES_MS: 600000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

/**
 * O dublê de `TrafegoPage` conserva o RECUO PRÓPRIO que a página real ainda
 * traz de quando era uma rota inteira. Um dublê sem recuo esconderia justamente
 * o que a prova de estabilidade mede: a moldura precisa neutralizar aquele
 * recuo, senão a aba Oportunidades desenha o conteúdo mais estreito e mais
 * baixo que as outras duas.
 */
vi.mock('@/pages/trafego/TrafegoPage', () => ({
  default: () => <div className="p-4 md:p-8">quadro de oportunidades</div>,
}));

function montar(endereco = '/trafego') {
  return render(
    <MemoryRouter initialEntries={[endereco]}>
      <HubDeTrafegoPage oportunidades={<div className="p-4 md:p-8">funis prontos</div>} />
    </MemoryRouter>,
  );
}

function largura(px: number) {
  Object.defineProperty(window, 'innerWidth', { value: px, writable: true, configurable: true });
}

const MONITOR = 1440;
const TELEFONE = 390;

beforeEach(() => {
  leitura = { ...leituraBase, inventario: inventarioRenderavel() };
  notificacoes = {
    data: quadroDeAlertasDeProva(),
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  };
  largura(MONITOR);
});
afterEach(cleanup);

// ── o cabeçalho ─────────────────────────────────────────────────────────────

describe('o cabeçalho responde antes de mostrar número', () => {
  it('tem kicker, um título só, e uma descrição que não repete o título', () => {
    montar();
    expect(screen.getByText('compra de tráfego')).toBeTruthy();
    const titulos = screen.getAllByRole('heading', { level: 1 });
    expect(titulos.length).toBe(1);
    expect(titulos[0].textContent).toBe('Tráfego');

    const descricao = screen.getByText(/Controle campanhas, criação e decisões de mídia/);
    // Uma descrição que começa repetindo o título gasta a linha mais lida da
    // tela dizendo o que já está dito dois centímetros acima.
    expect(descricao.textContent).not.toContain('Tráfego');
  });

  it('diz quando foi lido e como está a leitura, antes das abas', () => {
    montar();
    const cabecalho = document.querySelector('header')!;
    // A palavra do estado e a idade, juntas: separadas, "lido há 6 min" não
    // informa se aquela leitura voltou inteira, e "registro lido" sozinho não
    // diz de quando.
    expect(within(cabecalho).getByText('registro lido')).toBeTruthy();
    expect(within(cabecalho).getByText('lido há 6 min')).toBeTruthy();
    expect(within(cabecalho).getByText('2 contas neste inventário')).toBeTruthy();
  });

  it('o estado do conjunto é dito no escopo do conjunto, não no da conta', () => {
    // ⚠️ O vocabulário de frescor da CONTA é escrito no singular ("a última
    // tentativa de ler ESTA CONTA não deu certo"). Reusá-lo no cabeçalho faria
    // o operador ler "esta conta" olhando para uma tela que fala de quatro.
    leitura = { ...leituraBase, inventario: inventarioDeProva() };
    montar();
    const cabecalho = document.querySelector('header')!;
    expect(cabecalho.textContent).not.toContain('esta conta não deu certo');
    expect(within(cabecalho).getByText('leitura parcial')).toBeTruthy();
    expect(cabecalho.textContent).toContain('parte das contas não pôde ser lida');
  });

  it('leitura parcial é dita no cabeçalho, contando CONTAS e não motivos', () => {
    leitura = { ...leituraBase, inventario: inventarioDeProva() };
    montar();
    expect(screen.getByText(/1 conta não pôde ser lida nesta leitura/)).toBeTruthy();
  });

  it('com o conjunto marcado como falho, não afirma que não há leitura boa', () => {
    // O envelope de prova vem com frescor `falhou` E com o inventário inteiro
    // visível abaixo. Dizer "sem leitura boa anterior" no cabeçalho seria falso
    // na direção mais cara: sugere que não há dado quando há, e o operador
    // desconfiaria de números que estão certos.
    leitura = { ...leituraBase, inventario: inventarioDeProva() };
    montar();
    const cabecalho = document.querySelector('header')!;
    expect(cabecalho.textContent).not.toContain('sem leitura boa anterior');
    expect(within(cabecalho).getByText('lido há 6 min')).toBeTruthy();
  });

  it('sem inventário nenhum, o cabeçalho diz que está lendo — nunca um zero', () => {
    leitura = { ...leituraBase, inventario: null, carregando: true };
    montar();
    const cabecalho = document.querySelector('header')!;
    expect(within(cabecalho).getByText('lendo o registro')).toBeTruthy();
    expect(cabecalho.textContent).toContain('isso é diferente de não haver campanha');
    // Sem leitura, nem idade nem contagem são afirmadas: `0` seria dizer "não
    // há nada", que é exatamente o que ainda não se sabe.
    expect(cabecalho.textContent).not.toContain('0 contas');
    expect(cabecalho.textContent).not.toContain('lido há');
  });

  it('nenhum ramo da frase de situação fica em silêncio', () => {
    // Ausência de frase, numa tela cuja promessa é procedência, lê-se como
    // "está tudo bem" — e "ainda não sei" leva à decisão oposta.
    const casos: LeituraDoInventario[] = [
      { ...leituraBase, inventario: null, carregando: true },
      { ...leituraBase, inventario: null, falhou: true },
      { ...leituraBase, inventario: inventarioDeProva() },
      { ...leituraBase, inventario: inventarioRenderavel() },
      { ...leituraBase, inventario: inventarioRenderavel(), falhou: true },
      { ...leituraBase, inventario: inventarioVelho() },
    ];
    for (const caso of casos) {
      expect(fraseDaSituacao(caso).trim().length).toBeGreaterThan(10);
    }
  });
});

describe('a ação da moldura declara o que faz e o que não faz', () => {
  it('existe, chama-se "Atualizar dados" e explica o custo e o limite dela', () => {
    montar();
    const botao = screen.getByRole('button', { name: /Atualizar dados/ });
    const descricao = document.getElementById(botao.getAttribute('aria-describedby') ?? '');
    expect(descricao).toBeTruthy();

    const frase = descricao!.textContent ?? '';
    expect(frase).toMatch(/pode levar alguns instantes/i);
    // O que ela NÃO faz é a metade que tira o medo de clicar numa tela que fala
    // com a conta de anúncio de um cliente.
    expect(frase).toMatch(/não altera nenhuma campanha/i);
  });

  it('relê as duas leituras da moldura ao mesmo tempo', () => {
    // O inventário e os avisos alimentam dois contadores do MESMO grupo de
    // abas. Atualizar só um deixaria dois números da mesma tela lidos em
    // momentos diferentes, e ninguém saberia qual dos dois é o velho.
    const recarregar = vi.fn();
    const refetch = vi.fn();
    leitura = { ...leituraBase, recarregar };
    notificacoes = { ...notificacoes, refetch };
    montar();
    fireEvent.click(screen.getByRole('button', { name: /Atualizar dados/ }));
    expect(recarregar).toHaveBeenCalledTimes(1);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('enquanto atualiza, o botão diz que está ocupado e não aceita novo clique', () => {
    leitura = { ...leituraBase, atualizando: true };
    montar();
    const botao = screen.getByRole('button', { name: /atualizando/ }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(botao.getAttribute('aria-busy')).toBe('true');
  });

  it('quando a atualização falha, dá frase de operação e um código copiável', () => {
    leitura = {
      ...leituraBase,
      falhou: true,
      motivoDaFalha: 'PautadorApiError: 500 em /api/trafego/inventario?cursor=eyJ',
    };
    montar();
    expect(screen.getByText(/Não consegui atualizar agora/)).toBeTruthy();
    expect(screen.getByText('código desta ocorrência')).toBeTruthy();
    expect(screen.getByRole('button', { name: /copiar/ })).toBeTruthy();

    // ⚠️ O detalhe técnico fica no log, não na tela. A mensagem crua do servidor
    // fala de rota, status e biblioteca — nada disso ajuda quem está decidindo
    // se mexe numa campanha, e ainda carrega endereço interno.
    const texto = document.body.textContent ?? '';
    expect(texto).not.toContain('PautadorApiError');
    expect(texto).not.toContain('/api/trafego/inventario');
  });

  it('o cabeçalho não fala a língua da máquina', () => {
    leitura = { ...leituraBase, inventario: inventarioDeProva(), falhou: true };
    montar();
    const texto = (document.body.textContent ?? '').toLowerCase();
    for (const proibido of ['gaql', 'postgrest', 'snapshot', 'payload', 'cursor', 'mutate']) {
      expect(texto).not.toContain(proibido);
    }
  });
});

// ── a moldura fica parada ───────────────────────────────────────────────────

describe('trocar de aba não move a interface', () => {
  it('cabeçalho, situação e ação continuam idênticos nas três abas', () => {
    montar();
    const antes = () => ({
      titulo: screen.getAllByRole('heading', { level: 1 }).length,
      kicker: screen.getAllByText('compra de tráfego').length,
      acao: screen.getAllByRole('button', { name: /Atualizar dados/ }).length,
      abas: screen.getAllByRole('tab').length,
    });

    const naCampanhas = antes();
    fireEvent.mouseDown(screen.getByRole('tab', { name: /preparar/ }));
    expect(antes()).toEqual(naCampanhas);
    fireEvent.mouseDown(screen.getByRole('tab', { name: /atenção/ }));
    expect(antes()).toEqual(naCampanhas);
  });

  it('o painel de cada aba começa na mesma altura e na mesma largura', () => {
    montar();
    const recuos: string[] = [];
    for (const nome of [/campanhas/, /preparar/, /atenção/]) {
      fireEvent.mouseDown(screen.getByRole('tab', { name: nome }));
      recuos.push(screen.getByRole('tabpanel').className);
    }
    // Todos os painéis abrem com a MESMA margem superior. Conteúdo que salta
    // entre abas obriga o olho a reencontrar a interface a cada clique.
    for (const classe of recuos) expect(classe).toContain('mt-6');
  });

  it('o recuo próprio da página injetada é neutralizado pela moldura', () => {
    // A página de oportunidades ainda traz `p-4 md:p-8` de quando era rota
    // inteira. Somado ao recuo do Hub, o quadro de funis ficaria mais estreito
    // e mais baixo que as outras abas — quem manda no recuo é a moldura.
    montar('/trafego?aba=oportunidades');
    const painel = screen.getByRole('tabpanel');
    expect(painel.className).toContain('[&>div]:p-0');
    expect(within(painel).getByText('funis prontos')).toBeTruthy();
  });
});

// ── o grupo de conta ────────────────────────────────────────────────────────

describe('o grupo de conta identifica sem expor', () => {
  it('mascara o identificador no formato que o painel do Google usa', () => {
    expect(mascararConta('8017851692')).toBe('•••-•••-1692');
    expect(mascararConta('123-456-7890')).toBe('•••-•••-7890');
    // Identificador curto não vira palpite de formato: mascara o que dá.
    expect(mascararConta('98765')).toBe('•••8765');
    expect(mascararConta('12')).toBe('••');
  });

  it('o resumo mostra o mascarado; a expansão da campanha traz o completo', () => {
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Crédito Up');
    expect(within(grupo).getByText('•••-•••-1692')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /^BR - Maquininha de Cartão/ }));
    expect(screen.getByText(/conta 8017851692 · campanha 24155134757/)).toBeTruthy();
  });

  it('o botão da conta declara que pergunta à conta e que não altera campanha', () => {
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Crédito Up');
    const botao = within(grupo).getByRole('button', { name: /ler esta conta agora/ });
    const descricao = document.getElementById(botao.getAttribute('aria-describedby') ?? '');
    expect(descricao!.textContent).toMatch(/pergunta a esta conta o que ela tem agora/i);
    expect(descricao!.textContent).toMatch(/não altera campanha nenhuma/i);
  });

  it('o cabeçalho do grupo traz nome, quantidade, resultado da leitura e idade', () => {
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Crédito Up');
    expect(within(grupo).getByText('Crédito Up')).toBeTruthy();
    expect(within(grupo).getByText('3 campanhas')).toBeTruthy();
    expect(within(grupo).getByText('leitura recente')).toBeTruthy();
    expect(within(grupo).getAllByText(/lido há 6 min/).length).toBeGreaterThan(0);
  });

  it('a conta é o primeiro nível e recolhe a própria lista de campanhas', () => {
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Crédito Up');
    const alternador = within(grupo).getByRole('button', { name: /conta de anúncios.*Crédito Up/i });
    expect(alternador.getAttribute('aria-expanded')).toBe('true');
    expect(within(grupo).getByText('BR - Maquininha de Cartão')).toBeTruthy();
    fireEvent.click(alternador);
    expect(alternador.getAttribute('aria-expanded')).toBe('false');
    expect(within(grupo).queryByText('BR - Maquininha de Cartão')).toBeNull();
  });
});

// ── as colunas do monitor ───────────────────────────────────────────────────

describe('a tabela do monitor é comparativa de verdade', () => {
  it('estado e canal têm coluna própria, e a idade da medida também', () => {
    render(<InventarioDeCampanhas />);
    const linha = screen
      .getByRole('button', { name: /^BR - Maquininha de Cartão/ })
      .closest('tr')!;
    const celulas = Array.from(linha.children).map((c) => c.textContent ?? '');

    // Primeira coluna: o estado, isolado — é por ela que o olho desce quando a
    // pergunta é "quais estão pausadas?".
    expect(celulas[0]).toContain('ENABLED');
    expect(celulas[0]).toContain('entregando');
    expect(celulas[1]).toContain('BR - Maquininha de Cartão');
    expect(celulas[2]).toBe('busca');
    expect(celulas[3]).toBe('CPC manual');
    // Última coluna: a idade da medida, que qualifica os TRÊS números de
    // entrega e não só o custo debaixo do qual ela morava.
    expect(celulas[celulas.length - 1]).toContain('lido há 6 min');
  });

  it('a célula de estado não repete a mesma palavra três vezes', () => {
    // A conta manda `estado_externo: REMOVED` e `veiculacao: REMOVED` na mesma
    // campanha. Sem cuidado, a célula sai "REMOVED / removida / removida" — e
    // repetição assim treina o olho a pular a célula inteira, inclusive nas
    // linhas em que as duas palavras divergem e informam alguma coisa.
    leitura = {
      ...leituraBase,
      inventario: inventarioDeProva({
        contas: [
          {
            ...creditoUp,
            campanhas: [{ ...maquininha, estado_externo: 'REMOVED', veiculacao: 'REMOVED' }],
            quantidade: 1,
          },
        ],
        parcial: false,
        faltou: [],
      }),
    };
    render(<InventarioDeCampanhas />);
    const estado = screen
      .getByRole('button', { name: /^BR - Maquininha de Cartão/ })
      .closest('tr')!.children[0];
    expect((estado.textContent ?? '').match(/removida/g)?.length ?? 0).toBe(1);

    // E quando as duas DIVERGEM, as duas aparecem: "ligada" e "não entrega" na
    // mesma linha é a campanha que está no ar e fora do leilão.
    cleanup();
    leitura = {
      ...leituraBase,
      inventario: inventarioDeProva({
        contas: [
          {
            ...creditoUp,
            campanhas: [{ ...maquininha, estado_externo: 'ENABLED', veiculacao: 'NOT_SERVING' }],
            quantidade: 1,
          },
        ],
        parcial: false,
        faltou: [],
      }),
    };
    render(<InventarioDeCampanhas />);
    const divergente = screen
      .getByRole('button', { name: /^BR - Maquininha de Cartão/ })
      .closest('tr')!.children[0];
    expect(divergente.textContent).toContain('ENABLED');
    expect(divergente.textContent).toContain('não entrega');
  });

  it('as colunas de número alinham à direita, e só elas', () => {
    render(<InventarioDeCampanhas />);
    const cabecalhos = screen.getAllByRole('columnheader');
    const direita = cabecalhos
      .filter((th) => th.className.includes('text-right'))
      .map((th) => th.textContent);
    expect(direita).toEqual([
      'lance', 'orçamento diário', 'teto estimado', 'impressões', 'cliques', 'custo',
    ]);
  });

  it('a largura de cada coluna é declarada, para a tabela nunca vazar da página', () => {
    const { container } = render(<InventarioDeCampanhas />);
    const tabela = screen.getByRole('table');
    expect(tabela.className).toContain('table-fixed');

    const colunas = Array.from(container.querySelectorAll('colgroup col'));
    expect(colunas.length).toBe(screen.getAllByRole('columnheader').length);
    const soma = colunas.reduce(
      (total, col) => total + Number.parseFloat((col as HTMLElement).style.width),
      0,
    );
    expect(Math.round(soma)).toBe(100);

    // Rolagem lateral é o jeito de uma tabela caber sem caber: comparar custo
    // arrastando já é não conseguir comparar.
    for (const elemento of container.querySelectorAll('*')) {
      expect(elemento.className.toString()).not.toContain('overflow-x');
    }
  });

  it('a nova largura mínima do monitor é a que faz onze colunas caberem', () => {
    // A janela NÃO é a largura da tabela: a navegação lateral ocupa 320 px e o
    // recuo da página come mais 64. Em 1280 sobram ~900 px para onze colunas, e
    // o nome da campanha fica com menos de vinte caracteres visíveis.
    expect(densidadeDaLargura(1279)).toBe('media');
    expect(densidadeDaLargura(1439)).toBe('media');
    expect(densidadeDaLargura(1440)).toBe('ampla');
  });
});

describe('teto estimado: "não deu para calcular" e "não se aplica" são diferentes', () => {
  it('com lance manual e os dois valores, o número aparece com a conta que o gerou', () => {
    const r = tetoDaCampanha(maquininha);
    expect(r.texto).toBe('83');
    expect(r.explica).toMatch(/orçamento diário ÷ lance/);
  });

  it('com lance automático o teto NÃO É travessão: ele não se aplica', () => {
    // ⚠️ O travessão deste módulo significa uma coisa só — não foi possível
    // medir. Usá-lo para "não existe" faria a mesma marca responder a duas
    // perguntas opostas, e uma coluna cheia de travessões passaria a parecer
    // leitura furada quando está completa.
    const automatica = { ...maquininha, estrategia: 'MAXIMIZE_CONVERSIONS' as const, teto_de_cliques: null };
    const r = tetoDaCampanha(automatica);
    expect(r.texto).toBe('não se aplica');
    expect(r.texto).not.toBe('—');
  });

  it('faltando o lance ou o orçamento, aí sim é travessão', () => {
    const semLance = { ...fgts, lance_micros: null, teto_de_cliques: null };
    expect(tetoDaCampanha(semLance).texto).toBe('—');
    expect(tetoDaCampanha(semLance).explica).toMatch(/falta o lance ou o orçamento/);
  });

  it('a tela não calcula o teto por conta própria quando a leitura não o trouxe', () => {
    // `fgtsDeTeste` tem lance, orçamento e lance manual, e mesmo assim veio sem
    // teto. Dividir aqui produziria um número com aparência de medido.
    const r = tetoDaCampanha(fgtsDeTeste);
    expect(r.texto).toBe('—');
    expect(r.explica).toMatch(/esta tela não o calcula/);
  });
});

// ── telefone ────────────────────────────────────────────────────────────────

describe('no telefone, uma campanha por bloco e nada de arrasto', () => {
  it('a entrega vem antes da compra: primeiro o dinheiro que já saiu', () => {
    largura(TELEFONE);
    leitura = {
      ...leituraBase,
      inventario: inventarioDeProva({
        contas: [{ ...creditoUp, campanhas: [maquininha], quantidade: 1 }],
        parcial: false,
        faltou: [],
      }),
    };
    render(<InventarioDeCampanhas />);
    const bloco = screen.getByRole('listitem');
    const rotulos = Array.from(bloco.querySelectorAll('.kicker')).map((n) => n.textContent);
    expect(rotulos).toEqual([
      'impressões', 'cliques', 'custo', 'lance', 'orçamento diário', 'teto estimado', 'estratégia',
    ]);
  });

  it('todo alvo de toque tem pelo menos 44 px de altura no telefone', () => {
    largura(TELEFONE);
    render(<InventarioDeCampanhas />);
    // `h-11`/`min-h-11` é 2,75rem = 44px, o mínimo que o dedo acerta sem
    // ampliar. Os botões encolhem para `md:h-9` só a partir do tablet, onde
    // quem aponta é o ponteiro.
    for (const botao of screen.getAllByRole('button')) {
      expect(botao.className).toMatch(/\b(min-)?h-11\b/);
    }
  });

  it('e o botão do cabeçalho também, porque ele também é tocado', () => {
    largura(TELEFONE);
    montar();
    expect(screen.getByRole('button', { name: /Atualizar dados/ }).className).toMatch(
      /\bh-11\b/,
    );
  });

  it('o detalhe continua embutido — modal não é a primeira interação', () => {
    largura(TELEFONE);
    render(<InventarioDeCampanhas />);
    const botao = screen.getByRole('button', { name: /^BR - Maquininha de Cartão,/ });
    expect(botao.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(botao);
    expect(botao.getAttribute('aria-expanded')).toBe('true');
    expect(screen.queryByRole('dialog')).toBeNull();
    const detalhe = document.getElementById(botao.getAttribute('aria-controls') ?? '');
    expect(detalhe).toBeTruthy();
    expect(botao.closest('li')!.contains(detalhe!)).toBe(true);
  });
});

// ── a expansão ──────────────────────────────────────────────────────────────

describe('a expansão diz de onde o número veio e o que pesa contra ele', () => {
  it('herda a conta e a última leitura boa dela', () => {
    render(<InventarioDeCampanhas />);
    fireEvent.click(screen.getByRole('button', { name: /^BR - Maquininha de Cartão/ }));
    expect(screen.getByText('de onde vem este número')).toBeTruthy();
    expect(screen.getByText(/Crédito Up · •••-•••-1692/)).toBeTruthy();
    expect(screen.getByText(/última leitura boa desta conta/)).toBeTruthy();
  });

  it('sem ressalva nenhuma, diz que não há — em vez de deixar um espaço vazio', () => {
    render(<InventarioDeCampanhas />);
    fireEvent.click(screen.getByRole('button', { name: /^BR - Maquininha de Cartão/ }));
    expect(screen.getByText(/nenhuma — o que está na linha veio inteiro/)).toBeTruthy();
  });

  it('campanha nunca medida traz a ressalva, e sem repetir o que já tem campo', () => {
    render(<InventarioDeCampanhas />);
    fireEvent.click(
      screen.getByRole('button', { name: /^BR BR - FGTS Saque-Aniversário \(teste/ }),
    );
    expect(screen.getByText('esta campanha ainda não teve entrega medida')).toBeTruthy();
    // "sem painel próprio" já é dito no campo "onde continuar": repetido na
    // lista, o operador leria a mesma falta duas vezes e procuraria a segunda.
    expect(screen.getAllByText(/sem painel próprio/i).length).toBe(1);
  });
});
