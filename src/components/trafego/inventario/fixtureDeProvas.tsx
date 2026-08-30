/**
 * O inventário de prova — derivado do FORMATO real, não de nomes escritos à mão
 * dentro de um `if`.
 *
 * As duas campanhas que as provas exigem (Maquininha de Cartão e FGTS
 * Saque-Aniversário) entram aqui como DADO, exatamente como chegariam do
 * servidor. Nenhum componente sabe o nome delas; se amanhã a conta tiver outras
 * duas, a tela continua correta e este arquivo é o único que muda.
 *
 * Os valores vêm do que já foi medido na conta (contas, ids, lance de R$ 0,12,
 * verba de R$ 10, 1 e 4 impressões, R$ 0,00 gastos, as três linhas de fevereiro
 * sem conta identificada). O formato vem do contrato em `src/types/trafego.ts`
 * e da projeção em `backend/app/trafego/inventario.py`.
 *
 * ⚠️ Importado só por testes. Nenhum caminho da aplicação depende dele.
 */
import type {
  AlertaDeEntrega,
  CampanhaNoInventario,
  ContaNoInventario,
  Inventario,
  QuadroDeAlertas,
} from '@/types/trafego';

/** O grupo sintético do servidor para linhas sem conta utilizável. */
export const SEM_CONTA = 'conta-nao-identificada';

const AGORA = '2026-08-24T17:06:00Z';

const leitura = (idadeSegundos: number) => ({
  lido_em: new Date(Date.parse(AGORA) - idadeSegundos * 1000).toISOString(),
  idade_s: idadeSegundos,
});

export const maquininha: CampanhaNoInventario = {
  volc_campaign_id: 'vc_24155134757',
  campaign_lineage_id: 'lg_maquininha',
  externa: { customer_id: '8017851692', campaign_id: '24155134757' },
  nome: 'BR - Maquininha de Cartão',
  estado_externo: 'ENABLED',
  veiculacao: 'SERVING',
  canal: 'SEARCH',
  estrategia: 'MANUAL_CPC',
  lance_micros: 120_000,
  verba_diaria_micros: 10_000_000,
  teto_de_cliques: 83,
  entrega: {
    impressoes: 1,
    cliques: 0,
    // ZERO MEDIDO, não ausência: a campanha entrou no leilão e não gastou.
    custo_micros: 0,
    moeda: 'BRL',
    leitura: leitura(372),
  },
  vinculo: {
    opportunity_id: 63,
    project_id: 4,
    confirmado_por: 'tarcisio@agenciavolc.com.br',
    confirmado_em: '2026-08-20T12:10:00Z',
  },
  procedencia: 'volc_os',
  presenca: 'presente' as CampanhaNoInventario['presenca'],
  cockpit_href: '/dashboard/campaign/41',
};

export const fgts: CampanhaNoInventario = {
  volc_campaign_id: 'vc_24156373085',
  campaign_lineage_id: 'lg_fgts',
  externa: { customer_id: '8017851692', campaign_id: '24156373085' },
  // O prefixo duplicado é fato da conta, não erro de digitação daqui.
  nome: 'BR BR - FGTS Saque-Aniversário',
  estado_externo: 'ENABLED',
  veiculacao: 'SERVING',
  canal: 'SEARCH',
  estrategia: 'MANUAL_CPC',
  lance_micros: 120_000,
  verba_diaria_micros: 10_000_000,
  teto_de_cliques: 83,
  entrega: {
    impressoes: 4,
    cliques: 0,
    custo_micros: 0,
    moeda: 'BRL',
    leitura: leitura(372),
  },
  vinculo: null,
  procedencia: 'desconhecida',
  presenca: 'presente' as CampanhaNoInventario['presenca'],
  cockpit_href: null,
};

