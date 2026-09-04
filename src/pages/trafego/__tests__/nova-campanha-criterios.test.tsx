// @vitest-environment jsdom
/**
 * O pedido que a Bancada monta — e, sobretudo, o que ele NÃO leva.
 *
 * ## A inversão que este arquivo sofreu, e por quê
 *
 * Ele afirmava, com seis testes, que a página "leva as positivas tipadas, uma
 * por keyword marcada". Estava certo sobre o código e errado sobre o produto: o
 * backend RECUSA positivas vindas do corpo. `somente_negativas_do_corpo`
 * (`portao_conjunto_pago.py:250`) levanta `POSITIVA_DO_CORPO` para qualquer
 * critério com `negativa: false`, e `conferir_positivas_do_brief` (:308) confere
 * de novo depois. As positivas saem de `keywords_por_grupo(<conjunto aprovado>)`
 * — a marcação do operador nunca entrou na conta.
 *
 * Ou seja: a tela mandava um payload que o servidor recusa, e a mesa escrevia
 * "o que você vê é o que vai para o Google", que não era verdade. Os testes
 * trancavam as duas coisas.
 *
 * A ordem de checagem no `_preparar` escondia isso: `criterios_do_cluster` roda
 * ANTES (`trafego.py:2959`), então o 409 que aparecia era
 * `CONJUNTO_PAGO_NAO_APROVADO` e `POSITIVA_DO_CORPO` só apareceria depois de o
 * conjunto ser aprovado. Dois defeitos empilhados, e o de cima escondia o de
 * baixo.
 *
 * Agora estes testes provam o contrário: o pedido leva SÓ negativas, e o
 * conjunto positivo é autoridade da mineração.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import type { Cockpit, PedidoDeProvaSearch } from '@/types/trafego';

const { cockpitDeTrafego, pedidoEspiado, KW } = vi.hoisted(() => ({
  cockpitDeTrafego: vi.fn(),
  pedidoEspiado: { atual: null as PedidoDeProvaSearch | null },
  KW: ['saque anual fgts', 'valor do saque anual'],
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// O espião do pedido. Não renderiza diálogo nenhum — só guarda o que recebeu.
vi.mock('@/components/trafego/Lancamento', () => ({
  Lancamento: ({ pedido }: { pedido: PedidoDeProvaSearch }) => {
    pedidoEspiado.atual = pedido;
    return <div data-testid="lancamento-aberto" />;
  },
}));

/** O conjunto pago APROVADO — é ele que carrega as positivas, não a tela. */
const CONJUNTO = {
  opportunity_id: 73, cluster_id: 4,
  selecionadas: KW.map((termo) => ({
    termo, termo_normalizado: termo, match_type: 'PHRASE' as const,
    subintencao: 'ACESSO', volume: 27100, cpc: null, motivo: null,
  })),
  excluidas: [], em_revisao_humana: [], negativas: [],
  selected_set_sha256: 'b'.repeat(64),
  approved_set_sha256: 'b'.repeat(64),
  aprovado_por: 'operador@volc', selection_policy_version: 'v1',
  blockers: [], alertas: [], pode_aprovar: false, porque_nao: 'já aprovado',
};

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    cockpitDeTrafego,
    estadoDaTrava: async () => ({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
      motivo: '', explicacao: 'A trava é de dois fatores.',
    }),
    // ⚠️ A lista NÃO pode vir vazia neste dublê, e isso é contrato, não
    // conveniência: uma lista vazia significa "os portões de política não foram
    // lidos do servidor", e ausência de regra nunca é verde. A Bancada barra
    // nesse caso — fail-closed, como o resto da casa —, então um teste sobre o
    // PEDIDO precisa de uma vertical de fato adjudicada.
    verticaisEPortoes: async () => ({
      verticais: [
        { id: 'informativo', titulo: 'Informativo',
          descricao: 'O site explica e compara.', exige: null,
          severidade: null, paises_exigem: [] },
      ],
    }),
    revisarConjuntoPago: async () => CONJUNTO,
    aprovarConjuntoPago: vi.fn(),
    planoDeMensuracaoVigente: async () => { throw new Error('sem plano gravado'); },
    // A copy PRONTA — sem ela a ação dominante nasce desabilitada e o pedido
    // nunca é montado, que é o que este arquivo quer inspecionar.
    lerCopy: async () => ({
      existe: true, status: 'done', perdida: false,
      opportunity_id: 73, run_id: 6, keywords: [...KW],
      copy: { headlines: ['Saque Anual 2026'], descriptions: ['Veja as regras.'],
              sitelinks: [], callouts: [], snippet: null },
      aceita: true, pendentes: [], diario: [],
      geracoes_conjunto: 1, geracoes_asset: 0,
      fatos_usados: 3, fatos_descartados: [],
      medicao: { chamadas: 1, falhas: 0, por_papel: {}, ilegiveis: 0,
                 tokens_entrada: 100, tokens_saida: 100, latencia_s: 10,
                 custo_usd: null, sem_custo: 1, motivo_sem_custo: '' },
      segundos: 10, erro: null,
      criado_em: '2026-08-27T00:00:00Z', atualizado_em: '2026-08-27T00:00:00Z',
    }),
    salvarCopyEditada: vi.fn(),
    escreverCopy: vi.fn(),
    provarCampanha: vi.fn(),
    subirCampanha: vi.fn(),
  },
  PautadorApiError: class extends Error { corpo?: unknown; status = 0; },
}));

