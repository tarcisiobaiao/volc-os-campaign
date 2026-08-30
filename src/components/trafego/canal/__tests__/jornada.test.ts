/**
 * A gramática por canal é contrato. Estas provas existem para que o JSX
 * não volte a desenhar sete etapas genéricas — e para que Vídeo nunca
 * ganhe um botão de criar pela API.
 */
import { describe, expect, it } from 'vitest';

import type { CapacidadesDoOperador, EstadoDaTrava, ManifestoDeCanal } from '@/types/trafego';
import {
  FONTES_OFICIAIS,
  PALAVRA_DO_PAPEL,
  apresentarBancada,
  apresentarCanal,
  canalTemEtapaObrigatoriaDeImagem,
  etapaDeAnuncio,
} from '../jornada';

const manifesto = (over: Partial<ManifestoDeCanal> = {}): ManifestoDeCanal => ({
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo'],
  paineis: [],
  campos_do_pedido: ['url_final', 'verba_diaria', 'copy'],
  capacidades: ['ler', 'propor', 'escrever'],
  provas_obrigatorias: ['politica', 'duplicidade', 'selo'],
  indisponibilidades: [],
  sabe_provar: true,
  sabe_criar: true,
  ...over,
});

const adminQueEscreve: CapacidadesDoOperador = {
  is_admin: true,
  lab_mode: false,
  google_read: true,
  google_validate_only: true,
  google_demand_gen_validate_only: false,
  google_mutate: true,
  porque_sem_mutacao: null,
};

const travaAberta: EstadoDaTrava = {
  // Retrato real de `/trava` em repouso: o primeiro fator só fica true
  // dentro da rota final. `env_presente` é a autorização durável.
  escrita_permitida: false,
  destravado_no_codigo: false,
  env_presente: true,
  motivo: '',
  explicacao: '',
};

const travaFechada: EstadoDaTrava = {
  escrita_permitida: false,
  destravado_no_codigo: false,
  env_presente: false,
  motivo: 'fechada',
  explicacao: 'A trava de dois fatores está fechada.',
};

describe('Search', () => {
  const a = apresentarCanal('SEARCH', manifesto(), { capacidades: adminQueEscreve, trava: travaAberta });

  it('nomeia a etapa Anúncio e recursos, nunca Criativos de imagem e vídeo', () => {
    const etapa = etapaDeAnuncio(a);
    expect(etapa?.titulo).toBe('Anúncio e recursos');
    expect(etapa?.titulo.toLowerCase()).not.toContain('criativo');
    expect(a.etapas.some((e) => /criativos de imagem e vídeo/i.test(e.titulo))).toBe(false);
  });

  it('não trata imagem ou vídeo como requisito de criação', () => {
    expect(canalTemEtapaObrigatoriaDeImagem(a)).toBe(false);
    const anuncio = etapaDeAnuncio(a);
    expect(anuncio?.pergunta).toMatch(/não são requisito/i);
    expect(anuncio?.detalhes).toEqual(
      expect.arrayContaining(['pelo menos 3 headlines', 'pelo menos 2 descriptions', 'URL final']),
    );
  });

  it('aponta o CTA operacional para o cockpit real em Preparar', () => {
    expect(a.cta.tipo).toBe('cockpit');
    expect(a.cta.rotulo).toBe('Começar campanha');
    expect(a.cta.destino).toBe('/trafego?aba=preparar');
    expect(a.etapasComoFormulario).toBe(true);
    expect(a.papel).toBe('operacional');
  });

  it('a criação pausada e a ativação são etapas distintas', () => {
    expect(a.etapas.map((e) => e.chave)).toEqual(
      expect.arrayContaining(['criacao', 'ativacao']),
    );
    const criacao = a.etapas.find((e) => e.chave === 'criacao');
    const ativacao = a.etapas.find((e) => e.chave === 'ativacao');
    expect(criacao?.pergunta).toMatch(/pausada/);
    expect(ativacao?.pergunta).toMatch(/separada/);
  });
});

