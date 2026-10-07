// @vitest-environment jsdom
/**
 * Retratos das superfícies novas, para conferência visual fora do login.
 *
 * ## Por que isto existe
 *
 * O produto é fechado por autenticação, e a conferência visual de uma tela de
 * operação não pode depender de alguém estar com a sessão aberta. Aqui as
 * superfícies são renderizadas em cada um dos seus estados e o HTML é gravado
 * em disco, para ser aberto com o CSS real do produto — mesmos tokens, mesma
 * tipografia, mesmo tema claro e escuro.
 *
 * ⚠️ Isto NÃO substitui ver a tela logada com dado real. Ele cobre o que o
 * login não deveria impedir: hierarquia, densidade, contraste, e os estados
 * que quase nunca aparecem na navegação normal — falha de leitura, ausência
 * apurada e ausência não apurada.
 *
 * ⚠️ E não afirma nada sobre o produto: se `RETRATOS=1` não estiver no
 * ambiente, o arquivo inteiro é pulado. Um teste que grava arquivo a cada
 * `vitest run` polui a árvore de quem só queria rodar a suíte.
 */
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RevisarCorrespondencia } from '@/components/trafego/vinculo/RevisarCorrespondencia';
import {
  FaixaDeLaboratorio,
  MolduraDePrototipo,
} from '@/components/trafego/laboratorio/SeloDePrototipo';
import { EstruturaDoCanal } from '@/components/trafego/hub/EstruturaDoCanal';
import { EstudioMulticanal } from '@/components/trafego/estudio/EstudioMulticanal';
import type { ManifestoDeCanal, RevisaoDeCorrespondencia } from '@/types/trafego';

const api = vi.hoisted(() => ({
  correspondenciasDaCampanha: vi.fn(),
  confirmarVinculo: vi.fn(),
  desfazerVinculo: vi.fn(),
}));
vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));

const DESTINO = process.env.RETRATOS_DIR || '';
const LIGADO = process.env.RETRATOS === '1' && Boolean(DESTINO);

const ID = 'gads-8017851692-24155134757';
const URL_MAQ = 'https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa/';

const base: RevisaoDeCorrespondencia = {
  volc_campaign_id: ID,
  estado: 'correspondencia_unica',
  url_da_campanha: URL_MAQ,
  correspondencias: [
    {
      opportunity_id: 74,
      run_id: 7,
      project_id: 2,
      destinos: [URL_MAQ],
      sinais: [
        { regra: 'url_final_da_conta', forca: 'historica', evidencia: { url: URL_MAQ } },
      ],
      estado_do_funil: 'correspondencia_provavel',
      outras_campanhas_presentes: 0,
      forca_maxima: 'historica',
    },
  ],
  sinais_ausentes: [],
  vinculo: null,
  exige_confirmacao_humana: true,
};

function guardar(nome: string, html: string) {
  fs.mkdirSync(DESTINO, { recursive: true });
  fs.writeFileSync(path.join(DESTINO, `${nome}.html`), html, 'utf8');
}

function envolver(no: React.ReactNode) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={cliente}>{no}</QueryClientProvider>);
}

afterEach(cleanup);