/** Segunda instância da mesma intenção — pausada, e assim permanece. */
/**
 * A campanha que NÃO pede nada — e é preciso dizer o que isso exige.
 *
 * ⚠️ `maquininha` e `fgts` NÃO servem para isto, e essa confusão custou uma
 * rodada inteira. As duas modelam as campanhas REAIS da casa, que estão ligadas
 * e sem um clique: sob a regra do domínio (`sintoma_de_entrega`), elas pedem
 * atenção — são justamente as 2 condições de 84 que a fila existe para mostrar.
 * Usá-las como "saudável" fazia o teste afirmar o contrário do que o sistema faz.
 *
 * Saudável exige as quatro coisas juntas: ENABLED, leitura fresca, impressões
 * MEDIDAS e ao menos um clique. Faltando qualquer uma, há sintoma.
 */
export const campanhaSaudavel: CampanhaNoInventario = {
  volc_campaign_id: 'gads-8017851692-24160000001',
  campaign_lineage_id: 'linhagem-saudavel',
  externa: { customer_id: '8017851692', campaign_id: '24160000001' },
  nome: 'BR - Consignado INSS',
  estado_externo: 'ENABLED',
  veiculacao: 'SERVING',
  canal: 'SEARCH',
  estrategia: 'MANUAL_CPC',
  lance_micros: 150_000,
  verba_diaria_micros: 12_000_000,
  teto_de_cliques: 80,
  entrega: {
    impressoes: 412,
    // O clique é o que a separa da Maquininha: entregou E foi clicada.
    cliques: 9,
    custo_micros: 1_340_000,
    moeda: 'BRL',
    leitura: leitura(300),
  },
  vinculo: {
    opportunity_id: 71,
    project_id: 4,
    confirmado_por: 'tarcisio@agenciavolc.com.br',
    confirmado_em: '2026-08-20T14:00:00Z',
  },
  procedencia: 'volc_os',
  presenca: 'presente',
  cockpit_href: '/dashboard/campaign/71',
};

export const fgtsDeTeste: CampanhaNoInventario = {
  ...fgts,
  volc_campaign_id: 'vc_24161105437',
  externa: { customer_id: '8017851692', campaign_id: '24161105437' },
  nome: 'BR BR - FGTS Saque-Aniversário (teste de Ad Strength)',
  estado_externo: 'PAUSED',
  veiculacao: 'PAUSED',
  teto_de_cliques: null,
  // Nunca foi medida: ausência de medida é `null` em todos os campos, e a
  // leitura ausente é o que impede a tela de exibir isso como "0".
  entrega: { impressoes: null, cliques: null, custo_micros: null, moeda: 'BRL', leitura: null },
  procedencia: 'volc_os',
  cockpit_href: null,
};

/** Conta que não respondeu: o último dado bom continua na tela, com a idade. */
export const campanhaDeContaQueFalhou: CampanhaNoInventario = {
  volc_campaign_id: 'vc_98110022334',
  campaign_lineage_id: null,
  externa: { customer_id: '3849678045', campaign_id: '98110022334' },
  nome: 'BR - Consignado INSS',
  estado_externo: 'ENABLED',
  veiculacao: null,
  canal: 'SEARCH',
  estrategia: 'MAXIMIZE_CONVERSIONS',
  lance_micros: null,
  verba_diaria_micros: 20_000_000,
  teto_de_cliques: null,
  entrega: {
    impressoes: 812,
    cliques: 19,
    custo_micros: 47_310_000,
    moeda: 'BRL',
    leitura: leitura(26_400),
  },
  vinculo: null,
  procedencia: 'descoberta',
  presenca: 'sincronizacao_falhou',
  cockpit_href: null,
};

