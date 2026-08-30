/**
 * A estrutura narrativa do build: hook e beats.
 *
 * ## Por que isto não é uma timeline
 *
 * SPEC §9.1: "O frontend dirige um contrato narrativo e inspeciona evidências.
 * Não oferece edição livre por frames." Reordenar beat ou renderizar cena
 * isolada só aparece quando o runtime suportar a operação com prova. Este build
 * foi OBSERVADO: o VOLC O.S. não o produziu e não pode reeditá-lo.
 *
 * ## Teclado, não arraste
 *
 * A lista é de botões. Cada beat abre e fecha por Enter ou Espaço, e a leitura
 * completa está no DOM sem depender de gesto. SPEC §17: "Storyboard funciona
 * por teclado e não depende de drag."
 */
import React from 'react';
import { ChevronDown } from 'lucide-react';

import { cn } from '@/lib/utils';
import { segundosLegiveis } from '@/components/criativos/comum/formato';
import type { BeatDeVideo, ContratoDeVideo } from '@/types/criativos';

const Linha: React.FC<{ rotulo: string; valor: string | null }> = ({ rotulo, valor }) => (
  <div className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)] gap-3 py-1">
    <dt className="text-[12px] text-muted-foreground">{rotulo}</dt>
    <dd className="text-[13px] leading-relaxed text-foreground">{valor ?? 'não registrado'}</dd>
  </div>
);

const Beat: React.FC<{ beat: BeatDeVideo }> = ({ beat }) => {
  const [aberto, setAberto] = React.useState(false);
  const idPainel = `beat-${beat.indice}-detalhe`;
  return (
    <li className="border-b border-border/70 last:border-b-0">
      <button
        type="button"
        aria-expanded={aberto}
        aria-controls={idPainel}
        onClick={() => setAberto((v) => !v)}
        className={cn(
          'flex w-full items-start gap-3 px-3 py-2.5 text-left',
          'transition-colors duration-150 ease-out hover:bg-muted/60',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
        )}
      >
        <span className="mt-0.5 shrink-0 font-display text-[11px] font-semibold tabular-nums text-muted-foreground">
          {String(beat.indice).padStart(2, '0')}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-medium text-foreground">
            {beat.papel ?? 'papel narrativo não registrado'}
          </span>
          <span className="mt-0.5 block truncate text-[12px] text-muted-foreground">
            {beat.copy ?? 'sem copy registrada'}
          </span>
        </span>
        <span className="shrink-0 text-[12px] tabular-nums text-muted-foreground">
          {segundosLegiveis(beat.duracaoS)}
        </span>
        <ChevronDown
          className={cn(
            'mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-150 ease-out motion-reduce:transition-none',
            aberto && 'rotate-180',
          )}
          aria-hidden
        />
      </button>
      {aberto && (
        <dl id={idPainel} className="px-3 pb-3 pl-11">
          <Linha rotulo="Copy" valor={beat.copy} />
          <Linha rotulo="Visual" valor={beat.visual} />
          <Linha rotulo="Asset" valor={beat.assetArquivo} />
          <Linha
            rotulo="Início"
            valor={beat.inicioS === null ? null : segundosLegiveis(beat.inicioS)}
          />
          <Linha
            rotulo="Duração"
            valor={
              beat.duracaoFrames === null
                ? segundosLegiveis(beat.duracaoS)
                : `${segundosLegiveis(beat.duracaoS)}, ${beat.duracaoFrames} frames`
            }
          />
        </dl>
      )}
    </li>
  );
};

export const Direcao: React.FC<{ contrato: ContratoDeVideo }> = ({ contrato }) => (
  <div className="space-y-4">
    <div>
      <p className="kicker">Hook</p>
      {contrato.hook ? (
        <dl className="mt-1">
          <Linha rotulo="Linha" valor={contrato.hook.linha} />
          <Linha rotulo="Tipo" valor={contrato.hook.tipo} />
          <Linha rotulo="Persona" valor={contrato.hook.persona} />
          <Linha rotulo="Cenário" valor={contrato.hook.cenario} />
          <Linha
            rotulo="Segundos"
            valor={contrato.hook.segundos === null ? null : segundosLegiveis(contrato.hook.segundos)}
          />
        </dl>
      ) : (
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
          Este build não registrou hook. Ausência de registro não é ausência de hook no vídeo.
        </p>
      )}
    </div>

    <div>
      <p className="kicker">Cenas</p>
      {contrato.beats.length ? (
        <ol className="mt-1 rounded-md border border-border">
          {contrato.beats.map((beat) => (
            <Beat key={beat.indice} beat={beat} />
          ))}
        </ol>
      ) : (
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
          O build não registrou beats. A lista vazia significa que ninguém gravou a estrutura, não
          que o vídeo não tem cenas.
        </p>
      )}
    </div>

    <div>
      <p className="kicker">Elementos de retenção</p>
      {contrato.elementosDeRetencao.length ? (
        <ul className="mt-1 list-inside list-disc space-y-0.5 text-[13px] leading-relaxed text-foreground">
          {contrato.elementosDeRetencao.map((el) => (
            <li key={el}>{el}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-[13px] text-muted-foreground">Nenhum elemento registrado.</p>
      )}
    </div>

    <div>
      <p className="kicker">Chamada final</p>
      <p className="mt-1 text-[13px] leading-relaxed text-foreground">
        {contrato.cta ?? 'não registrada'}
      </p>
    </div>
  </div>
);
