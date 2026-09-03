// @vitest-environment jsdom
/**
 * O cockpit MONTA, as travas barram, e a copy PAGA não se perde.
 *
 * Os três primeiros testes são os de sempre. Os quatro últimos existem por
 * causa de um defeito real, vivido em 18/08/2026: o operador clicou em escrever
 * a copy, saiu da página e voltou — e não havia nada. Nenhum sinal de que
 * tinha rodado, o botão oferecendo começar de novo, e ~174 s de LLM já pagos.
 *
 * O resultado vivia só na memória do browser. Agora vive em
 * `pautador_trafego_copy`, e estes testes são o contrato dessa mudança.
 *
 * ## O que mudou com o portão de destino pago
 *
 * Dois destes testes afirmavam o comportamento ANTIGO e precisaram mudar junto
 * com ele:
 *
 * * o lançamento era barrado por um `Set(['LP_EM_RASCUNHO','URL_PROVISORIA'])`
 *   escrito no cliente. Ele saiu: quem barra agora é a severidade que o
 *   servidor declara e o recibo do portão de política. Os dois códigos
 *   continuam impedindo o lançamento — pelo estado da PUBLICAÇÃO, que é o fato
 *   que eles descrevem, e não pelo nome deles numa lista do browser;
 * * "a copy já escrita libera o botão" só valia porque a página nunca olhava o
 *   destino. Um cockpit em rascunho e sem recibo agora barra, então o caso
 *   feliz precisa de uma origem publicada e avaliada.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import type { Cockpit, CopyPersistida } from '@/types/trafego';
import { reciboApto } from '@/lib/landing-policy/__tests__/recibos';

const { escreverCopy, cockpitDeTrafego, lerCopy } = vi.hoisted(() => ({
  escreverCopy: vi.fn(),
  cockpitDeTrafego: vi.fn(),
  lerCopy: vi.fn(),
}));

// `Layout` puxa a navegação, que puxa o AuthContext. Este teste é sobre o
// conteúdo da página, não sobre a moldura do app.
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    cockpitDeTrafego,
    estadoDaTrava: async () => ({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
      motivo: '', explicacao: 'A trava é de dois fatores.',
    }),
    // O portão de política é carregado junto do cockpit. `financeiro` com
    // severidade `bloqueio` em BR é o caso que barrou o card 74 de verdade.
    verticaisEPortoes: async () => ({
      verticais: [
        { id: 'informativo', titulo: 'Informativo',
          descricao: 'O site explica e compara.', exige: null,
          severidade: null, paises_exigem: [] },
        { id: 'financeiro', titulo: 'Financeiro',
          descricao: 'Verificação obrigatória por país.',
          exige: 'verificacao_servicos_financeiros', severidade: 'bloqueio',
          paises_exigem: ['BR', 'MX'] },
      ],
    }),
    escreverCopy,
    lerCopy,
    provarCampanha: vi.fn(),
    subirCampanha: vi.fn(),
  },
  PautadorApiError: class extends Error { corpo?: unknown; status = 0; },
}));

import NovaCampanhaPage from '../NovaCampanhaPage';

const KW = ['banco pan telefone', 'cartão de crédito caixa telefone'];

/**
 * A origem APTA: publicada e com recibo de portão no ponto de campanha.
 *
 * ⚠️ O recibo entra em `origem` sob `landing_policy_receipt` — a mesma chave de
 * transporte do backend. Sem ele a página é INDETERMINADA, que é o
 * comportamento correto e o assunto de um teste abaixo.
 */
const ORIGEM_APTA = {
  status_wp: 'publish',
  url_final: 'https://creditoup.com.br/cartao-para-negativado',
  landing_policy_receipt: reciboApto({}, { agora_epoch: Date.now() / 1000 }),
};