/** As três linhas de fevereiro: existem, sem conta em que procurá-las. */
export const legadoDeFevereiro: CampanhaNoInventario[] = [
  '9001', '9002', '9003',
].map((id, i) => ({
  volc_campaign_id: `vc_legado_${id}`,
  campaign_lineage_id: null,
  externa: { customer_id: SEM_CONTA, campaign_id: id },
  nome: `portalmundomais — campanha ${i + 1}`,
  estado_externo: 'PAUSED',
  veiculacao: null,
  canal: 'SEARCH',
  estrategia: null,
  lance_micros: null,
  verba_diaria_micros: null,
  teto_de_cliques: null,
  entrega: { impressoes: null, cliques: null, custo_micros: null, moeda: null, leitura: null },
  vinculo: null,
  procedencia: 'legado',
  presenca: 'legado_nao_reconciliado',
  cockpit_href: `/dashboard/campaign/${10 + i}`,
} satisfies CampanhaNoInventario));

/** A conta respondeu e declara esta campanha como removida. Fato, não sumiço. */
export const campanhaRemovida: CampanhaNoInventario = {
  ...fgts,
  volc_campaign_id: 'vc_24099887766',
  campaign_lineage_id: 'lg_maquininha',
  externa: { customer_id: '8017851692', campaign_id: '24099887766' },
  nome: 'BR - Maquininha de Cartão (primeira versão)',
  estado_externo: 'REMOVED',
  veiculacao: 'REMOVED',
  teto_de_cliques: null,
  entrega: {
    impressoes: 96,
    cliques: 3,
    custo_micros: 1_140_000,
    moeda: 'BRL',
    leitura: leitura(372),
  },
  procedencia: 'volc_os',
  presenca: 'removida',
  cockpit_href: null,
};

/**
 * A conta foi lida com sucesso e esta campanha NÃO estava na resposta.
 *
 * Diferente de `sincronizacao_falhou` por inteiro: aqui a leitura foi boa. O
 * que não se sabe é o que aconteceu com a campanha — e a tela não tenta saber.
 */
export const campanhaNaoEncontrada: CampanhaNoInventario = {
  ...fgts,
  volc_campaign_id: 'vc_24070001122',
  campaign_lineage_id: null,
  externa: { customer_id: '8017851692', campaign_id: '24070001122' },
  nome: 'BR - Empréstimo Consignado (não veio na leitura)',
  estado_externo: null,
  veiculacao: null,
  lance_micros: null,
  verba_diaria_micros: null,
  teto_de_cliques: null,
  entrega: { impressoes: null, cliques: null, custo_micros: null, moeda: null, leitura: null },
  procedencia: 'volc_os',
  presenca: 'nao_encontrada',
  cockpit_href: null,
};

/** Linha nossa, sem conta utilizável: não sabemos onde procurá-la. */
export const campanhaSemContaIdentificada: CampanhaNoInventario = {
  ...campanhaNaoEncontrada,
  volc_campaign_id: 'vc_sem_conta_7781',
  externa: { customer_id: SEM_CONTA, campaign_id: '7781' },
  nome: 'BR - Cartão de Crédito (sem conta vinculada)',
  procedencia: 'desconhecida',
  presenca: 'conta_nao_identificada',
  cockpit_href: null,
};

/**
 * ⚠️ A CAMPANHA DO FUTURO — o servidor mandou palavras que este pacote não tem.
 *
 * Presença, procedência, canal, estratégia e estado externo, todos com valores
 * fora das uniões declaradas em `src/types/trafego.ts`. Não é dado inválido: é
 * dado de uma versão do servidor mais nova que este pacote, que é exatamente o
 * que acontece entre um deploy e o outro.
 *
 * Os casts existem porque o TypeScript está certo — estes valores não estão nas
 * uniões. A prova é justamente sobre o que acontece quando a garantia de
 * compilação não alcança o dado de execução.
 */
