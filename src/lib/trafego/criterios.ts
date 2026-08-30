/**
 * A regra dos critérios de keyword — fora de qualquer componente React.
 *
 * ## Por que isto não mora na tela
 *
 * "A negativa X bloqueia a keyword Y?" é uma pergunta de negócio com resposta
 * exata, definida pela semântica de correspondência da Google Ads API. Se ela
 * morasse dentro de um `.tsx`, existiriam duas implementações da mesma regra —
 * esta e a de `volc_ads/campanha/criterio.py` — e elas divergiriam no primeiro
 * ajuste, com a tela afirmando uma coisa e o payload fazendo outra.
 *
 * Mora aqui, testável sem montar componente, e o teste compara com os mesmos
 * casos que a prova em Python usa.
 *
 * ## O que a tela ganha com isso
 *
 * O operador vê o conflito ANTES de gastar os ~120 s de `validate_only`. E vê
 * o alcance real da negativa que escreveu: `BROAD` parece inofensivo e não é.
 */
import type {
  CriterioDeKeyword,
  MatchType,
  NivelCriterio,
  OrigemCriterio,
} from '@/types/trafego';

/**
 * Minúscula, espaço colapsado — e ACENTO PRESERVADO. Espelha `criterio.chave`
 * do Python, inclusive na decisão sobre acento.
 *
 * `"curso  gratis"` e `"curso gratis"` são a mesma keyword: deduplicar sem
 * colapsar espaço manda duas operações para o mesmo critério, e a API recusa a
 * segunda — num envio atômico, derruba a campanha inteira.
 *
 * ⚠️ `"grátis"` e `"gratis"`, ao contrário, continuam DIFERENTES. Assimetria de
 * custo: se o Google as tratar como iguais, mandar as duas custa uma operação
 * redundante que ele aceita; se as tratar como diferentes — e a doutrina de
 * negativa é que ela não expande para variantes próximas —, deduplicá-las apaga
 * um bloqueio que o operador declarou. Mandar as duas nunca é pior.
 */
export function chave(texto: string): string {
  return texto.normalize('NFC').toLowerCase().trim().split(/\s+/).join(' ');
}

function tokens(texto: string): string[] {
  const k = chave(texto);
  return k ? k.split(' ') : [];
}

/**
 * Esta NEGATIVA bloquearia a consulta?
 *
 * Semântica real da API, que NÃO é a das keywords positivas:
 *
 *   EXACT   só a consulta idêntica.
 *   PHRASE  os tokens na ordem, contíguos, em qualquer lugar da consulta.
 *   BROAD   todos os tokens, em qualquer ordem, não necessariamente juntos.
 *
 * ⚠️ Negativa não expande para variantes próximas — plural, erro de digitação e
 * sinônimo passam. É por isso que uma negativa BROAD parece inofensiva e não é:
 * ela não expande, mas "todos os tokens em qualquer ordem" já pega muito mais
 * do que quem a escreveu costuma imaginar.
 */
export function bloqueia(negativa: CriterioDeKeyword, consulta: string): boolean {
  if (!negativa.negativa) return false;
  const meus = tokens(negativa.texto);
  const alvo = tokens(consulta);
  if (meus.length === 0 || alvo.length === 0) return false;

  if (negativa.match_type === 'EXACT') {
    return meus.length === alvo.length && meus.every((t, i) => t === alvo[i]);
  }
  if (negativa.match_type === 'BROAD') {
    return meus.every((t) => alvo.includes(t));
  }
  // PHRASE — subsequência contígua na ordem declarada.
  for (let i = 0; i + meus.length <= alvo.length; i += 1) {
    if (meus.every((t, j) => t === alvo[i + j])) return true;
  }
  return false;
}

/** O que torna dois critérios a MESMA operação para a API.
 *
 *  Inclui o match type de propósito: `"curso"` EXACT e `"curso"` PHRASE são
 *  critérios diferentes e legítimos no mesmo ad group. */
export function identidade(c: CriterioDeKeyword): string {
  return [chave(c.texto), c.match_type, c.negativa, c.nivel, c.grupo ?? ''].join('\u0000');
}

