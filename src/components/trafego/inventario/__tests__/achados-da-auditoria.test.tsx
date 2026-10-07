// @vitest-environment jsdom
/**
 * Os achados da auditoria, um a um, fechados com prova.
 *
 * Cada `describe` abaixo nomeia o arquivo e a linha onde o defeito morava. Não
 * é homenagem ao bug: é o único jeito de quem reabrir isto daqui a seis meses
 * saber que a asserção estranha tem uma história, e que apagá-la reabre uma
 * porta que já esteve aberta.
 *
 * Sete dos oito têm a mesma raiz: uma regra que valia em UM caminho e não nos
 * outros. Frescor exigido no bloco de entrega e não na tabela ampla; ausência
 * declarada no valor e não na unidade; vocabulário tolerante no selo e não no
 * canal. Regra que depende de cada componente lembrar dela já foi perdida — por
 * isso as correções mudaram o lugar da decisão, e não só o sintoma.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { computeAccessibleName } from 'dom-accessibility-api';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { QuadroDeAlertas } from '@/types/trafego';
import { leituraMaisVelha, mesclarPaginas } from '@/hooks/useInventario';

import HubDeTrafegoPage from '@/pages/trafego/HubDeTrafegoPage';
import { FilaDeAtencao } from '@/components/trafego/inventario/FilaDeAtencao';
import { InventarioDeCampanhas } from '@/components/trafego/inventario/InventarioDeCampanhas';
import { LinhaEmTabela } from '@/components/trafego/inventario/LinhaDeCampanha';
import {
  PRESENCA,
  dinheiro,
  presencaLegivel,
} from '@/components/trafego/inventario/formato';
import {
  creditoUp,
  fgts,
  inventarioDeProva,
  inventarioRenderavel,
  maquininha,
  portalMundoMais,
  quadroDeAlertasDeProva,
} from '@/components/trafego/inventario/fixtureDeProvas';

// ⚠️ `{ wrapper: MemoryRouter }` nas montagens avulsas.
//
// As linhas do inventário navegam com `<Link>` para rotas DESTE aplicativo
// (`/trafego/campanhas/:id`, `/dashboard/campaign/:id`), e `<Link>` fora de um
// roteador lança. Antes eram `<a href>`: renderizavam em qualquer lugar e
// cobravam ao operador uma recarga de documento inteiro — o teste passava
// justamente porque a navegação era a errada.
//
// As montagens que já têm a própria moldura (`montar()`) continuam sem o
// wrapper: dois roteadores aninhados lançam igual.


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

vi.mock('@/hooks/useInventario', async (original) => {
  const real = await original<typeof import('@/hooks/useInventario')>();
  return {
    ...real,
    useInventario: () => leitura,
    usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
  };
});

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

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

/**
 * O dublê de `TrafegoPage` traz o CABEÇALHO DE PÁGINA que a página real tem.
 *
 * Um dublê que devolvesse só `<div>quadro</div>` esconderia exatamente o
 * defeito em prova: o Hub montava a página inteira dentro da aba, e o título
 * "Tráfego" aparecia duas vezes. Dublê que apaga a característica sob teste é
 * uma prova que passa sozinha.
 */
vi.mock('@/pages/trafego/TrafegoPage', () => ({
  default: () => (
    <div className="p-4 md:p-8">
      <div className="kicker">compra de tráfego</div>
      <h1>Tráfego</h1>
      <div>quadro de oportunidades</div>
    </div>
  ),
}));

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
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
});
afterEach(cleanup);

// ── 1 ───────────────────────────────────────────────────────────────────────

