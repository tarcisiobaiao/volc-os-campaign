/**
 * A PROJEÇÃO DE ATENÇÃO — uma função pura que responde "o que pede algo de mim
 * hoje?", e a única resposta que a aba Atenção e o sino conhecem.
 *
 * ## Por que isto é uma função, e não código dentro de dois componentes
 *
 * O sino é a projeção da aba. Enquanto cada um derivava a própria lista, os
 * dois podiam discordar sobre o mesmo fato — e discordariam exatamente no dia
 * em que um deles ganhasse uma condição nova. Aqui a derivação mora num lugar
 * só: os dois componentes recebem o MESMO array, e divergir deixa de ser
 * possível sem alguém apagar esta linha de propósito.
 *
 * ## Por que a lista é por SINTOMA e não por conta
 *
 * A pergunta do operador não é "quais contas têm problema", é "o que eu faço
 * agora". Duas campanhas com o mesmo sintoma pedem a mesma revisão, na mesma
 * ordem; duas campanhas da mesma conta com sintomas diferentes pedem coisas
 * opostas. Agrupar por conta obrigaria a reler item a item para descobrir isso.
 *
 * ## ⚠️ O QUE NÃO ENTRA AQUI, E POR QUÊ
 *
 * `sem vínculo` e `sem procedência` NÃO são condições de atenção. Elas são
 * verdade sobre quase todo o registro no primeiro dia, e um sino que acende
 * para tudo é um sino que ninguém olha na segunda semana. As duas continuam
 * visíveis onde pertencem: na linha do inventário, como selo.
 *
 * E `indisponibilidade de consulta` também não entra: "não consegui perguntar"
 * e "perguntei e há três problemas" levam a ações opostas. A primeira vira
 * `ContaSemLeitura`, que a tela mostra separada e NUNCA soma ao contador.
 *
 * ## De onde vem a régua
 *
 * Do próprio domínio, em `backend/app/trafego/dominio.py:pede_atencao`: conta
 * que não pôde ser lida, presença com ressalva, ligada sem entrega medida, e
 * ligada com sintoma medido. Esta projeção espelha aquela regra em vez de
 * inventar uma segunda — duas definições de "pede atenção" no mesmo produto é
 * como o contador da aba passa a discordar do contador do servidor.
 */
import type {
  AlertaDeEntrega as Alerta,
  CampanhaNoInventario,
  ContaNoInventario,
  Inventario,
  QuadroDeAlertas,
} from '@/types/trafego';

import {
  PRESENCA,
  frescorLegivel,
  idade,
  lidoHa,
  presencaLegivel,
} from '@/components/trafego/inventario/formato';
import { tempoLigada } from '@/components/trafego/AlertaDeEntrega';

// ── vocabulário ─────────────────────────────────────────────────────────────

/**
 * Os sintomas que esta tela sabe NOMEAR.
 *
 * Cada chave é um SINTOMA OBSERVADO, nunca uma causa. "não encontrada" afirma
 * que a conta respondeu e a campanha não estava na resposta; ela não afirma que
 * alguém apagou a campanha, porque isso a tela não viu.
 */
export type Sintoma =
  | 'ligada_sem_impressao'
  | 'ligada_sem_clique'
  | 'ligada_sem_medida'
  | 'sincronizacao_falhou'
  | 'campanha_nao_encontrada'
  | 'estado_desconhecido'
  | 'conta_nao_identificada'
  | 'campanha_removida'
  | 'conta_fora_de_escopo'
  | 'legado_nao_reconciliado'
  | 'leitura_desatualizada'
  | 'condicao_nao_reconhecida';

/** Sobre o que o item fala: uma campanha, ou a leitura de uma conta inteira. */
export type Escopo = 'campanha' | 'conta';

export interface DescricaoDoSintoma {
  /** O título do grupo, em linguagem de operação. */
  titulo: string;
  /** O que a condição AFIRMA — e só o que ela afirma. */
  afirma: string;
  /** O que fazer agora sem risco de piorar. Nunca "resolva"; sempre "confira". */
  proximaAcao: string;
  escopo: Escopo;
  /**
   * Ordem de atenção. Menor primeiro. Não é gravidade abstrata: é quanto
   * dinheiro pode estar saindo enquanto ninguém olha. Campanha ligada vem
   * antes de campanha removida porque só uma das duas pode estar gastando.
   */
  ordem: number;
}

