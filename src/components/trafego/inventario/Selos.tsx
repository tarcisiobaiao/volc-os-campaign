/**
 * Os selos do inventário: presença, procedência, vínculo, estado e frescor.
 *
 * ## A regra que todos obedecem: glifo + palavra + descrição
 *
 * Nenhum estado desta tela é comunicado por cor. Um operador com deuteranopia,
 * um monitor mal calibrado e um print em preto e branco precisam ler o mesmo
 * fato — então a cor é o terceiro sinal, nunca o primeiro. O glifo dá a forma,
 * a palavra dá o nome, e a descrição diz o que aquele nome AFIRMA.
 *
 * A descrição não é enfeite: `não encontrada` e `sincronização falhou` parecem
 * vizinhas e são opostas — uma afirma que a conta respondeu, a outra que ela
 * não respondeu. Sem a frase, as duas viram "sumiu", que é a conclusão que
 * este módulo inteiro existe para não tirar.
 */
import React from 'react';
import {
  Ban,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleHelp,
  CircleOff,
  CirclePause,
  CircleSlash,
  Clock,
  Inbox,
  Link2,
  Link2Off,
  TriangleAlert,
  WifiOff,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  ContaNoInventario,
  EstadoDePresenca,
  Frescor,
  Procedencia,
  VinculoDeFunil,
} from '@/types/trafego';

import {
  DESCRICAO_DO_ESTADO_EXTERNO,
  frescorLegivel,
  horaDeLeitura,
  idade,
  lidoHa,
  presencaLegivel,
  procedenciaLegivel,
} from './formato';

/**
 * ⚠️ `verificado` NÃO é `bom`, e não é `info`.
 *
 * O `DESIGN.md` separa os três em uma frase: `verified` significa que a fonte
 * foi OBSERVADA ou reconciliada, e "does not mean success"; `success` é um
 * estado saudável concluído; `info` é aviso neutro. O produto vinha pintando
 * "eu vi isto na conta" com a mesma tinta de "isto está bem", e as duas levam a
 * decisões diferentes: a primeira convida a conferir, a segunda a seguir.
 *
 * O token `--verified` nasceu no V0 e ficou sem consumidor. Ele entra
 * AQUI e só aqui — nos dois lugares em que "observado" é a afirmação verdadeira
 * — e não por substituição das 112 ocorrências de `info`, que em protótipo e
 * laboratório significam outra coisa.
 */
export type Tom = 'neutro' | 'bom' | 'verificado' | 'atencao' | 'ruim' | 'info';

/**
 * ⚠️ A cor semântica fica na BORDA, no fundo e no glifo — nunca na palavra.
 *
 * `--warning` no claro é laranja a 48% de luminosidade: contra o branco do
 * cartão dá ~2,2:1, e a palavra tem 11 px. Colorir o texto com a cor do estado
 * é o jeito mais comum de tornar ilegível justamente o rótulo que precisa ser
 * lido. A palavra usa a tinta do texto normal; o estado continua distinguível
 * pelo glifo e pela própria palavra, que é o que a regra exige.
 */
const TINTA: Record<Tom, string> = {
  neutro: 'border-border/70 text-muted-foreground',
  bom: 'border-success/40 bg-success/[0.08] text-foreground',
  verificado: 'border-verified/45 bg-verified/[0.08] text-foreground',
  atencao: 'border-warning/50 bg-warning/[0.10] text-foreground',
  ruim: 'border-destructive/45 bg-destructive/[0.08] text-foreground',
  info: 'border-info/40 bg-info/[0.08] text-foreground',
};

const TINTA_DO_GLIFO: Record<Tom, string> = {
  neutro: 'text-muted-foreground',
  bom: 'text-success',
  verificado: 'text-verified',
  atencao: 'text-warning',
  ruim: 'text-destructive',
  info: 'text-info',
};

export const Chip: React.FC<{
  glifo: React.ComponentType<{ className?: string }>;
  palavra: string;
  /** O que a palavra afirma. Vai para leitor de tela e para o `title`. */
  descricao: string;
  tom?: Tom;
  className?: string;
}> = ({ glifo: Glifo, palavra, descricao, tom = 'neutro', className }) => (
  <span
    className={cn(
      'inline-flex max-w-full items-center gap-1 rounded-sm border px-1.5 py-0.5',
      'font-display text-[0.6875rem] font-semibold uppercase leading-none tracking-[0.08em]',
      TINTA[tom],
      className,
    )}
    title={`${palavra} — ${descricao}`}
  >
    <Glifo className={cn('h-3 w-3 shrink-0', TINTA_DO_GLIFO[tom])} aria-hidden />
    <span className="truncate">{palavra}</span>
    <span className="sr-only"> — {descricao}</span>
  </span>
);

// ── presença ────────────────────────────────────────────────────────────────

const GLIFO_DA_PRESENCA: Record<
  string,
  { glifo: React.ComponentType<{ className?: string }>; tom: Tom }
