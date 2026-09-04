/**
 * A projeção das seis paradas da Bancada.
 *
 * ## A regra que este módulo existe para impor
 *
 * **O navegador projeta; o servidor adjudica.** Nada aqui inventa um veredito:
 * cada estado de parada sai de um fato que o servidor emitiu — a severidade do
 * aviso (já resolvida em `Cockpit.bloqueado`/`bloqueios`), o recibo do portão de
 * destino pago, o `status` da copy, o `vinculada` da conta, o
 * `approved_set_sha256` do conjunto pago.
 *
 * A versão anterior fazia o contrário. `NovaCampanhaPage.tsx:332-343` montava um
 * `const pendencias: string[] = []` a cada render e concluía
 * `podeLancar = pendencias.length === 0`, com duas regras que eram política pura
 * do browser ("marcar ao menos uma keyword", "escrever a copy") e um filtro de
 * severidade próprio. Cada cartão tinha ainda a sua própria expressão booleana
 * ad-hoc, e o trilho do topo tinha uma terceira: ele passava `origem` como
 * literal `true` — sempre verde, mesmo com o destino BLOQUEADO — e marcava a
 * copy como pronta para `status: 'running'`, `'error'` e linha perdida.
 *
 * Três réguas para a mesma pergunta, na mesma tela, discordando entre si.
 *
 * ## Por que `indeterminada` nunca vira `pendente`
 *
 * "não consegui ler" e "falta fazer" são fatos diferentes, e achatá-los é como
 * uma falha de leitura vira uma tarefa do operador — que ele então "cumpre" sem
 * que nada tenha sido lido. O destino pago já distingue os dois
 * (`leituraDoDestinoPago` separa `bloqueadores` de `desconhecidos`), e esta
 * projeção preserva a distinção até a tela.
 */
import type {
  AvisoDoCockpit, Cockpit, CopyPersistida, EstadoDaParada, ParadaDaBancada,
  ParadaProjetada, RevisaoDoConjuntoPago, VerticalDePolitica,
} from '@/types/trafego';
import { PARADAS_SEARCH } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';

export const ROTULO_DA_PARADA: Record<ParadaDaBancada, string> = {
  destino: 'Destino',
  politica: 'Política',
  termos: 'Termos',
  anuncio: 'Anúncio',
  economia: 'Economia',
  revisao: 'Revisão',
  display_destino: 'Objetivo e destino',
  display_geografia: 'Alcance geográfico',
  display_audiencia: 'Audiência e contexto',
  display_criativo: 'Criativo responsivo',
  display_inventario: 'Brand safety',
  display_economia: 'Economia',
  display_revisao: 'Revisão',
  demand_resultado: 'Resultado esperado',
  demand_superficies: 'Superfícies',
  demand_audiencia: 'Audiência',
  demand_kit: 'Kit de mídia',
  demand_mensagem: 'Mensagem',
  demand_economia: 'Economia',
  demand_revisao: 'Revisão',
  pmax_objetivo: 'Objetivo',
  pmax_lp: 'Destino aprovado',
  pmax_asset_group: 'Asset Group',
  pmax_sinais: 'Sinais',
  pmax_marca: 'Expansão e marca',
  pmax_economia: 'Economia',
  pmax_revisao: 'Revisão',
};