/** O card 73, medido em 18/08/2026 — inclusive os dois avisos que barram. */
function cockpitDoCard73(
  avisos = AVISOS_REAIS,
  origemExtra: Record<string, unknown> = {},
): Cockpit {
  return {
    opportunity_id: 73,
    cluster_id: 4,
    origem: {
      opportunity_id: 73, run_id: 6, project_id: 2,
      url_final: 'https://creditoup.com.br/?post_type=r&p=2152',
      url_procedencia: 'wp', status_wp: 'draft', post_type: 'r',
      dominio: 'https://creditoup.com.br', nicho: 'Cartão para Negativado',
      slug: 'cartao', pais: 'BR', idioma: 'pt', idioma_declarado: 'pt-BR',
      vertical: 'financeiro', vertical_declarada: 'financeiro',
      resumo_da_pesquisa: '', fatos: [], tem_texto_da_lp: true,
      ...origemExtra,
    },
    triagem: {
      analisadas: 100, aprovadas_anuncio: 23, para_conteudo: 25, descartadas: 63,
      breakdown: {}, volume_total: 37400, volume_da_fila: 37400,
    },
    grupos: [{
      tipo: 'ACESSO', descricao: 'contatos e meios digitais',
      keywords: [
        { texto: KW[0], volume: 27100, cpc: null, competicao: '',
          tendencia: null, tags: [], motivo: '', tambem_em_conteudo: false },
        { texto: KW[1], volume: 1600, cpc: null,
          competicao: '', tendencia: null, tags: [], motivo: '', tambem_em_conteudo: false },
      ],
      volume: 28700, cpc_simples: null, cpc_ponderado: null,
      volume_declarado: null, keywords_declaradas: null, fora_da_fila: [],
    }],
    descartadas: [],
    procedencia: { servicos_declarados: [], engine: '' } as never,
    avisos,
    conta: {
      project_id: 2, dominio: 'creditoup.com.br', customer_id: '8017851692',
      login_customer_id: '6016739364', vinculada: true, motivo: null,
    },
  } as unknown as Cockpit;
}

const AVISOS_REAIS = [
  { codigo: 'LP_EM_RASCUNHO', severidade: 'atencao', titulo: 'A LP está como `draft` no WordPress',
    detalhe: 'Rascunho não é visível para quem não está logado.' },
  { codigo: 'URL_PROVISORIA', severidade: 'atencao', titulo: 'A URL de destino é provisória',
    detalhe: 'Quando a página for publicada o permalink muda.' },
  { codigo: 'IDIOMA_TROCADO', severidade: 'informacao', titulo: 'Idioma ajustado',
    detalhe: 'pt-BR não é segmentável; usando pt.' },
];

function copiaPronta(over: Partial<CopyPersistida> = {}): CopyPersistida {
  return {
    existe: true, status: 'done', perdida: false,
    opportunity_id: 73, run_id: 6, keywords: [...KW],
    copy: { headlines: ['Cartão para Negativado'], descriptions: ['Veja as regras.'],
            sitelinks: [], callouts: [], snippet: null },
    aceita: true, pendentes: [], diario: [],
    geracoes_conjunto: 2, geracoes_asset: 0,
    fatos_usados: 6, fatos_descartados: [],
    medicao: { chamadas: 2, falhas: 0, por_papel: {}, ilegiveis: 0,
               tokens_entrada: 29078, tokens_saida: 34315, latencia_s: 174,
               custo_usd: null, sem_custo: 2,
               motivo_sem_custo: 'preço por token não configurado (VOLC_ADS_PRECO_ENTRADA_MI)' },
    segundos: 174, erro: null,
    criado_em: new Date().toISOString(), atualizado_em: new Date().toISOString(),
    ...over,
  } as CopyPersistida;
}

const renderizar = () =>
  render(
    <MemoryRouter initialEntries={['/trafego/nova/73?run=6']}>
      <Routes>
        <Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  lerCopy.mockResolvedValue({ existe: false });
});

