/**
 * TRADUTOR DE FIXTURE — `evidencia.json` → `DiagnosticoDeEntrega`.
 *
 * ## Por que este arquivo existe, e quando ele morre
 *
 * O contrato que a tela consome é `DiagnosticoDeEntrega`: um diagnóstico já
 * apurado, que o backend vai emitir em `GET /api/trafego/campanhas/{id}/
 * diagnostico`. Esse endereço ainda não existe. O que existe é o dump bruto do
 * runner somente-leitura, e é com ele que dá para provar a tela contra dados
 * reais em vez de contra invenção.
 *
 * Então este módulo é uma PONTE DECLARADA, não a casa das regras de negócio:
 *
 *  - ele é puro, isolado em `lib/` e nenhum componente React o importa;
 *  - a tela só conhece `DiagnosticoDeEntrega`; trocar a ponte pelo endpoint não
 *    toca em nenhum componente;
 *  - condição de aposentadoria: quando o backend emitir `DiagnosticoDeEntrega`,
 *    este arquivo passa a ser usado só nos testes, e depois some.
 *
 * ⚠️ Não faz e nunca fará chamada ao Google Ads. Ele lê um JSON que outra
 * pessoa colheu, em outra máquina, com escrita travada.
 */
import {
  VERSAO_DIAGNOSTICO,
  type DegrauDeEntrega,
  type DiagnosticoDeEntrega,
  type EixoDeEntrega,
  type EstadoDoDegrau,
  type EvidenciaDeCampo,
  type OrigemDaEvidencia,
} from '@/types/diagnostico';
import type { Leitura } from '@/types/trafego';
import { dinheiro } from '@/components/trafego/inventario/formato';

import {
  booleanoMedido,
  campo,
  idDaCampanha,
  lista,
  linhasDaCampanha,
  motivoDaFalha,
  respondida,
  texto,
  zeroMedido,
  type ConsultaRespondida,
  type EvidenciaDeDiagnostico,
  type LinhaDaConsulta,
} from './evidencia';
import { escadaParcial } from './escada';

// ── formatação local ────────────────────────────────────────────────────────

/** Fração 0..1 vira percentual legível. `null` continua `null`. */
export function percentual(fracao: number | null): string | null {
  if (fracao == null || !Number.isFinite(fracao)) return null;
  const v = fracao * 100;
  // Zero medido sai `0%`, sem casa decimal: `0,0%` sugere precisão onde há um
  // fato inteiro, e numa coluna de perdas isso lê-se como "quase zero".
  if (v === 0) return '0%';
  return `${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: v < 10 ? 1 : 0,
    maximumFractionDigits: v < 10 ? 1 : 0,
  }).format(v)}%`;
}

function leituraDe(iso: string | undefined, agora: Date): Leitura | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return {
    lido_em: d.toISOString(),
    idade_s: Math.round((agora.getTime() - d.getTime()) / 1000),
  };
}

/** Uma frase da conta de anúncio, em minúscula legível: `LOW_QUALITY` → `low quality`. */
function fraseDaConta(bruto: string): string {
  return bruto.toLowerCase().replace(/_/g, ' ');
}

// ── construção de evidência ─────────────────────────────────────────────────

interface Contexto {
  ev: EvidenciaDeDiagnostico;
  campaignId: string;
  moeda: string | null;
  janela: string;
  agora: Date;
}

function prova(
  ctx: Contexto,
  consulta: string,
  rotulo: string,
  campoNome: string,
  valor: string | null,
  origem: OrigemDaEvidencia = 'conta',
  comJanela = false,
): EvidenciaDeCampo {
  const reg = ctx.ev.consultas?.[consulta];
  return {
    rotulo,
    valor,
    campo: campoNome,
    janela: comJanela ? ctx.janela : null,
    leitura: leituraDe(reg?.lido_em_utc, ctx.agora),
    origem,
  };
}

function degrauNaoApurado(
  eixo: EixoDeEntrega,
  palavra: string,
  impedimento: string,
): DegrauDeEntrega {
  return {
    eixo,
    estado: 'nao_apurado',
    palavra,
    frase:
      'não deu para apurar este degrau. Enquanto isso não for lido, o que está ' +
      'acima dele nesta escada não sustenta conclusão.',
    motivo_da_conta: [],
    evidencias: [],
    impedimento,
    propostas: [],
  };
}

// ── degrau 1 · conta ────────────────────────────────────────────────────────

