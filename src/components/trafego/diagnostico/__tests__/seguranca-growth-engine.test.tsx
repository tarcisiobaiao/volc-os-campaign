// @vitest-environment jsdom
/**
 * O PORTÃO DAS SUPERFÍCIES DO GROWTH ENGINE.
 *
 * Duas provas, e as duas são absolutas.
 *
 * ## 1 · Zero chamada ao Google Ads no render
 *
 * A varredura estática pega o endereço escrito à mão; a sonda de render pega o
 * caso que a varredura não vê — uma dependência que abre conexão sozinha ao
 * montar. As duas juntas cobrem o que cada uma deixa passar: renderizamos TODAS
 * as superfícies novas com `fetch`, `XMLHttpRequest`, `WebSocket`,
 * `sendBeacon` e `EventSource` trocados por dublês que EXPLODEM se forem
 * chamados. Uma tela de conferência que consome cota da conta de anúncio do
 * cliente a cada abertura é o defeito que a Fase 1B já pagou uma vez.
 *
 * ## 2 · Zero credencial e zero poder de mutação
 *
 * Nada privilegiado sai do browser: nem chave, nem `service_role`, nem endereço
 * de webhook, nem `mutate`. O bundle é público por definição.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { derivarDiagnostico } from '@/lib/diagnostico/derivar';
import { evidenciaDeProva, ID_FGTS } from '@/lib/diagnostico/fixtureDeEvidencia';
import { proporMudancas } from '@/lib/diagnostico/propor';
import { montarConversa } from '@/components/trafego/criacao/conversa';
import { EscadaDeEntrega } from '../EscadaDeEntrega';
import { CaixaDePropostas } from '../CaixaDePropostas';
import { CartaoDeRecibo } from '@/components/trafego/recibos/CartaoDeRecibo';
import { lerRecibo } from '@/components/trafego/recibos/recibo';
import { QuadroDoLote } from '@/components/trafego/lote/QuadroDoLote';
import { ConversaDeCriacao } from '@/components/trafego/criacao/ConversaDeCriacao';
import { BibliotecaDeCriativos } from '@/components/trafego/criativos/BibliotecaDeCriativos';
import { VisaoDoCanal } from '@/components/trafego/canal/VisaoDoCanal';
import { PropostaDeAcao } from '@/components/trafego/hub/PropostaDeAcao';

// ── 1 · a sonda de render ───────────────────────────────────────────────────

const REDE_PROIBIDA = 'uma superfície do Growth Engine tentou usar a rede no render';

function explodir(): never {
  throw new Error(REDE_PROIBIDA);
}

const originais = {
  fetch: globalThis.fetch,
  XMLHttpRequest: globalThis.XMLHttpRequest,
  WebSocket: globalThis.WebSocket,
  EventSource: globalThis.EventSource,
  sendBeacon: navigator.sendBeacon,
};

beforeEach(() => {
  globalThis.fetch = vi.fn(explodir) as unknown as typeof fetch;
  globalThis.XMLHttpRequest = vi.fn(explodir) as unknown as typeof XMLHttpRequest;
  globalThis.WebSocket = vi.fn(explodir) as unknown as typeof WebSocket;
  globalThis.EventSource = vi.fn(explodir) as unknown as typeof EventSource;
  Object.defineProperty(navigator, 'sendBeacon', { value: explodir, configurable: true });
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originais.fetch;
  globalThis.XMLHttpRequest = originais.XMLHttpRequest;
  globalThis.WebSocket = originais.WebSocket;
  globalThis.EventSource = originais.EventSource;
  Object.defineProperty(navigator, 'sendBeacon', {
    value: originais.sendBeacon,
    configurable: true,
  });
});

const AGORA = new Date('2026-08-26T18:10:11.000Z');
const diagnostico = derivarDiagnostico(evidenciaDeProva(), ID_FGTS, { agora: AGORA });
const caixa = proporMudancas(diagnostico);
const recibo = lerRecibo({
  estado: 'ACEITO',
  carimbo: '20260819_200616',
  customer_id: '8017851692',
  login_customer_id: '6016739364',
  nome_campanha: 'FGTS',
  n_operacoes: 1,
  impressao: 'b468513e616f020f8156ff680f7a669887de58f4e6d5550252965817f39e302e',
  motivo: 'lançamento',
  criados: [{ posicao: 0, tipo: 'campaign_result', resource_name: 'customers/1/campaigns/2' }],
  request_id: '',
  falha: null,
  explicacao: 'a API confirmou.',
  nada_foi_criado: false,
})!;

const SUPERFICIES: [string, () => JSX.Element][] = [
  ['escada de entrega', () => <EscadaDeEntrega diagnostico={diagnostico} eixoAberto="orcamento" />],
  ['caixa de propostas', () => <CaixaDePropostas caixa={caixa} abertoInicial="subir-verba" />],
  ['proposta de ação', () => <PropostaDeAcao acao="orcamento" antes="R$ 20,00" />],
  ['recibo', () => <CartaoDeRecibo recibo={recibo} />],
  [
    'lote',
    () => (
      <QuadroDoLote
        lote={{
          id: 'l',
          estado: 'executando',
          aprovado_em: '2026-08-26T12:00:00.000Z',
          aprovado_por: 'tarcisio',
          itens: [
            {
              id: '1',
              rotulo: 'a',
              estado: 'criada_pausada',
              proxima_acao: 'verificar',
              falha: null,
              recibo,
              recibo_em_voo: false,
              encontradas_na_conta: 1,
            },
            {
              id: '2',
              rotulo: 'b',
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
        }}
      />
    ),
  ],
  [
    'conversa de criação',
    () => (
      <ConversaDeCriacao
        passos={montarConversa({
          manifesto: {
            plataforma: 'GOOGLE_ADS',
            canal: 'SEARCH',
            rotulo: 'Search',
            hierarquia: [],
            paineis: [],
            campos_do_pedido: ['objetivo', 'conversion_action'],
            capacidades: ['ler'],
            provas_obrigatorias: [],
            indisponibilidades: [],
            sabe_criar: true,
          },
          respostas: {},
          travaAberta: null,
          podeAprovar: true,
        })}
      />
    ),
  ],
  ['biblioteca de criativos', () => <BibliotecaDeCriativos criativos={[]} />],
  ['visão do canal', () => <VisaoDoCanal manifesto={null} />],
];

describe('⚠️ zero chamada ao Google Ads no render', () => {
  for (const [nome, montar] of SUPERFICIES) {
    it(`${nome} monta sem tocar a rede`, () => {
      expect(() => render(montar())).not.toThrow();
      expect(globalThis.fetch).not.toHaveBeenCalled();
      expect(globalThis.XMLHttpRequest).not.toHaveBeenCalled();
      expect(globalThis.WebSocket).not.toHaveBeenCalled();
      expect(globalThis.EventSource).not.toHaveBeenCalled();
    });
  }
});

// ── 2 · a varredura estática ────────────────────────────────────────────────

/**
 * ⚠️ Dois escopos, porque as afirmações não são a mesma.
 *
 * A varredura por pasta garante que um arquivo NOVO entra sozinho — mas só
 * dentro de uma pasta listada. Três arquivos desta mesma entrega ficaram de
 * fora: o hook, a página e o cliente HTTP. A auditoria adversarial encontrou o
 * buraco, e a correção não é acrescentar os três à mesma lista: `pautadorApi`
 * **existe para falar com a rede**, e metê-lo no escopo de "nenhum fetch"
 * transformaria o portão numa exceção permanente, que é como um portão morre.
 *
 * `APRESENTACAO` — não pode ter rede, nem mutação, nem segredo.
 * `TUDO` — acrescenta o cliente da casa, e vale só para as regras que valem
 * para ele também: segredo e endereço do Google Ads.
 */
