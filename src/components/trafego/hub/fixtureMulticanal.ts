/**
 * Fixtures do Hub U0 / H0 — tipadas, isoladas, e o único lugar que conhece
 * FGTS e Maquininha pelo nome.
 *
 * A tela não detecta campanha existente pelo título. Estes objetos simulam o
 * que o contrato real devolve: o objeto `reconciliacao`.
 */
import type {
  AcaoDeReconciliacao,
  CandidatoNoQuadro,
  EstadoDeReconciliacao,
  Reconciliacao,
} from '@/types/trafego';

import type { CandidatoPreparar } from './contrato';

const ACAO: Record<EstadoDeReconciliacao, AcaoDeReconciliacao> = {
  vinculada: 'abrir_o_que_existe',
  correspondencia_provavel: 'confirmar_vinculo',
  conflito: 'abrir_revisao',
  sem_campanha: 'montar',
  somente_historico: 'relancar_declarado',
};

export function veredito(
  opportunity_id: number,
  run_id: number,
  estado: EstadoDeReconciliacao,
  extra?: Partial<Reconciliacao>,
): Reconciliacao {
  return {
    opportunity_id,
    run_id,
    estado,
    candidatas: [],
    sinais_ausentes: [],
    acao_permitida: ACAO[estado],
    exige_confirmacao_humana: estado === 'correspondencia_provavel' || estado === 'conflito',
    pode_montar: estado === 'sem_campanha',
    pode_relancar: estado === 'somente_historico',
    ...extra,
  };
}

export const maquininhaVinculada: CandidatoPreparar = {
  opportunity_id: 63,
  run_id: 7,
  titulo: 'Maquininha de cartão para MEI',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/maquininha/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 23,
  volume_total: 148_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 1,
  reconciliacao: veredito(63, 7, 'vinculada'),
};

export const fgtsVinculada: CandidatoPreparar = {
  opportunity_id: 71,
  run_id: 8,
  titulo: 'FGTS saque-aniversário',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/fgts/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 18,
  volume_total: 96_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 1,
  reconciliacao: veredito(71, 8, 'vinculada'),
};

export const candidatoEmConflito: CandidatoPreparar = {
  opportunity_id: 90,
  run_id: 12,
  titulo: 'Portabilidade de consignado',
  dominio: 'portalmundomais.com.br',
  lp_url: null,
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 11,
  volume_total: 40_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 2,
  reconciliacao: veredito(90, 12, 'conflito'),
};

export const candidatoSomenteHistorico: CandidatoPreparar = {
  opportunity_id: 55,
  run_id: 4,
  titulo: 'Cartão de crédito consignado',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/cartao/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 9,
  volume_total: 22_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 0,
  reconciliacao: veredito(55, 4, 'somente_historico'),
};

export const candidatoSemCampanha: CandidatoPreparar = {
  opportunity_id: 101,
  run_id: 14,
  titulo: 'Empréstimo com garantia',
  dominio: 'creditoup.com.br',
  lp_url: null,
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 7,
  volume_total: 12_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 0,
  reconciliacao: veredito(101, 14, 'sem_campanha'),
};

/** FGTS sem declaração canônica — o caso que não pode virar "montar". */
export const fgtsSemReconciliacao: CandidatoPreparar = {
  opportunity_id: 71,
  run_id: 8,
  titulo: 'FGTS saque-aniversário',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/fgts/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 18,
  volume_total: 96_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 0,
};

/** Lançada na conta, mas a fonte canônica ainda não declarou o vínculo. */
export const lancadaSemReconciliacao: CandidatoPreparar = {
  opportunity_id: 72,
  run_id: 9,
  titulo: 'FGTS saque-aniversário',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/fgts/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 18,
  volume_total: 96_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 1,
};

export const candidatoCorrespondencia: CandidatoPreparar = {
  opportunity_id: 88,
  run_id: 10,
  titulo: 'Antecipação do 13º',
  dominio: 'creditoup.com.br',
  lp_url: null,
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 5,
  volume_total: 8_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 0,
  reconciliacao: veredito(88, 10, 'correspondencia_provavel'),
};

/** FGTS real (run 9): correspondência provável — nome/URL não liberam montagem. */
export const fgtsCorrespondencia: CandidatoPreparar = {
  opportunity_id: 71,
  run_id: 9,
  titulo: 'FGTS saque-aniversário',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/fgts/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 18,
  volume_total: 96_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 1,
  reconciliacao: veredito(71, 9, 'correspondencia_provavel'),
};

/** Maquininha real (run 7): correspondência provável. */
export const maquininhaCorrespondencia: CandidatoPreparar = {
  opportunity_id: 63,
  run_id: 7,
  titulo: 'Maquininha de cartão para MEI',
  dominio: 'creditoup.com.br',
  lp_url: 'https://creditoup.com.br/r/maquininha/',
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 23,
  volume_total: 148_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 1,
  reconciliacao: veredito(63, 7, 'correspondencia_provavel'),
};

/** `reconciliacao: null` — a prova falhou. Não é `sem_campanha`. */
export const reconciliacaoNula: CandidatoPreparar = {
  ...fgtsSemReconciliacao,
  campanhas_lancadas: null,
  reconciliacao: null,
};

/** Rascunho: sem_campanha com confirmação pendente. Montar segue liberado. */
export const rascunhoComAviso: CandidatoPreparar = {
  opportunity_id: 50,
  run_id: 6,
  titulo: 'Funil em rascunho',
  dominio: 'creditoup.com.br',
  lp_url: null,
  paginas_publicadas: 1,
  tem_cluster: true,
  keywords_para_anuncio: 4,
  volume_total: 3_000,
  servicos_declarados: ['n8n:dataforseo'],
  campanhas_lancadas: 0,
  reconciliacao: veredito(50, 6, 'sem_campanha', {
    exige_confirmacao_humana: true,
    pode_montar: true,
    sinais_ausentes: [{
      regra: 'url_final_da_conta',
      motivo: 'funil ainda em rascunho, sem URL colhida',
      impede_prova: true,
    }],
  }),
};

/** sem_campanha sem pode_montar — a montagem não abre. */
export const semCampanhaSemPodeMontar: CandidatoPreparar = {
  ...candidatoSemCampanha,
  opportunity_id: 102,
  titulo: 'Antecipação do IR',
  reconciliacao: veredito(102, 14, 'sem_campanha', { pode_montar: false }),
};

export function comoCandidatoDoContrato(c: CandidatoPreparar): CandidatoNoQuadro {
  return c;
}