import NovaCampanhaPage from '../NovaCampanhaPage';
import { reciboApto } from '@/lib/landing-policy/__tests__/recibos';

afterEach(() => {
  cleanup();
  pedidoEspiado.atual = null;
  window.sessionStorage.clear();
  vi.clearAllMocks();
});

function cockpitLimpo(): Cockpit {
  return {
    opportunity_id: 73, cluster_id: 4,
    origem: {
      opportunity_id: 73, run_id: 6, project_id: 2,
      url_final: 'https://creditoup.com.br/r/saque/',
      url_procedencia: 'wp', status_wp: 'publish', post_type: 'r',
      dominio: 'https://creditoup.com.br', nicho: 'Saque Anual',
      slug: 'saque', pais: 'BR', idioma: 'pt', idioma_declarado: 'pt',
      vertical: 'informativo', vertical_declarada: 'informativo',
      resumo_da_pesquisa: '', fatos: [], tem_texto_da_lp: true,
      // O RECIBO DO PORTÃO DE DESTINO PAGO — pela mesma razão que a copy chega
      // pronta neste arquivo: sem ele a ação nasce desabilitada e o pedido nunca
      // é montado. Um destino publicado e sem avaliação é INDETERMINADO, e
      // indeterminado não abre nada.
      landing_policy_receipt: reciboApto({
        url: 'https://creditoup.com.br/r/saque/',
      }, { agora_epoch: Date.now() / 1000 }),
    },
    triagem: {
      analisadas: 100, aprovadas_anuncio: 2, para_conteudo: 0, descartadas: 98,
      breakdown: {}, volume_total: 28700, volume_da_fila: 28700,
    },
    grupos: [{
      tipo: 'ACESSO', descricao: 'acesso',
      keywords: [
        { texto: KW[0], volume: 27100, cpc: null, competicao: '',
          tendencia: null, tags: [], motivo: '', tambem_em_conteudo: false },
        { texto: KW[1], volume: 1600, cpc: null, competicao: '',
          tendencia: null, tags: [], motivo: '', tambem_em_conteudo: false },
      ],
      volume: 28700, cpc_simples: null, cpc_ponderado: null,
      volume_declarado: null, keywords_declaradas: null, fora_da_fila: [],
    }],
    descartadas: [], procedencia: { servicos_declarados: [], engine: '' } as never,
    avisos: [],
    conta: {
      project_id: 2, dominio: 'creditoup.com.br', customer_id: '8017851692',
      login_customer_id: '6016739364', vinculada: true, motivo: null,
    },
    campanhas_lancadas: [],
  } as unknown as Cockpit;
}