const APRESENTACAO = [
  'src/types/diagnostico.ts',
  'src/lib/diagnostico',
  'src/components/trafego/diagnostico',
  'src/components/trafego/recibos',
  'src/components/trafego/lote',
  'src/components/trafego/criacao',
  'src/components/trafego/criativos',
  'src/components/trafego/canal',
  'src/components/trafego/hub/PropostaDeAcao.tsx',
  'src/hooks/useDiagnosticoDeEntrega.ts',
  'src/pages/trafego/CampanhaCanonPage.tsx',
];

//: O único módulo desta entrega que tem o direito de abrir uma conexão.
const CLIENTE_DA_CASA = ['src/lib/pautadorApi.ts'];

const RAIZES = APRESENTACAO;

/**
 * ⚠️ O próprio varredor sai da varredura.
 *
 * Ele CITA os padrões proibidos para poder procurá-los, e se varresse a si
 * mesmo acusaria a si mesmo — um teste que falha sempre não prova nada e é
 * removido na primeira semana. Qualquer OUTRO arquivo, teste e fixture
 * inclusive, continua dentro: segredo em fixture vai para o repositório do
 * mesmo jeito que segredo em código.
 */
const ESTE_ARQUIVO = 'seguranca-growth-engine.test.tsx';

function arquivos(caminho: string): string[] {
  if (statSync(caminho).isFile()) {
    return caminho.endsWith(ESTE_ARQUIVO) ? [] : [caminho];
  }
  return readdirSync(caminho).flatMap((n) => arquivos(join(caminho, n)));
}