describe.runIf(LIGADO)('retratos das superfícies', () => {
  it('grava cada estado da revisão de correspondência', async () => {
    const estados: Array<[string, RevisaoDeCorrespondencia]> = [
      ['vinculo-correspondencia-unica', base],
      [
        'vinculo-disputado',
        {
          ...base,
          correspondencias: [
            { ...base.correspondencias[0], estado_do_funil: 'conflito', outras_campanhas_presentes: 1 },
          ],
        },
      ],
      [
        'vinculo-mais-de-uma',
        {
          ...base,
          estado: 'mais_de_uma_correspondencia',
          correspondencias: [
            base.correspondencias[0],
            {
              ...base.correspondencias[0],
              opportunity_id: 65,
              run_id: 9,
              destinos: ['https://creditoup.com.br/r/fgts-saque-aniversario/'],
              sinais: [
                { regra: 'url_no_nome_declarado', forca: 'medio', evidencia: {} },
              ],
              forca_maxima: 'medio',
            },
          ],
        },
      ],
      [
        'vinculo-sem-correspondencia',
        { ...base, estado: 'sem_correspondencia', correspondencias: [], exige_confirmacao_humana: false },
      ],
      [
        'vinculo-nao-apurada',
        {
          ...base,
          estado: 'nao_apurada',
          correspondencias: [],
          exige_confirmacao_humana: false,
          sinais_ausentes: [
            {
              regra: 'conta_da_campanha',
              motivo: 'esta campanha não tem conta de anúncio identificada; sem conta não há onde procurar',
              impede_prova: true,
            },
          ],
        },
      ],
      [
        'vinculo-associada',
        {
          ...base,
          estado: 'associada',
          correspondencias: [],
          exige_confirmacao_humana: false,
          vinculo: { vinculo_id: 'a1b2c3d4-0000-0000-0000-000000000000', opportunity_id: 74, run_id: 7 },
        },
      ],
    ];

    for (const [nome, dados] of estados) {
      api.correspondenciasDaCampanha.mockResolvedValue(dados);
      const { container } = envolver(
        <RevisarCorrespondencia
          volcCampaignId={ID}
          nomeDaCampanha="BR - 20260819_131546 / Maquininha de Cartão"
          contaExterna="8017851692"
          idExterno="24155134757"
          estadoExterno="ENABLED"
        />,
      );
      await waitFor(() => expect(container.textContent).not.toContain('procurando funis'));
      guardar(nome, container.innerHTML);
      cleanup();
    }

    // O estado de falha, que é o que quase nunca se vê e mais importa acertar.
    api.correspondenciasDaCampanha.mockRejectedValue(
      Object.assign(new Error('x'), { status: 503 }),
    );
    const { container } = envolver(
      <RevisarCorrespondencia volcCampaignId={ID} nomeDaCampanha="Maquininha" />,
    );
    await screen.findByRole('alert');
    guardar('vinculo-falha-de-leitura', container.innerHTML);
  });

  it('grava o laboratório, o protótipo e as ausências de canal', () => {
    const { container: lab } = envolver(
      <div className="space-y-6">
        <FaixaDeLaboratorio ligado />
        <MolduraDePrototipo
          fonte="fixture determinística do estúdio de Demand Gen"
          aindaNao="não há construtor de campanha para Demand Gen: o engine sabe ajustar uma campanha existente, não criar uma."
        >
          <div className="space-y-2">
            <p className="font-display text-sm font-semibold">Público e criativo</p>
            <p className="text-[13px] text-muted-foreground">
              Três formatos de exemplo, com números fixos que não entram em total nenhum.
            </p>
          </div>
        </MolduraDePrototipo>
      </div>,
    );
    guardar('laboratorio-e-prototipo', lab.innerHTML);
    cleanup();

    const { container: canais } = envolver(
      <div className="space-y-8">
        <EstruturaDoCanal
          rede="google"
          canal="SEARCH"
          aba="estrutura"
          manifesto={{
            plataforma: 'GOOGLE_ADS', canal: 'SEARCH', rotulo: 'Search',
            hierarquia: ['campanha'], paineis: [], campos_do_pedido: ['keywords'],
            capacidades: ['ler', 'propor'], provas_obrigatorias: [],
            indisponibilidades: [], sabe_provar: true, sabe_criar: false,
          }}
        />
        <EstruturaDoCanal
          rede="google"
          canal="DISPLAY"
          aba="estrutura"
          manifesto={{
            plataforma: 'GOOGLE_ADS', canal: 'DISPLAY', rotulo: 'Display',
            hierarquia: ['campanha'], paineis: [], campos_do_pedido: ['copy'],
            capacidades: ['ler', 'propor'], provas_obrigatorias: [],
            indisponibilidades: [], sabe_provar: true, sabe_criar: true,
          }}
        />
        <EstruturaDoCanal rede="google" canal="VIDEO" aba="desempenho" manifesto={null} />
      </div>,
    );
    guardar('canais-ausencia-declarada', canais.innerHTML);
  });

  it('grava o estúdio: canal que sabe criar e canal que declara a recusa', () => {
    // Os manifestos REAIS que `plataforma.py` emite hoje — não uma invenção.
    const manifestos: ManifestoDeCanal[] = [
      {
        plataforma: 'GOOGLE_ADS' as const, canal: 'SEARCH', rotulo: 'Search',
        hierarquia: ['campanha', 'grupo', 'anuncio', 'keyword'],
        paineis: ['keywords', 'termos_de_busca', 'anuncios', 'negativas'],
        campos_do_pedido: ['grupos', 'keywords', 'negativas', 'copy', 'url_final',
                           'verba_diaria', 'estrategia_de_lance'],
        capacidades: ['ler', 'propor'], provas_obrigatorias: ['politica', 'duplicidade', 'selo'],
        indisponibilidades: [], sabe_provar: true, sabe_criar: true,
      },
      {
        plataforma: 'GOOGLE_ADS' as const, canal: 'DISPLAY', rotulo: 'Display',
        hierarquia: ['campanha', 'grupo', 'anuncio', 'asset'],
        paineis: ['anuncios', 'criativos'],
        campos_do_pedido: ['copy', 'criativos', 'url_final', 'verba_diaria', 'estrategia_de_lance'],
        capacidades: ['ler', 'propor'], provas_obrigatorias: ['politica', 'duplicidade', 'selo'],
        indisponibilidades: [
          'a primeira fatia de Display não monta segmentação: a campanha nasce em inventário aberto, escolhido pelo lance.',
          'Display não aceita lance manual: a tabela oficial de estratégias não declara compatibilidade do CPC manual com este canal.',
        ],
        sabe_provar: true,
        sabe_criar: true,
      },
      {
        plataforma: 'GOOGLE_ADS' as const, canal: 'PERFORMANCE_MAX', rotulo: 'Performance Max',
        hierarquia: ['campanha', 'asset_group', 'asset'], paineis: [], campos_do_pedido: [],
        capacidades: ['ler'], provas_obrigatorias: [],
        indisponibilidades: [
          'não há construtor de campanha para Performance Max — o engine levanta exceção. O canal existe no inventário porque a conta pode ter campanhas dele, e escondê-las seria mentir sobre o que está gastando.',
        ],
        sabe_provar: false,
        sabe_criar: false,
      },
    ];
    const capacidades = {
      is_admin: true, lab_mode: true, google_read: true,
      google_validate_only: true, google_mutate: false,
      porque_sem_mutacao: 'a permissão operacional para escrever nas contas está fechada neste servidor.',
    };

    for (const [nome, canal] of [['estudio-search', 'SEARCH'], ['estudio-pmax-recusa', 'PERFORMANCE_MAX']] as const) {
      const { container } = envolver(
        <EstudioMulticanal manifestos={manifestos} capacidades={capacidades} canal={canal} />,
      );
      guardar(nome, container.innerHTML);
      cleanup();
    }
  });
});
