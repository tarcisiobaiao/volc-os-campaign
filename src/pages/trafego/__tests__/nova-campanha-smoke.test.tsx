// @vitest-environment jsdom
/**
 * A Bancada Guiada MONTA, as travas barram, e a copy PAGA não se perde.
 *
 * ## O que este arquivo herdou, e o que ele passou a afirmar
 *
 * Ele existia por um defeito real de 18/08/2026: o operador clicou em escrever a
 * copy, saiu da página e voltou — e não havia nada. Nenhum sinal de que tinha
 * rodado, o botão oferecendo começar de novo, e ~174 s de LLM já pagos. Essa
 * parte do contrato não mudou e continua trancada aqui.
 *
 * O que mudou em 03/09/2026 foi a TOPOLOGIA: a página deixou de ser uma coluna
 * de quatro cartões numerados renderizados ao mesmo tempo e virou seis paradas
 * com estado na URL. Três asserções mudaram junto, e cada uma diz por quê:
 *
 * 1. **o número-herói do volume selecionado saiu.** Ele somava o volume das
 *    keywords que o operador tinha MARCADO — e a marcação do operador nunca
 *    entrou na conta: em `/provar` a `Escolha` é montada com
 *    `keywords_por_grupo(<conjunto aprovado>)`. O herói media uma decisão que
 *    não existia. O que a Bancada mostra é o conjunto aprovado.
 * 2. **"marcar todas de ACESSO" saiu**, pelo mesmo motivo.
 * 3. **o botão "Lançar campanha" virou "Provar contra a conta"**, na parada
 *    Revisão. O ato dominante deixou de ser "lançar" porque a prova não lança:
 *    ela roda `validate_only` e descarta.
 *
 * O que NÃO mudou, e é o que este arquivo protege: rascunho barra, recibo
 * ausente barra, copy ausente barra, e a copy paga aparece ao abrir.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import type { Cockpit, CopyPersistida } from '@/types/trafego';
import { reciboApto } from '@/lib/landing-policy/__tests__/recibos';

const {
  escreverCopy, cockpitDeTrafego, lerCopy, revisarConjuntoPago,
} = vi.hoisted(() => ({
  escreverCopy: vi.fn(),
  cockpitDeTrafego: vi.fn(),
  lerCopy: vi.fn(),
  revisarConjuntoPago: vi.fn(),
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
    revisarConjuntoPago,
    aprovarConjuntoPago: vi.fn(),
    planoDeMensuracaoVigente: async () => { throw new Error('sem plano gravado'); },
    escreverCopy,
    lerCopy,
    salvarCopyEditada: vi.fn(),
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

/** O conjunto pago já congelado — para tirar a parada Termos do caminho. */
const CONJUNTO_APROVADO = {
  opportunity_id: 73, cluster_id: 4,
  selecionadas: KW.map((termo) => ({
    termo, termo_normalizado: termo, match_type: 'PHRASE' as const,
    subintencao: 'ACESSO', volume: 27100, cpc: null, motivo: null,
  })),
  excluidas: [], em_revisao_humana: [], negativas: [],
  selected_set_sha256: 'a'.repeat(64),
  approved_set_sha256: 'a'.repeat(64),
  aprovado_por: 'operador@volc', selection_policy_version: 'v1',
  blockers: [], alertas: [], pode_aprovar: false,
  porque_nao: 'já aprovado',
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
      vertical: 'informativo', vertical_declarada: 'informativo',
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

/** `etapa` explícita: a Bancada guarda o estado na URL. */
const renderizar = (etapa?: string) =>
  render(
    <MemoryRouter initialEntries={[`/trafego/nova/73?run=6${etapa ? `&etapa=${etapa}` : ''}`]}>
      <Routes>
        <Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.sessionStorage.clear();
  lerCopy.mockResolvedValue({ existe: false });
  revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);
});