/** A pergunta que a parada responde. É o H2 da coluna de decisão. */
export const PERGUNTA_DA_PARADA: Record<ParadaDaBancada, string> = {
  destino: 'Para onde este anúncio manda o clique?',
  politica: 'Esta vertical pode anunciar neste país?',
  termos: 'Quais termos a campanha vai comprar?',
  anuncio: 'O que o anúncio vai dizer?',
  economia: 'Quanto isto pode gastar por dia?',
  revisao: 'É isto que você quer criar?',
  display_destino: 'Qual a conta, o objetivo e o destino aprovado?',
  display_geografia: 'Onde, em qual idioma e em quais redes o anúncio aparece?',
  display_audiencia: 'Como o engine trata audiência nesta versão?',
  display_criativo: 'Quais imagens e textos formam o criativo responsivo?',
  display_inventario: 'Que proteção de inventário o engine realmente aplica?',
  display_economia: 'Qual o orçamento e a conversão observada?',
  display_revisao: 'O criativo e as segmentações estão prontos?',
  demand_resultado: 'Qual o resultado, a conta e o destino?',
  demand_superficies: 'Em quais superfícies este anúncio vai rodar?',
  demand_audiencia: 'Quais sinais e audiências direcionam a campanha?',
  demand_kit: 'O kit de mídia visual atende aos requisitos do canal?',
  demand_mensagem: 'Como a mensagem se apresenta no formato nativo?',
  demand_economia: 'Quanto isso vai custar e como será medido?',
  demand_revisao: 'A composição final pode ser submetida?',
  pmax_objetivo: 'Qual o objetivo e a conta desta automação?',
  pmax_lp: 'Qual a URL de destino exclusiva deste funil?',
  pmax_asset_group: 'Quais recursos formam a cobertura de mídia?',
  pmax_sinais: 'Quais sinais de audiência vão alimentar o algoritmo?',
  pmax_marca: 'Como a marca e a expansão de URL estão configuradas?',
  pmax_economia: 'Qual o orçamento e a elegibilidade da medição?',
  pmax_revisao: 'O mapa de cobertura e as regras estão corretos?',
};

/**
 * O que a parada precisa para deixar de estar pendente, em linguagem de
 * operador. Vira `falta` no Pedido e razão adjacente da ação dominante.
 */
export interface FaltaDaParada {
  parada: ParadaDaBancada;
  texto: string;
  /** `true` quando a falta é ignorância, não tarefa. Ver o ⚠️ do topo. */
  indeterminada: boolean;
}

/** Tudo que a projeção precisa ler. Todos os campos vêm do servidor. */
export interface FatosDaBancada {
  cockpit: Cockpit | null;
  destino: LeituraDoDestinoPago;
  conjunto: RevisaoDoConjuntoPago | null;
  /** `null` = ainda não foi lida; `{existe:false}` já virou `null` no chamador. */
  copy: CopyPersistida | null;
  verticais: VerticalDePolitica[];
  /** O orçamento e o lance que o operador digitou, já normalizados. */
  orcamento: number | null;
  lance: number | null;
  /** As habilitações que o operador declarou. Elas SATISFAZEM o portão da
   *  vertical — sem elas aqui, a Bancada criaria um bloqueio sem saída. */
  certificacoes: string[];
  /** Completude dos contratos verticais. Cada booleano é calculado a partir
   *  dos mesmos campos que compõem o pedido; não é um segundo contrato. */
  multicanal?: {
    displayCriativo: boolean;
    displayEconomia: boolean;
    demandSuperficies: boolean;
    demandAudiencia: boolean;
    demandKit: boolean;
    demandMensagem: boolean;
    demandEconomia: boolean;
    pmaxObjetivo: boolean;
    pmaxAssetGroup: boolean;
    pmaxSinais: boolean;
    pmaxMarca: boolean;
    pmaxEconomia: boolean;
  };
}

/**
 * A severidade da vertical, lida do servidor.
 *
 * ⚠️ `limitacao` BARRA. `PortaoDePolitica.tsx:159-165` escrevia que a campanha
 * "sobe com restrição", enquanto `volc_ads/campanha/conteudo.py:56` já punha
 * `limitacao` entre as severidades que barram — o efeito FULLY_LIMITED deixou 57
 * anúncios sem veicular em 39 contas. Anúncio que não veicula é reprovação com
 * outro nome, e agora a régua é uma só.
 */
