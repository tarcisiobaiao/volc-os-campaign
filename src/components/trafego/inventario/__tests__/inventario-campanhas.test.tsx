// @vitest-environment jsdom
/**
 * Provas do inventário.
 *
 * O que se prova aqui é sobretudo o que a tela NÃO faz: não transforma
 * ausência em zero, não achata "conta vazia" e "conta nunca lida" no mesmo
 * vazio, não apaga o último dado bom quando a leitura nova falha, e não
 * comunica nenhum estado só por cor — toda asserção de estado é sobre TEXTO.
 *
 * As duas campanhas que precisam aparecer (Maquininha e FGTS) vêm da fixture
 * derivada do formato real. Nenhum componente conhece o nome delas.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';

import {
  BlocoDeEntrega,
  LinhaEmTabela,
} from '@/components/trafego/inventario/LinhaDeCampanha';
import { InventarioDeCampanhas } from '@/components/trafego/inventario/InventarioDeCampanhas';
import {
  fgts,
  fgtsDeTeste,
  inventarioDeProva,
  inventarioRenderavel,
  maquininha,
} from '@/components/trafego/inventario/fixtureDeProvas';

// ── dublês ──────────────────────────────────────────────────────────────────
// O hook é dublê para que a prova seja sobre a TELA, e não sobre a rede: aqui
// interessa o que o operador lê, dado um envelope conhecido.

const leituraBase: LeituraDoInventario = {
  inventario: inventarioDeProva(),
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

/**
 * O gatilho de uma campanha, procurado pelo NOME ACESSÍVEL.
 *
 * Casar pelo INÍCIO e não pela frase inteira é deliberado: o nome é calculado a
 * partir do conteúdo do botão, e esse conteúdo muda com a largura. Na tabela
 * ampla o botão carrega só o nome da campanha — estado, canal e veiculação têm
 * coluna própria, e a célula do nome é o `th scope="row"` que dá contexto a
 * todas elas. No telefone e na largura do meio não há essas colunas, então os
 * mesmos fatos voltam para dentro do botão, e o nome acessível cresce.
 *
 * A vírgula que separava nome e estado saiu do casamento por isso: ela existe
 * quando há algo depois do nome, e presa aqui a prova passaria a exigir que
 * sempre haja.
 */
function botaoDaCampanha(nome: string): HTMLElement {
  const escapado = nome.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // `(,|$)` e não só `^nome`: duas campanhas da fixture começam com o mesmo
  // prefixo ("… Saque-Aniversário" e "… Saque-Aniversário - Teste 2"), e uma
  // âncora só no início devolveria as duas. Na tabela ampla o nome acessível
  // termina no nome da campanha; nas outras larguras ele continua depois da
  // vírgula invisível.
  return screen.getByRole('button', { name: new RegExp(`^${escapado}(,|$)`) });
}

function largura(px: number) {
  Object.defineProperty(window, 'innerWidth', { value: px, writable: true, configurable: true });
}

const MONITOR = 1440;
const TABLET = 1024;
const TELEFONE = 390;

beforeEach(() => {
  leitura = { ...leituraBase, inventario: inventarioDeProva() };
  largura(MONITOR);
});
afterEach(cleanup);

// ── as duas campanhas ───────────────────────────────────────────────────────