/**
 * Uma negativa que ANULA uma positiva declarada no mesmo pedido.
 *
 * ⚠️ Só o caso PROVÁVEL entra aqui: a negativa bloqueia o texto da positiva tal
 * como declarado, então aquela keyword não pode servir NENHUMA consulta — nasce
 * morta, e o dinheiro do grupo vai todo para as outras sem que o relatório
 * explique por quê.
 *
 * O caso "a negativa apenas ESTREITA o tráfego da positiva" foi deliberadamente
 * deixado de fora: decidir isso exigiria enumerar o espaço de consultas que uma
 * keyword PHRASE ou BROAD alcança, que é aberto. Marcar por semelhança de
 * palavras produziria alarme onde não há defeito — e alarme falso treina o
 * operador a ignorar a faixa inteira, inclusive quando ela estiver certa.
 */
export interface Conflito {
  negativa: CriterioDeKeyword;
  positiva: CriterioDeKeyword;
}

/** Toda negativa que bloqueia uma positiva que ela ALCANÇA.
 *
 *  O escopo importa: negativa do grupo `VALOR` não conflita com keyword do
 *  grupo `ACESSO`, porque não chega nela. Negativa de campanha, e negativa de
 *  ad group sem grupo declarado, alcançam todas. */
export function conflitos(criterios: CriterioDeKeyword[]): Conflito[] {
  const positivas = criterios.filter((c) => !c.negativa);
  const negativas = criterios.filter((c) => c.negativa);
  const saida: Conflito[] = [];
  for (const n of negativas) {
    for (const p of positivas) {
      if (
        n.nivel === 'AD_GROUP' &&
        n.grupo != null &&
        p.grupo != null &&
        chave(n.grupo) !== chave(p.grupo)
      ) {
        continue;
      }
      if (bloqueia(n, p.texto)) {
        saida.push({ negativa: n, positiva: p });
      }
    }
  }
  return saida;
}

export interface Duplicata {
  perdedor: CriterioDeKeyword;
  dono: CriterioDeKeyword;
}

/** Remove critérios com a mesma identidade, preservando a ORDEM de entrada.
 *
 *  O primeiro declarado vence — determinístico de propósito. Ordenar por
 *  "qualidade" faria o payload mudar entre duas execuções com a mesma entrada,
 *  e o selo deixaria de significar alguma coisa. */
export function deduplicar(criterios: CriterioDeKeyword[]): {
  unicos: CriterioDeKeyword[];
  descartados: Duplicata[];
} {
  const vistos = new Map<string, CriterioDeKeyword>();
  const unicos: CriterioDeKeyword[] = [];
  const descartados: Duplicata[] = [];
  for (const c of criterios) {
    const id = identidade(c);
    const dono = vistos.get(id);
    if (dono) {
      descartados.push({ perdedor: c, dono });
      continue;
    }
    vistos.set(id, c);
    unicos.push(c);
  }
  return { unicos, descartados };
}

/** Um critério tem número de conta atrás dele, ou é hipótese? */
export function medido(c: CriterioDeKeyword): boolean {
  return c.evidencia != null && c.evidencia.tipo === 'MEDIDO';
}

/** O alcance da negativa, em português, para quem nunca leu a doc da API.
 *
 *  Não é decoração: é a informação que falta para o operador entender que
 *  `BROAD` num termo de duas palavras bloqueia muito mais do que ele pensa. */
export function explicarAlcance(c: CriterioDeKeyword): string {
  const n = tokens(c.texto).length;
  if (!c.negativa) {
    switch (c.match_type) {
      case 'EXACT':
        return 'ativa só na busca exata por este termo';
      case 'PHRASE':
        return 'ativa quando a busca contém esta expressão na ordem';
      default:
        return 'ativa em buscas relacionadas — precisa de lance automático';
    }
  }
  switch (c.match_type) {
    case 'EXACT':
      return 'exclui só a busca idêntica a este termo';
    case 'PHRASE':
      return 'exclui toda busca que contenha esta expressão na ordem';
    default:
      return n > 1
        ? `exclui toda busca que contenha as ${n} palavras, em qualquer ordem`
        : 'exclui toda busca que contenha esta palavra';
  }
}