describe('Display não é Search e não é Demand Gen', () => {
  const display = apresentarCanal(
    'DISPLAY',
    manifesto({
      canal: 'DISPLAY',
      rotulo: 'Display',
      sabe_criar: true,
      indisponibilidades: ['a primeira fatia não monta segmentação'],
    }),
    { capacidades: adminQueEscreve, trava: travaAberta },
  );
  const demand = apresentarCanal('DEMAND_GEN', manifesto({ canal: 'DEMAND_GEN', rotulo: 'Demand Gen', sabe_provar: true, sabe_criar: false }));

  it('o contrato visual do RDA aparece na jornada', () => {
    const anuncio = etapaDeAnuncio(display);
    expect(anuncio?.titulo).toMatch(/display/i);
    expect(anuncio?.detalhes).toEqual(
      expect.arrayContaining(['imagens de marketing', 'imagens quadradas', 'long headline', 'business name']),
    );
    expect(display.papel).toBe('parcial');
  });

  it('Demand Gen tem etapas que o Display não tem, e vice-versa', () => {
    expect(demand.etapas.map((e) => e.chave)).toEqual(
      expect.arrayContaining(['audiencia', 'intencao', 'exclusoes', 'canais', 'tipo', 'atomico']),
    );
    expect(display.etapas.map((e) => e.chave)).not.toEqual(demand.etapas.map((e) => e.chave));
    expect(demand.etapas.some((e) => /payload|atômic/i.test(`${e.titulo} ${e.pergunta}`))).toBe(true);
    expect(demand.frase).toMatch(/não é Display/);
  });
});

describe('Performance Max', () => {
  const pmax = apresentarCanal(
    'PERFORMANCE_MAX',
    manifesto({
      canal: 'PERFORMANCE_MAX',
      rotulo: 'Performance Max',
      sabe_provar: false,
      sabe_criar: false,
      campos_do_pedido: [],
      indisponibilidades: ['não há construtor de campanha para Performance Max'],
    }),
  );

  it('é asset group, não grupo de anúncios de Search', () => {
    expect(pmax.etapas.some((e) => e.chave === 'asset-group')).toBe(true);
    expect(pmax.etapas.some((e) => /grupos de anúncios de Search/i.test(e.pergunta))).toBe(true);
    expect(pmax.etapas.some((e) => e.chave === 'keywords')).toBe(false);
  });

  it('sem construtor o CTA não é cockpit e as etapas não fingem formulário', () => {
    expect(pmax.cta.tipo).toBe('desbloqueio');
    expect(pmax.etapasComoFormulario).toBe(false);
    expect(pmax.intersecao.escritaLiberada).toBe(false);
    expect(pmax.papel).toBe('planejado');
  });
});

describe('Demand Gen tem prova estreita sem criação real', () => {
  const perfilDemand = manifesto({
    canal: 'DEMAND_GEN',
    rotulo: 'Demand Gen',
    sabe_provar: true,
    sabe_criar: false,
    indisponibilidades: ['criação real continua recusada em /subir'],
  });

  it('flag/capacidade ausente fecha o cockpit apesar de o builder existir', () => {
    const a = apresentarCanal('DEMAND_GEN', perfilDemand, {
      capacidades: { ...adminQueEscreve, google_demand_gen_validate_only: false },
      trava: travaAberta,
    });
    expect(a.intersecao.backend).toBe(true);
    expect(a.intersecao.provaLiberada).toBe(false);
    expect(a.cta.tipo).toBe('desbloqueio');
    expect(a.cta.porque).toMatch(/desligada/);
  });

  it('capacidade ligada expõe a prova HTTP sem fingir um cockpit Demand Gen', () => {
    const a = apresentarCanal('DEMAND_GEN', perfilDemand, {
      capacidades: { ...adminQueEscreve, google_demand_gen_validate_only: true },
      trava: travaAberta,
    });
    expect(a.intersecao.provaLiberada).toBe(true);
    expect(a.intersecao.escritaLiberada).toBe(false);
    expect(a.intersecao.cockpitLiberado).toBe(false);
    expect(a.etapasComoFormulario).toBe(false);
    expect(a.cta).toMatchObject({ tipo: 'desbloqueio', rotulo: 'Prova HTTP habilitada' });
    expect(a.cta.porque).toMatch(/não redireciona para o cockpit de Search/);
    expect(a.etapas.map((e) => e.chave)).toEqual(
      expect.arrayContaining(['audiencia', 'intencao', 'exclusoes', 'canais']),
    );
    expect(a.etapas.find((e) => e.chave === 'tipo')?.pergunta).toMatch(/MultiAssetAdInfo/);
  });
});

describe('Shopping', () => {
  const shopping = apresentarCanal('SHOPPING', null);

  it('sem Merchant Center é pré-requisito ausente, não erro de campanha', () => {
    expect(shopping.papel).toBe('pre_requisito');
    expect(PALAVRA_DO_PAPEL[shopping.papel]).toMatch(/Merchant Center/);
    expect(shopping.frase).toMatch(/pré-requisito ausente/);
    expect(shopping.cta.tipo).toBe('desbloqueio');
    expect(shopping.etapas.some((e) => e.chave === 'merchant')).toBe(true);
    expect(shopping.etapas.some((e) => e.chave === 'anuncio')).toBe(false);
  });
});

