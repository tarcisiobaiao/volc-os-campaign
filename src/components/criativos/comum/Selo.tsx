/**
 * O selo do Estúdio: glifo, palavra e descrição. Cor é o terceiro sinal.
 *
 * ## Por que não importa o `Chip` do inventário de Tráfego
 *
 * Porque o Estúdio não pertence ao Google Ads. `types/criativos.ts` já explica
 * a razão do contrato separado, e a razão vale igual para o vocabulário visual:
 * importar de `components/trafego/` faria o primeiro destino do patrimônio
 * virar dono do formato, e o segundo destino chegaria pedindo para desfazer.
 * O DESENHO é o mesmo de propósito, para o operador ler a mesma língua nas duas
 * áreas; a dependência é que não existe.
 *
 * ⚠️ A cor semântica fica na borda, no fundo e no glifo, NUNCA na palavra:
 * `--warning` no tema claro contra a superfície dá contraste insuficiente para
 * texto de 11px, e colorir a palavra é o jeito mais comum de tornar ilegível
 * justamente o rótulo que precisa ser lido.
 *
 * ⚠️ Nenhum tom usa `aurora-blue`, `aurora-purple` ou `aurora-orange`. A aurora
 * é assinatura de marca; um estado operacional pintado de aurora faz a marca
 * virar cor de alerta.
 */
import React from 'react';
import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleOff,
  CircleSlash,
  Clock,
  Eye,
  Loader,
  PauseCircle,
  PencilLine,
  TriangleAlert,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  DecisaoDeAprovacao,
  EstadoDaRendition,
  EstadoDoJob,
  ProcedenciaDeExecucao,
  RotuloDeEstado,
  TomDeEstado,
} from '@/types/criativos';
import {
  ROTULO_DA_APROVACAO,
  ROTULO_DA_RENDITION,
  ROTULO_DO_JOB,
} from '@/types/criativos';

type Glifo = React.ComponentType<{ className?: string }>;

const TINTA: Record<TomDeEstado, string> = {
  neutro: 'border-border/70 text-foreground',
  ativo: 'border-primary/45 bg-primary/[0.08] text-foreground',
  sucesso: 'border-success/45 bg-success/[0.08] text-foreground',
  atencao: 'border-warning/55 bg-warning/[0.10] text-foreground',
  erro: 'border-destructive/50 bg-destructive/[0.08] text-foreground',
};

const TINTA_DO_GLIFO: Record<TomDeEstado, string> = {
  neutro: 'text-muted-foreground',
  ativo: 'text-primary',
  sucesso: 'text-success',
  atencao: 'text-warning',
  erro: 'text-destructive',
};

export const Selo: React.FC<{
  glifo: Glifo;
  palavra: string;
  /** O que a palavra afirma. Vai para o leitor de tela e para o `title`. */
  descricao: string;
  tom?: TomDeEstado;
  className?: string;
}> = ({ glifo: G, palavra, descricao, tom = 'neutro', className }) => (
  <span
    className={cn(
      'inline-flex max-w-full items-center gap-1.5 rounded-sm border px-1.5 py-0.5',
      'font-display text-[0.6875rem] font-semibold uppercase leading-none tracking-[0.08em]',
      TINTA[tom],
      className,
    )}
    title={`${palavra}. ${descricao}`}
  >
    <G className={cn('h-3 w-3 shrink-0', TINTA_DO_GLIFO[tom])} aria-hidden />
    <span className="truncate">{palavra}</span>
    <span className="sr-only">. {descricao}</span>
  </span>
);

// ── job ─────────────────────────────────────────────────────────────────────

const GLIFO_DO_JOB: Record<EstadoDoJob, Glifo> = {
  draft: PencilLine,
  queued: Clock,
  running: Loader,
  partial: TriangleAlert,
  succeeded: CircleCheck,
  failed: CircleOff,
  cancelled: CircleSlash,
};