describe('LinhaDeCampanha:414 — a regra A não valia na tabela ampla', () => {
  const semData = {
    ...maquininha,
    entrega: { ...maquininha.entrega, impressoes: 812, cliques: 19, custo_micros: 47_310_000, leitura: null },
  };

  function tabela(fundida: boolean) {
    return render(
      <table>
        <tbody>
          <LinhaEmTabela
            campanha={semData}
            aberta={false}
            aoAlternar={() => undefined}
            linhagens={{}}
            fundida={fundida}
          />
        </tbody>
      </table>,
    );
  }

  it('a forma padrão do monitor recusa o número que chegou sem data', () => {
    const { container } = tabela(false);
    expect(screen.getByText(/medida sem data de leitura/)).toBeTruthy();
    expect(container.textContent).not.toContain('812');
    expect(container.textContent).not.toContain('19');
    expect(container.textContent).not.toContain('47,31');
  });

  it('e não escreve mais "ainda não medida" embaixo de um número', () => {
    const { container } = tabela(false);
    // A contradição antiga: três números na linha e a legenda dizendo que nada
    // foi medido. Quem lê a linha acredita no número, não na legenda.
    expect(container.textContent).not.toContain('ainda não medida');
  });

  it('a largura do meio já recusava, e continua recusando', () => {
    const { container } = tabela(true);
    expect(screen.getByText(/medida sem data de leitura/)).toBeTruthy();
    expect(container.textContent).not.toContain('812');
  });

  it('com data, os três números aparecem e a idade vem junto', () => {
    render(
      <table>
        <tbody>
          <LinhaEmTabela
            campanha={maquininha}
            aberta={false}
            aoAlternar={() => undefined}
            linhagens={{}}
            fundida={false}
          />
        </tbody>
      </table>,
    );
    expect(screen.getByText('R$ 0,00')).toBeTruthy();
    expect(screen.getByText('lido há 6 min')).toBeTruthy();
  });
});

// ── 2 ───────────────────────────────────────────────────────────────────────

describe('FilaDeAtencao:62 — o foco reaplicava sozinho a cada releitura', () => {
  const FOCO = '8017851692-24155134757';

  it('foca uma vez quando o sino manda para cá', () => {
    render(<FilaDeAtencao foco={FOCO} />);
    expect(document.activeElement).toBe(document.getElementById(`alerta-${FOCO}`));
  });

  it('não rouba o cursor quando a consulta se repete sozinha', () => {
    const { rerender } = render(<FilaDeAtencao foco={FOCO} />);
    expect(document.activeElement).toBe(document.getElementById(`alerta-${FOCO}`));

    // O operador saiu de onde o sino o deixou e foi trabalhar noutro controle.
    const outro = screen.getByRole('button', { name: /conferir de novo/ });
    outro.focus();
    expect(document.activeElement).toBe(outro);

    // O React Query relê sozinho no intervalo e ao voltar o foco para a aba, e
    // devolve um OBJETO NOVO com o mesmo conteúdo. Era esta identidade nova que
    // reexecutava o efeito e arrancava o cursor de onde ele estivesse.
    notificacoes = { ...notificacoes, data: quadroDeAlertasDeProva() };
    rerender(<FilaDeAtencao foco={FOCO} />);

    expect(document.activeElement).toBe(outro);
  });

  it('um foco NOVO no endereço volta a mover o cursor', () => {
    const { rerender } = render(<FilaDeAtencao foco={FOCO} />);
    const outro = screen.getByRole('button', { name: /conferir de novo/ });
    outro.focus();

    const segundo = '8017851692-24156373085';
    rerender(<FilaDeAtencao foco={segundo} />);
    expect(document.activeElement).toBe(document.getElementById(`alerta-${segundo}`));
  });
});

// ── 3 ───────────────────────────────────────────────────────────────────────

describe('HubDeTrafegoPage:148 — o cabeçalho aparecia duas vezes', () => {
  function montar(props: React.ComponentProps<typeof HubDeTrafegoPage> = {}) {
    return render(
      <MemoryRouter initialEntries={['/trafego?aba=oportunidades']}>
        <HubDeTrafegoPage {...props} />
      </MemoryRouter>,
    );
  }

  it('sem a prop, a aba Oportunidades tem UM título de página, não dois', () => {
    montar();
    // Dois `<h1>` numa página só não são redundância visual: são dois títulos
    // de documento, e a estrutura deixa de dizer a quem ouve onde ele está.
    expect(screen.getAllByRole('heading', { level: 1, name: 'Tráfego' }).length).toBe(1);
    expect(screen.getAllByText('compra de tráfego').length).toBe(1);
    expect(screen.getByText('quadro de oportunidades')).toBeTruthy();
  });

  it('com o conteúdo já sem moldura, o cabeçalho volta a ser do Hub', () => {
    montar({ oportunidades: <div>funis prontos</div> });
    const titulo = screen.getByRole('heading', { level: 1, name: 'Tráfego' });
    expect(titulo).toBeTruthy();
    expect(screen.getByText(/Todo\s+número traz a hora em que foi lido/)).toBeTruthy();
    expect(screen.getByText('funis prontos')).toBeTruthy();
    expect(screen.queryByText('quadro de oportunidades')).toBeNull();
  });

  it('nas outras abas o cabeçalho é sempre do Hub', () => {
    render(
      <MemoryRouter initialEntries={['/trafego']}>
        <HubDeTrafegoPage />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole('heading', { level: 1, name: 'Tráfego' }).length).toBe(1);
    expect(screen.getByText(/Controle campanhas, criação e decisões de mídia/)).toBeTruthy();
  });
});