export const SINTOMAS: Record<Sintoma, DescricaoDoSintoma> = {
  ligada_sem_impressao: {
    titulo: 'ligada e sem impressão',
    afirma:
      'a campanha está ligada na conta e não apareceu nenhuma vez na medida lida. ' +
      'Não entrou no leilão — o que se revisa aqui é lance, aprovação e volume.',
    proximaAcao:
      'Abra a campanha no Google Ads e confira, nesta ordem, o que o Google está dizendo, ' +
      'o lance do grupo e o orçamento do dia. Mexer na verba antes disso não muda nada.',
    escopo: 'campanha',
    ordem: 1,
  },
  ligada_sem_clique: {
    titulo: 'apareceu e ninguém clicou',
    afirma:
      'a campanha entrou no leilão e não recebeu clique na medida lida. ' +
      'O que se revisa aqui é o anúncio e a página, não o lance.',
    proximaAcao:
      'Abra o anúncio e a página de destino. Subir o lance aqui paga mais caro pelo ' +
      'mesmo anúncio que ninguém clicou.',
    escopo: 'campanha',
    ordem: 2,
  },
  ligada_sem_medida: {
    titulo: 'ligada e sem medida de entrega',
    afirma:
      'a conta declara a campanha como ligada e não há medida de impressão, clique ou ' +
      'custo para o período lido. Ela pode estar gastando agora, e não sabemos quanto.',
    proximaAcao:
      'Peça uma leitura desta conta no inventário. Enquanto não houver medida, trate a ' +
      'campanha como gastando por padrão e confira o painel do Google antes de decidir.',
    escopo: 'campanha',
    ordem: 3,
  },
  sincronizacao_falhou: {
    titulo: 'sincronização falhou',
    afirma:
      'a última tentativa de ler esta conta não deu certo. Não dá para afirmar presença ' +
      'nem ausência do que ela contém — o que está na tela é a última leitura boa.',
    proximaAcao:
      'Peça uma leitura desta conta no inventário. Se ela continuar sem responder, ' +
      'confira o painel do Google antes de decidir qualquer gasto nessas campanhas.',
    escopo: 'conta',
    ordem: 4,
  },
  campanha_nao_encontrada: {
    titulo: 'campanha não encontrada',
    afirma:
      'a conta foi lida com sucesso e esta campanha não estava na resposta. Isto não ' +
      'afirma que ela deixou de existir — afirma que ela não veio na leitura.',
    proximaAcao:
      'Confira no painel do Google se a campanha foi renomeada, removida ou movida de ' +
      'conta. Só depois disso o registro daqui deve ser mexido.',
    escopo: 'campanha',
    ordem: 5,
  },
  estado_desconhecido: {
    titulo: 'estado desconhecido',
    afirma:
      'a conta não informou em que estado esta campanha está, ou informou uma palavra ' +
      'que esta versão da tela não sabe ler. O fato é real; o que falta é a frase.',
    proximaAcao:
      'Confira esta campanha no painel do Google. Não conte com o estado que aparece ' +
      'aqui até a leitura seguinte trazer uma palavra conhecida.',
    escopo: 'campanha',
    ordem: 6,
  },
  conta_nao_identificada: {
    titulo: 'conta não identificada',
    afirma:
      'a linha existe no nosso registro sem conta utilizável. Não sabemos em qual conta ' +
      'de anúncio procurar por esta campanha.',
    proximaAcao:
      'Descubra a conta antes de qualquer outra coisa: sem ela não há onde conferir nem ' +
      'onde agir, e nenhum número desta linha pode ser confirmado.',
    escopo: 'campanha',
    ordem: 7,
  },
  campanha_removida: {
    titulo: 'campanha removida',
    afirma:
      'a conta respondeu e declara esta campanha como removida. Ela continua no nosso ' +
      'registro, e o nosso registro ainda não sabe se isso foi intencional.',
    proximaAcao:
      'Confira se o encerramento foi intencional. Se foi, o registro pode ser arquivado; ' +
      'se não foi, a campanha precisa ser recriada — nenhuma das duas acontece sozinha.',
    escopo: 'campanha',
    ordem: 8,
  },
  conta_fora_de_escopo: {
    titulo: 'conta fora do escopo da casa',
    afirma:
      'a conta existe, mas não é uma das contas administradas pela casa. As leituras ' +
      'automáticas não a alcançam.',
    proximaAcao:
      'Confira com quem administra a conta se ela deveria estar sob a nossa gestão. ' +
      'Enquanto não estiver, nada aqui se atualiza sozinho.',
    escopo: 'campanha',
    ordem: 9,
  },
  legado_nao_reconciliado: {
    titulo: 'linha antiga nunca conferida',
    afirma:
      'esta linha veio de antes do inventário e nunca foi conferida contra uma conta ' +
      'real. Ela é visível de propósito — some do total seria pior que aparecer sem prova.',
    proximaAcao:
      'Confira se ela ainda corresponde a alguma campanha real antes de somá-la a ' +
      'qualquer total ou de apagá-la.',
    escopo: 'campanha',
    ordem: 10,
  },
  leitura_desatualizada: {
    titulo: 'leitura desatualizada',
    afirma:
      'nada deu errado com esta conta: só passou tempo. Os números dela continuam na ' +
      'tela, e descrevem o momento em que foram lidos, não agora.',
    proximaAcao:
      'Peça uma leitura desta conta no inventário antes de decidir gasto com estes ' +
      'números. Nenhuma ação é urgente só por causa da idade.',
    escopo: 'conta',
    ordem: 11,
  },
  condicao_nao_reconhecida: {
    titulo: 'condição não reconhecida',
    // ⚠️ A frase "o que falta aqui é a frase, não o fato" vive UMA vez na tela,
    // na linha que mostra a palavra crua do servidor. Repeti-la aqui produziria
    // dois parágrafos dizendo o mesmo no mesmo cabeçalho.
    afirma:
      'a varredura marcou estas campanhas com uma condição que esta versão da tela não ' +
      'sabe explicar. Elas continuam listadas porque a condição foi observada.',
    proximaAcao:
      'Confira estas campanhas no painel do Google e avise quem cuida do sistema: a ' +
      'condição existe do outro lado e ainda não tem nome deste.',
    escopo: 'campanha',
    ordem: 12,
  },
};