export const campanhaDeEstadoDesconhecido: CampanhaNoInventario = {
  ...fgts,
  volc_campaign_id: 'vc_24999000111',
  campaign_lineage_id: null,
  externa: { customer_id: '8017851692', campaign_id: '24999000111' },
  nome: 'BR - Portabilidade (estado novo do servidor)',
  estado_externo: 'PENDING_REVIEW',
  veiculacao: 'LIMITED_BY_POLICY',
  canal: 'HOTEL' as CampanhaNoInventario['canal'],
  estrategia: 'TARGET_ROAS' as CampanhaNoInventario['estrategia'],
  procedencia: 'importada_do_parceiro' as CampanhaNoInventario['procedencia'],
  presenca: 'em_revisao_de_politica' as CampanhaNoInventario['presenca'],
  cockpit_href: null,
};

export const creditoUp: ContaNoInventario = {
  customer_id: '8017851692',
  nome: 'Crédito Up',
  frescor: 'recente',
  leitura: leitura(372),
  ultima_leitura_boa: leitura(372),
  motivo: null,
  quantidade: 3,
  campanhas: [maquininha, fgts, fgtsDeTeste],
};

/** Conta cujas campanhas não pedem nada. Usada por `inventarioSaudavel`. */
export const contaSaudavel: ContaNoInventario = {
  customer_id: '5470965390',
  nome: 'Conta Tranquila',
  frescor: 'recente',
  leitura: leitura(300),
  ultima_leitura_boa: leitura(300),
  motivo: null,
  quantidade: 1,
  campanhas: [campanhaSaudavel],
};

export const pmundo: ContaNoInventario = {
  customer_id: '3849678045',
  nome: 'PMUNDO+',
  frescor: 'falhou',
  leitura: leitura(95),
  ultima_leitura_boa: leitura(26_400),
  motivo: 'a conta não respondeu à última tentativa de leitura',
  quantidade: 1,
  campanhas: [campanhaDeContaQueFalhou],
};

/** ⚠️ Conta LIDA com zero campanhas. Não é o mesmo que conta nunca lida. */
export const portalMundoMais: ContaNoInventario = {
  customer_id: '5478096539',
  nome: 'Portal Mundo Mais',
  frescor: 'vazio_confirmado',
  leitura: leitura(372),
  ultima_leitura_boa: leitura(372),
  motivo: null,
  quantidade: 0,
  campanhas: [],
};

/** ⚠️ Grupo NUNCA lido — não sabemos em que conta procurar estas linhas. */
export const semConta: ContaNoInventario = {
  customer_id: SEM_CONTA,
  nome: null,
  frescor: 'nunca_lido',
  leitura: null,
  ultima_leitura_boa: null,
  motivo: null,
  quantidade: 3,
  campanhas: legadoDeFevereiro,
};

export function inventarioDeProva(ajuste: Partial<Inventario> = {}): Inventario {
  return {
    versao: 2,
    frescor: 'falhou',
    leitura: leitura(372),
    parcial: true,
    faltou: [{
      customer_id: '3849678045',
      escopo: 'conta',
      motivo: 'a última varredura desta conta falhou; o que está abaixo é a última leitura boa',
    }],
    contas: [creditoUp, pmundo, portalMundoMais, semConta],
    proximo_cursor: null,
    totais: { contas: 4, operacionais: 7, historicas: 0, geral: 7, atencao: 2 },
    ...ajuste,
  };
}

/**
 * Tudo lido agora, nada faltando, e NADA pedindo atenção.
 *
 * ⚠️ Não usa `creditoUp`: aquela conta carrega `maquininha` e `fgts`, que são as
 * duas campanhas reais ligadas e sem clique — elas pedem atenção por desenho.
 * Um inventário "saudável" montado com elas afirmava silêncio sobre dados que
 * gritam, e foi o que fez sete provas passarem enquanto a regra estava
 * incompleta.
 */
export function inventarioSaudavel(): Inventario {
  return inventarioDeProva({
    frescor: 'recente',
    parcial: false,
    faltou: [],
    contas: [contaSaudavel, portalMundoMais],
    totais: { contas: 2, operacionais: 1, historicas: 0, geral: 1, atencao: 0 },
  });
}

