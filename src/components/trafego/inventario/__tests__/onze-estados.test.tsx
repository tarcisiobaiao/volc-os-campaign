// @vitest-environment jsdom
/**
 * OS ONZE ESTADOS DO INVENTÁRIO, um por um, com prova de render.
 *
 * Esta tela existe para responder três perguntas antes de alguém gastar
 * dinheiro: o que existe, em que estado está, e quão recente é essa
 * informação. Cada um dos onze estados abaixo é uma resposta diferente para a
 * terceira pergunta, e a diferença entre eles é o produto inteiro — achatar
 * dois quaisquer num só é o defeito que este arquivo existe para impedir de
 * voltar.
 *
 * A ordem é a do enunciado, e o número está no nome de cada prova de propósito:
 * quem vier conferir a cobertura precisa conseguir contar até onze sem ler o
 * código.
 *
 * ⚠️ O décimo é o que costuma faltar. O servidor pode ganhar um estado novo
 * antes deste pacote ser publicado — é o que acontece entre um deploy e o
 * outro — e a tela precisa nomear o desconhecido E continuar mostrando as
 * outras linhas. Uma tela de conferência que se apaga inteira diante de uma
 * palavra que não conhece esconde as quarenta campanhas que estavam certas.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { QuadroDeAlertas } from '@/types/trafego';

import { InventarioDeCampanhas } from '@/components/trafego/inventario/InventarioDeCampanhas';
import { FilaDeAtencao } from '@/components/trafego/inventario/FilaDeAtencao';
import {
  alertaDaMaquininha,
  alertaDeSintomaDesconhecido,
  inventarioDeAusencias,
  inventarioDeEstadoDesconhecido,
  inventarioDeProva,
  inventarioSaudavel,
  inventarioVelho,
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

vi.mock('@/hooks/useInventario', () => ({
  useInventario: () => leitura,
  usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
}));

interface DubleDeNotificacoes {
  data: QuadroDeAlertas | null;
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => void;
}

let notificacoes: DubleDeNotificacoes = {
  data: quadroDeAlertasDeProva(),
  isLoading: false,
  isError: false,
  isFetching: false,
  error: null,
  refetch: vi.fn(),
};

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: () => notificacoes,
  INTERVALO_NOTIFICACOES_MS: 600000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

const MONITOR = 1440;
const TELEFONE = 390;

function largura(px: number) {
  Object.defineProperty(window, 'innerWidth', { value: px, writable: true, configurable: true });
}

beforeEach(() => {
  leitura = { ...leituraBase, inventario: inventarioSaudavel() };
  notificacoes = {
    data: quadroDeAlertasDeProva(),
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  };
  largura(MONITOR);
  document.documentElement.classList.remove('dark');
});
afterEach(cleanup);

// ── 1 · carregando ──────────────────────────────────────────────────────────

describe('1 · carregando', () => {
  it('mostra a FORMA do que vem, e não um giro no meio da tela', () => {
    leitura = { ...leituraBase, inventario: null, carregando: true };
    const { container } = render(<InventarioDeCampanhas />);

    const aviso = screen.getByRole('status');
    expect(within(aviso).getByText('lendo o inventário das contas')).toBeTruthy();
    expect(aviso.getAttribute('aria-live')).toBe('polite');
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(3);

    // O esqueleto respeita quem pediu menos movimento — e continua sendo
    // esqueleto, porque a informação está na forma, não na animação.
    for (const osso of container.querySelectorAll('.animate-pulse')) {
      expect(osso.className).toContain('motion-reduce:animate-none');
    }
  });
});

// ── 2 · vazio confirmado ────────────────────────────────────────────────────

describe('2 · vazio confirmado', () => {
  it('diz que a conta respondeu e não tem nada — um fato medido', () => {
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Portal Mundo Mais');
    expect(within(grupo).getAllByText('nenhuma campanha').length).toBeGreaterThan(0);
    expect(
      within(grupo).getByText(/a conta respondeu e não há campanha nenhuma nela. Isto é um fato medido/i),
    ).toBeTruthy();
    expect(within(grupo).queryByText(/nunca lido/i)).toBeNull();
  });
});

// ── 3 · nunca lido ──────────────────────────────────────────────────────────

describe('3 · nunca lido', () => {
  it('diz que ninguém perguntou nada — e que isso não é estar vazia', () => {
    leitura = { ...leituraBase, inventario: inventarioDeProva() };
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Sem conta identificada');
    expect(within(grupo).getAllByText('nunca lido').length).toBeGreaterThan(0);
    expect(
      within(grupo).getAllByText(/ainda não perguntamos nada a esta conta/i).length,
    ).toBeGreaterThan(0);
  });

  it('não anuncia idade de leitura para uma conta que nunca foi lida', () => {
    leitura = { ...leituraBase, inventario: inventarioDeProva() };
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Sem conta identificada');
    expect(within(grupo).queryByText(/^lido há/)).toBeNull();
    expect(within(grupo).queryByText(/^às /)).toBeNull();
  });
});

// ── 4 · falha parcial ───────────────────────────────────────────────────────

describe('4 · falha parcial', () => {
  it('nomeia a conta que não voltou e mantém as outras inteiras', () => {
    leitura = { ...leituraBase, inventario: inventarioDeProva() };
    render(<InventarioDeCampanhas />);

    expect(screen.getByText(/Leitura parcial/i)).toBeTruthy();
    // ⚠️ O `motivo` do servidor deixou de ser impresso: é coluna de texto livre
    // da tentativa de varredura, e a própria frase padrão do backend diz "o
    // dado abaixo é o último snapshot bom" — vocabulário de máquina chegando à
    // tela por um campo de nome inofensivo. O que faltou continua nomeado, pelo
    // campo estruturado (`escopo`), traduzido.
    expect(screen.queryByText(/varredura/i)).toBeNull();
    expect(screen.getByText(/não foi possível ler esta conta por inteiro/i)).toBeTruthy();
    expect(screen.getByText(/Nada foi apagado/i)).toBeTruthy();

    // A conta que falhou continua com o último dado bom, com a idade dele.
    const falha = screen.getByLabelText('conta PMUNDO+');
    expect(within(falha).getByText('BR - Consignado INSS')).toBeTruthy();
    expect(within(falha).getAllByText(/última leitura boa há 7 h/).length).toBeGreaterThan(0);

    // E a conta saudável ao lado não foi contaminada por ela.
    const boa = screen.getByLabelText('conta Crédito Up');
    expect(within(boa).getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(within(boa).getAllByText('leitura recente').length).toBeGreaterThan(0);
  });
});

// ── 5 · erro total ──────────────────────────────────────────────────────────

describe('5 · erro total', () => {
  it('sem nada guardado, a falha aparece inteira, com motivo e saída', () => {
    const tentar = vi.fn();
    leitura = {
      ...leituraBase,
      inventario: null,
      falhou: true,
      motivoDaFalha: 'a rede não respondeu',
      recarregar: tentar,
    };
    render(<InventarioDeCampanhas />);

    expect(screen.getByText('Não consegui ler o inventário')).toBeTruthy();
    // ⚠️ O texto cru do erro NÃO chega mais aqui — nem quando ele é inofensivo.
    //
    // `motivoDaFalha` já foi `error.message`, e esse `message` nasce no cliente
    // HTTP para quem conserta o sistema: URL do backend, nome de variável de
    // ambiente, `detail` do servidor com exceção recortada. Deixar passar "a
    // rede não respondeu" porque essa frase específica é aceitável obrigaria
    // cada frase futura a ser auditada uma a uma. O vocabulário é fechado: o
    // que não está nele é descartado e vira a frase do caso não previsto.
    expect(screen.queryByText('a rede não respondeu')).toBeNull();
    expect(
      screen.getByText('A leitura não terminou, e o sistema não soube dizer por quê.'),
    ).toBeTruthy();
    expect(
      screen.getByText(/O que está nas contas de anúncio não mudou por causa disto/i),
    ).toBeTruthy();
    // A frase curta sozinha é beco sem saída para quem for investigar: o código
    // é o que liga o que o operador viu ao que ficou registrado do outro lado.
    expect(screen.getByText(/^VOLC-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}$/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'copiar código' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'tentar de novo' })).toBeTruthy();
  });
});

// ── 6 · dado velho ──────────────────────────────────────────────────────────

describe('6 · dado velho', () => {
  it('o número continua na tela, e a idade dele vem junto', () => {
    leitura = { ...leituraBase, inventario: inventarioVelho() };
    render(<InventarioDeCampanhas />);

    expect(screen.getByText(/Estes números são da última leitura boa, há 9 h/)).toBeTruthy();
    expect(screen.getByText(/Confira a idade de cada conta antes de decidir gasto/)).toBeTruthy();

    const grupo = screen.getByLabelText('conta Crédito Up');
    expect(within(grupo).getAllByText('leitura antiga').length).toBeGreaterThan(0);
    expect(within(grupo).getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(within(grupo).getAllByText(/lido há 9 h/).length).toBeGreaterThan(0);
  });

  it('velho não é falha: a tela não acusa problema onde só passou tempo', () => {
    leitura = { ...leituraBase, inventario: inventarioVelho() };
    const { container } = render(<InventarioDeCampanhas />);
    expect(container.textContent).not.toContain('A atualização mais recente falhou');
    expect(screen.queryByText(/Leitura parcial/i)).toBeNull();
  });
});

// ── 7 · campanha removida ───────────────────────────────────────────────────

describe('7 · campanha removida', () => {
  it('a conta declara removida, e a tela repete a declaração sem concluir nada', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    render(<InventarioDeCampanhas />);

    expect(screen.getByText('BR - Maquininha de Cartão (primeira versão)')).toBeTruthy();
    expect(screen.getAllByText('removida').length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/a conta respondeu e declara esta campanha como removida/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText('REMOVED').length).toBeGreaterThan(0);
  });

  it('removida ainda mostra o que gastou, porque o gasto aconteceu', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    render(<InventarioDeCampanhas />);
    expect(screen.getAllByText('R$ 1,14').length).toBeGreaterThan(0);
  });
});

// ── 8 · campanha não encontrada ─────────────────────────────────────────────

describe('8 · campanha não encontrada', () => {
  it('afirma que a LEITURA foi boa e a campanha não estava nela', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    render(<InventarioDeCampanhas />);

    expect(screen.getAllByText('não encontrada').length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/a conta foi lida com sucesso e esta campanha não estava na resposta/i)
        .length,
    ).toBeGreaterThan(0);
  });

  it('não conclui sumiço, e não confunde com sincronização falhou', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    const { container } = render(<InventarioDeCampanhas />);
    const texto = (container.textContent ?? '').toLowerCase();
    expect(texto).not.toContain('sumiu');
    expect(texto).not.toContain('sincronização falhou');
  });

  it('sem medida nenhuma, mostra travessão — nunca zero', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    render(<InventarioDeCampanhas />);
    const linha = screen
      .getByText('BR - Empréstimo Consignado (não veio na leitura)')
      .closest('tr');
    expect(linha).toBeTruthy();
    expect(within(linha as HTMLElement).getAllByText('—').length).toBeGreaterThan(0);
    expect(within(linha as HTMLElement).queryByText('0')).toBeNull();
  });
});

// ── 9 · conta não identificada ──────────────────────────────────────────────

describe('9 · conta não identificada', () => {
  it('diz que a linha existe e que não se sabe onde procurá-la', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    render(<InventarioDeCampanhas />);

    expect(screen.getByText('BR - Cartão de Crédito (sem conta vinculada)')).toBeTruthy();
    expect(screen.getAllByText('conta não identificada').length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/sem conta utilizável — não sabemos onde procurar/i).length,
    ).toBeGreaterThan(0);
  });

  it('o grupo tem nome de gente, e a chave sintética do servidor não vaza', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    render(<InventarioDeCampanhas />);
    expect(screen.getByLabelText('conta Sem conta identificada')).toBeTruthy();
    expect(screen.queryByText('conta-nao-identificada')).toBeNull();
  });

  it('e não oferece "ler esta conta agora" para uma conta que não existe', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta Sem conta identificada');
    expect(within(grupo).queryByRole('button', { name: /ler esta conta agora/ })).toBeNull();
  });
});

// ── 10 · estado desconhecido vindo do servidor ──────────────────────────────

describe('10 · estado que o servidor conhece e este pacote não', () => {
  it('nomeia o desconhecido em vez de sumir com a linha', () => {
    leitura = { ...leituraBase, inventario: inventarioDeEstadoDesconhecido() };
    render(<InventarioDeCampanhas />);

    expect(screen.getByText('BR - Portabilidade (estado novo do servidor)')).toBeTruthy();
    expect(screen.getAllByText('presença não reconhecida').length).toBeGreaterThan(0);
    expect(screen.getAllByText('procedência não reconhecida').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/em_revisao_de_politica/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/importada_do_parceiro/).length).toBeGreaterThan(0);
  });

  it('canal, estratégia e estado externo desconhecidos aparecem, não somem', () => {
    leitura = { ...leituraBase, inventario: inventarioDeEstadoDesconhecido() };
    render(<InventarioDeCampanhas />);

    // Antes, `MAPA[valor]` devolvia `undefined` e o JSX simplesmente não
    // desenhava nada: uma campanha de canal novo ficava indistinguível de uma
    // campanha sem canal. Silêncio é a pior resposta possível nesta tela.
    expect(screen.getByText('canal hotel (não reconhecido)')).toBeTruthy();
    expect(screen.getByText('target_roas (estratégia não reconhecida)')).toBeTruthy();
    expect(screen.getByText('limited_by_policy (não reconhecida)')).toBeTruthy();
    // ⚠️ O estado externo desconhecido continua VISÍVEL, e deixou de ser a
    // PALAVRA do selo. O vocabulário da conta de anúncio inclui `UNSPECIFIED` e
    // `UNKNOWN`; imprimir um deles como se fosse o estado da campanha põe
    // vocabulário de máquina exatamente onde o operador procura a resposta — e
    // ainda por cima uma palavra que ele não vai achar no painel do Google para
    // conferir. Agora o selo diz que não reconhece, e nomeia o que recebeu.
    expect(screen.getByText('estado não reconhecido')).toBeTruthy();
    expect(screen.getByText(/PENDING_REVIEW/)).toBeTruthy();
  });

  it('as outras linhas continuam inteiras ao lado da desconhecida', () => {
    leitura = { ...leituraBase, inventario: inventarioDeEstadoDesconhecido() };
    render(<InventarioDeCampanhas />);
    expect(screen.getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(screen.getByText('BR BR - FGTS Saque-Aniversário')).toBeTruthy();
    expect(screen.getAllByText('R$ 0,12').length).toBeGreaterThan(0);
  });

  it('frescor desconhecido NUNCA degrada para recente', () => {
    leitura = { ...leituraBase, inventario: inventarioDeEstadoDesconhecido() };
    render(<InventarioDeCampanhas />);

    expect(screen.getByText(/O servidor descreveu esta leitura como/)).toBeTruthy();
    expect(screen.getAllByText(/sincronizando_em_lote/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Trate os números abaixo como de idade desconhecida/)).toBeTruthy();
    expect(screen.queryByText('leitura recente')).toBeNull();
  });

  it('releitura falhada E frescor desconhecido: as duas coisas são ditas', () => {
    // São fatos independentes, e cabem na mesma tela ao mesmo tempo. Contar só
    // o que apareceu primeiro deixaria o operador com metade da explicação
    // justamente no caso mais confuso dos dois.
    leitura = {
      ...leituraBase,
      inventario: inventarioDeEstadoDesconhecido(),
      falhou: true,
      motivoDaFalha: 'tempo esgotado',
    };
    render(<InventarioDeCampanhas />);
    expect(screen.getByText(/A atualização mais recente falhou/)).toBeTruthy();
    expect(screen.getByText(/O servidor descreveu esta leitura como/)).toBeTruthy();
    expect(screen.getByText(/Trate os números abaixo como de idade desconhecida/)).toBeTruthy();
  });

  it('vazio de frescor desconhecido não vira "a conta respondeu e não tem nada"', () => {
    const inventario = inventarioDeEstadoDesconhecido();
    leitura = {
      ...leituraBase,
      inventario: {
        ...inventario,
        contas: [{ ...inventario.contas[0], campanhas: [], quantidade: 0 }],
      },
    };
    render(<InventarioDeCampanhas />);
    expect(screen.getByText('estado de leitura não reconhecido')).toBeTruthy();
    expect(
      screen.getByText(/Não dá para dizer se esta conta está vazia ou se a leitura não voltou/i),
    ).toBeTruthy();
    expect(screen.queryByText(/Isto é um fato medido/i)).toBeNull();
  });

  it('na fila de atenção, condição nova não apaga os outros grupos', () => {
    notificacoes = {
      ...notificacoes,
      data: quadroDeAlertasDeProva({
        alertas: [alertaDaMaquininha, alertaDeSintomaDesconhecido],
        verificadas: 2,
      }),
    };
    render(<FilaDeAtencao foco={null} />);

    expect(screen.getByText('ligada e sem impressão')).toBeTruthy();
    expect(screen.getByText('condição não reconhecida')).toBeTruthy();
    expect(screen.getByText(/orcamento_esgotado/)).toBeTruthy();
    expect(screen.getByText(/o que falta aqui é a frase, não o fato/i)).toBeTruthy();
  });
});

// ── 11 · claro E escuro ─────────────────────────────────────────────────────

describe('11 · claro e escuro', () => {
  it('o mesmo fato é legível nos dois temas, palavra por palavra', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };

    const claro = render(<InventarioDeCampanhas />).container.textContent;
    cleanup();

    document.documentElement.classList.add('dark');
    const escuro = render(<InventarioDeCampanhas />).container.textContent;

    // O estado não muda de nome ao mudar o tema porque ele nunca foi cor: é
    // glifo mais palavra mais descrição, e as três atravessam o tema intactas.
    expect(escuro).toBe(claro);
    expect(escuro).toContain('não encontrada');
    expect(escuro).toContain('removida');
  });

  it('nenhuma cor fixa: toda tinta desta pasta vem dos tokens do tema', () => {
    // Um `#D32F2F` cravado aqui pareceria certo no claro e sumiria no escuro —
    // e a checagem seria manual para sempre. Os tokens em `src/index.css` já
    // trocam de valor entre os temas; o que esta prova impede é alguém
    // desviar deles.
    const pasta = join(process.cwd(), 'src/components/trafego/inventario');
    const arquivos = readdirSync(pasta).filter((f) => f.endsWith('.tsx'));
    expect(arquivos.length).toBeGreaterThan(4);

    const proibidos = [
      /#[0-9a-fA-F]{3,8}\b/,
      /\brgba?\(/,
      /\bhsla?\(/,
      /\b(?:text|bg|border)-(?:white|black)\b/,
      /\b(?:text|bg|border)-(?:slate|gray|zinc|neutral|stone|red|green|blue|amber|yellow|emerald)-\d{2,3}\b/,
    ];

    for (const arquivo of arquivos) {
      const fonte = readFileSync(join(pasta, arquivo), 'utf8');
      for (const proibido of proibidos) {
        expect(
          proibido.test(fonte),
          `${arquivo} usa cor fora dos tokens do tema: ${proibido}`,
        ).toBe(false);
      }
    }
  });

  it('todo selo de estado carrega palavra e descrição, não só o glifo', () => {
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    const { container } = render(<InventarioDeCampanhas />);

    const selos = container.querySelectorAll('[title]');
    expect(selos.length).toBeGreaterThan(5);
    for (const selo of selos) {
      const titulo = selo.getAttribute('title') ?? '';
      // O `title` do selo é sempre "palavra — o que ela afirma". Um selo que
      // chegasse só com a palavra estaria comunicando pelo desenho.
      if (!titulo.includes(' — ')) continue;
      const [palavra, descricao] = titulo.split(' — ');
      expect(palavra.trim().length).toBeGreaterThan(0);
      expect(descricao.trim().length).toBeGreaterThan(10);
      expect((selo.textContent ?? '').trim().length).toBeGreaterThan(0);
    }
  });
});

// ── monitor e telefone, com os estados dentro ───────────────────────────────

describe('as mesmas onze respostas nas duas formas', () => {
  it('no telefone é lista, sem tabela e sem arrasto lateral', () => {
    largura(TELEFONE);
    leitura = { ...leituraBase, inventario: inventarioDeAusencias() };
    const { container } = render(<InventarioDeCampanhas />);

    expect(container.querySelector('table')).toBeNull();
    expect(screen.getAllByRole('listitem').length).toBe(4);

    // Rolagem horizontal é o jeito de uma tabela caber num telefone sem caber:
    // comparar custo arrastando já é não conseguir comparar.
    for (const elemento of container.querySelectorAll('*')) {
      expect(elemento.className.toString()).not.toContain('overflow-x-auto');
    }

    // E os estados continuam nomeados, não abreviados por falta de espaço.
    expect(screen.getAllByText('não encontrada').length).toBeGreaterThan(0);
    expect(screen.getAllByText('conta não identificada').length).toBeGreaterThan(0);
  });

  it('no telefone o estado desconhecido também tem nome', () => {
    largura(TELEFONE);
    leitura = { ...leituraBase, inventario: inventarioDeEstadoDesconhecido() };
    render(<InventarioDeCampanhas />);
    expect(screen.getAllByText('presença não reconhecida').length).toBeGreaterThan(0);
    expect(screen.getByText('canal hotel (não reconhecido)')).toBeTruthy();
  });
});