export function politicaBarra(
  v: VerticalDePolitica | null | undefined,
  pais?: string | null,
  certificacoes: string[] = [],
): boolean {
  if (!v?.exige) return false;
  // ⚠️ O PORTÃO É POR PAÍS, E A CERTIFICAÇÃO O SATISFAZ.
  //
  // A primeira versão desta função olhava só `severidade`, e isso era uma régua
  // NOVA do navegador — mais dura que a do produto e cega a duas coisas que
  // `PortaoDePolitica.tsx:48-50` já tratava certo desde sempre:
  //
  //   1. `paises_exigem` — verificar no Brasil não habilita o México, e uma
  //      vertical marcada `bloqueio` que NÃO exige neste país não barra nada;
  //   2. `certificacoes` — quando a conta já declarou a habilitação exigida, o
  //      portão está cumprido.
  //
  // Sem isso, a Bancada criava um bloqueio sem saída: o operador marcava a
  // certificação na própria parada e continuava barrado.
  const exigeAqui = (v.paises_exigem || []).includes(pais ?? '');
  if (!exigeAqui) return false;
  if (certificacoes.includes(v.exige)) return false;
  return v.severidade === 'bloqueio' || v.severidade === 'limitacao';
}

/** A vertical desta oportunidade, quando o servidor a reconhece. */
export function verticalDaOportunidade(
  cockpit: Cockpit | null, verticais: VerticalDePolitica[],
): VerticalDePolitica | null {
  const id = cockpit?.origem?.vertical;
  if (!id) return null;
  return verticais.find((v) => v.id === id) ?? null;
}

/**
 * Os bloqueios do cockpit, PREFERINDO os que o servidor já filtrou.
 *
 * ⚠️ A ausência de `bloqueios` no payload é "este servidor é mais antigo", não
 * "não há bloqueio". Nesse caso o navegador refiltra — e refiltra fail-closed,
 * pela mesma régua do engine, com `limitacao` barrando.
 */
export function bloqueiosDoCockpit(cockpit: Cockpit | null): AvisoDoCockpit[] {
  if (!cockpit) return [];
  if (Array.isArray(cockpit.bloqueios)) return cockpit.bloqueios;
  return (cockpit.avisos ?? []).filter(
    (a) => a.severidade === 'bloqueio' || a.severidade === 'limitacao'
      || (a.severidade !== 'atencao' && a.severidade !== 'informacao'),
  );
}