const TODOS = RAIZES.flatMap(arquivos);
const CONTEUDO = TODOS.map((p) => readFileSync(p, 'utf8')).join('\n');

//: Apresentação + o cliente da casa. Segredo não tem exceção para ninguém.
const CONTEUDO_COM_CLIENTE = [...TODOS, ...CLIENTE_DA_CASA.flatMap(arquivos)]
  .map((p) => readFileSync(p, 'utf8'))
  .join('\n');

describe('⚠️ nada privilegiado sai do browser', () => {
  it('a varredura cobre todos os arquivos novos, e não uma lista que envelhece', () => {
    // Se alguém acrescentar um arquivo numa destas pastas, ele entra sozinho.
    expect(TODOS.length).toBeGreaterThan(14);
  });

  it('nenhum endereço do Google Ads aparece em lugar nenhum', () => {
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/googleads\.googleapis\.com/);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/https:\/\/[a-z.]*googleapis\.com/);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/developer-token/i);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/login-customer-id/i);
  });

  it('nenhum segredo, chave ou token — inclusive no cliente da casa', () => {
    // ⚠️ Aqui a varredura INCLUI `pautadorApi`. Ele pode abrir conexão; não pode
    // carregar segredo.
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/service_role/i);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/SUPABASE_SERVICE_ROLE/);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/refresh_token/);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/client_secret/);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/Bearer\s+[A-Za-z0-9._-]{20,}/);
    expect(CONTEUDO_COM_CLIENTE).not.toMatch(/eyJ[A-Za-z0-9_-]{20,}\./);

    // `VITE_PAUTADOR_API_KEY` continua proibida na apresentação. No cliente ela
    // aparece uma vez, num comentário que registra a REMOÇÃO dela em 24/08/2026
    // — tudo que começa com `VITE_` vira valor literal no build, e a chave era
    // o portão de 24 rotas do backend. Apagar o comentário apagaria a memória de
    // por que ela não pode voltar; o teste garante que ela não voltou como uso.
    expect(CONTEUDO).not.toMatch(/VITE_PAUTADOR_API_KEY/);
    const cliente = CLIENTE_DA_CASA.flatMap(arquivos)
      .map((p) => readFileSync(p, 'utf8'))
      .join('\n');
    expect(cliente).not.toMatch(/import\.meta\.env\.VITE_PAUTADOR_API_KEY/);
    expect(cliente).not.toMatch(/['"]X-API-Key['"]/);
  });

  it('nenhum caminho de mutação e nenhum webhook', () => {
    expect(CONTEUDO).not.toMatch(/mutateGoogle/i);
    expect(CONTEUDO).not.toMatch(/GoogleAdsService\.Mutate/i);
    expect(CONTEUDO).not.toMatch(/n8n\.[a-z]+\/webhook/i);
    // `validate_only` pode ser NOMEADO (é uma prova obrigatória do manifesto);
    // o que não pode é esta camada montar a chamada.
    expect(CONTEUDO).not.toMatch(/method:\s*['"]POST['"]/);
  });

  it('nenhum `fetch` direto: quem fala com o servidor é o cliente da casa', () => {
    expect(CONTEUDO).not.toMatch(/\bfetch\s*\(/);
    expect(CONTEUDO).not.toMatch(/new\s+XMLHttpRequest/);
    expect(CONTEUDO).not.toMatch(/axios/);
  });
});