describe('inventário — o que existe nas contas', () => {
  it('mostra as duas campanhas da conta, cada uma no seu grupo', () => {
    render(<InventarioDeCampanhas />);
    expect(screen.getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(screen.getByText('BR BR - FGTS Saque-Aniversário')).toBeTruthy();

    const grupo = screen.getByLabelText('conta Crédito Up');
    expect(within(grupo).getByText('BR - Maquininha de Cartão')).toBeTruthy();
    // O identificador da conta aparece MASCARADO no cabeçalho do grupo. Esta
    // tela é projetada em reunião e printada em relatório, e o nome da conta
    // mais os quatro últimos dígitos já respondem "em qual conta?". O
    // identificador inteiro continua a um clique, dentro da expansão da
    // campanha, para quem precisa copiá-lo.
    expect(within(grupo).getByText('•••-•••-1692')).toBeTruthy();
    expect(within(grupo).queryByText('8017851692')).toBeNull();
  });

  it('agrupa por conta e declara a idade da leitura de cada uma', () => {
    render(<InventarioDeCampanhas />);
    expect(screen.getByLabelText('conta Crédito Up')).toBeTruthy();
    expect(screen.getByLabelText('conta PMUNDO+')).toBeTruthy();
    expect(screen.getByLabelText('conta Portal Mundo Mais')).toBeTruthy();
    expect(screen.getAllByText(/lido há 6 min/).length).toBeGreaterThan(0);
  });

  it('nomeia o grupo sem conta em vez de exibir a chave sintética do servidor', () => {
    render(<InventarioDeCampanhas />);
    expect(screen.getByLabelText('conta Sem conta identificada')).toBeTruthy();
    expect(screen.queryByText('conta-nao-identificada')).toBeNull();
  });
});

// ── conta vazia ≠ conta nunca lida ──────────────────────────────────────────

describe('os vazios que não podem virar o mesmo vazio', () => {
  it('separa "respondeu e não tem nada" de "nunca foi lida"', () => {
    render(<InventarioDeCampanhas />);

    const lida = screen.getByLabelText('conta Portal Mundo Mais');
    expect(within(lida).getAllByText(/a conta respondeu e não há campanha nenhuma nela/i).length)
      .toBeGreaterThan(0);
    expect(within(lida).queryByText(/nunca lido/i)).toBeNull();
    expect(within(lida).queryByText(/ainda não perguntamos/i)).toBeNull();

    const nuncaLida = screen.getByLabelText('conta Sem conta identificada');
    expect(within(nuncaLida).getAllByText(/nunca lido/i).length).toBeGreaterThan(0);
  });

  it('a conta nunca lida diz o que falta fazer, não "nenhum resultado"', () => {
    leitura = {
      ...leituraBase,
      inventario: inventarioDeProva({
        contas: [
          {
            customer_id: '3849678045',
            nome: 'PMUNDO+',
            frescor: 'nunca_lido',
            leitura: null,
            ultima_leitura_boa: null,
            motivo: null,
            quantidade: 0,
            campanhas: [],
          },
        ],
        parcial: false,
        faltou: [],
      }),
    };
    render(<InventarioDeCampanhas />);
    // A frase aparece no selo e no vazio do grupo: o operador lê o mesmo fato
    // no rótulo e no lugar onde ele esperaria encontrar campanhas.
    expect(screen.getAllByText(/ainda não perguntamos nada a esta conta/i).length).toBe(2);
    expect(screen.getByText(/isso é diferente de saber que não tem/i)).toBeTruthy();
  });
});

// ── ausência é `null`, nunca zero ───────────────────────────────────────────

describe('ausência e zero são coisas diferentes', () => {
  it('zero medido aparece como 0 e vem colado à hora da leitura', () => {
    render(<BlocoDeEntrega campanha={maquininha} comRotulos />);
    expect(screen.getByText('1')).toBeTruthy();
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.getByText('R$ 0,00')).toBeTruthy();
    expect(screen.getByText('lido há 6 min')).toBeTruthy();
  });

  it('campanha nunca medida mostra travessão — e nenhum zero', () => {
    const { container } = render(<BlocoDeEntrega campanha={fgtsDeTeste} comRotulos />);
    expect(screen.getAllByText('—').length).toBe(3);
    expect(screen.queryByText('0')).toBeNull();
    expect(screen.getByText('ainda não medida')).toBeTruthy();
    expect(container.textContent).not.toContain('R$ 0,00');
  });

  it('recusa exibir medida que chega sem data de leitura', () => {
    // Não deveria acontecer — e é justamente por isso que a tela não confia:
    // um custo sem data é indistinguível de um custo de ontem.
    const semData = {
      ...maquininha,
      entrega: { ...maquininha.entrega, leitura: null },
    };
    render(<BlocoDeEntrega campanha={semData} />);
    expect(screen.getByText('medida sem data de leitura — não exibida')).toBeTruthy();
    expect(screen.queryByText('R$ 0,00')).toBeNull();
  });

  it('teto de cliques ausente não vira número inventado', () => {
    render(<BlocoDeEntrega campanha={fgtsDeTeste} />);
    expect(screen.queryByText('83')).toBeNull();
  });
});

// ── estados em palavras, não em cores ───────────────────────────────────────