/** As faltas de cada parada, na ordem do conserto. */
export function faltasDaParada(
  parada: ParadaDaBancada, f: FatosDaBancada,
): FaltaDaParada[] {
  const faltas: FaltaDaParada[] = [];
  const add = (texto: string, indeterminada = false) =>
    faltas.push({ parada, texto, indeterminada });

  switch (parada) {
    case 'destino': {
      // O destino entra INTEIRO, e não só quando há bloqueio: testar apenas
      // `bloqueadores.length` ignoraria os `desconhecidos` — a verificação
      // exigida que não pôde ser concluída.
      if (!f.destino.apto_para_campanha) {
        // ⚠️ SEM RECIBO É IGNORÂNCIA INTEIRA, e não uma lista de tarefas.
        //
        // Quando `sem_recibo`, TODAS as faltas do destino são indeterminadas: o
        // portão não avaliou nada, então nenhuma delas é "você deixou de fazer
        // X" — são todas "ninguém apurou". Marcar uma como tarefa faria o
        // operador "cumpri-la" sem que nada tivesse sido lido, que é exatamente
        // como uma falha de leitura vira um verde.
        if (f.destino.sem_recibo) {
          add('avaliar o destino desta campanha', true);
          for (const p of f.destino.pendencias) add(p, true);
          break;
        }
        for (const p of f.destino.pendencias) {
          // Com recibo, `desconhecidos` sem `bloqueadores` é verificação que não
          // concluiu; qualquer bloqueador declarado é fato apurado.
          add(p, f.destino.desconhecidos.length > 0 && f.destino.bloqueadores.length === 0);
        }
      }
      break;
    }
    case 'politica': {
      const v = verticalDaOportunidade(f.cockpit, f.verticais);
      // ⚠️ Ausência de regra NUNCA é verde. Não achar a vertical na lista do
      // servidor significa que ninguém adjudicou este país × vertical — e um
      // portão que ninguém leu não é um portão aberto.
      if (!f.cockpit?.origem?.vertical) add('resolver a vertical desta oportunidade', true);
      else if (f.verticais.length === 0) add('ler os portões de política do servidor', true);
      else if (!v) add(`adjudicar a vertical "${f.cockpit.origem.vertical}"`, true);
      else if (politicaBarra(v, f.cockpit?.origem?.pais, f.certificacoes)) {
        add(v.exige ? `declarar a habilitação: ${v.exige}` : 'liberar o portão desta vertical');
      }
      break;
    }
    case 'termos': {
      // ⚠️ A tela NÃO acrescenta positivas. O conjunto é o aprovado na
      // mineração, e o que falta aqui é o ATO de aprová-lo — não escolher.
      if (!f.conjunto) add('carregar o conjunto pago desta oportunidade', true);
      else if (!f.conjunto.approved_set_sha256) add('aprovar o conjunto positivo');
      else if (f.conjunto.blockers.length > 0)
        for (const b of f.conjunto.blockers) add(b);
      break;
    }
    case 'anuncio': {
      // Uma regra só de pronto, e ela é o `status` do servidor. `!!escrita` daria
      // verde para 'running', 'error' e linha perdida.
      if (!f.copy) add('escrever o anúncio');
      else if (f.copy.status === 'running') add('esperar a escrita do anúncio terminar', true);
      else if (f.copy.status !== 'done') add('reescrever o anúncio: a escrita não fechou');
      else if (!f.copy.copy) add('reescrever o anúncio: a copy não veio no payload');
      break;
    }
    case 'economia': {
      if (!f.cockpit?.conta?.vinculada) add('vincular a conta de anúncio ao projeto');
      if (f.orcamento == null || f.orcamento <= 0) add('declarar o orçamento diário');
      if (f.lance == null || f.lance <= 0) add('declarar o lance inicial');
      break;
    }
    case 'revisao': {
      // Revisão nunca adiciona faltas próprias, ela é o agregado final das outras.
      break;
    }

    // -- Display
    case 'display_destino':
      if (!f.destino.apto_para_campanha) {
        if (f.destino.sem_recibo) { add('avaliar o destino desta campanha', true); }
        else { for (const p of f.destino.pendencias) add(p, f.destino.desconhecidos.length > 0 && f.destino.bloqueadores.length === 0); }
      }
      break;
    case 'display_geografia':
      if (!f.cockpit?.origem?.pais) add('resolver o país da oportunidade', true);
      if (!f.cockpit?.origem?.idioma) add('resolver o idioma da oportunidade', true);
      break;
    case 'display_audiencia':
    case 'display_inventario':
      // Não operados nesta fatia: a tela explica a ausência e não exige um
      // campo que o payload descartaria.
      break;
    case 'display_criativo':
      if (!f.multicanal?.displayCriativo) add('completar texto e imagens obrigatórias do anúncio Display');
      break;
    case 'display_economia':
      if (!f.cockpit?.conta?.vinculada) add('vincular a conta de anúncio ao projeto');
      if (!f.multicanal?.displayEconomia) add('declarar orçamento e CPA-alvo válido, quando usado');
      break;
    case 'display_revisao':
      break;

    // -- Demand Gen
    case 'demand_resultado':
      if (!f.destino.apto_para_campanha) {
        if (f.destino.sem_recibo) { add('avaliar o destino desta campanha', true); }
        else { for (const p of f.destino.pendencias) add(p, f.destino.desconhecidos.length > 0 && f.destino.bloqueadores.length === 0); }
      }
      break;
    case 'demand_superficies':
      if (!f.multicanal?.demandSuperficies) add('escolher explicitamente as superfícies Demand Gen');
      break;
    case 'demand_audiencia':
      if (!f.multicanal?.demandAudiencia) add('declarar targeting e confirmar a lista de audiências');
      break;
    case 'demand_kit':
      if (!f.multicanal?.demandKit) add('anexar ao menos uma imagem de marketing e um logo quadrado');
      break;
    case 'demand_mensagem':
      if (!f.multicanal?.demandMensagem) add('completar nome, títulos e descrições do anúncio');
      break;
    case 'demand_economia':
      if (!f.cockpit?.conta?.vinculada) add('vincular a conta de anúncio ao projeto');
      if (!f.multicanal?.demandEconomia) add('declarar o orçamento diário');
      break;
    case 'demand_revisao':
      break;

    // -- PMax
    case 'pmax_objetivo':
      if (!f.multicanal?.pmaxObjetivo) add('resolver uma meta de conversão válida na conta', true);
      break;
    case 'pmax_lp':
      if (!f.destino.apto_para_campanha) {
        if (f.destino.sem_recibo) { add('avaliar o destino desta campanha', true); }
        else { for (const p of f.destino.pendencias) add(p, f.destino.desconhecidos.length > 0 && f.destino.bloqueadores.length === 0); }
      }
      break;
    case 'pmax_asset_group':
      if (!f.multicanal?.pmaxAssetGroup) add('completar a cobertura mínima do asset group');
      break;
    case 'pmax_sinais':
      if (!f.multicanal?.pmaxSinais) add('confirmar sinais e negativas, mesmo quando vazios');
      break;
    case 'pmax_marca':
      if (!f.multicanal?.pmaxMarca) add('decidir o uso imutável de brand guidelines');
      break;
    case 'pmax_economia':
      if (!f.cockpit?.conta?.vinculada) add('vincular a conta de anúncio ao projeto');
      if (!f.multicanal?.pmaxEconomia) add('declarar orçamento e estratégia PMax');
      break;
    case 'pmax_revisao':
      break;
  }
  return faltas;
}
/**
 * Todas as faltas da Bancada, na ordem das paradas.
 *
 * É esta lista, e só ela, que decide se a ação dominante da Revisão acende. Uma
 * segunda expressão booleana em qualquer lugar da tela seria a quarta régua.
 */