describe('a Bancada Guiada', () => {
  it('monta com as seis paradas e o estado na URL', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73());
    lerCopy.mockResolvedValue({ existe: false });
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);
    renderizar('destino');
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    const mapa = screen.getByRole('navigation', { name: 'paradas do lançamento' });
    expect(mapa).toBeTruthy();
    for (const p of ['Destino', 'Política', 'Termos', 'Anúncio', 'Economia', 'Revisão']) {
      expect(screen.getAllByText(p).length).toBeGreaterThan(0);
    }
    // A pergunta da parada aberta é o H2 da coluna de decisão.
    expect(screen.getByText('Para onde este anúncio manda o clique?')).toBeTruthy();
  });

  it('LP em rascunho BARRA o lançamento — pelo estado da publicação', async () => {
    // O cockpit do card 73 é `status_wp: 'draft'` e sem recibo de política. Os
    // dois fatos barram, e cada um aparece com o nome dele: uma página em
    // rascunho não está publicada, e uma página sem recibo não foi avaliada.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73());
    lerCopy.mockResolvedValue(copiaPronta());
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);
    renderizar('revisao');
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    const provar = await screen.findByRole('button', { name: /Provar contra a conta/ });
    expect((provar as HTMLButtonElement).disabled).toBe(true);

    // A razão é VISÍVEL — o disabled nunca é mudo — e nomeia o fato. Na Revisão
    // ela vem curta, na linguagem do conserto; a frase inteira mora na parada
    // Destino, junto do recibo que a sustenta.
    expect(screen.getAllByText(/avaliar o destino desta campanha/).length).toBeGreaterThan(0);

    // "idioma ajustado" continua sendo informação, e não ganha o espaço de um
    // bloqueio — dar a ela o mesmo peso foi o defeito de 18/08.
    expect(screen.queryByText('Idioma ajustado')).toBeNull();
  });

  it('a parada Destino nomeia a publicação e o recibo, cada um com o nome dele', async () => {
    // Uma página em rascunho não está publicada, e uma página sem recibo não foi
    // avaliada. São dois fatos, e a tela anterior os confundia num só.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73());
    lerCopy.mockResolvedValue(copiaPronta());
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);
    renderizar('destino');
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    expect(screen.getAllByText(/publicar a página no WordPress/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/nenhum recibo de política chegou/).length).toBeGreaterThan(0);
    // ⚠️ E o painel NUNCA afirma nada sobre o revisor do Google.
    expect(screen.getAllByText(/não lê a decisão do revisor/).length).toBeGreaterThan(0);
    // A armadilha do rascunho é dita em português operacional, não por código.
    expect(screen.getByText(/o permalink muda e a campanha fica apontando/)).toBeTruthy();
  });

  it('sem recibo de política o destino NÃO fica pronto', async () => {
    // ⚠️ A contraprova do fail-open medido: a linha antiga era
    // `pronto={status_wp !== 'draft'}`, que marcava a etapa como pronta quando
    // `status_wp` era `null` — ou seja, quando ninguém tinha lido o WordPress.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], { status_wp: null }));
    lerCopy.mockResolvedValue(copiaPronta());
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);
    renderizar('destino');
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    expect(screen.queryByText('LP no ar')).toBeNull();
    expect(screen.getAllByText(/destino não avaliado|nenhum recibo de política/).length)
      .toBeGreaterThan(0);
    // ⚠️ E o painel NUNCA afirma nada sobre o revisor do Google.
    expect(screen.getAllByText(/não lê a decisão do revisor/).length).toBeGreaterThan(0);
    // "ninguém leu o WordPress" é ausência, e não "está no ar".
    expect(screen.getByText('ninguém leu o WordPress')).toBeTruthy();
  });

  it('sem copy o lançamento continua barrado, mesmo sem nenhuma trava', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], ORIGEM_APTA));
    lerCopy.mockResolvedValue({ existe: false });
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);
    renderizar('revisao');
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    const provar = await screen.findByRole('button', { name: /Provar contra a conta/ });
    expect((provar as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByText(/escrever o anúncio/).length).toBeGreaterThan(0);
  });

  it('a copy já escrita aparece AO ABRIR, sem clicar em nada', async () => {
    // ⚠️ É o defeito vivido: clicar, sair, voltar — e não havia nada. O texto
    // custou ~174 s de LLM pago e vivia só na memória do browser.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], ORIGEM_APTA));
    lerCopy.mockResolvedValue(copiaPronta());
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);

    renderizar('anuncio');
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());

    // Sem nenhum clique: a medição da geração anterior está na tela.
    await waitFor(() => expect(screen.getByText('preço não configurado')).toBeTruthy());
    expect(escreverCopy).not.toHaveBeenCalled();
  });

  it('escrita em curso retoma o cronômetro de onde estava, não do zero', async () => {
    // Um cronômetro que reinicia a cada visita sugere que o trabalho recomeçou —
    // e o operador clicaria de novo, gastando dobrado.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], ORIGEM_APTA));
    lerCopy.mockResolvedValue(copiaPronta({
      status: 'running', copy: null, segundos: 0,
      criado_em: new Date(Date.now() - 112_000).toISOString(),
    }));
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);

    renderizar('anuncio');
    await waitFor(() => expect(screen.getByText('Escrevendo o anúncio…')).toBeTruthy());
    expect(screen.getByText(/11[0-9]s|12[0-9]s/)).toBeTruthy();
  });

  it('`running` velha demais é PERDIDA, não um cronômetro eterno', async () => {
    // A tarefa vive dentro do processo do backend; um reinício a mata e deixa a
    // linha `running` para sempre. O servidor marca `perdida` — a tela precisa
    // dizer isso, senão gira para sempre.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], ORIGEM_APTA));
    lerCopy.mockResolvedValue(copiaPronta({
      status: 'running', perdida: true, copy: null,
    }));
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);

    renderizar('anuncio');
    await waitFor(() =>
      expect(screen.getByText('A escrita anterior se perdeu')).toBeTruthy());
    expect(screen.queryByText('Escrevendo o anúncio…')).toBeNull();
  });

  it('conjunto NÃO aprovado barra, e a parada Termos diz qual é o ato', async () => {
    // ⚠️ O bloqueante A0. `aprovar()` existia no engine sem um único chamador de
    // produção, `funnel_factory` persistia sem `approved_set_sha256`, e o portão
    // recusava `/provar` e `/subir` com `CONJUNTO_PAGO_NAO_APROVADO`. A campanha
    // Search não nascia pelo caminho normal, e a tela não tinha onde aprovar.
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], ORIGEM_APTA));
    lerCopy.mockResolvedValue(copiaPronta());
    revisarConjuntoPago.mockResolvedValue({
      ...CONJUNTO_APROVADO,
      approved_set_sha256: null, aprovado_por: null,
      pode_aprovar: true, porque_nao: null,
    });

    renderizar('termos');
    await waitFor(() => expect(screen.getByText('não aprovado')).toBeTruthy());
    expect(screen.getByRole('button', { name: /Aprovar o conjunto positivo/ })).toBeTruthy();
    // A frase normativa substitui "o que você vê é o que vai para o Google",
    // que não era verdade.
    expect(screen.getByText(/O conjunto positivo é o aprovado na mineração/)).toBeTruthy();
  });

  it('o rascunho sobrevive ao refresh, e a etapa também', async () => {
    cockpitDeTrafego.mockResolvedValue(cockpitDoCard73([], ORIGEM_APTA));
    lerCopy.mockResolvedValue(copiaPronta());
    revisarConjuntoPago.mockResolvedValue(CONJUNTO_APROVADO);

    // Simula o que a sessão anterior gravou: orçamento e lance digitados.
    window.sessionStorage.setItem('volc.bancada.rascunho.73.6', JSON.stringify({
      orcamento: '15,50', lance: '0,40', estrategia: 'MANUAL_CPC', graduacao: 30,
      certificacoes: [], negativasCampanha: [], negativasAdgroup: [],
      matchPorKeyword: {}, keywordsFora: [], vertical: null, modeloDaCopy: '',
    }));

    renderizar('economia');
    await waitFor(() => expect(screen.getByText('Cartão para Negativado')).toBeTruthy());
    // ⚠️ `15,50` com vírgula chegava ao Pedido como 0, porque
    // `Number(budget) || 0` engolia a vírgula que a mesa já normalizava.
    await waitFor(() => expect(screen.getAllByText(/R\$ 15,50/).length).toBeGreaterThan(0));
    // E a possibilidade de gasto servido é 2x — dita como possibilidade.
    expect(screen.getAllByText(/R\$ 31,00/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/não um teto garantido/).length).toBeGreaterThan(0);
  });
});