// ── 4 ───────────────────────────────────────────────────────────────────────

describe('formato:39 — dinheiro sem moeda devolvia número puro', () => {
  it('o valor sai com a falta da unidade dita ao lado', () => {
    expect(dinheiro(120_000, null)).toBe('0,12 (sem moeda declarada)');
    expect(dinheiro(null, null)).toBe('—');
  });

  it('e a falta chega à célula, não só à função', () => {
    const semMoeda = {
      ...fgts,
      volc_campaign_id: 'vc_sem_moeda',
      entrega: { ...fgts.entrega, moeda: null },
    };
    render(
      <table>
        <tbody>
          <LinhaEmTabela
            campanha={semMoeda}
            aberta={false}
            aoAlternar={() => undefined}
            linhagens={{}}
            fundida={false}
          />
        </tbody>
      </table>,
    );
    expect(screen.getAllByText(/sem moeda declarada/).length).toBeGreaterThan(0);
    expect(screen.queryByText('R$ 0,12')).toBeNull();
  });
});

// ── 5 ───────────────────────────────────────────────────────────────────────

describe('LinhaDeCampanha:223 — o aria-label substituía o nome calculado', () => {
  /**
   * ⚠️ ESTE BLOCO MUDOU DE FORMA, E NÃO DE INTENÇÃO.
   *
   * O defeito original era um `aria-label` escrito à mão no gatilho: como
   * `aria-label` SUBSTITUI o nome calculado, tudo que a linha mostrava e a frase
   * não repetia — a descrição do selo, o aviso de estado não lido — sumia para
   * quem usa leitor de tela. A correção foi apagar o `aria-label` e deixar o
   * nome vir do conteúdo.
   *
   * O que mudou depois: na tabela ampla, estado, veiculação e canal saíram de
   * dentro do botão e ganharam coluna própria. O botão passou a carregar só o
   * nome — e é assim que tem de ser numa tabela, porque a célula do nome é o
   * `th scope="row"` da linha e o leitor de tela anuncia "nome da campanha,
   * estado, ENABLED — ligada no Google" ao entrar na célula do estado. O fato
   * não saiu do ouvido; ele passou a ser anunciado com o rótulo da coluna junto.
   *
   * Por isso a prova agora tem dois lados: nenhum `aria-label` em lugar nenhum
   * da linha (o defeito é impossível por construção), e o estado legível como
   * TEXTO na mesma linha — no monitor, na célula própria; no telefone, dentro do
   * nome, que é onde ele volta a morar quando não há coluna.
   */
  function largura(px: number) {
    Object.defineProperty(window, 'innerWidth', { value: px, writable: true, configurable: true });
  }

  function botao() {
    render(<InventarioDeCampanhas />, { wrapper: MemoryRouter });
    return screen.getByRole('button', { name: /^BR - Maquininha de Cartão/ });
  }

  it('o gatilho não tem aria-label: o nome vem do que está na tela', () => {
    expect(botao().getAttribute('aria-label')).toBeNull();
  });

  it('e nada na linha inteira carrega rótulo escrito à mão', () => {
    // Mais forte que a prova original: não é só o gatilho que não pode ter uma
    // segunda fonte de rótulo — é a linha toda. Duas fontes para o mesmo nome
    // divergem no primeiro selo novo que alguém esquecer de repetir.
    const alvo = botao();
    const linha = alvo.closest('tr');
    expect(linha).toBeTruthy();
    expect(linha!.querySelectorAll('[aria-label]').length).toBe(0);
  });

  it('e o estado que o olho vê agora também é o que o ouvido ouve', () => {
    const alvo = botao();
    expect(computeAccessibleName(alvo)).toContain('BR - Maquininha de Cartão');

    const linha = alvo.closest('tr')!;
    const texto = linha.textContent ?? '';
    // A palavra do Google, o que ela afirma, a veiculação e o canal — os quatro
    // continuam na linha, em texto, e não dependem de cor nem de glifo.
    expect(texto).toContain('ENABLED');
    expect(texto).toContain('ligada no Google');
    expect(texto).toContain('entregando');
    expect(texto).toContain('busca');
  });

  it('no telefone, onde não há coluna de estado, ele volta para dentro do nome', () => {
    largura(390);
    render(<InventarioDeCampanhas />, { wrapper: MemoryRouter });
    const nome = computeAccessibleName(
      screen.getByRole('button', { name: /^BR - Maquininha de Cartão,/ }),
    );
    expect(nome).toContain('ENABLED');
    expect(nome).toContain('ligada no Google');
    expect(nome).toContain('entregando');
    expect(nome).toContain('busca');
    // O ponto médio é decoração e não é lido; a vírgula invisível é o que
    // impede "Maquininha de CartãoENABLEDentregandobusca".
    expect(nome).not.toContain('·');
    expect(nome).toContain(',');
  });

  it('estado não lido aparece na linha em vez de virar silêncio', () => {
    const semEstado = { ...maquininha, estado_externo: null, veiculacao: null };
    leitura = {
      ...leituraBase,
      inventario: inventarioDeProva({
        contas: [{ ...creditoUp, campanhas: [semEstado], quantidade: 1 }],
        parcial: false,
        faltou: [],
      }),
    };
    render(<InventarioDeCampanhas />, { wrapper: MemoryRouter });
    const alvo = screen.getByRole('button', { name: /^BR - Maquininha de Cartão/ });
    expect(alvo.closest('tr')!.textContent).toContain('estado não lido');
  });
});

