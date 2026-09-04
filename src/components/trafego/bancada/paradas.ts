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
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';

export const ROTULO_DA_PARADA: Record<ParadaDaBancada, string> = {
  destino: 'Destino',
  politica: 'Política',
  termos: 'Termos',
  anuncio: 'Anúncio',
  economia: 'Economia',
  revisao: 'Revisão',
};

/** A pergunta que a parada responde. É o H2 da coluna de decisão. */
export const PERGUNTA_DA_PARADA: Record<ParadaDaBancada, string> = {
  destino: 'Para onde este anúncio manda o clique?',
  politica: 'Esta vertical pode anunciar neste país?',
  termos: 'Quais termos a campanha vai comprar?',
  anuncio: 'O que o anúncio vai dizer?',
  economia: 'Quanto isto pode gastar por dia?',
  revisao: 'É isto que você quer criar?',
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
export function politicaBarra(v: VerticalDePolitica | null | undefined): boolean {
  return v?.severidade === 'bloqueio' || v?.severidade === 'limitacao';
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
        if (f.destino.sem_recibo) add('avaliar o destino desta campanha', true);
        for (const p of f.destino.pendencias) {
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
      else if (politicaBarra(v)) add(v.exige ? `cumprir: ${v.exige}` : 'liberar o portão desta vertical');
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
    case 'revisao':
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
export function faltasDaBancada(f: FatosDaBancada): FaltaDaParada[] {
  const das: FaltaDaParada[] = [];
  for (const p of ['destino', 'politica', 'termos', 'anuncio', 'economia'] as ParadaDaBancada[]) {
    das.push(...faltasDaParada(p, f));
  }
  // Os bloqueios que o servidor adjudicou entram como faltas da Revisão: eles
  // não pertencem a uma parada só, e escondê-los numa delas os tiraria da conta.
  for (const b of bloqueiosDoCockpit(f.cockpit)) {
    das.push({ parada: 'revisao', texto: b.titulo.toLowerCase(), indeterminada: false });
  }
  return das;
}

/** O estado de cada parada, para o mapa. */
export function projetarParadas(
  f: FatosDaBancada, atual: ParadaDaBancada,
): ParadaProjetada[] {
  // ⚠️ Enquanto o cockpit não chegou, NADA é confirmado. Pintar verde sobre um
  // payload ausente é o defeito de origem desta tela: o trilho antigo passava
  // `origem` como literal `true` e ficava verde com o destino bloqueado.
  const lendo = f.cockpit === null;

  return (['destino', 'politica', 'termos', 'anuncio', 'economia', 'revisao'] as ParadaDaBancada[])
    .map((parada) => {
      const rotulo = ROTULO_DA_PARADA[parada];
      if (lendo) {
        return { parada, rotulo, estado: 'indeterminada' as EstadoDaParada, causa: 'lendo…' };
      }

      const faltas = faltasDaParada(parada, f);
      let estado: EstadoDaParada;
      let causa: string | null = null;

      if (parada === 'revisao') {
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
        const anteriores = faltasDaBancada(f);
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
 */
export function primeiraNaoConfirmada(paradas: ParadaProjetada[]): ParadaDaBancada {
  const p = paradas.find((x) => x.estado !== 'confirmada');
  return p?.parada ?? 'revisao';
}

/** Se a parada pode ser aberta. Bloqueada não é alcançável; o resto é. */
export function paradaAlcancavel(p: ParadaProjetada): boolean {
  return p.estado !== 'bloqueada' && p.estado !== 'nao_se_aplica';
}