/**
 * Um inventário NORMAL para renderizar: leitura fresca, nada faltando, com a
 * Crédito Up e suas campanhas reais.
 *
 * ⚠️ Não confundir com `inventarioSaudavel()`. "Renderável" quer dizer que a
 * tela tem conteúdo e nenhuma degradação; "saudável" quer dizer que NADA pede
 * atenção. As duas campanhas da Crédito Up pedem — e é isso que as provas de
 * coluna, expansão e responsividade querem ter na tela para medir.
 *
 * O nome único para as duas ideias foi o que fez dezesseis provas de layout
 * mudarem de resultado quando a regra de atenção foi corrigida.
 */
export function inventarioRenderavel(): Inventario {
  return inventarioDeProva({
    frescor: 'recente',
    parcial: false,
    faltou: [],
    contas: [creditoUp, portalMundoMais],
    totais: { contas: 2, operacionais: 3, historicas: 0, geral: 3, atencao: 2 },
  });
}

/**
 * As duas campanhas REAIS da casa, com os valores medidos em 25/08/2026.
 *
 * Maquininha: 1 impressão, 0 clique. FGTS: 5 impressões, 0 clique. As duas
 * ENABLED, leitura fresca. É exatamente o que a API responde com
 * `?atencao=true`, e o que a aba e o sino têm de mostrar: DUAS condições.
 */
export function inventarioComCondicoesReais(): Inventario {
  return inventarioDeProva({
    frescor: 'recente',
    parcial: false,
    faltou: [],
    contas: [{
      ...creditoUp,
      quantidade: 2,
      campanhas: [maquininha, fgts],
    }],
    totais: { contas: 1, operacionais: 2, historicas: 0, geral: 2, atencao: 2 },
  });
}

/** Entrega não medida: a leitura da conta veio, a da entrega não. */
export function inventarioSemEntregaMedida(): Inventario {
  return inventarioDeProva({
    frescor: 'recente',
    parcial: false,
    faltou: [],
    contas: [{
      ...creditoUp,
      quantidade: 1,
      campanhas: [{
        ...maquininha,
        entrega: { impressoes: null, cliques: null, custo_micros: null,
                   moeda: 'BRL', leitura: null },
      }],
    }],
    totais: { contas: 1, operacionais: 1, historicas: 0, geral: 1, atencao: 1 },
  });
}

/** Uma conta cuja leitura falhou — indisponibilidade, não alerta de campanha. */
export function inventarioComFalha(): Inventario {
  return inventarioDeProva({
    frescor: 'parcial',
    parcial: true,
    contas: [pmundo],
    totais: { contas: 1, operacionais: 1, historicas: 0, geral: 1, atencao: 1 },
  });
}

/**
 * Tudo lido, e lido faz tempo. O número continua na tela; a idade também.
 *
 * ⚠️ `velho` não é `falhou`: nada deu errado, só passou tempo. A tela avisa
 * porque quem decide gasto precisa saber que está olhando para ontem, não
 * porque houve problema.
 */
export function inventarioVelho(): Inventario {
  const conta: ContaNoInventario = {
    ...creditoUp,
    frescor: 'velho',
    leitura: leitura(31_000),
    ultima_leitura_boa: leitura(31_000),
    campanhas: [{ ...maquininha, entrega: { ...maquininha.entrega, leitura: leitura(31_000) } }],
    quantidade: 1,
  };
  return inventarioDeProva({
    frescor: 'velho',
    leitura: leitura(31_000),
    parcial: false,
    faltou: [],
    contas: [conta],
    totais: { contas: 1, operacionais: 1, historicas: 0, geral: 1, atencao: 0 },
  });
}

/**
 * Uma conta com as três presenças que descrevem ausência ou dúvida, ao lado de
 * uma campanha viva. Serve para provar que os quatro convivem na mesma leitura
 * sem que a linguagem de uma contamine a da outra.
 */