> = {
  presente: { glifo: CircleCheck, tom: 'neutro' },
  removida: { glifo: CircleSlash, tom: 'neutro' },
  nao_encontrada: { glifo: CircleOff, tom: 'atencao' },
  conta_nao_identificada: { glifo: CircleHelp, tom: 'atencao' },
  fora_de_escopo: { glifo: Ban, tom: 'neutro' },
  sincronizacao_falhou: { glifo: WifiOff, tom: 'ruim' },
  legado_nao_reconciliado: { glifo: CircleDashed, tom: 'atencao' },
};

export const SeloDePresenca: React.FC<{ presenca: EstadoDePresenca }> = ({ presenca }) => {
  // Lookup tolerante de propósito: o servidor já emite um sétimo valor que a
  // união de tipos ainda não tem, e uma tela que quebra ao encontrar palavra
  // desconhecida é pior que uma tela que diz não reconhecer a palavra.
  const visual = GLIFO_DA_PRESENCA[presenca] ?? { glifo: CircleHelp, tom: 'atencao' as Tom };
  const { palavra, descricao } = presencaLegivel(presenca);
  return <Chip glifo={visual.glifo} palavra={palavra} descricao={descricao} tom={visual.tom} />;
};

// ── procedência ─────────────────────────────────────────────────────────────

const GLIFO_DA_PROCEDENCIA: Record<
  Procedencia,
  { glifo: React.ComponentType<{ className?: string }>; tom: Tom }
> = {
  volc_os: { glifo: CircleCheck, tom: 'bom' },
  // Observada na conta pela varredura — é o caso exemplar de `verificado`.
  descoberta: { glifo: CircleDot, tom: 'verificado' },
  legado: { glifo: CircleDashed, tom: 'neutro' },
  desconhecida: { glifo: CircleAlert, tom: 'atencao' },
};

/**
 * Consulta de mapa que NÃO quebra a tela.
 *
 * Os mapas são `Record<UniãoFechada, …>` e o TypeScript garante a completude —
 * em tempo de compilação. Em tempo de execução o valor vem do servidor, e o
 * servidor pode ganhar um estado novo antes deste bundle ser publicado. O
 * acesso direto devolveria `undefined`, a desestruturação lançaria, e o
 * inventário INTEIRO sumiria por causa de uma palavra desconhecida numa linha.
 *
 * Uma tela de conferência que apaga tudo quando encontra algo que não conhece é
 * pior que uma que mostra "estado desconhecido": a primeira esconde as outras
 * quarenta campanhas que estavam certas.
 */
function doMapa<T>(mapa: Record<string, T>, chave: string, reserva: T): T {
  return mapa[chave] ?? reserva;
}

export const SeloDeProcedencia: React.FC<{ procedencia: Procedencia }> = ({ procedencia }) => {
  const { glifo, tom } = doMapa(GLIFO_DA_PROCEDENCIA, procedencia,
    { glifo: CircleAlert, tom: 'atencao' as const });
  // A palavra vem da função tolerante e NÃO do valor cru: exibir `foo_bar` como
  // se fosse o rótulo faria a tela falar a língua da máquina justamente no caso
  // em que ela não entendeu nada.
  const { palavra, descricao } = procedenciaLegivel(procedencia);
  return <Chip glifo={glifo} palavra={palavra} descricao={descricao} tom={tom} />;
};

// ── vínculo com o funil ─────────────────────────────────────────────────────

export const SeloDeVinculo: React.FC<{ vinculo: VinculoDeFunil | null }> = ({ vinculo }) => {
  // Vínculo sem confirmação humana não existe (é a regra do domínio), então a
  // tela não pode exibir um palpite do sincronizador como se fosse vínculo.
  const confirmado = Boolean(vinculo?.opportunity_id && vinculo?.confirmado_por);
  if (!confirmado) {
    return (
      <Chip
        glifo={Link2Off}
        palavra="sem vínculo"
        descricao="nenhum funil confirmado por uma pessoa para esta campanha"
        tom="atencao"
      />
    );
  }
  const quando = horaDeLeitura(vinculo?.confirmado_em);
  return (
    <Chip
      glifo={Link2}
      palavra={`funil ${vinculo?.opportunity_id}`}
      descricao={`confirmado por ${vinculo?.confirmado_por}${quando ? ` em ${quando}` : ''}`}
      tom="bom"
    />
  );
};

// ── estado do lado do Google ────────────────────────────────────────────────

const GLIFO_DO_ESTADO_EXTERNO: Record<
  string,
  { glifo: React.ComponentType<{ className?: string }>; tom: Tom }
> = {
  ENABLED: { glifo: CircleDot, tom: 'bom' },
  PAUSED: { glifo: CirclePause, tom: 'neutro' },
  REMOVED: { glifo: CircleSlash, tom: 'neutro' },
};