describe('Vídeo', () => {
  it('a API não cria: mesmo com manifesto mentiroso o CTA não é criar', () => {
    const video = apresentarCanal(
      'VIDEO',
      manifesto({ canal: 'VIDEO', rotulo: 'Vídeo', sabe_criar: true }),
      { capacidades: adminQueEscreve, trava: travaAberta },
    );
    expect(video.papel).toBe('somente_leitura');
    expect(video.cta.tipo).toBe('observar');
    expect(video.cta.rotulo).toBe('Observar e analisar');
    expect(video.intersecao.api).toBe(false);
    expect(video.intersecao.cockpitLiberado).toBe(false);
    expect(video.intersecao.escritaLiberada).toBe(false);
    expect(video.recusa).toMatch(/não cria/);
    expect(`${video.cta.rotulo} ${video.frase} ${video.recusa}`.toLowerCase()).not.toMatch(
      /criar campanha video pela api/,
    );
    expect(video.alternativas.map((a) => a.canal)).toEqual(['DEMAND_GEN', 'PERFORMANCE_MAX']);
    expect(video.fontes).toContainEqual(FONTES_OFICIAIS.video);
  });

  it('sem manifesto continua observável — ausência não some o canal', () => {
    const video = apresentarCanal('VIDEO', null);
    expect(video.papel).toBe('somente_leitura');
    expect(video.cta.tipo).toBe('observar');
  });
});

describe('a interseção que libera escrita', () => {
  const search = manifesto();

  it('cockpit abre com API e VOLC; escrita só com permissão e trava', () => {
    const a = apresentarCanal('SEARCH', search, {
      capacidades: { ...adminQueEscreve, google_mutate: false, porque_sem_mutacao: 'permissão fechada neste servidor' },
      trava: travaAberta,
    });
    expect(a.cta.tipo).toBe('cockpit');
    expect(a.intersecao.cockpitLiberado).toBe(true);
    expect(a.intersecao.escritaLiberada).toBe(false);
    expect(a.intersecao.eixo).toBe('permissao');
    expect(a.intersecao.porqueNao).toMatch(/permissão fechada/);
  });

  it('trava fechada não some o cockpit e não afirma escrita', () => {
    const a = apresentarCanal('SEARCH', search, { capacidades: adminQueEscreve, trava: travaFechada });
    expect(a.cta.tipo).toBe('cockpit');
    expect(a.intersecao.escritaLiberada).toBe(false);
    expect(a.intersecao.eixo).toBe('trava');
  });

  it('env presente libera a tentativa mesmo com escrita_permitida false em repouso', () => {
    const a = apresentarCanal('SEARCH', search, {
      capacidades: adminQueEscreve,
      trava: {
        ...travaAberta,
        escrita_permitida: false,
        destravado_no_codigo: false,
      },
    });
    expect(a.intersecao.trava).toBe(true);
    expect(a.intersecao.escritaLiberada).toBe(true);
    expect(a.intersecao.eixo).toBeNull();
  });

  it('permissão ainda não lida não vira recusa de papel', () => {
    const a = apresentarCanal('SEARCH', search, { capacidades: null, trava: travaAberta });
    expect(a.intersecao.permissao).toBeNull();
    expect(a.intersecao.porqueNao).toMatch(/não chegou/);
    expect(a.cta.tipo).toBe('cockpit');
  });

  it('sem construtor o cockpit não abre mesmo com trava aberta', () => {
    const a = apresentarCanal(
      'DEMAND_GEN',
      manifesto({ canal: 'DEMAND_GEN', sabe_provar: false, sabe_criar: false, indisponibilidades: ['sem construtor'] }),
      { capacidades: adminQueEscreve, trava: travaAberta },
    );
    expect(a.cta.tipo).toBe('desbloqueio');
    expect(a.intersecao.cockpitLiberado).toBe(false);
    expect(a.intersecao.eixo).toBe('backend');
  });
});

describe('a bancada tem os seis canais, nesta ordem', () => {
  it('completa o que o manifesto não listou, sem inventar construtor', () => {
    const bancada = apresentarBancada([manifesto(), manifesto({ canal: 'DISPLAY', rotulo: 'Display' })]);
    expect(bancada.map((c) => c.canal)).toEqual([
      'SEARCH',
      'DISPLAY',
      'DEMAND_GEN',
      'PERFORMANCE_MAX',
      'VIDEO',
      'SHOPPING',
    ]);
    expect(bancada.find((c) => c.canal === 'VIDEO')?.papel).toBe('somente_leitura');
    expect(bancada.find((c) => c.canal === 'SHOPPING')?.papel).toBe('pre_requisito');
    expect(bancada.find((c) => c.canal === 'SEARCH')?.cta.tipo).toBe('cockpit');
  });
});