export function faltasDaBancada(
  f: FatosDaBancada,
  paradasDoCanal: readonly ParadaDaBancada[] = PARADAS_SEARCH,
): FaltaDaParada[] {
  const das: FaltaDaParada[] = [];
  // Exclui a revisão da enumeração normal porque ela é o agregado final
  const paradasDeTrabalho = paradasDoCanal.filter(p => p !== 'revisao' && !p.endsWith('_revisao'));
  for (const p of paradasDeTrabalho) {
    das.push(...faltasDaParada(p, f));
  }
  // Os bloqueios que o servidor adjudicou entram como faltas da Revisão: eles
  // não pertencem a uma parada só, e escondê-los numa delas os tiraria da conta.
  for (const b of bloqueiosDoCockpit(f.cockpit)) {
    // Pegamos a parada de revisão da lista, se existir
    const revisao = paradasDoCanal.find(p => p === 'revisao' || p.endsWith('_revisao')) || 'revisao';
    das.push({ parada: revisao, texto: b.titulo.toLowerCase(), indeterminada: false });
  }
  return das;
}

/** O estado de cada parada, para o mapa. */
export function projetarParadas(
  f: FatosDaBancada,
  atual: ParadaDaBancada,
  paradasDoCanal: readonly ParadaDaBancada[] = PARADAS_SEARCH,
): ParadaProjetada[] {
  // ⚠️ Enquanto o cockpit não chegou, NADA é confirmado. Pintar verde sobre um
  // payload ausente é o defeito de origem desta tela: o trilho antigo passava
  // `origem` como literal `true` e ficava verde com o destino bloqueado.
  const lendo = f.cockpit === null;

  return paradasDoCanal.map((parada) => {
      const rotulo = ROTULO_DA_PARADA[parada];
      if (lendo) {
        return { parada, rotulo, estado: 'indeterminada' as EstadoDaParada, causa: 'lendo…' };
      }

      const faltas = faltasDaParada(parada, f);
      let estado: EstadoDaParada;
      let causa: string | null = null;

      if (parada === 'revisao' || parada.endsWith('_revisao')) {
        // ⚠️ A REVISÃO NUNCA É BLOQUEADA, e isso não é indulgência.
        //
        // Ela não tem falta própria: reflete o resto. E o trabalho dela é
        // JUSTAMENTE mostrar o que falta, quem bloqueou e qual é o próximo ato —
        // em menos de dez segundos. Torná-la inalcançável enquanto houvesse
        // pendência esconderia a única tela que responde "por que eu não posso
        // criar isto?", exatamente de quem precisa da resposta.
        //
        // Quem bloqueia é a AÇÃO dentro dela, que nasce desabilitada com as
        // faltas enumeradas ao lado. Parada alcançável, ato fechado.
        const anteriores = faltasDaBancada(f, paradasDoCanal);
        if (anteriores.length === 0) estado = 'confirmada';
        else {
          const soIndeterminadas = anteriores.every((x) => x.indeterminada);
          estado = soIndeterminadas ? 'indeterminada' : 'pendente';
          causa = anteriores[0].texto;
        }
      } else if (faltas.length === 0) {
        estado = 'confirmada';
      } else if (faltas.every((x) => x.indeterminada)) {
        estado = 'indeterminada';
        causa = faltas[0].texto;
      } else {
        estado = 'pendente';
        causa = faltas[0].texto;
      }

      // A parada em que o operador está sobrepõe `pendente` — mas nunca
      // `bloqueada` nem `indeterminada`: estar olhando para um bloqueio não o
      // resolve.
      if (parada === atual && (estado === 'pendente' || estado === 'confirmada')) {
        estado = 'atual';
      }
      return { parada, rotulo, estado, causa };
    });
}