function degrauDaConta(ctx: Contexto): DegrauDeEntrega {
  const conta = respondida(ctx.ev, 'conta');
  const faturamento = respondida(ctx.ev, 'faturamento');
  if (!conta) {
    return degrauNaoApurado(
      'conta',
      'conta não lida',
      motivoDaFalha(ctx.ev, 'conta') ?? 'a leitura da conta não veio nesta evidência',
    );
  }

  const linha = conta.linhas[0] ?? {};
  const status = texto(linha, 'customer.status');
  const nome = texto(linha, 'customer.descriptive_name');
  const teste = booleanoMedido(linha, 'customer.test_account');

  const evidencias: EvidenciaDeCampo[] = [
    prova(ctx, 'conta', 'estado da conta', 'customer.status', status),
    prova(ctx, 'conta', 'nome da conta', 'customer.descriptive_name', nome),
  ];

  // Faturamento é degrau da conta, não da campanha: conta sem cobrança ativa
  // não veicula nem com tudo ligado, e o operador que olha só a campanha nunca
  // encontra a causa.
  let situacaoDoFaturamento: string | null = null;
  if (faturamento) {
    const aprovados = faturamento.linhas.filter(
      (l) => texto(l, 'billing_setup.status') === 'APPROVED',
    );
    situacaoDoFaturamento = aprovados.length > 0 ? 'ativo' : 'nenhum aprovado';
    evidencias.push(
      prova(
        ctx,
        'faturamento',
        'cobrança da conta',
        'billing_setup.status',
        situacaoDoFaturamento,
      ),
    );
  }

  if (teste) {
    evidencias.push(
      prova(ctx, 'conta', 'conta de teste', 'customer.test_account', 'sim'),
    );
    return {
      eixo: 'conta',
      estado: 'bloqueia',
      palavra: 'conta de teste',
      frase:
        'esta é uma conta de teste. Ela aceita campanha, valida pedido e não ' +
        'veicula nada — nenhum anúncio dela entra em leilão real.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  if (status && status !== 'ENABLED') {
    return {
      eixo: 'conta',
      estado: 'bloqueia',
      palavra: 'conta não ativa',
      frase:
        `a conta de anúncio está ${fraseDaConta(status)}. Nenhuma campanha dela ` +
        'veicula, independentemente do que a campanha diga.',
      motivo_da_conta: [status],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  if (faturamento && situacaoDoFaturamento === 'nenhum aprovado') {
    return {
      eixo: 'conta',
      estado: 'bloqueia',
      palavra: 'sem cobrança ativa',
      frase:
        'a conta não tem forma de cobrança aprovada. Campanha ligada nesta ' +
        'situação não entra em leilão e não gasta.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  if (!faturamento) {
    // Conta ativa e cobrança não lida: o degrau NÃO é `ok`. Dizer "a conta está
    // bem" sem ter lido a cobrança é afirmar sobre o que não se apurou.
    return degrauNaoApurado(
      'conta',
      'cobrança não lida',
      motivoDaFalha(ctx.ev, 'faturamento') ??
        'a situação de cobrança não veio nesta evidência',
    );
  }

  return {
    eixo: 'conta',
    estado: 'ok',
    palavra: 'conta ativa',
    frase: 'a conta está ativa e tem cobrança aprovada.',
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── degrau 2 · campanha ─────────────────────────────────────────────────────

function linhaDaCampanha(ctx: Contexto): LinhaDaConsulta | null {
  const c = respondida(ctx.ev, 'campanhas');
  if (!c) return null;
  return c.linhas.find((l) => idDaCampanha(l) === ctx.campaignId) ?? null;
}

function degrauDaCampanha(ctx: Contexto): DegrauDeEntrega {
  const c = respondida(ctx.ev, 'campanhas');
  if (!c) {
    return degrauNaoApurado(
      'campanha',
      'campanha não lida',
      motivoDaFalha(ctx.ev, 'campanhas') ?? 'a lista de campanhas não veio',
    );
  }
  const linha = linhaDaCampanha(ctx);
  if (!linha) {
    return {
      eixo: 'campanha',
      estado: 'bloqueia',
      palavra: 'não está na conta',
      frase:
        'a conta respondeu e esta campanha não estava na resposta. Não é uma ' +
        'falha de leitura: a conta foi lida e não a tem.',
      motivo_da_conta: [],
      evidencias: [],
      impedimento: null,
      propostas: [],
    };
  }

  const status = texto(linha, 'campaign.status');
  const primario = texto(linha, 'campaign.primary_status');
  const razoes = lista(linha, 'campaign.primary_status_reasons');
  const veiculacao = texto(linha, 'campaign.serving_status');

  const evidencias = [
    prova(ctx, 'campanhas', 'estado da campanha', 'campaign.status', status),
    prova(ctx, 'campanhas', 'situação de veiculação', 'campaign.primary_status', primario),
    prova(ctx, 'campanhas', 'veiculação', 'campaign.serving_status', veiculacao),
  ];
  const motivo = razoes.map(fraseDaConta);

  if (status === 'REMOVED') {
    return {
      eixo: 'campanha',
      estado: 'bloqueia',
      palavra: 'removida',
      frase: 'a conta declara esta campanha como removida. Removida não volta: relançar cria outra.',
      motivo_da_conta: motivo,
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (status === 'PAUSED') {
    return {
      eixo: 'campanha',
      estado: 'bloqueia',
      palavra: 'pausada',
      frase: 'a campanha está pausada no Google. Pausada não entra em leilão e não gasta.',
      motivo_da_conta: motivo,
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (primario === 'NOT_ELIGIBLE' || primario === 'REMOVED' || primario === 'ENDED') {
    return {
      eixo: 'campanha',
      estado: 'bloqueia',
      palavra: 'não elegível',
      frase: 'o próprio Google declara esta campanha inelegível para veicular.',
      motivo_da_conta: motivo,
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (primario === 'LIMITED' || primario === 'MISCONFIGURED' || primario === 'LEARNING') {
    return {
      eixo: 'campanha',
      estado: 'limita',
      palavra: 'entrega limitada',
      frase: 'a campanha veicula, e o Google declara que algo a está segurando.',
      motivo_da_conta: motivo,
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (!status) {
    return degrauNaoApurado(
      'campanha',
      'estado não lido',
      'a conta não informou o estado desta campanha nesta leitura',
    );
  }
  return {
    eixo: 'campanha',
    estado: 'ok',
    palavra: 'ligada',
    frase: 'a campanha está ligada e o Google não declara impedimento nela.',
    motivo_da_conta: motivo,
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── degrau 3 · orçamento ────────────────────────────────────────────────────

function degrauDoOrcamento(ctx: Contexto): DegrauDeEntrega {
  const linha = linhaDaCampanha(ctx);
  const metricas = respondida(ctx.ev, 'metricas_campanha');
  if (!linha) {
    return degrauNaoApurado(
      'orcamento',
      'verba não lida',
      motivoDaFalha(ctx.ev, 'campanhas') ?? 'a campanha não veio na leitura',
    );
  }

  const verba = campo(linha, 'campaign_budget.amount_micros');
  const verbaMicros =
    typeof verba === 'number' ? verba : typeof verba === 'string' ? Number(verba) : null;
  const evidencias = [
    prova(
      ctx,
      'campanhas',
      'verba diária',
      'campaign_budget.amount_micros',
      verbaMicros == null || Number.isNaN(verbaMicros)
        ? null
        : dinheiro(verbaMicros, ctx.moeda),
    ),
  ];

  if (!metricas) {
    evidencias.push(
      prova(ctx, 'metricas_campanha', 'perda por verba', 'metrics.search_budget_lost_impression_share', null, 'conta', true),
    );
    return {
      eixo: 'orcamento',
      estado: 'nao_apurado',
      palavra: 'perda por verba não lida',
      frase:
        'a verba está declarada e a parcela de leilões perdida por verba não pôde ' +
        'ser medida. Sem ela, não dá para dizer se a verba está segurando a entrega.',
      motivo_da_conta: [],
      evidencias,
      impedimento:
        motivoDaFalha(ctx.ev, 'metricas_campanha') ?? 'as métricas não vieram nesta leitura',
      propostas: [],
    };
  }

  const m = linhasDaCampanha(metricas, ctx.campaignId)[0];
  if (!m) {
    return {
      eixo: 'orcamento',
      estado: 'ok',
      palavra: 'sem perda por verba',
      frase:
        'a conta respondeu e não há métrica desta campanha na janela — nenhum ' +
        'leilão foi perdido por verba porque não houve leilão nenhum.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  const perdida = zeroMedido(m, 'metrics.search_budget_lost_impression_share');
  evidencias.push(
    prova(
      ctx,
      'metricas_campanha',
      'leilões perdidos por verba',
      'metrics.search_budget_lost_impression_share',
      percentual(perdida),
      'conta',
      true,
    ),
  );

  if (perdida >= 0.1) {
    return {
      eixo: 'orcamento',
      estado: 'limita',
      palavra: 'verba segura a entrega',
      frase:
        `a campanha perdeu ${percentual(perdida)} dos leilões por falta de verba. ` +
        'Existe demanda que a verba atual não alcança.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  return {
    eixo: 'orcamento',
    estado: 'ok',
    palavra: 'verba não é o gargalo',
    frase: 'a verba não está segurando a entrega nesta janela.',
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── degrau 4 · grupo ────────────────────────────────────────────────────────

function degrauDoGrupo(ctx: Contexto): DegrauDeEntrega {
  const grupos = respondida(ctx.ev, 'grupos');
  if (!grupos) {
    return degrauNaoApurado(
      'grupo',
      'grupos não lidos',
      motivoDaFalha(ctx.ev, 'grupos') ?? 'os grupos não vieram nesta leitura',
    );
  }
  const meus = linhasDaCampanha(grupos, ctx.campaignId);
  const ligados = meus.filter((g) => texto(g, 'ad_group.status') === 'ENABLED');
  const evidencias = [
    prova(ctx, 'grupos', 'grupos na campanha', 'ad_group.id', String(meus.length)),
    prova(ctx, 'grupos', 'grupos ligados', 'ad_group.status', String(ligados.length)),
  ];

  if (meus.length === 0) {
    return {
      eixo: 'grupo',
      estado: 'bloqueia',
      palavra: 'sem grupo',
      frase:
        'a conta respondeu e esta campanha não tem grupo nenhum. Campanha sem ' +
        'grupo não tem onde pendurar anúncio nem keyword.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (ligados.length === 0) {
    return {
      eixo: 'grupo',
      estado: 'bloqueia',
      palavra: 'nenhum grupo ligado',
      frase: 'todos os grupos desta campanha estão pausados ou removidos.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  const razoes = ligados.flatMap((g) => lista(g, 'ad_group.primary_status_reasons'));
  const limitados = ligados.filter((g) => {
    const p = texto(g, 'ad_group.primary_status');
    return p === 'LIMITED' || p === 'NOT_ELIGIBLE' || p === 'MISCONFIGURED';
  });
  if (limitados.length > 0) {
    return {
      eixo: 'grupo',
      estado: 'limita',
      palavra: 'grupo com ressalva',
      frase: `${limitados.length} de ${ligados.length} grupos ligados têm ressalva declarada pelo Google.`,
      motivo_da_conta: [...new Set(razoes)].map(fraseDaConta),
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  return {
    eixo: 'grupo',
    estado: 'ok',
    palavra: 'grupos ligados',
    frase: `${ligados.length} de ${meus.length} grupos estão ligados e sem ressalva.`,
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── degrau 5 · anúncio ──────────────────────────────────────────────────────

function degrauDoAnuncio(ctx: Contexto): DegrauDeEntrega {
  const anuncios = respondida(ctx.ev, 'anuncios');
  if (!anuncios) {
    return degrauNaoApurado(
      'anuncio',
      'anúncios não lidos',
      motivoDaFalha(ctx.ev, 'anuncios') ?? 'os anúncios não vieram nesta leitura',
    );
  }
  const meus = linhasDaCampanha(anuncios, ctx.campaignId);
  const ligados = meus.filter((a) => texto(a, 'ad_group_ad.status') === 'ENABLED');
  const reprovados = ligados.filter(
    (a) => texto(a, 'ad_group_ad.policy_summary.approval_status') === 'DISAPPROVED',
  );
  const emRevisao = ligados.filter((a) => {
    const r = texto(a, 'ad_group_ad.policy_summary.review_status');
    return r === 'UNDER_REVIEW' || r === 'REVIEW_IN_PROGRESS';
  });
  const forcaFraca = ligados.filter((a) => {
    const f = texto(a, 'ad_group_ad.ad_strength');
    return f === 'POOR' || f === 'PENDING';
  });

  const evidencias = [
    prova(ctx, 'anuncios', 'anúncios ligados', 'ad_group_ad.status', String(ligados.length)),
    prova(
      ctx,
      'anuncios',
      'reprovados por política',
      'ad_group_ad.policy_summary.approval_status',
      String(reprovados.length),
    ),
    prova(
      ctx,
      'anuncios',
      'em revisão do Google',
      'ad_group_ad.policy_summary.review_status',
      String(emRevisao.length),
    ),
  ];

  if (meus.length === 0 || ligados.length === 0) {
    return {
      eixo: 'anuncio',
      estado: 'bloqueia',
      palavra: 'sem anúncio ligado',
      frase:
        'não há anúncio ligado nesta campanha. Sem anúncio não há o que mostrar ' +
        'em leilão nenhum.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (reprovados.length === ligados.length) {
    return {
      eixo: 'anuncio',
      estado: 'bloqueia',
      palavra: 'todos reprovados',
      frase: 'todo anúncio ligado desta campanha foi reprovado pela política do Google.',
      motivo_da_conta: [
        ...new Set(reprovados.flatMap((a) => topicosDePolitica(a))),
      ],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (emRevisao.length === ligados.length) {
    return {
      eixo: 'anuncio',
      estado: 'limita',
      palavra: 'em revisão',
      frase:
        'todos os anúncios ligados ainda estão na fila de revisão do Google. ' +
        'Enquanto o veredito não sai, a entrega é reduzida.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (reprovados.length > 0 || forcaFraca.length === ligados.length) {
    return {
      eixo: 'anuncio',
      estado: 'limita',
      palavra: 'anúncio com ressalva',
      frase:
        reprovados.length > 0
          ? `${reprovados.length} de ${ligados.length} anúncios ligados estão reprovados.`
          : 'todos os anúncios ligados têm força fraca declarada pelo Google.',
      motivo_da_conta: [...new Set(reprovados.flatMap((a) => topicosDePolitica(a)))],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  return {
    eixo: 'anuncio',
    estado: 'ok',
    palavra: 'anúncio aprovado',
    frase: `${ligados.length} anúncios ligados, sem reprovação de política.`,
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

function topicosDePolitica(linha: LinhaDaConsulta): string[] {
  const entradas = campo(linha, 'ad_group_ad.policy_summary.policy_topic_entries');
  if (!Array.isArray(entradas)) return [];
  return entradas
    .map((e) => (typeof e === 'object' && e !== null ? (e as Record<string, unknown>).topic : null))
    .filter((t): t is string => typeof t === 'string');
}

// ── degrau 6 · keyword ──────────────────────────────────────────────────────

function degrauDaKeyword(ctx: Contexto): DegrauDeEntrega {
  const kws = respondida(ctx.ev, 'keywords');
  if (!kws) {
    return degrauNaoApurado(
      'keyword',
      'keywords não lidas',
      motivoDaFalha(ctx.ev, 'keywords') ?? 'as keywords não vieram nesta leitura',
    );
  }
  const meus = linhasDaCampanha(kws, ctx.campaignId).filter(
    (k) => !booleanoMedido(k, 'ad_group_criterion.negative'),
  );
  const ligadas = meus.filter((k) => texto(k, 'ad_group_criterion.status') === 'ENABLED');
  const raras = ligadas.filter(
    (k) => texto(k, 'ad_group_criterion.system_serving_status') === 'RARELY_SERVED',
  );
  const reprovadas = ligadas.filter(
    (k) => texto(k, 'ad_group_criterion.approval_status') === 'DISAPPROVED',
  );

  const evidencias = [
    prova(ctx, 'keywords', 'keywords ligadas', 'ad_group_criterion.status', String(ligadas.length)),
    prova(
      ctx,
      'keywords',
      'raramente veiculadas',
      'ad_group_criterion.system_serving_status',
      String(raras.length),
    ),
    prova(
      ctx,
      'keywords',
      'reprovadas',
      'ad_group_criterion.approval_status',
      String(reprovadas.length),
    ),
  ];

  if (ligadas.length === 0) {
    return {
      eixo: 'keyword',
      estado: 'bloqueia',
      palavra: 'sem keyword ligada',
      frase: 'não há keyword ligada nesta campanha. Sem keyword, a campanha não disputa consulta nenhuma.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (raras.length === ligadas.length) {
    return {
      eixo: 'keyword',
      estado: 'bloqueia',
      palavra: 'todas raramente veiculadas',
      frase:
        'o Google marca todas as keywords ligadas como raramente veiculadas — ' +
        'volume baixo demais para entrar em leilão.',
      motivo_da_conta: ['rarely served'],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (raras.length > 0 || reprovadas.length > 0) {
    return {
      eixo: 'keyword',
      estado: 'limita',
      palavra: 'parte das keywords não serve',
      frase: `${raras.length + reprovadas.length} de ${ligadas.length} keywords ligadas não estão disputando leilão.`,
      motivo_da_conta: [...new Set(ligadas.flatMap((k) => lista(k, 'ad_group_criterion.disapproval_reasons')))].map(
        fraseDaConta,
      ),
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  return {
    eixo: 'keyword',
    estado: 'ok',
    palavra: 'keywords elegíveis',
    frase: `${ligadas.length} keywords ligadas e elegíveis.`,
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── degrau 7 · segmentação ──────────────────────────────────────────────────

function degrauDaSegmentacao(ctx: Contexto): DegrauDeEntrega {
  const criterios = respondida(ctx.ev, 'criterios_campanha');
  const kws = respondida(ctx.ev, 'keywords');
  if (!criterios) {
    return degrauNaoApurado(
      'segmentacao',
      'segmentação não lida',
      motivoDaFalha(ctx.ev, 'criterios_campanha') ?? 'a segmentação não veio nesta leitura',
    );
  }
  const meus = linhasDaCampanha(criterios, ctx.campaignId);
  const geo = meus.filter(
    (c) => texto(c, 'campaign_criterion.type') === 'LOCATION' && !booleanoMedido(c, 'campaign_criterion.negative'),
  );
  const idioma = meus.filter((c) => texto(c, 'campaign_criterion.type') === 'LANGUAGE');
  const negativas = meus.filter((c) => booleanoMedido(c, 'campaign_criterion.negative'));

  const evidencias = [
    prova(ctx, 'criterios_campanha', 'localizações alvo', 'campaign_criterion.location', String(geo.length)),
    prova(ctx, 'criterios_campanha', 'idiomas alvo', 'campaign_criterion.language', String(idioma.length)),
    prova(ctx, 'criterios_campanha', 'negativas na campanha', 'campaign_criterion.negative', String(negativas.length)),
  ];

  if (geo.length === 0) {
    return {
      eixo: 'segmentacao',
      estado: 'bloqueia',
      palavra: 'sem localização alvo',
      frase:
        'a campanha não tem nenhuma localização alvo. Sem geografia, o Google não ' +
        'tem onde mostrar o anúncio.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  // A negativa que anula uma keyword ativa é a única checagem de segmentação
  // que PROVA um bloqueio a partir de dois fatos observados — o resto seria
  // opinião sobre o recorte, e opinião não é diagnóstico.
  const textosNegativos = new Set(
    negativas
      .map((c) => texto(c, 'campaign_criterion.keyword.text')?.toLowerCase())
      .filter((t): t is string => Boolean(t)),
  );
  const anuladas = kws
    ? linhasDaCampanha(kws, ctx.campaignId)
        .filter(
          (k) =>
            !booleanoMedido(k, 'ad_group_criterion.negative') &&
            texto(k, 'ad_group_criterion.status') === 'ENABLED',
        )
        .map((k) => texto(k, 'ad_group_criterion.keyword.text'))
        .filter((t): t is string => Boolean(t) && textosNegativos.has(t.toLowerCase()))
    : [];

  if (anuladas.length > 0) {
    evidencias.push(
      prova(
        ctx,
        'criterios_campanha',
        'keywords anuladas por negativa',
        'campaign_criterion.keyword.text',
        anuladas.join(', '),
        'derivado',
      ),
    );
    return {
      eixo: 'segmentacao',
      estado: 'limita',
      palavra: 'negativa anula keyword ativa',
      frase: `${anuladas.length} keyword(s) ligada(s) desta campanha estão anuladas por uma negativa da própria campanha.`,
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }

  return {
    eixo: 'segmentacao',
    estado: 'ok',
    palavra: 'segmentação declarada',
    frase: `${geo.length} localização(ões) e ${idioma.length} idioma(s) alvo, sem negativa anulando keyword ligada.`,
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── degrau 8 · conversão ────────────────────────────────────────────────────

function degrauDaConversao(ctx: Contexto): DegrauDeEntrega {
  const acoes = respondida(ctx.ev, 'conversoes');
  const linha = linhaDaCampanha(ctx);
  const estrategia = linha ? texto(linha, 'campaign.bidding_strategy_type') : null;
  if (!acoes) {
    return degrauNaoApurado(
      'conversao',
      'conversões não lidas',
      motivoDaFalha(ctx.ev, 'conversoes') ?? 'as ações de conversão não vieram',
    );
  }
  const ativas = acoes.linhas.filter((a) => texto(a, 'conversion_action.status') === 'ENABLED');
  const principais = ativas.filter((a) => booleanoMedido(a, 'conversion_action.primary_for_goal'));
  const evidencias = [
    prova(ctx, 'conversoes', 'ações de conversão ativas', 'conversion_action.status', String(ativas.length)),
    prova(ctx, 'conversoes', 'ações principais', 'conversion_action.primary_for_goal', String(principais.length)),
    prova(ctx, 'campanhas', 'estratégia de lance', 'campaign.bidding_strategy_type', estrategia),
  ];

  const automatica =
    estrategia != null &&
    ['MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE', 'TARGET_CPA', 'TARGET_ROAS'].includes(
      estrategia,
    );

  if (ativas.length === 0) {
    return {
      eixo: 'conversao',
      estado: automatica ? 'bloqueia' : 'limita',
      palavra: 'sem conversão registrada',
      frase: automatica
        ? 'a campanha usa lance automático e a conta não tem ação de conversão ativa. ' +
          'O modelo não tem do que aprender.'
        : 'a conta não tem ação de conversão ativa. A campanha veicula, e não há como ' +
          'saber o que ela produziu.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  return {
    eixo: 'conversao',
    estado: 'ok',
    palavra: 'conversão registrada',
    frase: `${ativas.length} ação(ões) de conversão ativa(s) na conta.`,
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── degrau 9 · leilão ───────────────────────────────────────────────────────

function degrauDoLeilao(ctx: Contexto): DegrauDeEntrega {
  const metricas = respondida(ctx.ev, 'metricas_campanha');
  const termos = respondida(ctx.ev, 'termos_de_busca');
  if (!metricas) {
    return degrauNaoApurado(
      'leilao',
      'entrega não medida',
      motivoDaFalha(ctx.ev, 'metricas_campanha') ?? 'as métricas não vieram nesta leitura',
    );
  }
  const m = linhasDaCampanha(metricas, ctx.campaignId)[0];

  // ⚠️ Linha ausente NÃO é zero medido, e este degrau já afirmou o contrário.
  //
  // `zeroMedido` vale para campo ausente numa linha QUE VEIO — é a exceção
  // documentada em `evidencia.ts`, e ela existe porque o runner serializa com
  // `always_print_fields_with_no_presence=False`. Um ternário `m ? … : 0`
  // estendia a exceção para a linha que NÃO veio, e o efeito era a pior classe
  // de mentira que esta tela pode contar: o degrau saía `bloqueia`, com a
  // palavra "não houve leilão" e a frase "isto é medida, não ausência de
  // medida: a conta respondeu e o número é zero" — apoiada em nada. Junto iam
  // cinco evidências fabricadas, carimbadas com `origem: 'conta'`.
  //
  // O degrau do orçamento, no mesmo arquivo, já tratava este caso. O autor viu
  // o caso num degrau e não no outro.
  if (!m) {
    return degrauNaoApurado(
      'leilao',
      'sem linha desta campanha',
      'a conta respondeu à consulta de métricas, e nenhuma linha desta campanha ' +
        'veio na janela. Não dá para distinguir "zero impressões" de "a campanha ' +
        'não entrou no recorte", e as duas levam a decisões opostas.',
    );
  }

  const impressoes = zeroMedido(m, 'metrics.impressions');
  const cliques = zeroMedido(m, 'metrics.clicks');
  const custo = zeroMedido(m, 'metrics.cost_micros');
  const perdaPorRank = zeroMedido(m, 'metrics.search_rank_lost_impression_share');
  const nTermos = termos ? linhasDaCampanha(termos, ctx.campaignId).length : null;

  const evidencias = [
    prova(ctx, 'metricas_campanha', 'impressões', 'metrics.impressions', String(impressoes), 'conta', true),
    prova(ctx, 'metricas_campanha', 'cliques', 'metrics.clicks', String(cliques), 'conta', true),
    prova(ctx, 'metricas_campanha', 'custo', 'metrics.cost_micros', dinheiro(custo, ctx.moeda), 'conta', true),
    prova(
      ctx,
      'metricas_campanha',
      'leilões perdidos por posição',
      'metrics.search_rank_lost_impression_share',
      percentual(perdaPorRank),
      'conta',
      true,
    ),
    prova(
      ctx,
      'termos_de_busca',
      'termos que trouxeram tráfego',
      'search_term_view.search_term',
      nTermos == null ? null : String(nTermos),
      'conta',
      true,
    ),
  ];

  if (impressoes === 0) {
    return {
      eixo: 'leilao',
      estado: 'bloqueia',
      palavra: 'não houve leilão',
      frase:
        'a campanha não teve impressão nenhuma na janela. Isto é medida, não ' +
        'ausência de medida: a conta respondeu e o número é zero.',
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  if (perdaPorRank >= 0.3) {
    return {
      eixo: 'leilao',
      estado: 'limita',
      palavra: 'perde por posição',
      frase: `a campanha perdeu ${percentual(perdaPorRank)} dos leilões por posição — lance ou qualidade abaixo do necessário.`,
      motivo_da_conta: [],
      evidencias,
      impedimento: null,
      propostas: [],
    };
  }
  return {
    eixo: 'leilao',
    estado: 'ok',
    palavra: 'entregando',
    frase: `${impressoes} impressões e ${cliques} cliques na janela.`,
    motivo_da_conta: [],
    evidencias,
    impedimento: null,
    propostas: [],
  };
}

// ── a escada inteira ────────────────────────────────────────────────────────

export interface OpcoesDaDerivacao {
  /** Injetável para o teste ser determinístico. */
  agora?: Date;
  /** Nome legível da campanha, quando a evidência não o traz. */
  nome?: string;
}

/**
 * Deriva o diagnóstico de UMA campanha a partir da evidência bruta.
 *
 * A escada sai sempre COMPLETA: nenhum eixo é omitido por falta de dado, porque
 * eixo ausente na lista some da tela, e "não apareceu" lê-se como "não é
 * problema". Um eixo que não pôde ser lido aparece como `nao_apurado`.
 */
export function derivarDiagnostico(
  ev: EvidenciaDeDiagnostico,
  campaignId: string,
  opcoes: OpcoesDaDerivacao = {},
): DiagnosticoDeEntrega {
  const agora = opcoes.agora ?? new Date();
  const conta = respondida(ev, 'conta');
  const moeda = conta ? texto(conta.linhas[0] ?? {}, 'customer.currency_code') : null;
  const janela = janelaLegivel(ev._meta?.janela_das_metricas);

  const ctx: Contexto = { ev, campaignId, moeda, janela, agora };
  const linha = linhaDaCampanha(ctx);

  const leitura = leituraDe(ev._meta?.lido_em_utc, agora);
  const frescor = leitura == null
    ? 'nao_apurado'
    : leitura.idade_s > 30 * 60
      ? 'velho'
      : 'recente';
  const degrausObservados: DegrauDeEntrega[] = [
    degrauDaConta(ctx),
    degrauDaCampanha(ctx),
    degrauDoOrcamento(ctx),
    degrauDoGrupo(ctx),
    degrauDoAnuncio(ctx),
    degrauDaKeyword(ctx),
    degrauDaSegmentacao(ctx),
    degrauDaConversao(ctx),
    degrauDoLeilao(ctx),
  ];
  // Esta ponte de fixture não lê o ledger v12, por isso não inventa um estado
  // de coleta. Evidência velha também fecha os degraus: o backend é a fonte
  // canônica do limiar e usa os mesmos 30 minutos do inventário.
  const degraus = frescor === 'velho'
    ? degrausObservados.map(({ eixo }) =>
        degrauNaoApurado(
          eixo,
          'leitura velha',
          'a evidência da fixture ultrapassou a janela de confiança',
        ))
    : degrausObservados;

  return {
    versao: VERSAO_DIAGNOSTICO,
    volc_campaign_id: campaignId,
    customer_id: ev._meta?.customer_id ?? '',
    nome_campanha: (linha ? texto(linha, 'campaign.name') : null) ?? opcoes.nome ?? campaignId,
    moeda,
    estado_coleta: null,
    frescor,
    janela,
    leitura,
    degraus,
    parcial: escadaParcial(degraus),
  };
}

/** `LAST_30_DAYS` → `últimos 30 dias`. Vocabulário de máquina não vai para a tela. */
export function janelaLegivel(bruto: string | undefined): string {
  if (!bruto) return 'janela não declarada';
  const m = /^LAST_(\d+)_DAYS$/.exec(bruto);
  if (m) return `últimos ${m[1]} dias`;
  const conhecidas: Record<string, string> = {
    TODAY: 'hoje',
    YESTERDAY: 'ontem',
    THIS_MONTH: 'este mês',
    LAST_MONTH: 'mês passado',
    ALL_TIME: 'todo o período',
  };
  return conhecidas[bruto] ?? bruto.toLowerCase().replace(/_/g, ' ');
}

/** As campanhas que a evidência contém, para a tela escolher qual diagnosticar. */
export function campanhasNaEvidencia(
  ev: EvidenciaDeDiagnostico,
): { id: string; nome: string }[] {
  const c: ConsultaRespondida | null = respondida(ev, 'campanhas');
  if (!c) return [];
  const vistas = new Map<string, string>();
  for (const l of c.linhas) {
    const id = idDaCampanha(l);
    if (!id) continue;
    if (!vistas.has(id)) vistas.set(id, texto(l, 'campaign.name') ?? id);
  }
  return [...vistas].map(([id, nome]) => ({ id, nome }));
}