/** Consulta tolerante: valor novo do servidor não pode apagar a tela inteira. */
function doMapa<T>(mapa: Record<string, T>, chave: string, reserva: T): T {
  return mapa[chave] ?? reserva;
}

const DESCONHECIDO: RotuloDeEstado = {
  palavra: 'Estado não reconhecido',
  descricao: 'O servidor informou um estado que esta versão da tela não conhece.',
  tom: 'atencao',
};

export const SeloDoJob: React.FC<{ estado: EstadoDoJob; className?: string }> = ({
  estado,
  className,
}) => {
  const rotulo = doMapa(ROTULO_DO_JOB as Record<string, RotuloDeEstado>, estado, DESCONHECIDO);
  const glifo = doMapa(GLIFO_DO_JOB as Record<string, Glifo>, estado, CircleAlert);
  return (
    <Selo
      glifo={glifo}
      palavra={rotulo.palavra}
      descricao={rotulo.descricao}
      tom={rotulo.tom}
      className={className}
    />
  );
};

const GLIFO_DA_RENDITION: Record<EstadoDaRendition, Glifo> = {
  pendente: CircleDashed,
  gerando: Loader,
  pronta: CircleCheck,
  falhou: CircleOff,
  cancelada: CircleSlash,
};

export const SeloDaPeca: React.FC<{ estado: EstadoDaRendition; className?: string }> = ({
  estado,
  className,
}) => {
  const rotulo = doMapa(
    ROTULO_DA_RENDITION as Record<string, RotuloDeEstado>,
    estado,
    DESCONHECIDO,
  );
  const glifo = doMapa(GLIFO_DA_RENDITION as Record<string, Glifo>, estado, CircleAlert);
  return (
    <Selo
      glifo={glifo}
      palavra={rotulo.palavra}
      descricao={rotulo.descricao}
      tom={rotulo.tom}
      className={className}
    />
  );
};

const GLIFO_DA_APROVACAO: Record<DecisaoDeAprovacao, Glifo> = {
  aprovado: CircleCheck,
  ajuste_solicitado: TriangleAlert,
  rejeitado: CircleOff,
};

/**
 * `null` NÃO é "reprovado". É "ninguém decidiu ainda", que é o estado em que a
 * maioria dos ativos passa a maior parte do tempo.
 */
export const SeloDaAprovacao: React.FC<{
  decisao: DecisaoDeAprovacao | null;
  className?: string;
}> = ({ decisao, className }) => {
  if (!decisao) {
    return (
      <Selo
        glifo={Eye}
        palavra="Aguardando revisão"
        descricao="Nenhuma decisão foi registrada para esta versão."
        tom="neutro"
        className={className}
      />
    );
  }
  const rotulo = doMapa(
    ROTULO_DA_APROVACAO as Record<string, RotuloDeEstado>,
    decisao,
    DESCONHECIDO,
  );
  const glifo = doMapa(GLIFO_DA_APROVACAO as Record<string, Glifo>, decisao, CircleAlert);
  return (
    <Selo
      glifo={glifo}
      palavra={rotulo.palavra}
      descricao={rotulo.descricao}
      tom={rotulo.tom}
      className={className}
    />
  );
};

/**
 * Quem executou.
 *
 * ⚠️ `observado` não é sucesso e não é falha: é o VOLC O.S. declarando que LEU
 * um build que já existia. Este é o selo mais importante desta área, porque é a
 * mentira mais fácil de cometer nesta fatia.
 *
 * ⚠️⚠️ `null` é um TERCEIRO valor, e não um sinônimo de `volc_os`.
 * `AssetMaster.procedenciaExecucao` é `ProcedenciaDeExecucao | null`, e o
 * comentário do contrato diz por quê: `null` significa **não apurada** — o
 * servidor não leu o job desta peça. A versão anterior deste componente
 * ramificava `=== 'observado' ? A : B`, então o `null` caía no `else` e o selo
 * afirmava "Produzido aqui" para um ativo cuja autoria ninguém verificou
 * (defeito D1 da auditoria P17). Com `strict: false` no `tsconfig.app.json` o
 * compilador não reclama de `null` numa prop não-nula, então a guarda tem de
 * ser esta, em runtime.
 *
 * O tom é `atencao` porque ausência de procedência num patrimônio criativo é
 * uma pendência, não um estado neutro de operação: publicar sem saber quem
 * produziu é exatamente o risco que a coluna existe para conter.
 */
