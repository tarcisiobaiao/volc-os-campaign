/**
 * A receita do Laboratório: contrato, compilação e validação.
 *
 * Aqui não há React. É a única parte do Laboratório que decide alguma coisa, e
 * ela decide sobre dado do banco — exigência de canal, teto combinado, estado de
 * prova do modo. Um componente que fizesse essa conta na renderização tornaria a
 * regra invisível para o teste e impossível de reusar no backend depois.
 *
 * ## Três verbos, nesta ordem
 *
 * `compilar` transforma um rascunho de operador numa `RenderRecipe` — o objeto
 * que um motor executaria. `validar` confronta a receita com o que o canal exige.
 * `podeProduzirAgora` responde a única pergunta que autoriza um botão de gasto.
 *
 * ## O que NÃO acontece aqui
 *
 * Nada é salvo. `criativo_template` não existe no banco (é a v11_03, planejada e
 * não aplicada). Uma receita compilada nesta fatia vive na memória da aba e morre
 * com ela — e a tela diz isso, em vez de desenhar um botão "Salvar" que mente.
 */
import type {
  ExigenciaDeCanal,
  Finalidade,
  FormatoDoParque,
  ModoDeProducao,
  MotorRegistrado,
  Parque,
  Skin,
  TetoCombinado,
  Voz,
} from '@/types/parqueCriativo';
import { PROVA } from '@/types/parqueCriativo';

// ─────────────────────────────────────────────────────────────────────────────
// Contrato
// ─────────────────────────────────────────────────────────────────────────────

/** O que o operador escolheu. Tudo opcional: um rascunho incompleto é legítimo. */
export interface RascunhoDeReceita {
  nome: string;
  finalidadeSlug: string | null;
  canal: string | null;
  slots: string[];
  motorSlug: string | null;
  modoSlug: string | null;
  skinSlug: string | null;
  vozSlug: string | null;
  /** Segundos. `null` = não decidido, que é diferente de zero. */
  duracaoAlvoS: number | null;
  /**
   * Semente do render. Fixa de propósito.
   *
   * ⚠️ Não é enfeite. `@remotion/rough-notation` sorteia a forma do rabisco a
   * partir dela, e a fábrica renderiza com `--concurrency=8`. Com semente livre,
   * o mesmo grifo sai diferente em cada chunk do MESMO vídeo — defeito que passa
   * despercebido no preview e só aparece no arquivo final.
   */
  seed: number;
}

export const RASCUNHO_VAZIO: RascunhoDeReceita = {
  nome: '',
  finalidadeSlug: null,
  canal: null,
  slots: [],
  motorSlug: null,
  modoSlug: null,
  skinSlug: null,
  vozSlug: null,
  duracaoAlvoS: null,
  seed: 1,
};

/** Uma saída pedida, já resolvida contra o catálogo. */
export interface SaidaDaReceita {
  slot: string;
  rotulo: string;
  largura: number;
  altura: number;
  midia: string;
  tipoDeAsset: string;
  /** O executor deste ambiente produz este slot? Vem do servidor. */
  executavelAgora: boolean;
  motivoSeNao: string | null;
  /** O catálogo ainda oferece este formato? */
  ativo: boolean;
}

/** O objeto que um motor executaria. Derivado, nunca digitado à mão. */
export interface RenderRecipe {
  nome: string;
  finalidade: Finalidade | null;
  canal: string | null;
  motor: MotorRegistrado | null;
  modo: ModoDeProducao | null;
  skin: Skin | null;
  voz: Voz | null;
  saidas: SaidaDaReceita[];
  duracaoAlvoS: number | null;
  seed: number;
  /**
   * Slots que o operador escolheu e o catálogo não tem mais.
   *
   * ⚠️ S1. A compilação filtrava esses slots em silêncio: o custo caía, a lista
   * de saídas encolhia e nenhum achado aparecia. O React Query refaz a leitura a
   * cada 5 minutos; basta alguém aposentar um formato entre a escolha e a
   * compilação para a receita virar outra coisa sem avisar ninguém.
   */
  slotsPerdidos: string[];
  /**
   * Estimativa declarada com fonte, em dólares. `null` quando o motor não
   * declara custo — que é diferente de custo zero.
   */
  custoEstimadoUsd: number | null;
  custoFonte: string | null;
  /** De onde cada peça do catálogo veio. Procedência viaja com a receita. */
  procedencia: { campo: string; fonte: string }[];
}