describe('todo estado tem palavra, não só cor', () => {
  it('nomeia procedência, vínculo e presença em texto', () => {
    render(<InventarioDeCampanhas />);
    expect(screen.getAllByText('sem procedência').length).toBeGreaterThan(0);
    expect(screen.getAllByText('sem vínculo').length).toBeGreaterThan(0);
    expect(screen.getAllByText('registrada').length).toBeGreaterThan(0);
    expect(screen.getAllByText('legado não reconciliado').length).toBeGreaterThan(0);
    expect(screen.getAllByText('sincronização falhou').length).toBeGreaterThan(0);
  });

  it('cada selo carrega a frase do que ele afirma', () => {
    render(<InventarioDeCampanhas />);
    expect(
      screen.getAllByText(/não sabemos como esta campanha entrou no registro/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/não dá para afirmar presença nem ausência/i).length,
    ).toBeGreaterThan(0);
  });

  it('não usa a conclusão proibida "sumiu"', () => {
    const { container } = render(<InventarioDeCampanhas />);
    expect((container.textContent ?? '').toLowerCase()).not.toContain('sumiu');
  });

  it('não fala a língua da máquina com o operador', () => {
    const { container } = render(<InventarioDeCampanhas />);
    const texto = (container.textContent ?? '').toLowerCase();
    for (const proibido of ['gaql', 'postgrest', 'snapshot', 'payload', 'cursor']) {
      expect(texto).not.toContain(proibido);
    }
  });
});

// ── degradação honesta ──────────────────────────────────────────────────────

describe('falha de uma conta não contamina as outras', () => {
  it('declara o que faltou, com conta e motivo', () => {
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
  });

  it('preserva o último dado bom da conta que não respondeu', () => {
    render(<InventarioDeCampanhas />);
    const grupo = screen.getByLabelText('conta PMUNDO+');
    expect(within(grupo).getByText('BR - Consignado INSS')).toBeTruthy();
    expect(within(grupo).getAllByText(/última leitura boa há 7 h/).length).toBeGreaterThan(0);
  });

  it('quando a atualização falha por cima de dado bom, diz que é o antigo', () => {
    leitura = { ...leituraBase, falhou: true, motivoDaFalha: 'tempo esgotado' };
    render(<InventarioDeCampanhas />);
    expect(screen.getByText(/A atualização mais recente falhou/i)).toBeTruthy();
    expect(screen.getByText('BR - Maquininha de Cartão')).toBeTruthy();
  });

  it('sem nenhum dado guardado, a falha aparece inteira e oferece nova tentativa', () => {
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
    // O texto cru do erro não chega à tela; a frase do vocabulário fechado e o
    // código copiável tomam o lugar dele. Ver `erros.ts`.
    expect(screen.queryByText('a rede não respondeu')).toBeNull();
    expect(screen.getByText(/^VOLC-/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'tentar de novo' }));
    expect(tentar).toHaveBeenCalled();
  });
});

// ── carregamento e vazio geral ──────────────────────────────────────────────

describe('carregando e vazio', () => {
  it('carrega com a forma do conteúdo, não com um giro no meio da tela', () => {
    leitura = { ...leituraBase, inventario: null, carregando: true };
    const { container } = render(<InventarioDeCampanhas />);
    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.getByText('lendo o inventário das contas')).toBeTruthy();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(3);
  });

  it('o vazio ensina o que aquilo mostraria', () => {
    leitura = {
      ...leituraBase,
      inventario: inventarioDeProva({ contas: [], parcial: false, faltou: [] }),
    };
    render(<InventarioDeCampanhas />);
    expect(screen.getByText('Nenhuma conta no inventário')).toBeTruthy();
    expect(screen.getByText(/ficar vazio\s+não significa que as contas estejam vazias/i)).toBeTruthy();
  });
});

// ── expansão embutida e teclado ─────────────────────────────────────────────