/**
 * A primeira parada que ainda não está confirmada. É o destino do `?etapa=`
 * ausente.
 *
 * ⚠️ A PROJEÇÃO PRECISA VIR SEM VIÉS DE `atual`, e este era um defeito real.
 *
 * `projetarParadas` promove a parada em que o operador está para `atual`, o que
 * a torna diferente de `confirmada`. Se alguém projetar com `atual: 'destino'` e
 * perguntar aqui qual é a primeira não confirmada, a resposta é sempre
 * `'destino'` — mesmo com o destino resolvido. A entrada sem `?etapa` ficaria
 * presa na primeira parada para sempre.
 *
 * Por isso existe `SEM_PARADA_ATUAL`: uma projeção que não promove ninguém.
 */
export function primeiraNaoConfirmada(paradas: ParadaProjetada[]): ParadaDaBancada {
  const p = paradas.find((x) => x.estado !== 'confirmada' && x.estado !== 'atual');
  return p?.parada ?? paradas.at(-1)?.parada ?? 'revisao';
}

/**
 * O valor a passar em `projetarParadas` quando não se quer promover parada
 * nenhuma a `atual` — ver `primeiraNaoConfirmada`.
 */
export const SEM_PARADA_ATUAL = '__nenhuma__' as unknown as ParadaDaBancada;

/**
 * Se a parada pode ser aberta.
 *
 * ⚠️ HOJE, NO CANAL SEARCH, ISTO É SEMPRE VERDADEIRO — e o fato merece ser dito
 * em vez de escondido atrás de um ramo que nunca roda.
 *
 * `projetarParadas` não produz `bloqueada` para nenhuma das seis paradas, e a
 * decisão é deliberada: cada parada é o lugar onde se descobre POR QUE ela não
 * está pronta, e trancar a porta esconderia a explicação de quem precisa dela.
 * Quem bloqueia é sempre a AÇÃO — a aprovação do conjunto, a escrita da copy, a
 * prova —, com as faltas enumeradas ao lado.
 *
 * Os dois estados que fecham a porta continuam existindo no contrato porque têm
 * consumidor previsto e não hipotético:
 *
 * - `nao_se_aplica` nasce quando a Bancada atender canal que o manifesto declare
 *   sem aquela etapa (Performance Max não tem mesa de termos como Search tem);
 * - `bloqueada` nasce quando o manifesto do servidor declarar a etapa inoperável
 *   para o canal — que é diferente de "falta fazer" e de "não consegui ler".
 *
 * Enquanto só Search estiver implementado, este predicado é uma guarda que não
 * dispara. `MapaDeParadas` já sabe desenhar os dois estados, com teste próprio.
 */
export function paradaAlcancavel(p: ParadaProjetada): boolean {
  return p.estado !== 'bloqueada' && p.estado !== 'nao_se_aplica';
}