export type GravidadeDoAchado = 'impede' | 'avisa';

export interface AchadoDeValidacao {
  gravidade: GravidadeDoAchado;
  /** Frase de operador. Nunca nome de coluna nem código de erro. */
  oQue: string;
  /** Onde conferir o número que gerou o achado. */
  fonte: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Compilar
// ─────────────────────────────────────────────────────────────────────────────

function achar<T extends { slug: string }>(lista: T[] | null, slug: string | null): T | null {
  if (!lista || !slug) return null;
  return lista.find((i) => i.slug === slug) ?? null;
}

export function compilar(rascunho: RascunhoDeReceita, parque: Parque): RenderRecipe {
  const motor = achar(parque.motores, rascunho.motorSlug);
  const modo = achar(parque.modos, rascunho.modoSlug);
  const skin = achar(parque.skins, rascunho.skinSlug);
  const voz = achar(parque.vozes, rascunho.vozSlug);
  const finalidade = achar(parque.finalidades, rascunho.finalidadeSlug);

  const porSlot = new Map((parque.formatos ?? []).map((f) => [f.slot, f]));
  const slotsPerdidos = rascunho.slots.filter((slot) => !porSlot.has(slot));
  const saidas: SaidaDaReceita[] = rascunho.slots
    .map((slot) => porSlot.get(slot))
    .filter((f): f is FormatoDoParque => Boolean(f))
    .map((f) => ({
      slot: f.slot,
      rotulo: f.rotulo,
      largura: f.largura,
      altura: f.altura,
      midia: f.midia,
      tipoDeAsset: f.tipoDeAsset,
      // `?? true` seria o erro clássico: um servidor antigo que não mande o
      // campo passaria a autorizar TODO slot. `=== true` faz o ausente valer
      // "não sei", e não saber não autoriza gasto.
      executavelAgora: f.executavelAgora === true,
      motivoSeNao: f.motivoSeNao ?? null,
      ativo: f.ativo,
    }));

  const procedencia: { campo: string; fonte: string }[] = [];
  if (motor) procedencia.push({ campo: 'motor', fonte: motor.fonte });
  if (modo) procedencia.push({ campo: 'modo', fonte: modo.fonte });
  if (skin) procedencia.push({ campo: 'skin', fonte: skin.fonte });
  if (voz) procedencia.push({ campo: 'voz', fonte: voz.fonte });
  for (const s of saidas) {
    const f = porSlot.get(s.slot);
    if (f) procedencia.push({ campo: `formato ${f.slot}`, fonte: f.fonte });
  }

  // ⚠️ `custo × quantidade` só quando o motor declara custo. `?? 0` aqui
  // transformaria "não sei quanto custa" em "é de graça", que é a mentira mais
  // fácil de cometer numa tela de estimativa.
  const custoEstimadoUsd =
    motor && motor.custoReferenciaUsd !== null && saidas.length > 0
      ? Number((motor.custoReferenciaUsd * saidas.length).toFixed(4))
      : null;

  return {
    nome: rascunho.nome.trim(),
    finalidade,
    canal: rascunho.canal,
    motor,
    modo,
    skin,
    voz,
    saidas,
    duracaoAlvoS: rascunho.duracaoAlvoS,
    seed: rascunho.seed,
    slotsPerdidos,
    custoEstimadoUsd,
    custoFonte: motor?.custoFonte ?? null,
    procedencia,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Validar
// ─────────────────────────────────────────────────────────────────────────────

function proporcaoDe(largura: number, altura: number): number {
  return largura / altura;
}

function alvoDe(texto: string | null): number | null {
  if (!texto) return null;
  const m = texto.match(/^(\d+(?:\.\d+)?)\s*[:x]\s*(\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const a = Number(m[1]);
  const b = Number(m[2]);
  return b === 0 ? null : a / b;
}

/**
 * Confronta a receita com o que o canal exige.
 *
 * ⚠️ Uma exigência marcada `provisorio` gera AVISO, nunca impedimento. O número
 * ainda não foi conferido contra a fonte oficial, e bloquear uma produção por um
 * número que nós mesmos marcamos como não conferido é transferir para o operador
 * a nossa incerteza.
 */
export function validar(receita: RenderRecipe, parque: Parque): AchadoDeValidacao[] {
  const achados: AchadoDeValidacao[] = [];

  if (!receita.nome) {
    achados.push({
      gravidade: 'impede',
      oQue: 'A receita precisa de um nome para poder ser encontrada depois.',
      fonte: null,
    });
  }
  if (!receita.finalidade) {
    achados.push({
      gravidade: 'impede',
      oQue: 'Escolha a finalidade: mídia paga e orgânico têm obrigações diferentes.',
      fonte: null,
    });
  }
  if (!receita.motor) {
    achados.push({ gravidade: 'impede', oQue: 'Escolha o motor de produção.', fonte: null });
  }
  if (receita.saidas.length === 0) {
    achados.push({ gravidade: 'impede', oQue: 'Escolha ao menos um formato.', fonte: null });
  }

  // ── o catálogo mudou debaixo da escolha? ─────────────────────────────────
  for (const slot of receita.slotsPerdidos) {
    achados.push({
      gravidade: 'impede',
      oQue: `O formato "${slot}" foi escolhido e não está mais no catálogo. A receita mudou desde a escolha.`,
      fonte: null,
    });
  }

  // ── o formato é executável neste ambiente? ───────────────────────────────
  // ⚠️ Este é o furo que a auditoria adversarial achou, e ele era o pior tipo:
  // a rota `GET /parque` foi escrita com um comentário dizendo que apontar
  // `/formatos` para o banco faria "a tela oferecer um formato que o motor
  // recusa depois do clique" — e o Laboratório era essa tela. Ele listava os 7
  // slots do banco, o executor conhece 4, e o selo dizia "Nada impede".
  for (const saida of receita.saidas.filter((s) => !s.executavelAgora)) {
    achados.push({
      gravidade: 'impede',
      oQue:
        saida.motivoSeNao ??
        `O executor deste ambiente não sabe produzir "${saida.rotulo}".`,
      fonte: null,
    });
  }

  // ── o catálogo ainda oferece o que foi escolhido? ────────────────────────
  // A tela filtra por `ativo`; a regra não filtrava. Bastava o operador
  // escolher e alguém desativar no banco entre a escolha e o refetch para a
  // receita seguir compilando, somando custo e estampando verde.
  for (const saida of receita.saidas.filter((s) => !s.ativo)) {
    achados.push({
      gravidade: 'impede',
      oQue: `O formato "${saida.rotulo}" saiu do catálogo e não pode mais ser pedido.`,
      fonte: null,
    });
  }
  if (receita.motor && !receita.motor.ativo) {
    achados.push({
      gravidade: 'impede',
      oQue: `O motor "${receita.motor.nome}" foi desativado no catálogo.`,
      fonte: receita.motor.fonte,
    });
  }
  if (receita.finalidade && !receita.finalidade.ativo) {
    achados.push({
      gravidade: 'impede',
      oQue: `A finalidade "${receita.finalidade.nome}" foi desativada no catálogo.`,
      fonte: null,
    });
  }

  // ── o modo produz aqui? ──────────────────────────────────────────────────
  if (receita.modo) {
    const prova = PROVA[receita.modo.estadoDeProva];
    if (!prova) {
      // ⚠️ Falhar ABERTO aqui era o defeito: `if (prova && !prova.podeProduzir)`
      // deixava passar um `estado_de_prova` que esta versão não conhece. A tela
      // desabilitava a opção (`!p?.podeProduzir` vira `true`) e a regra
      // liberava — as duas pontas leem a mesma coluna e discordavam, e quem
      // discordava a favor do gasto era a regra.
      achados.push({
        gravidade: 'impede',
        oQue: `O modo "${receita.modo.nome}" está num estado que esta versão da tela não conhece. Não dá para afirmar que ele produz.`,
        fonte: receita.modo.fonte,
      });
    } else if (!prova.podeProduzir) {
      achados.push({
        gravidade: 'impede',
        oQue: `${receita.modo.nome}: ${prova.explicacao}`,
        fonte: receita.modo.prova ?? receita.modo.fonte,
      });
    }
  }

  // ── o motor produz a mídia pedida? ───────────────────────────────────────
  if (receita.motor) {
    for (const midia of new Set(receita.saidas.map((s) => s.midia))) {
      if (!receita.motor.produz.includes(midia)) {
        achados.push({
          gravidade: 'impede',
          oQue: `${receita.motor.nome} não produz ${midia}.`,
          fonte: receita.motor.fonte,
        });
      }
    }
  }

  // ── a finalidade combina com o canal? ────────────────────────────────────
  // Dos três defeitos de negócio caros, este era o que a fatia deixava aberto:
  // finalidade `organica` com canal de mídia paga passava sem UM aviso, enquanto
  // a tela imprimia "mídia paga e orgânico têm obrigações diferentes".
  if (receita.canal && receita.finalidade) {
    const classe = receita.finalidade.classe;
    const canalDePaga = (parque.exigenciasDeCanal ?? []).some(
      (e) => e.canal === receita.canal,
    );
    if (canalDePaga && classe === 'organica') {
      achados.push({
        gravidade: 'impede',
        oQue: `"${receita.finalidade.nome}" é uma finalidade orgânica e ${receita.canal} é canal de mídia paga. Entregar peça orgânica como anúncio muda obrigação de aviso e de direito de uso.`,
        fonte: null,
      });
    }
  }

  if (!receita.canal) return achados;

  // ── exigências do canal ──────────────────────────────────────────────────
  const doCanal = (parque.exigenciasDeCanal ?? []).filter((e) => e.canal === receita.canal);
  if (doCanal.length === 0) {
    achados.push({
      gravidade: 'avisa',
      oQue: `Não há exigência registrada para ${receita.canal}. A peça não foi conferida contra as regras desse canal.`,
      fonte: null,
    });
    return achados;
  }

  for (const saida of receita.saidas) {
    const exigencias = doCanal.filter((e) => e.tipoDeAsset === saida.tipoDeAsset);
    if (exigencias.length === 0) {
      achados.push({
        gravidade: 'avisa',
        oQue: `${receita.canal} não declara exigência para "${saida.rotulo}". Não dá para dizer que serve nem que não serve.`,
        fonte: null,
      });
      continue;
    }
    for (const e of exigencias) {
      achados.push(...conferirUma(saida, e));
    }
  }

  achados.push(...conferirTetos(receita, parque.tetosCombinados ?? []));
  return achados;
}

function conferirUma(saida: SaidaDaReceita, e: ExigenciaDeCanal): AchadoDeValidacao[] {
  const achados: AchadoDeValidacao[] = [];
  const gravidade: GravidadeDoAchado = e.provisorio ? 'avisa' : 'impede';
  const fonte = e.provisorio
    ? `${e.fonteDosNumeros} (número ainda não conferido)`
    : e.fonteDosNumeros;

  const alvo = alvoDe(e.proporcaoAlvo);
  if (e.proporcaoAlvo && alvo === null) {
    // ⚠️ `proporcao_alvo` é `text` livre no banco, sem CHECK de forma. Um valor
    // como "1,91:1" (vírgula) ou "vertical" desligava a conferência EM SILÊNCIO,
    // e a ausência de leitura virava aprovação — o padrão que este projeto
    // combate em todos os outros campos.
    achados.push({
      gravidade: 'avisa',
      oQue: `${saida.rotulo}: a proporção exigida por ${e.canal} está escrita como "${e.proporcaoAlvo}", que esta versão não sabe interpretar. A proporção NÃO foi conferida.`,
      fonte,
    });
  }
  if (alvo !== null) {
    const real = proporcaoDe(saida.largura, saida.altura);
    if (Math.abs(real - alvo) > e.toleranciaProporcao) {
      achados.push({
        gravidade,
        oQue: `${saida.rotulo} (${saida.largura}×${saida.altura}) não bate a proporção ${e.proporcaoAlvo} que ${e.canal} exige.`,
        fonte,
      });
    }
  }
  // `null` é "sem piso declarado", não "piso zero" — por isso o teste é explícito.
  if (e.larguraMinima !== null && saida.largura < e.larguraMinima) {
    achados.push({
      gravidade,
      oQue: `${saida.rotulo} tem ${saida.largura}px de largura e ${e.canal} exige pelo menos ${e.larguraMinima}px.`,
      fonte,
    });
  }
  if (e.alturaMinima !== null && saida.altura < e.alturaMinima) {
    achados.push({
      gravidade,
      oQue: `${saida.rotulo} tem ${saida.altura}px de altura e ${e.canal} exige pelo menos ${e.alturaMinima}px.`,
      fonte,
    });
  }
  return achados;
}

function conferirTetos(receita: RenderRecipe, tetos: TetoCombinado[]): AchadoDeValidacao[] {
  const achados: AchadoDeValidacao[] = [];
  for (const teto of tetos.filter((t) => t.canal === receita.canal)) {
    const quantos = receita.saidas.filter((s) => teto.tipos.includes(s.tipoDeAsset)).length;
    if (quantos < teto.minimo) {
      achados.push({
        gravidade: 'impede',
        oQue: `${teto.rotulo}: ${receita.canal} pede no mínimo ${teto.minimo} e a receita tem ${quantos}.`,
        fonte: teto.fonte,
      });
    }
    if (teto.maximo !== null && quantos > teto.maximo) {
      achados.push({
        gravidade: 'impede',
        oQue: `${teto.rotulo}: ${receita.canal} aceita no máximo ${teto.maximo} e a receita tem ${quantos}.`,
        fonte: teto.fonte,
      });
    }
  }
  return achados;
}

/**
 * A única pergunta que autoriza um botão de gasto.
 *
 * ⚠️ Aviso não bloqueia. Se bloqueasse, todo número marcado `provisorio` viraria
 * uma parede, e o operador aprenderia a ignorar a diferença entre os dois — que é
 * justamente a informação que o aviso carrega.
 */
export function podeProduzirAgora(achados: AchadoDeValidacao[]): boolean {
  return !achados.some((a) => a.gravidade === 'impede');
}

/**
 * Quantas exigências do canal são provisórias, e quantas são firmes.
 *
 * ⚠️ Medido em produção em 28/08/2026: **as 18 linhas de
 * `criativo_exigencia_de_canal` estão com `provisorio = true`**. Como provisório
 * gera aviso e não impedimento, nenhuma regra de proporção ou de dimensão mínima
 * consegue barrar nada hoje. A validação está correta no código e vazia no dado.
 *
 * Isso precisa aparecer na tela. Um painel que diz "Nada impede" sem dizer que
 * nenhuma exigência do canal foi conferida convida o operador a ler ausência de
 * bloqueio como aprovação.
 */
export function firmezaDoCanal(
  parque: Parque,
  canal: string | null,
): { firmes: number; provisorias: number } {
  const doCanal = (parque.exigenciasDeCanal ?? []).filter((e) => e.canal === canal);
  return {
    firmes: doCanal.filter((e) => !e.provisorio).length,
    provisorias: doCanal.filter((e) => e.provisorio).length,
  };
}

/** Canais que aparecem no seletor: os que o banco de fato declara exigência. */
export function canaisConhecidos(parque: Parque): string[] {
  const canais = new Set<string>();
  for (const e of parque.exigenciasDeCanal ?? []) canais.add(e.canal);
  for (const t of parque.tetosCombinados ?? []) canais.add(t.canal);
  return [...canais].sort();
}