describe('expansão embutida, com teclado', () => {
  it('a linha abre no lugar e anuncia o estado com aria-expanded', () => {
    render(<InventarioDeCampanhas />);
    const botao = botaoDaCampanha('BR - Maquininha de Cartão');

    expect(botao.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('abrir no Google Ads')).toBeNull();

    fireEvent.click(botao);
    expect(botao.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getAllByText('abrir no Google Ads').length).toBe(1);

    fireEvent.click(botao);
    expect(botao.getAttribute('aria-expanded')).toBe('false');
  });

  it('não abre em modal: o detalhe é apontado pelo próprio botão', () => {
    render(<InventarioDeCampanhas />);
    const botao = botaoDaCampanha('BR - Maquininha de Cartão');
    fireEvent.click(botao);
    const alvo = botao.getAttribute('aria-controls');
    expect(alvo).toBeTruthy();
    expect(document.getElementById(alvo as string)).toBeTruthy();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it('o gatilho é botão nativo, recebe foco e tem alvo de toque de 44px', () => {
    render(<InventarioDeCampanhas />);
    const botao = botaoDaCampanha('BR - Maquininha de Cartão');
    expect(botao.tagName).toBe('BUTTON');
    botao.focus();
    expect(document.activeElement).toBe(botao);
    expect(botao.className).toContain('min-h-11');
    expect(botao.className).toContain('focus-visible:ring-2');
  });

  it('o detalhe conta a linhagem a partir do que está carregado', () => {
    render(<InventarioDeCampanhas />);
    fireEvent.click(botaoDaCampanha('BR BR - FGTS Saque-Aniversário'));
    expect(screen.getByText('2 instâncias neste inventário')).toBeTruthy();
  });

  it('quando não há painel próprio, diz isso em vez de oferecer um link torto', () => {
    render(<InventarioDeCampanhas />);
    fireEvent.click(botaoDaCampanha('BR BR - FGTS Saque-Aniversário'));
    expect(screen.getByText(/sem painel próprio/i)).toBeTruthy();
  });
});

// ── as três larguras ────────────────────────────────────────────────────────

describe('monitor, tablet e telefone', () => {
  it('no monitor é tabela comparativa, com onze colunas rotuladas', () => {
    largura(MONITOR);
    render(<InventarioDeCampanhas />);
    expect(screen.getByRole('table')).toBeTruthy();
    const colunas = screen.getAllByRole('columnheader').map((th) => th.textContent);
    // Estado e canal ganharam coluna própria: dentro da célula do nome eles
    // começavam num ponto diferente em cada linha, e "quais estão pausadas?" só
    // se responde descendo o olho por uma coluna alinhada. A idade da medida
    // também saiu de baixo do custo e virou coluna, porque ela qualifica os
    // TRÊS números de entrega, não só o último.
    expect(colunas).toEqual([
      'estado', 'campanha', 'canal', 'estratégia', 'lance', 'orçamento diário',
      'teto estimado', 'impressões', 'cliques', 'custo', 'entrega lida',
    ]);
  });

  it('no tablet as colunas se FUNDEM — e nenhum valor é cortado', () => {
    largura(TABLET);
    leitura = { ...leituraBase, inventario: inventarioRenderavel() };
    render(<InventarioDeCampanhas />);

    const colunas = screen.getAllByRole('columnheader').map((th) => th.textContent);
    expect(colunas).toEqual(['campanha', 'compra', 'entrega', 'situação']);

    // Fundir é juntar, não esconder: os mesmos números continuam legíveis.
    const grupo = screen.getByLabelText('conta Crédito Up');
    expect(within(grupo).getAllByText('R$ 0,12').length).toBe(3);
    expect(within(grupo).getAllByText('R$ 10,00').length).toBe(3);
    // O teto some só onde ele não é calculável — não some com a coluna.
    expect(within(grupo).getAllByText('83').length).toBe(2);
    expect(within(grupo).getAllByText(/impressões/).length).toBeGreaterThan(0);
  });

  it('no telefone não há tabela nem grade de cartões: linhas altas em lista', () => {
    largura(TELEFONE);
    leitura = { ...leituraBase, inventario: inventarioRenderavel() };
    const { container } = render(<InventarioDeCampanhas />);

    expect(screen.queryByRole('table')).toBeNull();
    expect(container.querySelector('table')).toBeNull();
    expect(screen.getAllByRole('listitem').length).toBe(3);

    // Os mesmos fatos continuam na tela, agora com rótulo ao lado do valor.
    expect(screen.getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(screen.getAllByText('R$ 0,12').length).toBe(3);
    expect(screen.getAllByText(/lance/).length).toBeGreaterThan(0);
  });

  it('a expansão é embutida também no telefone', () => {
    largura(TELEFONE);
    leitura = { ...leituraBase, inventario: inventarioRenderavel() };
    render(<InventarioDeCampanhas />);
    const botao = botaoDaCampanha('BR - Maquininha de Cartão');
    fireEvent.click(botao);
    expect(botao.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getAllByText('abrir no Google Ads').length).toBe(1);
  });
});

// ── a linha isolada, sem a tela em volta ────────────────────────────────────

describe('linha de campanha', () => {
  it('mostra o estado do Google na palavra do Google, com a tradução ao lado', () => {
    render(
      <table>
        <tbody>
          <LinhaEmTabela
            campanha={fgts}
            aberta={false}
            aoAlternar={() => undefined}
            linhagens={{}}
            fundida={false}
          />
        </tbody>
      </table>,
    );
    expect(screen.getByText('ENABLED')).toBeTruthy();
    expect(screen.getByText(/ligada no Google/)).toBeTruthy();
    expect(screen.getByText('entregando')).toBeTruthy();
    expect(screen.getByText('busca')).toBeTruthy();
    expect(screen.getByText('CPC manual')).toBeTruthy();
  });
});