/** Orçamento e lance declarados: sem eles a Economia barra, e é correto. */
function comEconomiaDeclarada() {
  window.sessionStorage.setItem('volc.bancada.rascunho.73.sem-run', JSON.stringify({
    orcamento: '10', lance: '0,12', estrategia: 'MANUAL_CPC', graduacao: 30,
    certificacoes: [],     matchPorKeyword: {}, keywordsFora: [], vertical: null, modeloDaCopy: '',
  }));
}

const renderizar = (etapa = 'revisao') =>
  render(
    <MemoryRouter initialEntries={[`/trafego/nova/73?etapa=${etapa}`]}>
      <Routes>
        <Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} />
      </Routes>
    </MemoryRouter>,
  );

async function provar() {
  comEconomiaDeclarada();
  cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
  renderizar('revisao');
  const botao = await screen.findByRole('button', { name: /Provar contra a conta/ });
  await waitFor(() => expect((botao as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(botao);
  await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());
}

describe('o pedido que a Bancada monta', () => {
  it('NÃO leva positiva nenhuma no corpo — o conjunto é autoridade da mineração', async () => {
    // ⚠️ A CONTRAPROVA. `somente_negativas_do_corpo` recusa qualquer critério com
    // `negativa: false`; mandar positivas era montar um payload que o servidor
    // rejeita, e a tela nem sabia disso porque outro 409 chegava primeiro.
    await provar();

    const crits = pedidoEspiado.atual!.criterios ?? [];
    const positivas = crits.filter((c) => !c.negativa);
    expect(positivas).toHaveLength(0);
    // E `grupos` também vai vazio: as positivas saem de
    // `keywords_por_grupo(<conjunto aprovado>)`, no servidor.
    expect(pedidoEspiado.atual!.grupos).toHaveLength(0);
  });

  it('leva a exclusão que o operador escreveu, com nível e match type dela', async () => {
    comEconomiaDeclarada();
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('termos');
    await screen.findByLabelText('Termo a excluir');

    fireEvent.change(screen.getByLabelText('Termo a excluir'), {
      target: { value: 'simulador' },
    });
    fireEvent.change(screen.getByLabelText('Correspondência da exclusão'), {
      target: { value: 'EXACT' },
    });
    fireEvent.change(screen.getByLabelText(/^Motivo/), {
      target: { value: 'nao vendemos simulacao' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Adicionar exclusão/ }));

    // Navega para a Revisão e prova.
    fireEvent.click(screen.getByRole('link', { name: /Revisão/ }));
    const botao = await screen.findByRole('button', { name: /Provar contra a conta/ });
    await waitFor(() => expect((botao as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(botao);
    await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());

    const negativas = (pedidoEspiado.atual!.criterios ?? []).filter((c) => c.negativa);
    expect(negativas).toHaveLength(1);
    // ⚠️ A CORRESPONDÊNCIA E O MOTIVO SOBREVIVEM ATÉ O PEDIDO.
    //
    // A primeira versão do rascunho guardava `string[]` e remontava o critério
    // com `match_type: 'PHRASE'` fixo — o que trocava silenciosamente a decisão
    // do operador: excluir `simulador` em EXACT bloqueia um termo, em PHRASE
    // bloqueia uma família inteira. E o motivo, que é a frase que responde "por
    // que este termo está fora?" três meses depois, sumia junto.
    expect(negativas[0]).toMatchObject({
      texto: 'simulador', match_type: 'EXACT', nivel: 'CAMPAIGN',
      grupo: null, origem: 'MANUAL', motivo: 'nao vendemos simulacao',
    });
    expect(negativas[0].evidencia).toBeNull();
  });

  it('a exclusão declarada sobrevive ao refresh, com correspondência e motivo', async () => {
    // O rascunho é da ABA, e o F5 não pode desfazer uma decisão de exclusão.
    window.sessionStorage.setItem('volc.bancada.rascunho.73.sem-run', JSON.stringify({
      orcamento: '10', lance: '0,12', estrategia: 'MANUAL_CPC', graduacao: 30,
      certificacoes: [],
      negativas: [{
        texto: 'simulador', match_type: 'EXACT', negativa: true, nivel: 'CAMPAIGN',
        grupo: null, origem: 'MANUAL', motivo: 'nao vendemos simulacao',
        evidencia: null, observado_em: null, aprovado_por: null,
      }],
      matchPorKeyword: {}, keywordsFora: [], vertical: null, modeloDaCopy: '',
    }));
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('revisao');
    const botao = await screen.findByRole('button', { name: /Provar contra a conta/ });
    await waitFor(() => expect((botao as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(botao);
    await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());

    const negativas = (pedidoEspiado.atual!.criterios ?? []).filter((c) => c.negativa);
    expect(negativas[0]).toMatchObject({ match_type: 'EXACT', motivo: 'nao vendemos simulacao' });
  });

  it('continua mandando `match_type` como padrão do pedido', async () => {
    await provar();
    // O campo antigo continua no pedido: é ele que preenche a lacuna de quem
    // não declara critério, e sob MANUAL_CPC o padrão da casa é PHRASE.
    expect(pedidoEspiado.atual!.match_type).toBe('PHRASE');
  });

  it('leva o orçamento e o lance DIGITADOS, e não um default de máquina', async () => {
    // ⚠️ `Number(budget) || 0` transformava texto inválido — e a vírgula que o
    // teclado brasileiro produz — em `0`, silenciosamente. Um orçamento zero é
    // um pedido que o operador não fez.
    await provar();
    expect(pedidoEspiado.atual!.budget_diario).toBe(10);
    expect(pedidoEspiado.atual!.cpc_inicial).toBe(0.12);
  });

  it('a ação dominante NÃO abre a ignição enquanto falta alguma coisa', async () => {
    // Sem rascunho: orçamento e lance não declarados. A Economia barra, e a
    // Revisão mostra a falta em vez de deixar provar um pedido incompleto.
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('revisao');
    const botao = await screen.findByRole('button', { name: /Provar contra a conta/ });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByText(/declarar o orçamento diário/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/declarar o lance inicial/).length).toBeGreaterThan(0);
    fireEvent.click(botao);
    expect(pedidoEspiado.atual).toBeNull();
  });
});

describe('a prova NÃO é re-disparada por re-render', () => {
  it('o pedido tem identidade estável entre renders da página', async () => {
    // ⚠️ O BLOQUEANTE QUE ISTO FECHA.
    //
    // `pedido` era um objeto literal recriado a CADA render. Ele é prop de
    // `<Lancamento>`, onde `provar` é um `useCallback` com deps
    // `[pedido, trava, destino]` e existe
    // `useEffect(() => { void provar(); }, [provar])`.
    //
    // Identidade nova a cada render → `provar` novo → o efeito dispara de novo →
    // `POST /provar` outra vez, que é a chamada mais lenta e mais cara do fluxo.
    // Pior: `provar()` começa com `setEstado('provando')`, então a escada
    // VOLTAVA ao começo — inclusive depois de `criada`, apagando da tela o
    // recibo da campanha que acabou de nascer.
    //
    // O caminho concreto: `setRecibo` dispara o efeito de capacidades, que faz
    // `setPodeReconciliar`, que re-renderiza a página logo DEPOIS da criação.
    comEconomiaDeclarada();
    cockpitDeTrafego.mockResolvedValue(cockpitLimpo());
    renderizar('revisao');
    const botao = await screen.findByRole('button', { name: /Provar contra a conta/ });
    await waitFor(() => expect((botao as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(botao);
    await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());

    const primeiro = pedidoEspiado.atual;
    // Força re-renders da página sem mudar nada que componha o pedido.
    for (let i = 0; i < 3; i += 1) {
      fireEvent.click(screen.getByTestId('lancamento-aberto'));
      await waitFor(() => expect(pedidoEspiado.atual).toBeTruthy());
    }
    // MESMA referência: `useMemo` não recomputou, então `provar` não mudou de
    // identidade e o efeito não re-disparou.
    expect(pedidoEspiado.atual).toBe(primeiro);
  });
});