export const SeloDeEstadoExterno: React.FC<{ estado: string | null }> = ({ estado }) => {
  if (!estado) {
    return (
      <Chip
        glifo={CircleHelp}
        palavra="estado não lido"
        descricao="a conta não informou o estado desta campanha nesta leitura"
        tom="atencao"
      />
    );
  }
  const visual = GLIFO_DO_ESTADO_EXTERNO[estado];
  if (!visual) {
    // ⚠️ O valor cru NÃO vira a palavra do selo.
    //
    // `ENABLED`, `PAUSED` e `REMOVED` ficam em inglês de propósito: são as três
    // palavras que o operador lê no painel do Google, e traduzi-las criaria dois
    // nomes para o mesmo fato. Isso vale para as TRÊS — não para o que vier
    // depois delas. O vocabulário da conta de anúncio inclui coisas como
    // `UNSPECIFIED` e `UNKNOWN`, e imprimir uma dessas como se fosse o estado da
    // campanha põe vocabulário de máquina exatamente onde o operador procura a
    // resposta — e ainda por cima uma que ele não vai encontrar no painel do
    // Google para conferir. O valor continua dito, na descrição, que é onde o
    // resto deste módulo põe aquilo que não reconhece.
    return (
      <Chip
        glifo={CircleHelp}
        palavra="estado não reconhecido"
        descricao={`a conta de anúncio informou "${estado}", que esta versão da tela não conhece`}
        tom="atencao"
      />
    );
  }
  return (
    <Chip
      glifo={visual.glifo}
      palavra={estado}
      // A palavra fica em inglês porque é a palavra que o operador lê no painel
      // do Google; traduzir criaria dois nomes para o mesmo fato.
      descricao={DESCRICAO_DO_ESTADO_EXTERNO[estado] ?? 'estado declarado pela conta de anúncio'}
      tom={visual.tom}
    />
  );
};

// ── frescor ─────────────────────────────────────────────────────────────────

const GLIFO_DO_FRESCOR: Record<
  Frescor,
  { glifo: React.ComponentType<{ className?: string }>; tom: Tom }
> = {
  recente: { glifo: Clock, tom: 'neutro' },
  velho: { glifo: Clock, tom: 'atencao' },
  parcial: { glifo: TriangleAlert, tom: 'atencao' },
  falhou: { glifo: WifiOff, tom: 'ruim' },
  nunca_lido: { glifo: CircleHelp, tom: 'atencao' },
  vazio_confirmado: { glifo: Inbox, tom: 'neutro' },
};

/**
 * O selo de frescor de uma conta, com a frase de operação inteira.
 *
 * ⚠️ `nunca lido` e `nenhuma campanha` são fatos DIFERENTES e o selo não os
 * achata: "não perguntei" leva a pedir leitura, "perguntei e não há nada" leva
 * a não fazer nada. Achatar os dois em "vazio" produz a ação errada metade das
 * vezes.
 */
export const SeloDeFrescor: React.FC<{
  frescor: Frescor;
  leitura: ContaNoInventario['leitura'];
  ultimaLeituraBoa?: ContaNoInventario['ultima_leitura_boa'];
  className?: string;
}> = ({ frescor, leitura, ultimaLeituraBoa, className }) => {
  const { glifo, tom } = doMapa(GLIFO_DO_FRESCOR, frescor,
    { glifo: CircleAlert, tom: 'atencao' as const });
  const { palavra, descricao } = frescorLegivel(frescor);

  // ⚠️ `lidoHa` e não um `if` que devolve `null`.
  //
  // Antes, conta sem data de leitura simplesmente não ganhava complemento: o
  // selo dizia "leitura antiga" e nada mais, e a ausência da idade lia-se como
  // "está tudo dito". A regra do módulo é a oposta — número sem frescor não
  // aparece, e frescor que não se conhece é DECLARADO. `lidoHa(null)` responde
  // "sem data de leitura", que é o fato.
  const quando = lidoHa(leitura?.idade_s ?? null);
  const boa = ultimaLeituraBoa ? `última leitura boa ${idade(ultimaLeituraBoa.idade_s)}` : null;

  // Em `falhou` a frase útil não é a tentativa, é o último dado bom: é ele que
  // está na tela, e esconder a idade dele deixaria o operador decidir gasto
  // achando que olha para agora.
  const complemento =
    frescor === 'falhou'
      ? (boa ?? 'sem leitura boa anterior')
      : frescor === 'nunca_lido'
        ? null
        : quando;

  return (
    <span className={cn('inline-flex flex-wrap items-center gap-x-2 gap-y-1', className)}>
      <Chip glifo={glifo} palavra={palavra} descricao={descricao} tom={tom} />
      {complemento && (
        <span className="text-[11px] text-muted-foreground">{complemento}</span>
      )}
    </span>
  );
};

/**
 * Re-exportado para quem escreve a EVIDÊNCIA em texto em vez de chip.
 *
 * `LinhaDeCampanha` deixou de empilhar selos de procedência e vínculo e passou
 * a escrever uma frase (DESIGN.md: "Do not repeat piles of tags when a single
 * evidence sentence is clearer"). A frase precisa da mesma tradução tolerante
 * que o selo usava — duas traduções do mesmo vocabulário divergiriam no dia em
 * que o servidor emitisse um valor novo.
 */
export { procedenciaLegivel };