export function inventarioDeAusencias(): Inventario {
  const conta: ContaNoInventario = {
    ...creditoUp,
    campanhas: [maquininha, campanhaRemovida, campanhaNaoEncontrada],
    quantidade: 3,
  };
  const orfas: ContaNoInventario = {
    ...semConta,
    frescor: 'vazio_confirmado',
    leitura: leitura(372),
    ultima_leitura_boa: leitura(372),
    campanhas: [campanhaSemContaIdentificada],
    quantidade: 1,
  };
  return inventarioDeProva({
    frescor: 'recente',
    parcial: false,
    faltou: [],
    contas: [conta, orfas],
    totais: { contas: 2, operacionais: 4, historicas: 0, geral: 4, atencao: 2 },
  });
}

/**
 * O inventário que veio de um servidor mais novo que este pacote.
 *
 * A campanha desconhecida está ao lado de duas conhecidas de propósito: a
 * prova não é só que a linha estranha aparece nomeada — é que as outras
 * continuam lá.
 */
export function inventarioDeEstadoDesconhecido(): Inventario {
  const conta: ContaNoInventario = {
    ...creditoUp,
    frescor: 'sincronizando_em_lote' as ContaNoInventario['frescor'],
    campanhas: [maquininha, fgts, campanhaDeEstadoDesconhecido],
    quantidade: 3,
  };
  return inventarioDeProva({
    frescor: 'sincronizando_em_lote' as Inventario['frescor'],
    parcial: false,
    faltou: [],
    contas: [conta],
    totais: { contas: 1, operacionais: 3, historicas: 0, geral: 3, atencao: 1 },
  });
}

// ── a fila de atenção ───────────────────────────────────────────────────────
// Mesma condição que o sino mostra, e a mesma consulta: a fila e o sino não
// podem divergir, porque divergem exatamente quando importa.

export const alertaDaMaquininha: AlertaDeEntrega = {
  customer_id: '8017851692',
  customer_name: 'Crédito Up',
  campaign_id: '24155134757',
  campaign_name: 'BR - Maquininha de Cartão',
  status: 'ENABLED',
  veiculacao: 'SERVING',
  horas_ligada: 118.2,
  impressoes: 1,
  cliques: 0,
  custo: 0,
  lance: 0.12,
  orcamento: 10,
  teto_de_cliques: 83,
  razoes: [],
  aprovacao_do_anuncio: 'APPROVED',
  sintoma: 'sem_impressao',
  revisar: ['o que o Google está dizendo', 'o lance do grupo', 'o orçamento diário'],
  alteracoes: [],
};

export const alertaDoFgts: AlertaDeEntrega = {
  ...alertaDaMaquininha,
  campaign_id: '24156373085',
  campaign_name: 'BR BR - FGTS Saque-Aniversário',
  horas_ligada: 109.4,
  impressoes: 4,
};

/** Condição que a varredura passou a emitir e esta tela ainda não nomeia. */
export const alertaDeSintomaDesconhecido: AlertaDeEntrega = {
  ...alertaDaMaquininha,
  campaign_id: '24999000111',
  campaign_name: 'BR - Portabilidade (estado novo do servidor)',
  sintoma: 'orcamento_esgotado' as AlertaDeEntrega['sintoma'],
};

export function quadroDeAlertasDeProva(ajuste: Partial<QuadroDeAlertas> = {}): QuadroDeAlertas {
  return {
    alertas: [alertaDaMaquininha, alertaDoFgts],
    verificadas: 2,
    contas: [
      { customer_id: '8017851692', nome: 'Crédito Up', ligadas: 2 },
      { customer_id: '3849678045', nome: 'PMUNDO+', erro: 'a conta não respondeu' },
    ],
    horas_ate_alertar: 24,
    ...ajuste,
  };
}