describe('NovaCampanhaPage', () => {
  it('monta e mostra o número-herói do volume selecionado', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73());
    lerCopy.mockResolvedValue({ existe: false });
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    // 27.100 + 1.600 = 28.700 → "28,7k"
    expect(screen.getByText('28,7k')).toBeTruthy();
  });

  it('LP em rascunho BARRA o lançamento — agora pelo estado da publicação', async () => {
    // O cockpit do card 73 é `status_wp: 'draft'` e sem recibo de política. Os
    // dois fatos barram, e cada um aparece com o nome dele: uma página em
    // rascunho não está publicada, e uma página sem recibo não foi avaliada.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73());
    lerCopy.mockResolvedValue({ existe: false });
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
    expect((lancar as HTMLButtonElement).disabled).toBe(true);

    // `getAllBy…` porque a faixa do topo e o painel do cartão 01 dizem a mesma
    // frase — de propósito: a decisão é tomada na barra fixa, longe do painel.
    expect(screen.getAllByText(/publicar a página no WordPress/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/nenhum recibo de política chegou/).length).toBeGreaterThan(0);

    // ⚠️ E o painel NUNCA afirma nada sobre o revisor do Google.
    expect(screen.getAllByText(/não lê a decisão do revisor/).length).toBeGreaterThan(0);

    // "idioma ajustado" continua sendo informação recolhida, e não ganha o
    // espaço de um bloqueio — dar a ela o mesmo peso foi o defeito de 18/08.
    expect(screen.queryByText('Idioma ajustado')).toBeNull();
  });

  it('sem recibo de política o cartão da origem NÃO fica pronto', async () => {
    // ⚠️ A contraprova do fail-open medido: a linha antiga era
    // `pronto={status_wp !== 'draft'}`, que marcava a etapa como pronta quando
    // `status_wp` era `null` — ou seja, quando ninguém tinha lido o WordPress.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], { status_wp: null }));
    lerCopy.mockResolvedValue({ existe: false });
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    expect(screen.queryByText('LP no ar')).toBeNull();
    expect(screen.getByText('destino não avaliado')).toBeTruthy();
    expect(screen.getAllByText(/ler o status da página no WordPress/).length)
      .toBeGreaterThan(0);
    const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
    expect((lancar as HTMLButtonElement).disabled).toBe(true);
  });

  it('sem copy o lançamento continua barrado, mesmo sem nenhuma trava', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([]));
    lerCopy.mockResolvedValue({ existe: false });
    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
    expect((lancar as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/escrever a copy/)).toBeTruthy();
  });

  it('a copy já escrita aparece AO ABRIR, sem clicar em nada', async () => {
    // ⚠️ É o defeito vivido: clicar, sair, voltar — e não havia nada. O texto
    // custou ~174 s de LLM pago e vivia só na memória do browser.
    // ⚠️ `ORIGEM_APTA` não é conveniência de teste: sem destino publicado e
    // avaliado o botão fica fechado, e é assim que tem de ser. O que este teste
    // afirma é sobre a COPY, então o destino precisa sair do caminho — provado.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], ORIGEM_APTA));
    lerCopy.mockResolvedValue(copiaPronta());

    renderizar();
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    // Sem nenhum clique: a medição da geração anterior está na tela.
    await waitFor(() => expect(screen.getByText('preço não configurado')).toBeTruthy());
    expect(escreverCopy).not.toHaveBeenCalled();
    await waitFor(() => {
      const lancar = screen.getByRole('button', { name: /Lançar campanha/ });
      expect((lancar as HTMLButtonElement).disabled).toBe(false);
    });
  });

  it('escrita em curso retoma o cronômetro de onde estava, não do zero', async () => {
    // Um cronômetro que reinicia a cada visita sugere que o trabalho recomeçou —
    // e o operador clicaria de novo, gastando dobrado.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([]));
    lerCopy.mockResolvedValue(copiaPronta({
      status: 'running', copy: null, segundos: 0,
      criado_em: new Date(Date.now() - 112_000).toISOString(),
    }));

    renderizar();
    await waitFor(() => expect(screen.getByText('Escrevendo o anúncio…')).toBeTruthy());
    expect(screen.getByText(/11[0-9]s|12[0-9]s/)).toBeTruthy();
  });

  it('`running` velha demais é PERDIDA, não um cronômetro eterno', async () => {
    // A tarefa vive dentro do processo do backend; um reinício a mata e deixa a
    // linha `running` para sempre. O servidor marca `perdida` — a tela precisa
    // dizer isso, senão gira para sempre.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([]));
    lerCopy.mockResolvedValue(copiaPronta({
      status: 'running', perdida: true, copy: null,
    }));

    renderizar();
    await waitFor(() =>
      expect(screen.getByText('A escrita anterior se perdeu')).toBeTruthy());
    expect(screen.queryByText('Escrevendo o anúncio…')).toBeNull();
  });

  it('mexer nas keywords NÃO apaga a copy — avisa que ela é de outra seleção', async () => {
    // ⚠️ A versão anterior fazia `setEscrita(null)` aqui: trocar uma keyword
    // jogava fora um texto que custou minutos de LLM.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([]));
    lerCopy.mockResolvedValue(copiaPronta());

    renderizar();
    await waitFor(() => expect(screen.getByText('preço não configurado')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /marcar todas de ACESSO/ }));

    await waitFor(() =>
      expect(screen.getByText('Este texto foi escrito para outra seleção')).toBeTruthy());
    // O texto continua lá.
    expect(screen.getByText('preço não configurado')).toBeTruthy();
  });
});