/**
 * ⚠️ Sintoma novo no servidor não pode apagar a fila inteira.
 *
 * `SINTOMAS[chave]` devolveria `undefined` para algo que este pacote ainda não
 * conhece, e o `.titulo` logo a seguir lançaria — levando junto os outros
 * grupos, que estavam certos. A fila existe para mostrar o que pede atenção;
 * sumir por inteiro diante de algo desconhecido é a falha mais cara que ela
 * pode ter.
 */
export function descricaoDoSintoma(sintoma: string): DescricaoDoSintoma {
  return SINTOMAS[sintoma as Sintoma] ?? SINTOMAS.condicao_nao_reconhecida;
}

// ── o item ──────────────────────────────────────────────────────────────────

/** Um fato que pede um olho humano, com tudo que a decisão exige junto. */
export interface ItemDeAtencao {
  /**
   * A chave de foco que viaja no endereço: `{conta}-{campanha}` para item de
   * campanha, `{conta}` para item de conta. É o mesmo sufixo do `id` no DOM,
   * para o sino conseguir apontar e a fila conseguir revelar.
   */
  chave: string;
  sintoma: Sintoma;
  escopo: Escopo;
  /** Nome da campanha, ou `null` quando o item fala da conta inteira. */
  campanha: string | null;
  campanhaId: string | null;
  /** Nome da conta, sempre presente em palavra — nunca só o número. */
  conta: string;
  contaId: string;
  /** Há quanto tempo isto é verdade, na linguagem da operação. */
  desdeQuando: string;
  /** Os fatos medidos que sustentam o sintoma. Nunca inferência nossa. */
  evidencia: string[];
  /**
   * A palavra CRUA que o servidor usou, quando esta tela não a reconhece.
   *
   * Ela precisa chegar à tela: sem ela, "condição não reconhecida" vira um beco
   * — o operador sabe que há algo e não tem o que dizer a quem pode consertar.
   * `null` quando o sintoma está no vocabulário desta versão.
   */
  sintomaCru: string | null;
  /** O alerta inteiro, quando a origem foi a varredura de entrega. */
  alerta: Alerta | null;
  /** A campanha no Google Ads, quando há conta para montar o endereço. */
  urlExterna: string | null;
}

export interface ContaSemLeitura {
  contaId: string;
  conta: string;
  /** O que o servidor disse, já em linguagem de operação. */
  motivo: string;
  /** Idade da última leitura boa, quando existe. */
  ultimaLeituraBoa: string | null;
}

export interface GrupoDeSintoma {
  sintoma: Sintoma;
  descricao: DescricaoDoSintoma;
  itens: ItemDeAtencao[];
}

export interface Projecao {
  itens: ItemDeAtencao[];
  grupos: GrupoDeSintoma[];
  /** Indisponibilidade de leitura. Informação — NUNCA soma ao contador. */
  semLeitura: ContaSemLeitura[];
  /** Quantas campanhas ligadas a varredura conferiu, quando ela respondeu. */
  verificadas: number | null;
  /** A partir de quantas horas ligada sem gastar a varredura acusa. */
  horasAteAlertar: number | null;
}

// ── auxiliares ──────────────────────────────────────────────────────────────
/**
 * O vocabulário fechado de frescor, como conjunto.
 *
 * Declarado aqui e não importado de `formato` para manter esta função pura e
 * sem dependência de render — a tabela de lá é de APRESENTAÇÃO, esta é de
 * classificação, e as duas mudam por motivos diferentes.
 */
