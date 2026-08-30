// @vitest-environment jsdom
/**
 * AS SUPERFÍCIES DE EXECUÇÃO: recibo, lote, conversa, criativos e canal.
 *
 * Cada uma existe para não achatar um par de fatos que parecem iguais e levam a
 * ações opostas:
 *
 *  - recibo: `nada_foi_criado` é afirmação, não lista que não carregou;
 *  - lote: `nao_tentado` não é `falhou`;
 *  - conversa: criar e ligar são duas decisões;
 *  - criativos: `uso: null` não é "não está em uso";
 *  - canal: `manifesto: null` não é manifesto vazio.
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { Criativo, Lote, Recibo } from '@/types/diagnostico';
import type { ManifestoDeCanal } from '@/types/trafego';
import { CartaoDeRecibo } from '@/components/trafego/recibos/CartaoDeRecibo';
import { lerRecibo } from '@/components/trafego/recibos/recibo';
import { QuadroDoLote } from '@/components/trafego/lote/QuadroDoLote';
import { ConversaDeCriacao } from '@/components/trafego/criacao/ConversaDeCriacao';
import { montarConversa } from '@/components/trafego/criacao/conversa';
import { BibliotecaDeCriativos } from '@/components/trafego/criativos/BibliotecaDeCriativos';
import { VisaoDoCanal } from '@/components/trafego/canal/VisaoDoCanal';

afterEach(cleanup);

// ── recibo ──────────────────────────────────────────────────────────────────

const RECIBO: Recibo = lerRecibo({
  estado: 'ACEITO',
  carimbo: '20260819_200616',
  customer_id: '8017851692',
  login_customer_id: '6016739364',
  nome_campanha: 'BR - 20260819_200614 / FGTS Saque-Aniversário',
  n_operacoes: 3,
  impressao: 'b468513e616f020f8156ff680f7a669887de58f4e6d5550252965817f39e302e',
  motivo: 'lançamento de "FGTS Saque-Aniversário"',
  criados: [
    { posicao: 0, tipo: 'campaign_budget_result', resource_name: 'customers/8017851692/campaignBudgets/1' },
    { posicao: 1, tipo: 'campaign_result', resource_name: 'customers/8017851692/campaigns/2' },
    { posicao: 2, tipo: 'ad_group_result', resource_name: 'customers/8017851692/adGroups/3' },
  ],
  request_id: '',
  falha: null,
  explicacao: 'a API confirmou a criação do grafo inteiro. A campanha está PAUSED.',
  nada_foi_criado: false,
})!;

describe('recibo', () => {
  it('mostra quando, por que, e o que a conta confirmou', () => {
    render(<CartaoDeRecibo recibo={RECIBO} />);
    expect(screen.getByText('19/08/2026 20:06:16')).toBeTruthy();
    expect(screen.getByText('lançamento de "FGTS Saque-Aniversário"')).toBeTruthy();
    expect(screen.getByText(/3 de 3 operações confirmadas/)).toBeTruthy();
    expect(screen.getByText(/1 × orçamento/)).toBeTruthy();
  });

  it('⚠️ o carimbo não é convertido: o fuso não está no arquivo e a tela o declara', () => {
    render(<CartaoDeRecibo recibo={RECIBO} />);
    expect(screen.getByText(/fuso não declarado no recibo/)).toBeTruthy();
  });

  it('`request_id` vazio vira frase, não célula em branco', () => {
    render(<CartaoDeRecibo recibo={RECIBO} />);
    expect(screen.getByText('não devolvido pela conta de anúncio')).toBeTruthy();
  });

  it('⚠️ `nada_foi_criado` é dito como afirmação', () => {
    render(<CartaoDeRecibo recibo={{ ...RECIBO, nada_foi_criado: true, criados: [] }} />);
    expect(screen.getByText(/Isto é uma\s+afirmação do gravador/)).toBeTruthy();
  });

  it('a contradição entre declarado e entregue aparece na tela', () => {
    render(<CartaoDeRecibo recibo={{ ...RECIBO, n_operacoes: 113 }} />);
    expect(screen.getByText(/o recibo declara 113 e lista 3/)).toBeTruthy();
  });

  it('sem aprovação para conferir, a tela diz que nada amarra um ao outro', () => {
    render(<CartaoDeRecibo recibo={RECIBO} />);
    expect(screen.getByText(/nada amarra um ao outro/)).toBeTruthy();
  });

  it('impressão diferente da aprovada vira alerta, não nota de rodapé', () => {
    render(
      <CartaoDeRecibo
        recibo={RECIBO}
        aprovacao={{
          estado: 'aprovada',
          por: 'tarcisio',
          em: '2026-08-19T20:00:00.000Z',
          impressao: 'outra-impressao',
          motivo: null,
          vale_ate: null,
        }}
      />,
    );
    const alerta = screen.getByRole('alert');
    expect(alerta.textContent).toContain('Alguma coisa mudou entre a assinatura e o envio');
  });
});

// ── lote ────────────────────────────────────────────────────────────────────

const LOTE: Lote = {
  id: 'lote-fgts',
  estado: 'interrompido',
  aprovado_em: '2026-08-26T12:00:00.000Z',
  aprovado_por: 'tarcisio',
  itens: [
    {
      id: '1',
      rotulo: 'FGTS — saque aniversário',
      estado: 'criada_pausada',
      proxima_acao: 'verificar',
      falha: null,
      recibo: RECIBO,
      recibo_em_voo: false,
      encontradas_na_conta: 1,
    },
    {
      id: '2',
      rotulo: 'FGTS — antecipação',
      estado: 'falhou',
      proxima_acao: 'decidir_retomada',
      falha: { mensagem: 'a conta recusou: URL final fora do domínio verificado.', codigo: 'POLICY' },
      recibo: null,
      recibo_em_voo: false,
      encontradas_na_conta: null,
    },
    {
      id: '3',
      rotulo: 'Maquininha — taxa',
      estado: 'indeterminado',
      proxima_acao: 'verificar',
      falha: null,
      recibo: null,
      recibo_em_voo: true,
      encontradas_na_conta: null,
    },
  ],
  cancelado_por: null,
  cancelado_em: null,
  motivo_do_cancelamento: null,
};

describe('lote', () => {
  it('⚠️ o resumo separa `falhou` de `sem resposta da conta`', () => {
    render(<QuadroDoLote lote={LOTE} />);
    const resumo = screen.getByRole('status');
    expect(resumo.textContent).toContain('1 falhou');
    expect(resumo.textContent).toContain('não sabemos se criaram, e nenhuma será reenviada');
    expect(resumo.textContent).toContain('1 criada');
  });

  it('⚠️ o item sem resposta diz, na própria linha, que reenviar pode duplicar', () => {
    render(<QuadroDoLote lote={LOTE} />);
    expect(screen.getAllByText('sem resposta da conta').length).toBeGreaterThan(0);
    expect(screen.getByText('chamada em voo')).toBeTruthy();
    // A frase aparece duas vezes de propósito: no chip (para leitor de tela e
    // `title`) e na linha visível. Uma explicação que só existe no hover não
    // chega a quem lê por teclado nem a quem imprime a tela.
    expect(
      screen.getAllByText(/reenviar aqui pode criar uma segunda campanha real/).length,
    ).toBe(2);
  });

  it('cada item mostra o próximo passo que o SERVIDOR decidiu', () => {
    render(<QuadroDoLote lote={LOTE} />);
    expect(screen.getAllByText('verificar na conta antes de qualquer outra coisa').length).toBe(2);
    expect(screen.getByText('decidir se retoma este item')).toBeTruthy();
  });

  it('sem aprovação humana, a tela diz que nada será executado', () => {
    render(<QuadroDoLote lote={{ ...LOTE, aprovado_em: null, aprovado_por: null }} />);
    expect(screen.getByText(/Ainda sem aprovação humana/)).toBeTruthy();
  });

  it('a falha de um item não apaga os outros, e diz isso', () => {
    render(<QuadroDoLote lote={LOTE} />);
    const alerta = screen
      .getAllByRole('alert')
      .find((n) => n.textContent?.includes('URL final'))!;
    expect(alerta.textContent).toContain('URL final fora do domínio verificado');
    expect(alerta.textContent).toContain('Os outros itens deste lote continuam');
    expect(screen.getByText('FGTS — saque aniversário')).toBeTruthy();
    expect(screen.getByText('Maquininha — taxa')).toBeTruthy();
  });

  it('⚠️ retomar fica fechado com item em voo, e a frase diz que verificar vem antes', () => {
    render(<QuadroDoLote lote={LOTE} />);
    const botao = screen.getByRole('button', { name: 'retomar de onde parou' });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    const explicacao = document.getElementById(botao.getAttribute('aria-describedby')!)!;
    expect(explicacao.textContent).toContain('Verificar na conta vem antes de retomar');
  });

  it('lote cancelado explica que retomar exige decisão nova', () => {
    render(
      <QuadroDoLote
        lote={{
          ...LOTE,
          cancelado_em: '2026-08-26T12:00:00.000Z',
          cancelado_por: 'tarcisio',
          motivo_do_cancelamento: 'verba do mês esgotada',
        }}
      />,
    );
    expect(screen.getByText(/Lote cancelado por/).textContent).toContain('verba do mês esgotada');
    const botao = screen.getByRole('button', { name: 'retomar de onde parou' });
    const explicacao = document.getElementById(botao.getAttribute('aria-describedby')!)!;
    expect(explicacao.textContent).toContain('decisão nova');
  });
});

// ── conversa de criação ─────────────────────────────────────────────────────

const manifestoSearch: ManifestoDeCanal = {
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo', 'anuncio'],
  paineis: [],
  campos_do_pedido: ['objetivo', 'conta', 'url_final', 'conversion_action', 'geo', 'verba'],
  capacidades: ['ler', 'propor'],
  provas_obrigatorias: ['validate_only'],
  indisponibilidades: [],
  sabe_criar: true,
};

describe('conversa de criação', () => {
  it('pergunta uma coisa por vez, e diz em que etapa está', () => {
    const passos = montarConversa({
      manifesto: manifestoSearch,
      respostas: { objetivo: 'lead de FGTS · fundo de funil' },
      travaAberta: null,
      podeAprovar: true,
    });
    render(<ConversaDeCriacao passos={passos} />);
    expect(
      screen.getByRole('heading', { name: /em que conta de anúncio e em que canal ela vive\?/ }),
    ).toBeTruthy();
    expect(screen.getByText('etapa 2 de 13')).toBeTruthy();
    expect(screen.getByText('lead de FGTS · fundo de funil')).toBeTruthy();
  });

  it('⚠️ diz, em letras, que criar e ligar são duas decisões', () => {
    const passos = montarConversa({
      manifesto: manifestoSearch,
      respostas: {},
      travaAberta: null,
      podeAprovar: true,
    });
    render(<ConversaDeCriacao passos={passos} />);
    expect(screen.getByText(/A criação sai pausada/)).toBeTruthy();
    expect(screen.getByText(/Ligar é a etapa seguinte/)).toBeTruthy();
  });

  it('etapa bloqueada mostra a dependência real na própria linha', () => {
    const passos = montarConversa({
      manifesto: manifestoSearch,
      respostas: {},
      travaAberta: null,
      podeAprovar: false,
    });
    render(<ConversaDeCriacao passos={passos} />);
    expect(screen.getByText(/exige um papel que esta conta não tem/)).toBeTruthy();
  });

  it('canal sem construtor bloqueia a conversa inteira com a recusa do manifesto', () => {
    const passos = montarConversa({
      manifesto: { ...manifestoSearch, sabe_criar: false, indisponibilidades: ['Display não tem construtor aprovado.'] },
      respostas: {},
      travaAberta: true,
      podeAprovar: true,
    });
    render(<ConversaDeCriacao passos={passos} />);
    expect(screen.getAllByText('Display não tem construtor aprovado.').length).toBeGreaterThan(0);
  });

  it('a etapa atual é anunciada como passo corrente para o leitor de tela', () => {
    const passos = montarConversa({
      manifesto: manifestoSearch,
      respostas: {},
      travaAberta: null,
      podeAprovar: true,
    });
    const { container } = render(<ConversaDeCriacao passos={passos} />);
    expect(container.querySelectorAll('[aria-current="step"]').length).toBe(1);
  });
});

// ── criativos ───────────────────────────────────────────────────────────────

const criativos: Criativo[] = [
  {
    id: 'c1',
    tipo: 'titulo',
    conteudo: 'Antecipe seu saque-aniversário do FGTS',
    hash: 'a1b2c3d4e5f6a7b8',
    procedencia: 'volc_os',
    origem: 'run 9 do Redator',
    validacoes: [
      { canal: 'SEARCH', situacao: 'serve', motivo: null },
      { canal: 'DISPLAY', situacao: 'nao_serve', motivo: 'passa de 30 caracteres no título de Display' },
    ],
    uso: [{ volc_campaign_id: 'gads-1', nome_campanha: 'FGTS Saque-Aniversário', estado_externo: 'ENABLED' }],
  },
  {
    id: 'c2',
    tipo: 'imagem',
    conteudo: 'banner-fgts-1200x628.png',
    hash: null,
    procedencia: 'desconhecida',
    origem: null,
    validacoes: [{ canal: 'DISPLAY', situacao: 'nao_apurado', motivo: 'as dimensões não foram lidas' }],
    uso: null,
  },
  {
    id: 'c3',
    tipo: 'descricao',
    conteudo: 'Simulação em 2 minutos, sem consulta ao SPC.',
    hash: 'ffff0000ffff0000',
    procedencia: 'conta',
    origem: null,
    validacoes: [{ canal: 'SEARCH', situacao: 'serve', motivo: null }],
    uso: [],
  },
];

describe('biblioteca de criativos', () => {
  it('é tabela: colunas alinhadas para comparar, e não grade de cartões', () => {
    render(<BibliotecaDeCriativos criativos={criativos} />);
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getAllByRole('row').length).toBe(4);
  });

  it('⚠️ `uso: null` e `uso: []` são duas frases diferentes', () => {
    render(<BibliotecaDeCriativos criativos={criativos} />);
    expect(screen.getByText('uso não apurado')).toBeTruthy();
    expect(screen.getByText('em nenhuma campanha')).toBeTruthy();
  });

  it('peça sem impressão aparece como travessão, e o motivo está no título', () => {
    render(<BibliotecaDeCriativos criativos={criativos} />);
    const semHash = screen.getByTitle(/sem impressão calculada/);
    expect(semHash.textContent).toBe('—');
  });

  it('validação não apurada não vira "serve"', () => {
    render(<BibliotecaDeCriativos criativos={criativos} />);
    expect(screen.getByTitle(/display — as dimensões não foram lidas/)).toBeTruthy();
  });

  it('procedência desconhecida é dita: "sem procedência"', () => {
    render(<BibliotecaDeCriativos criativos={criativos} />);
    expect(screen.getByText('sem procedência')).toBeTruthy();
  });

  it('biblioteca não lida e biblioteca vazia são telas diferentes', () => {
    const { unmount } = render(<BibliotecaDeCriativos criativos={[]} lida={false} />);
    expect(screen.getByText(/significa que ninguém conseguiu olhar/)).toBeTruthy();
    unmount();

    render(<BibliotecaDeCriativos criativos={[]} lida />);
    expect(screen.getByText(/A biblioteca foi lida e não há peça registrada/)).toBeTruthy();
  });
});

// ── visão por canal ─────────────────────────────────────────────────────────

describe('visão por canal', () => {
  it('⚠️ manifesto nulo diz que o Hub não opera o canal', () => {
    render(<VisaoDoCanal manifesto={null} rotuloDeReserva="Vídeo" />);
    expect(screen.getByRole('heading', { name: /Vídeo não é operado pelo Hub/ })).toBeTruthy();
  });

  it('manifesto vazio é outra tela, com o rótulo do canal', () => {
    render(<VisaoDoCanal manifesto={{ ...manifestoSearch, capacidades: [] }} />);
    expect(
      screen.getByRole('heading', { name: /Search — nenhuma capacidade declarada/ }),
    ).toBeTruthy();
  });

  it('as capacidades vêm do manifesto, traduzidas, e as provas obrigatórias junto', () => {
    render(<VisaoDoCanal manifesto={manifestoSearch} />);
    const secao = screen.getByLabelText('capacidades do canal');
    expect(within(secao).getByText('ler a conta e mostrar o que existe')).toBeTruthy();
    expect(within(secao).getByText(/validate_only/)).toBeTruthy();
    expect(within(secao).getByText('o Hub sabe criar campanha neste canal.')).toBeTruthy();
  });

  it('recusa de criação usa a frase do manifesto', () => {
    render(
      <VisaoDoCanal
        manifesto={{
          ...manifestoSearch,
          sabe_criar: false,
          indisponibilidades: ['Performance Max não tem construtor aprovado'],
        }}
      />,
    );
    expect(
      screen.getByText('criação indisponível: Performance Max não tem construtor aprovado.'),
    ).toBeTruthy();
  });
});
