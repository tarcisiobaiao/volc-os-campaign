/**
 * A criação orientada por intenção — o trilho da conversa.
 *
 * Uma etapa de cada vez, com as respostas já dadas visíveis acima e as
 * perguntas seguintes visíveis abaixo. Não é um acordeão de dezenas de campos:
 * quem lança campanha uma vez por semana precisa ver onde está no caminho, e
 * um formulário longo esconde justamente isso.
 *
 * ⚠️ Este componente não envia nada. As etapas de prova, criação e ativação são
 * apresentadas com a dependência real que as segura; nenhuma delas dispara
 * chamada privilegiada a partir do browser.
 */
import React from 'react';
import { Check, CircleDashed, CircleDot, Lock, Minus } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { EstadoDaEtapa, EtapaDaCriacao, PassoDaCriacao } from '@/types/diagnostico';

import { PERGUNTA, ROTULO_DA_ETAPA, progressoDaConversa } from './conversa';

type Glifo = React.ComponentType<{ className?: string }>;

const VISUAL: Record<EstadoDaEtapa, { glifo: Glifo; nome: string }> = {
  respondida: { glifo: Check, nome: 'respondida' },
  atual: { glifo: CircleDot, nome: 'etapa atual' },
  pendente: { glifo: CircleDashed, nome: 'ainda não perguntada' },
  bloqueada: { glifo: Lock, nome: 'bloqueada' },
  nao_se_aplica: { glifo: Minus, nome: 'não se aplica a este canal' },
};

export interface ConversaDeCriacaoProps {
  passos: PassoDaCriacao[];
  /** Chamado ao escolher uma etapa já respondida para revisar. */
  aoAbrir?: (etapa: EtapaDaCriacao) => void;
  className?: string;
}

export const ConversaDeCriacao: React.FC<ConversaDeCriacaoProps> = ({
  passos,
  aoAbrir,
  className,
}) => {
  const progresso = progressoDaConversa(passos);
  const atual = passos.find((p) => p.estado === 'atual') ?? null;
  const primeiraBloqueada = passos.find((p) => p.estado === 'bloqueada') ?? null;

  /**
   * A dependência que segura TODAS as etapas bloqueadas, quando é uma só.
   *
   * ⚠️ Medido ao ver este componente montado pela primeira vez: um canal sem
   * construtor devolve treze etapas bloqueadas pela MESMA frase, e a lista
   * repetia a frase treze vezes. Não é redundância decorativa — são treze
   * parágrafos idênticos empurrando para fora da tela a única informação nova
   * de cada linha, que é o nome da etapa.
   *
   * Quando a causa é uma só, ela é dita UMA vez, no lugar em que o olho já
   * está. Quando as causas diferem — que é o caso interessante —, cada linha
   * volta a carregar a sua, porque aí a diferença é a informação.
   */
  const bloqueadas = passos.filter((p) => p.estado === 'bloqueada');
  const causas = new Set(bloqueadas.map((p) => p.dependencia?.dependencia ?? ''));
  const dependenciaUnica =
    bloqueadas.length > 1 && causas.size === 1
      ? (primeiraBloqueada?.dependencia?.dependencia ?? null)
      : null;

  return (
    <section aria-labelledby="conversa-titulo" className={cn('max-w-[78ch]', className)}>
      <p className="kicker">nova campanha</p>
      <h2
        id="conversa-titulo"
        className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
      >
        {atual ? PERGUNTA[atual.etapa] : 'Nada a perguntar agora'}
      </h2>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
        {atual
          ? `etapa ${progresso.respondidas + 1} de ${progresso.aplicaveis}`
          : primeiraBloqueada
            ? primeiraBloqueada.dependencia?.dependencia
            : 'todas as etapas aplicáveis foram respondidas.'}
      </p>

      {dependenciaUnica && !atual && (
        <p className="mt-2 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">
            As {bloqueadas.length} etapas abaixo estão fechadas pelo mesmo motivo.
          </span>{' '}
          Elas continuam na lista porque o caminho é este — o que falta é a
          autorização, não uma etapa.
        </p>
      )}

      <ol className="mt-5 border-t border-border" role="list">
        {passos.map((p, i) => (
          <Passo
            key={p.etapa}
            passo={p}
            posicao={i + 1}
            aoAbrir={aoAbrir}
            omitirDependencia={dependenciaUnica != null}
          />
        ))}
      </ol>

      <p className="mt-4 max-w-[70ch] text-[11px] leading-relaxed text-muted-foreground">
        Criar e ligar são duas decisões. A criação sai pausada: a campanha existe
        na conta, não entra em leilão e não gasta. Ligar é a etapa seguinte, e é
        ela que faz a conta do cliente começar a ser cobrada.
      </p>
    </section>
  );
};