const FRESCOR_CONHECIDO: Record<string, true> = {
  recente: true,
  velho: true,
  parcial: true,
  falhou: true,
  nunca_lido: true,
  vazio_confirmado: true,
};


const nomeDaConta = (id: string, nome: string | null | undefined): string =>
  nome?.trim() || id;

/**
 * ⚠️ TEXTO DO SERVIDOR SÓ PASSA SE PARECER PROSA DE OPERAÇÃO.
 *
 * `QuadroDeAlertas.contas[].erro` e `Faltou.motivo` chegam como texto livre, e
 * texto livre do servidor é onde entram, sem ninguém decidir, a URL interna, o
 * `detail` com exceção recortada, o nome da variável de ambiente e a chave do
 * JSON. Nada disso ajuda quem está decidindo se mexe numa campanha — e algumas
 * dessas coisas não deveriam sair do servidor de jeito nenhum.
 *
 * O filtro é por FORMA e não por lista de palavras proibidas: uma lista de
 * palavras precisa ser atualizada toda vez que o servidor inventa um erro novo,
 * e é sempre atualizada tarde demais. O que passa é frase curta sem os sinais
 * gráficos que só aparecem em despejo técnico.
 */
export function motivoOperacional(texto: string | null | undefined): string {
  const bruto = (texto ?? '').trim();
  const generico = 'a leitura desta conta não voltou, e o motivo não veio em linguagem de operação';
  if (!bruto) return generico;
  if (bruto.length > 200) return generico;
  // Crase, chaves, colchetes, aspas de código, dois-pontos seguidos de barra,
  // `MAIUSCULA_COM_UNDERSCORE`, `<`, `>` e quebra de linha: nenhum deles
  // aparece numa frase escrita para o operador, e todos aparecem em despejo.
  if (/[`{}[\]<>\n]/.test(bruto)) return generico;
  if (/https?:\/\//i.test(bruto)) return generico;
  if (/\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/.test(bruto)) return generico;
  if (/\b(Traceback|Exception|Error:|at [A-Za-z]+\.[A-Za-z]+)\b/.test(bruto)) return generico;
  return bruto;
}

const nomeDaCampanha = (c: CampanhaNoInventario): string =>
  c.nome?.trim() || `campanha ${c.externa.campaign_id}`;

/**
 * O endereço da campanha no painel do Google.
 *
 * Sem `customer_id` utilizável não se monta endereço nenhum: um link que abre a
 * conta errada é pior que link nenhum, porque o operador confere a campanha
 * errada e conclui que está tudo bem.
 */
export function urlNoGoogleAds(contaId: string, campanhaId: string | null): string | null {
  if (!campanhaId) return null;
  const conta = contaId.trim();
  // O grupo sintético de linhas sem conta não é um `customer_id`: ele não abre
  // conta nenhuma, e mandá-lo na URL produziria um endereço que não existe.
  if (!conta || !/^\d+$/.test(conta)) return null;
  return `https://ads.google.com/aw/campaigns?campaignId=${campanhaId}&__c=${conta}`;
}

const ehPresencaConhecida = (valor: string): boolean =>
  Object.prototype.hasOwnProperty.call(PRESENCA, valor);

/** A palavra de presença que o servidor mandou e esta tela não conhece. */
function presencaCrua(campanha: CampanhaNoInventario): string | null {
  const presenca = String(campanha.presenca ?? '');
  if (!presenca || ehPresencaConhecida(presenca)) return null;
  return presenca;
}

/**
 * Qual sintoma uma campanha do inventário apresenta — ou nenhum.
 *
 * A ordem dos testes É a regra: a primeira condição que casa é a que nomeia a
 * campanha, e é sempre a mais cara das que valem para ela. Uma campanha que
 * está numa conta que falhou E tem presença duvidosa aparece UMA vez, sob o
 * sintoma que pede a ação mais urgente.
 */
/**
 * Acima disto, zero clique acusa o ANÚNCIO; abaixo, acusa o alcance.
 *
 * Mesmo valor de `dominio.IMPRESSOES_PARA_CULPAR_O_ANUNCIO`. Duplicado de
 * propósito: o backend não expõe a constante, e importar o módulo Python no
 * navegador não é opção. Se um dos dois mudar, o outro tem de mudar junto — há
 * teste que compara a classificação dos dois lados.
 */
const IMPRESSOES_PARA_CULPAR_O_ANUNCIO = 100;

export function sintomaDaCampanha(campanha: CampanhaNoInventario): Sintoma | null {
  const presenca = String(campanha.presenca ?? '');

  if (presenca === 'sincronizacao_falhou') return 'sincronizacao_falhou';
  if (presenca === 'nao_encontrada') return 'campanha_nao_encontrada';
  if (presenca === 'conta_nao_identificada') return 'conta_nao_identificada';
  // ⚠️ `removida` NÃO entra na fila, e não é esquecimento.
  //
  // Ela é ACORDO entre o nosso registro e a conta: a conta diz que removeu e
  // nós registramos. Não há o que conferir — é história, e história mora no
  // inventário, com o selo na linha.
  //
  // Medido em 25/08/2026, na primeira varredura real: das 84 campanhas, 79
  // estavam removidas. Com elas na fila, a aba dizia 53 enquanto a fonte de
  // verdade dizia 2 — e um contador que não bate com o que a aba mostra ensina
  // o operador a não confiar em contador nenhum.
  //
  // `nao_encontrada` continua entrando, logo acima, e a diferença é o ponto:
  // ali a leitura foi BOA e a campanha não estava lá. Nosso registro e a conta
  // DISCORDAM, e discordância merece um olho.
  //
  // Esta regra é a tradução de `dominio.pede_atencao()` e do CASE da view
  // (`supabase/migrations/v9_02_atencao_sem_removida.sql`). As três mudam
  // sempre juntas — senão o sino, a aba e o banco contam histórias diferentes
  // sobre o mesmo fato.
  if (presenca === 'removida') return null;
  if (presenca === 'fora_de_escopo') return 'conta_fora_de_escopo';
  if (presenca === 'legado_nao_reconciliado') return 'legado_nao_reconciliado';
  // Presença que este pacote não conhece é FATO REAL sem palavra nossa: entra
  // nomeada como desconhecida, e nunca degrada para "presente".
  if (presenca && presenca !== 'presente' && !ehPresencaConhecida(presenca)) {
    return 'estado_desconhecido';
  }

  const estado = (campanha.estado_externo ?? '').trim().toUpperCase();
  if (!estado) return 'estado_desconhecido';
  if (estado !== 'ENABLED') return null;

  // Regra do domínio: ligada e sem entrega MEDIDA pede um olho. Sem a data de
  // leitura o número não é medida — e "não sei quanto está gastando" é
  // exatamente o estado que alguém precisa conferir.
  if (campanha.entrega.leitura == null) return 'ligada_sem_medida';

  // ⚠️ ESTE RAMO ESPELHA `dominio.sintoma_de_entrega()`, e faltava.
  //
  // A projeção parava aqui e devolvia `null` para toda campanha ligada com
  // entrega medida. O resultado, medido em 25/08/2026 com dado fresco: a API
  // dizia `atencao: 2` e a aba dizia 0 — as duas únicas campanhas ligadas da
  // casa, ligadas e sem um clique, não apareciam na fila que existe para
  // mostrá-las.
  //
  // Os avisos de entrega (`/alertas`) cobrem outra coisa: eles exigem 24 h
  // ligada SEM GASTAR. Uma campanha que gastou e não converteu clique nenhum
  // não entra lá, e não entrava aqui: caía no vão entre as duas fontes.
  //
  // A ordem dos ramos é a do backend, e o motivo de cada um está lá:
  //   impressões não medidas  → não afirma nada (regra B: null não é zero)
  //   algum clique            → está funcionando, não pede olho
  //   muitas impressões e zero clique → o anúncio é o suspeito
  //   poucas impressões       → quem não aparece não pode ser clicado
  const imp = campanha.entrega.impressoes;
  const cli = campanha.entrega.cliques;
  if (imp == null) return null;
  if (cli != null && cli > 0) return null;
  return imp >= IMPRESSOES_PARA_CULPAR_O_ANUNCIO
    ? 'ligada_sem_clique'
    : 'ligada_sem_impressao';
}

/** A evidência de uma campanha do inventário: só o que foi medido, com idade. */
function evidenciaDaCampanha(campanha: CampanhaNoInventario, conta: ContaNoInventario): string[] {
  const linhas: string[] = [];
  const presenca = String(campanha.presenca ?? '');
  if (presenca && presenca !== 'presente') {
    linhas.push(presencaLegivel(presenca).descricao);
  }
  if (campanha.estado_externo) {
    linhas.push(`a conta declara o estado ${campanha.estado_externo}`);
  } else {
    linhas.push('a conta não informou o estado desta campanha');
  }
  const leitura = campanha.entrega.leitura ?? conta.ultima_leitura_boa ?? conta.leitura;
  linhas.push(
    campanha.entrega.leitura
      ? `medida ${lidoHa(campanha.entrega.leitura.idade_s)}`
      : leitura
        ? `sem medida de entrega; a conta foi lida ${idade(leitura.idade_s)}`
        : 'sem medida de entrega e sem data de leitura desta conta',
  );
  return linhas;
}

// ── a projeção ──────────────────────────────────────────────────────────────

export interface FontesDaAtencao {
  /** O que a varredura de entrega respondeu. `null` = ela não respondeu. */
  alertas: QuadroDeAlertas | null;
  /** O último inventário utilizável. `null` = nunca houve nenhum. */
  inventario: Inventario | null;
}

/**
 * Junta as duas fontes numa lista só, sem repetir campanha.
 *
 * A varredura de entrega tem prioridade sobre o inventário para a MESMA
 * campanha: ela mediu o leilão, o inventário só descreve o registro. Uma
 * campanha que aparece nas duas é listada uma vez, com o sintoma da varredura —
 * que é o que traz a ordem de revisão pronta.
 */
export function projetarAtencao({ alertas, inventario }: FontesDaAtencao): Projecao {
  const itens: ItemDeAtencao[] = [];
  const jaListadas = new Set<string>();

  for (const alerta of alertas?.alertas ?? []) {
    const chave = `${alerta.customer_id}-${alerta.campaign_id}`;
    if (jaListadas.has(chave)) continue;
    jaListadas.add(chave);

    const sintoma: Sintoma =
      alerta.sintoma === 'sem_impressao'
        ? 'ligada_sem_impressao'
        : alerta.sintoma === 'sem_clique'
          ? 'ligada_sem_clique'
          : 'condicao_nao_reconhecida';

    itens.push({
      chave,
      sintoma,
      escopo: 'campanha',
      campanha: alerta.campaign_name || `campanha ${alerta.campaign_id}`,
      campanhaId: alerta.campaign_id,
      conta: nomeDaConta(alerta.customer_id, alerta.customer_name),
      contaId: alerta.customer_id,
      desdeQuando: `ligada ${tempoLigada(alerta.horas_ligada)} sem gastar`,
      evidencia: [
        `${alerta.impressoes} ${alerta.impressoes === 1 ? 'impressão' : 'impressões'}, ` +
          `${alerta.cliques} ${alerta.cliques === 1 ? 'clique' : 'cliques'} na medida lida`,
        alerta.razoes.length > 0
          ? `o Google diz: ${alerta.razoes.join(' · ')}`
          : 'o Google não fez observação nenhuma sobre esta campanha',
      ],
      sintomaCru: sintoma === 'condicao_nao_reconhecida' ? String(alerta.sintoma) : null,
      alerta,
      urlExterna: urlNoGoogleAds(alerta.customer_id, alerta.campaign_id),
    });
  }

  const semLeitura: ContaSemLeitura[] = [];

  for (const conta of inventario?.contas ?? []) {
    const nome = nomeDaConta(conta.customer_id, conta.nome);
    const frescor = String(conta.frescor ?? '');
    const contaFalhou = frescor === 'falhou';

    // A conta inteira em falha vira UM item, não um por campanha. Quarenta
    // linhas idênticas dizendo "a conta não respondeu" não informam quarenta
    // vezes mais: informam uma vez e escondem os outros sintomas.
    const noEscuro = conta.campanhas.filter(
      (c) => String(c.presenca ?? '') === 'sincronizacao_falhou',
    );

    if (contaFalhou || noEscuro.length > 0) {
      for (const c of noEscuro) jaListadas.add(`${c.externa.customer_id}-${c.externa.campaign_id}`);
      const nomes = noEscuro.slice(0, 3).map(nomeDaCampanha);
      itens.push({
        chave: conta.customer_id,
        sintoma: 'sincronizacao_falhou',
        escopo: 'conta',
        campanha: null,
        campanhaId: null,
        conta: nome,
        contaId: conta.customer_id,
        desdeQuando: conta.ultima_leitura_boa
          ? `última leitura boa ${idade(conta.ultima_leitura_boa.idade_s)}`
          : 'sem leitura boa anterior',
        evidencia: [
          motivoOperacional(conta.motivo),
          noEscuro.length === 0
            ? 'nenhuma campanha desta conta está no inventário desta leitura'
            : noEscuro.length === 1
              ? `1 campanha sem confirmação: ${nomes[0]}`
              : `${noEscuro.length} campanhas sem confirmação: ${nomes.join(', ')}` +
                (noEscuro.length > 3 ? ` e mais ${noEscuro.length - 3}` : ''),
        ],
        sintomaCru: null,
        alerta: null,
        urlExterna: null,
      });
    }

    // `velho` e frescor que esta tela não conhece caem juntos aqui, e nunca no
    // silêncio: desconhecido NÃO degrada para recente, porque decidir gasto
    // olhando para um número de idade desconhecida é o erro mais caro do módulo.
    const frescorEstranho = frescor !== '' && !(frescor in FRESCOR_CONHECIDO);
    if (frescor === 'velho' || frescorEstranho) {
      itens.push({
        chave: conta.customer_id,
        sintoma: 'leitura_desatualizada',
        escopo: 'conta',
        campanha: null,
        campanhaId: null,
        conta: nome,
        contaId: conta.customer_id,
        desdeQuando: conta.leitura ? lidoHa(conta.leitura.idade_s) : 'sem data de leitura',
        evidencia: [
          frescorLegivel(frescor).descricao,
          conta.quantidade === 1
            ? '1 campanha desta conta é descrita por esta leitura'
            : `${conta.quantidade} campanhas desta conta são descritas por esta leitura`,
        ],
        sintomaCru: frescorEstranho ? frescor : null,
        alerta: null,
        urlExterna: null,
      });
    }

    for (const campanha of conta.campanhas) {
      const chave = `${campanha.externa.customer_id}-${campanha.externa.campaign_id}`;
      if (jaListadas.has(chave)) continue;
      const sintoma = sintomaDaCampanha(campanha);
      if (!sintoma) continue;
      // A conta em falha já foi contada acima; repetir a campanha aqui somaria
      // o mesmo fato duas vezes ao contador.
      if (sintoma === 'sincronizacao_falhou') continue;
      jaListadas.add(chave);

      itens.push({
        chave,
        sintoma,
        escopo: 'campanha',
        campanha: nomeDaCampanha(campanha),
        campanhaId: campanha.externa.campaign_id,
        conta: nome,
        contaId: campanha.externa.customer_id,
        desdeQuando: campanha.entrega.leitura
          ? lidoHa(campanha.entrega.leitura.idade_s)
          : conta.ultima_leitura_boa
            ? `última leitura boa ${idade(conta.ultima_leitura_boa.idade_s)}`
            : 'sem data de leitura',
        evidencia: evidenciaDaCampanha(campanha, conta),
        sintomaCru: presencaCrua(campanha),
        alerta: null,
        urlExterna: urlNoGoogleAds(campanha.externa.customer_id, campanha.externa.campaign_id),
      });
    }
  }

  // Contas que a varredura não conseguiu consultar. Isto NÃO é condição ativa:
  // é ausência de leitura, e some do contador de propósito.
  for (const conta of alertas?.contas ?? []) {
    if (!conta.erro) continue;
    semLeitura.push({
      contaId: conta.customer_id,
      conta: nomeDaConta(conta.customer_id, conta.nome),
      motivo: motivoOperacional(conta.erro),
      ultimaLeituraBoa: null,
    });
  }
  for (const f of inventario?.faltou ?? []) {
    if (!f.customer_id) continue;
    if (semLeitura.some((s) => s.contaId === f.customer_id)) continue;
    const conta = inventario?.contas.find((c) => c.customer_id === f.customer_id);
    semLeitura.push({
      contaId: f.customer_id,
      conta: nomeDaConta(f.customer_id, conta?.nome ?? null),
      motivo: motivoOperacional(f.motivo),
      ultimaLeituraBoa: conta?.ultima_leitura_boa
        ? `última leitura boa ${idade(conta.ultima_leitura_boa.idade_s)}`
        : null,
    });
  }

  const ordenados = [...itens].sort((a, b) => {
    const pa = descricaoDoSintoma(a.sintoma).ordem;
    const pb = descricaoDoSintoma(b.sintoma).ordem;
    if (pa !== pb) return pa - pb;
    return a.chave.localeCompare(b.chave);
  });

  const porSintoma = new Map<Sintoma, ItemDeAtencao[]>();
  for (const item of ordenados) {
    const lista = porSintoma.get(item.sintoma) ?? [];
    lista.push(item);
    porSintoma.set(item.sintoma, lista);
  }

  return {
    itens: ordenados,
    grupos: [...porSintoma.entries()].map(([sintoma, lista]) => ({
      sintoma,
      descricao: descricaoDoSintoma(sintoma),
      itens: lista,
    })),
    semLeitura,
    verificadas: alertas?.verificadas ?? null,
    horasAteAlertar: alertas?.horas_ate_alertar ?? null,
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// A DECISÃO QUE O ITEM PEDE — a camada que a SPEC §11 cobra
// ═══════════════════════════════════════════════════════════════════════════
//
// A fila já agrupava por SINTOMA, e os sintomas estão certos. O que faltava era
// a camada acima: a SPEC §11 organiza a fila "por decisão necessária", não pela
// origem técnica da condição.
//
// ⚠️ Isto NÃO reagrupa nem reordena os itens dentro de um sintoma, e não muda a
// autoridade de contagem — o sino e a aba continuam lendo a mesma projeção. É
// uma camada de LEITURA por cima do que já existe: dois sintomas que pedem a
// mesma decisão passam a aparecer juntos, e o operador deixa de saltar entre
// "sincronização falhou" e "leitura desatualizada" como se fossem assuntos
// diferentes. São o mesmo assunto: a conta não está confiável agora.

export type FamiliaDeDecisao =
  | 'entrega'
  | 'leitura_da_conta'
  | 'existencia'
  | 'vinculo'
  | 'nao_classificada';

/** A ordem é a da SPEC §11: entrega primeiro, o que é meta-condição depois. */
export const FAMILIAS: ReadonlyArray<{
  chave: FamiliaDeDecisao;
  titulo: string;
  pergunta: string;
}> = [
  {
    chave: 'entrega',
    titulo: 'Entrega',
    pergunta: 'a campanha está comprando clique como devia?',
  },
  {
    chave: 'leitura_da_conta',
    titulo: 'Leitura da conta',
    pergunta: 'dá para confiar nos números desta conta agora?',
  },
  {
    // ⚠️ Família própria, separada de `vinculo`.
    // `campanha_nao_encontrada` e `campanha_removida` são fatos de EXISTÊNCIA —
    // "a conta foi lida e esta campanha não estava na resposta" —, não de
    // propriedade. Enquadrá-los como "sabemos de quem é esta campanha?" faz o
    // operador procurar um funil quando a pergunta é se a campanha ainda existe.
    chave: 'existencia',
    titulo: 'Existência na conta',
    pergunta: 'esta campanha ainda está na conta?',
  },
  {
    chave: 'vinculo',
    titulo: 'Vínculo e procedência',
    pergunta: 'sabemos de quem é esta campanha?',
  },
  {
    // ⚠️ Aqui cai o que o servidor emitir e este pacote não conhecer — e SÓ
    // isso. `estado_desconhecido` NÃO mora aqui: ele é um dos doze sintomas
    // nomeados, foi classificado de propósito, e pô-lo nesta família fazia a
    // tela afirmar que não conhece o que conhece.
    chave: 'nao_classificada',
    titulo: 'Ainda sem classificação',
    pergunta: 'o servidor descreveu algo que esta versão da tela não sabe agrupar',
  },
];

const FAMILIA_DO_SINTOMA: Record<string, FamiliaDeDecisao> = {
  ligada_sem_impressao: 'entrega',
  ligada_sem_clique: 'entrega',
  ligada_sem_medida: 'entrega',

  sincronizacao_falhou: 'leitura_da_conta',
  leitura_desatualizada: 'leitura_da_conta',
  conta_nao_identificada: 'leitura_da_conta',
  conta_fora_de_escopo: 'leitura_da_conta',

  legado_nao_reconciliado: 'vinculo',

  campanha_nao_encontrada: 'existencia',
  campanha_removida: 'existencia',

  // O estado veio da conta e este pacote não o traduz — é leitura, não falta de
  // classificação nossa.
  estado_desconhecido: 'leitura_da_conta',
  condicao_nao_reconhecida: 'nao_classificada',
};

/**
 * ⚠️ Sintoma desconhecido cai em `nao_classificada`, e NÃO em `entrega`.
 *
 * O padrão importa: um sintoma novo que o servidor emitisse e que caísse na
 * primeira família apareceria como problema de entrega, com a autoridade de
 * uma classificação — e o operador iria mexer em lance por causa de uma
 * condição que ninguém classificou.
 */
export function familiaDoSintoma(sintoma: string): FamiliaDeDecisao {
  return FAMILIA_DO_SINTOMA[sintoma] ?? 'nao_classificada';
}

/**
 * As DECISÕES que a SPEC §11 lista e para as quais ainda não há sensor.
 *
 * Declaradas para que a fila diga o que ela NÃO cobre. Uma fila silenciosa
 * sobre política e rastreamento lê-se como "não há problema de política" — que
 * é uma afirmação sobre algo que ninguém mediu.
 */
export const DECISOES_SEM_SENSOR: ReadonlyArray<{ titulo: string; porque: string }> = [
  {
    titulo: 'Orçamento e lance',
    porque:
      'não há regra de bidding aprovada, e por isso nenhuma condição de verba ou lance é levantada aqui (ADR-11)',
  },
  {
    titulo: 'Política e aprovação',
    porque:
      'o veredito de política é lido por campanha, sob demanda, e ainda não alimenta esta fila',
  },
  {
    titulo: 'Rastreamento e conversão',
    porque: 'o envio de conversão offline ainda não está ligado',
  },
  {
    titulo: 'Criativo e inventário',
    porque: 'a leitura das entidades abaixo da campanha existe apenas no Search',
  },
];