/**
 * ⚠️ A porta de criação força `conjunto_unico=True` — doutrina P7, decidida em
 * `backend/app/routers/trafego.py` e documentada em `docs/SPEC-ARBITRAGEM.md`:
 * campanha = rei, um termo, uma campanha, UM conjunto. As sub-intenções
 * continuam sendo a lente da triagem, mas não viram ad groups separados.
 *
 * A consequência para esta tela é direta: a campanha nasce com **um** ad group.
 * Oferecer "em qual grupo esta exclusão vale" seria oferecer uma distinção sem
 * diferença — as duas respostas produziriam o mesmo payload.
 *
 * O que NÃO colapsa é o NÍVEL: campanha e ad group continuam sendo recursos
 * diferentes da API (`CampaignCriterion` × `AdGroupCriterion`), com alcances
 * diferentes no dia em que a campanha tiver mais de um grupo. Por isso a
 * escolha de nível continua na tela e a de grupo, não.
 *
 * Esta constante existe para que a tela não invente uma topologia que o backend
 * não vai montar. No dia em que P7 for revista, ela muda AQUI e o seletor de
 * grupo volta — o engine já sabe fazer negativa por grupo, e há teste provando.
 */
export const NASCE_COM_UM_CONJUNTO = true;

/** Onde a exclusão vale, em português. */
export function explicarEscopo(c: CriterioDeKeyword): string {
  if (c.nivel === 'CAMPAIGN') return 'na campanha inteira';
  if (c.grupo) return `só no grupo ${c.grupo}`;
  // Com um conjunto só, "em todos os grupos" seria tecnicamente verdadeiro e
  // enganoso: sugere uma escolha que a campanha não tem.
  return NASCE_COM_UM_CONJUNTO ? 'no grupo de anúncios' : 'em todos os grupos';
}

export const MATCH_TYPES: MatchType[] = ['EXACT', 'PHRASE', 'BROAD'];

/** O rótulo curto que a tela mostra. O operador não precisa saber o nome do
 *  enum da API para escolher o alcance de uma palavra. */
export const ROTULO_DE_MATCH: Record<MatchType, string> = {
  EXACT: 'Exata',
  PHRASE: 'Frase',
  BROAD: 'Ampla',
};

export const ROTULO_DE_NIVEL: Record<NivelCriterio, string> = {
  CAMPAIGN: 'Campanha',
  AD_GROUP: 'Grupo',
};

export const ROTULO_DE_ORIGEM: Record<OrigemCriterio, string> = {
  MANUAL: 'digitada por você',
  PAUTADOR: 'da mineração',
  SITE: 'lida do site',
  SEARCH_TERM: 'observada na conta',
  LEGADO: 'de um pedido antigo',
};

/** Um critério novo, com os defaults da casa e nenhum campo inventado.
 *
 *  `motivo`, `evidencia` e `aprovado_por` nascem `null` — ausência é ausência.
 *  PHRASE é o default porque é o alcance que o operador quase sempre quer numa
 *  negativa, e porque BROAD é o mais largo dos três. */
export function novoCriterio(
  texto: string,
  troca: Partial<CriterioDeKeyword> = {},
): CriterioDeKeyword {
  return {
    texto: texto.trim(),
    match_type: 'PHRASE',
    negativa: true,
    nivel: 'AD_GROUP',
    grupo: null,
    origem: 'MANUAL',
    motivo: null,
    evidencia: null,
    observado_em: null,
    aprovado_por: null,
    ...troca,
  };
}

export interface ResumoDaRevisao {
  ativam: number;
  excluidasNaCampanha: number;
  excluidasNoGrupo: number;
  conflitos: Conflito[];
  duplicatas: Duplicata[];
  /** Negativas sem evidência medida. Não é erro — é o que a tela precisa
   *  mostrar como hipótese em vez de deixar parecer fato. */
  hipoteses: number;
}

export function resumir(criterios: CriterioDeKeyword[]): ResumoDaRevisao {
  const { descartados } = deduplicar(criterios);
  const negativas = criterios.filter((c) => c.negativa);
  return {
    ativam: criterios.filter((c) => !c.negativa).length,
    excluidasNaCampanha: negativas.filter((c) => c.nivel === 'CAMPAIGN').length,
    excluidasNoGrupo: negativas.filter((c) => c.nivel === 'AD_GROUP').length,
    conflitos: conflitos(criterios),
    duplicatas: descartados,
    hipoteses: negativas.filter((c) => !medido(c)).length,
  };
}