const Passo: React.FC<{
  passo: PassoDaCriacao;
  posicao: number;
  aoAbrir?: (etapa: EtapaDaCriacao) => void;
  /** A causa já foi dita uma vez acima, para todas. Ver o ⚠️ do cabeçalho. */
  omitirDependencia?: boolean;
}> = ({ passo, posicao, aoAbrir, omitirDependencia = false }) => {
  const visual = VISUAL[passo.estado] ?? VISUAL.pendente;
  const Glifo = visual.glifo;
  const clicavel = aoAbrir != null && (passo.estado === 'respondida' || passo.estado === 'atual');
  const rotulo = ROTULO_DA_ETAPA[passo.etapa] ?? passo.etapa;

  const miolo = (
    <>
      <span className="tabular mt-0.5 w-4 shrink-0 text-[11px] text-muted-foreground">
        {posicao}
      </span>
      <Glifo
        className={cn(
          'mt-0.5 h-4 w-4 shrink-0',
          passo.estado === 'respondida' ? 'text-success' : 'text-muted-foreground',
        )}
        aria-hidden
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span
            className={cn(
              'font-display text-[13px]',
              passo.estado === 'atual' ? 'font-semibold' : 'font-medium',
              passo.estado === 'nao_se_aplica' && 'text-muted-foreground line-through',
            )}
          >
            {rotulo}
          </span>
          <span className="text-[11px] text-muted-foreground">{visual.nome}</span>
        </span>
        {passo.resposta && (
          <span className="mt-0.5 block text-[12px] leading-relaxed">{passo.resposta}</span>
        )}
        {passo.estado === 'atual' && !passo.resposta && (
          <span className="mt-0.5 block text-[12px] leading-relaxed text-muted-foreground">
            {passo.pergunta}
          </span>
        )}
        {passo.estado === 'bloqueada' && passo.dependencia && !omitirDependencia && (
          <span className="mt-0.5 block max-w-[64ch] text-[12px] leading-relaxed text-muted-foreground">
            {passo.dependencia.dependencia}
          </span>
        )}
        {passo.estado === 'nao_se_aplica' && (
          <span className="mt-0.5 block text-[12px] leading-relaxed text-muted-foreground">
            este canal não pede esta resposta — não é uma etapa pulada, é uma
            pergunta que não existe aqui.
          </span>
        )}
      </span>
    </>
  );

  return (
    <li
      className={cn(
        'border-b border-border',
        passo.estado === 'nao_se_aplica' && 'opacity-70',
      )}
      aria-current={passo.estado === 'atual' ? 'step' : undefined}
    >
      {clicavel ? (
        <button
          type="button"
          onClick={() => aoAbrir?.(passo.etapa)}
          className={cn(
            'flex w-full min-h-11 items-start gap-3 px-1 py-3 text-left',
            'transition-colors duration-150 hover:bg-muted/40',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
          )}
        >
          {miolo}
        </button>
      ) : (
        <div className="flex min-h-11 items-start gap-3 px-1 py-3">{miolo}</div>
      )}
    </li>
  );
};

export default ConversaDeCriacao;