// ── 6 ───────────────────────────────────────────────────────────────────────

describe('LinhaDeCampanha:249 — "1 instância" era um chute, não uma contagem', () => {
  function abrir(linhagens: Record<string, number>) {
    render(
      <table>
        <tbody>
          <LinhaEmTabela
            campanha={fgts}
            aberta
            aoAlternar={() => undefined}
            linhagens={linhagens}
            fundida={false}
          />
        </tbody>
      </table>,
      { wrapper: MemoryRouter },
    );
  }

  it('sem a linhagem no mapa, a linha diz que não contou', () => {
    abrir({});
    expect(screen.getByText('instâncias não contadas')).toBeTruthy();
    expect(
      screen.getByText(/o inventário desta tela não a contou/i),
    ).toBeTruthy();
    expect(screen.queryByText('1 instância neste inventário')).toBeNull();
  });

  it('com a contagem na mão, ela é dita e é a contagem de verdade', () => {
    abrir({ lg_fgts: 2 });
    expect(screen.getByText('2 instâncias neste inventário')).toBeTruthy();
  });

  it('uma instância só continua sendo uma afirmação legítima', () => {
    abrir({ lg_fgts: 1 });
    expect(screen.getByText('1 instância neste inventário')).toBeTruthy();
  });
});

// ── 7 ───────────────────────────────────────────────────────────────────────

describe('formato:149 — PRESENCA.presente era código morto e contraditório', () => {
  it('existe uma palavra só para o estado normal', () => {
    // O mapa dizia `na conta` e a função respondia `presente`, antes mesmo de
    // consultar o mapa. Duas palavras para o mesmo fato, uma inalcançável.
    expect(PRESENCA.presente.palavra).toBe('presente');
    expect(presencaLegivel('presente').palavra).toBe('presente');
    expect(presencaLegivel('presente')).toBe(PRESENCA.presente);
  });

  it('a palavra antiga não sobrou em selo nenhum da tela', () => {
    render(<InventarioDeCampanhas />, { wrapper: MemoryRouter });
    // Consulta por nó de texto exato, e não por trecho do container: "na conta
    // de anúncio" é prosa legítima em outros lugares, e o que não pode voltar é
    // um SELO com essa palavra.
    expect(screen.queryByText('na conta')).toBeNull();

    // ⚠️ `presente` não aparece na LINHA, e isso é escolha: um selo repetido em
    // toda linha saudável treina o olho a pular a coluna inteira, inclusive nas
    // duas linhas em que ela diz "não encontrada". Na expansão ele aparece
    // sempre, porque quem abriu a campanha veio conferir justamente esta —
    // e ali "a conta respondeu e esta campanha estava na resposta" é resposta,
    // não ruído.
    expect(screen.queryByText('presente')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /^BR - Maquininha de Cartão/ }));
    expect(screen.getAllByText('presente').length).toBeGreaterThan(0);
  });

  it('e a tolerância a palavra desconhecida continua de pé', () => {
    const r = presencaLegivel('sumiu_da_conta');
    expect(r.palavra).toBe('presença não reconhecida');
    expect(r.descricao).toContain('sumiu_da_conta');
  });
});