export const SeloDeProcedencia: React.FC<{
  procedencia: ProcedenciaDeExecucao | null;
  className?: string;
}> = ({ procedencia, className }) => {
  if (!procedencia) {
    return (
      <Selo
        glifo={CircleDashed}
        palavra="Procedência não apurada"
        descricao="O servidor não informou quem executou este trabalho. Isso não é o mesmo que dizer que o VOLC O.S. o produziu."
        tom="atencao"
        className={className}
      />
    );
  }
  return procedencia === 'observado' ? (
    <Selo
      glifo={CircleDot}
      palavra="Observado"
      descricao="O VOLC O.S. leu um build produzido por uma fábrica externa. Ele não renderizou esta peça."
      tom="neutro"
      className={className}
    />
  ) : (
    <Selo
      glifo={CircleCheck}
      palavra="Produzido aqui"
      descricao="O motor do VOLC O.S. executou este trabalho."
      tom="neutro"
      className={className}
    />
  );
};

/**
 * O veredito do gate em palavra de operação.
 *
 * `PASS`, `WARN` e `FAIL` são vocabulário do build, não do painel de um
 * terceiro que o operador consulta em paralelo. Não há dois nomes para o mesmo
 * fato a preservar aqui, então a palavra vai em português e o código cru fica
 * na descrição, para quem for cruzar com o log da fábrica.
 */
const GLIFO_DO_GATE: Record<
  string,
  { glifo: Glifo; tom: TomDeEstado; palavra: string; descricao: string }
> = {
  PASS: {
    glifo: CircleCheck,
    tom: 'sucesso',
    palavra: 'Passou',
    descricao: 'O gate passou. Registrado pelo build como PASS.',
  },
  WARN: {
    glifo: TriangleAlert,
    tom: 'atencao',
    palavra: 'Ressalva',
    descricao: 'O gate passou com ressalva. Registrado pelo build como WARN.',
  },
  FAIL: {
    glifo: CircleOff,
    tom: 'erro',
    palavra: 'Reprovou',
    descricao: 'O gate reprovou. Registrado pelo build como FAIL.',
  },
  SKIPPED: {
    glifo: PauseCircle,
    tom: 'neutro',
    palavra: 'Pulado',
    descricao: 'O gate não foi executado neste build. Registrado como SKIPPED.',
  },
};

/**
 * `null` é "este QA não rodou neste build", que não é aprovação e não é
 * reprovação. SPEC §10: "validação ausente" não é "não serve".
 */
export const SeloDeGate: React.FC<{ resultado: string | null; className?: string }> = ({
  resultado,
  className,
}) => {
  if (!resultado) {
    return (
      <Selo
        glifo={CircleDashed}
        palavra="Não executado"
        descricao="Este gate não rodou neste build. Ausência de validação não é reprovação."
        tom="neutro"
        className={className}
      />
    );
  }
  const visual = GLIFO_DO_GATE[resultado] ?? {
    glifo: CircleAlert,
    tom: 'atencao' as TomDeEstado,
    palavra: 'Resultado não reconhecido',
    descricao: `O build informou "${resultado}", que esta versão da tela não conhece.`,
  };
  return (
    <Selo
      glifo={visual.glifo}
      palavra={visual.palavra}
      descricao={visual.descricao}
      tom={visual.tom}
      className={className}
    />
  );
};