// ── 8 ───────────────────────────────────────────────────────────────────────

describe('useInventario:115 — o frescor vinha de uma página e a data de outra', () => {
  it('a data do conjunto acompanha o pior caso, e não a primeira página', () => {
    const recente = inventarioDeProva({
      frescor: 'recente',
      leitura: { lido_em: '2026-08-24T17:00:00Z', idade_s: 120 },
      parcial: false,
      faltou: [],
      contas: [],
      proximo_cursor: 'x',
    });
    const velha = inventarioDeProva({
      frescor: 'velho',
      leitura: { lido_em: '2026-08-24T09:00:00Z', idade_s: 29_000 },
      parcial: false,
      faltou: [],
      contas: [],
      proximo_cursor: null,
    });

    const junto = mesclarPaginas([recente, velha]);
    expect(junto?.frescor).toBe('velho');
    // Antes: "leitura antiga" carimbada com `idade_s: 120` — a palavra de uma
    // página e o número da outra, e a idade impressa deixando de descrever o
    // dado que estava embaixo dela.
    expect(junto?.leitura?.idade_s).toBe(29_000);
  });

  it('página sem data faz o conjunto ficar sem data, não com a data da outra', () => {
    const comData = inventarioDeProva({ leitura: { lido_em: 'x', idade_s: 10 }, contas: [] });
    const semData = inventarioDeProva({ leitura: null, contas: [] });
    expect(mesclarPaginas([comData, semData])?.leitura).toBeNull();
    expect(leituraMaisVelha({ lido_em: 'x', idade_s: 10 }, null)).toBeNull();
  });

  it('a conta repetida adota o descritor inteiro da pior página', () => {
    const boa = inventarioDeProva({
      contas: [{ ...creditoUp, campanhas: [creditoUp.campanhas[0]] }],
      parcial: false,
      faltou: [],
    });
    const ruim = inventarioDeProva({
      contas: [
        {
          ...creditoUp,
          frescor: 'falhou',
          leitura: { lido_em: 'agora', idade_s: 30 },
          ultima_leitura_boa: { lido_em: 'antes', idade_s: 26_400 },
          motivo: 'a conta não respondeu à última tentativa de leitura',
          campanhas: [creditoUp.campanhas[1]],
        },
        portalMundoMais,
      ],
      parcial: false,
      faltou: [],
    });

    const junto = mesclarPaginas([boa, ruim]);
    const conta = junto?.contas.find((c) => c.customer_id === creditoUp.customer_id);

    expect(conta?.frescor).toBe('falhou');
    expect(conta?.motivo).toBe('a conta não respondeu à última tentativa de leitura');
    expect(conta?.ultima_leitura_boa?.idade_s).toBe(26_400);
    // Só campanhas e quantidade são a UNIÃO das páginas; o resto do descritor
    // vem inteiro de uma delas, para nenhuma frase misturar duas leituras.
    expect(conta?.campanhas.length).toBe(2);
    expect(junto?.contas.length).toBe(2);
  });

  it('a mescla continua sem inventar envelope onde não há página', () => {
    expect(mesclarPaginas([])).toBeNull();
  });
});

// ── e o que a auditoria não pediu, mas o hook prometia e não entregava ───────

describe('a releitura em curso chega à tela', () => {
  it('diz que está conferindo, em vez de parecer parada', () => {
    leitura = { ...leituraBase, atualizando: true };
    render(<InventarioDeCampanhas />, { wrapper: MemoryRouter });
    // Sem isto, quem clica em "ler esta conta agora" e vê a tela imóvel conclui
    // que não funcionou e clica de novo — e cada clique custa cota da conta.
    expect(screen.getByText('conferindo o registro…')).toBeTruthy();
  });

  it('e fica calada quando não há nada em curso', () => {
    render(<InventarioDeCampanhas />, { wrapper: MemoryRouter });
    expect(screen.queryByText('conferindo o registro…')).toBeNull();
  });
});
