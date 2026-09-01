/**
 * Os quatro portões de um canal — veredito, motivo e a quem pedir.
 *
 * ## A regra desta tela, em uma frase
 *
 * **Nada aparece verde sem evidência.** Um portão só ganha a marca de aberto
 * quando o SERVIDOR o declarou `PERMITIDO`; qualquer outro estado — inclusive
 * "não sei" — é desenhado como não-aberto, com o nome do estado escrito.
 *
 * ## Quatro estados, quatro desenhos — e nunca dois colapsados
 *
 *   PERMITIDO       aberto
 *   BLOQUEADO       fechado, com causa
 *   INDETERMINADO   não medido — tom PRÓPRIO, nunca o do fechado
 *   NAO_APLICAVEL   a pergunta não cabe
 *
 * ⚠️ `INDETERMINADO` desenhado como `BLOQUEADO` é o erro caro. As duas pedem
 * ações opostas — uma pede permissão, a outra pede uma leitura — e pintar
 * ignorância de vermelho ensina o operador a tratar todo vermelho como ruído.
 *
 * ## Cor é o terceiro sinal, nunca o primeiro
 *
 * Glifo, palavra e descrição vêm antes, como no resto do inventário. Um
 * operador com deuteranopia, um monitor mal calibrado e um print em preto e
 * branco precisam ler o mesmo fato.
 */
import React from 'react';
import {
  CircleCheck,
  CircleHelp,
  CircleSlash,
  Lock,
  MinusCircle,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import {
  A_QUEM_PEDIR,
  ORDEM_DOS_PORTOES,
  PERGUNTA_DO_PORTAO,
  ROTULO_DO_PORTAO,
  type BloqueadorDeCanal,
  type ContratoDeCanal,
  type EstadoDePortao,
  type PortaoDeCanal,
  portao,
  tomDoBloqueio,
} from '@/lib/trafego/canais';

/** Glifo, palavra e classe — nesta ordem de importância. */
const DESENHO: Record<
  EstadoDePortao,
  { Icone: React.ElementType; palavra: string; classe: string; borda: string }
> = {
  PERMITIDO: {
    Icone: CircleCheck,
    palavra: 'liberado',
    classe: 'text-emerald-700 dark:text-emerald-400',
    borda: 'border-emerald-300 dark:border-emerald-800',
  },
  BLOQUEADO: {
    Icone: Lock,
    palavra: 'bloqueado',
    classe: 'text-amber-700 dark:text-amber-400',
    borda: 'border-amber-300 dark:border-amber-800',
  },
  // ⚠️ Tom PRÓPRIO, e deliberadamente neutro. "Não sei" não é uma recusa.
  INDETERMINADO: {
    Icone: CircleHelp,
    palavra: 'não medido',
    classe: 'text-slate-600 dark:text-slate-400',
    borda: 'border-slate-300 dark:border-slate-700',
  },
  NAO_APLICAVEL: {
    Icone: MinusCircle,
    palavra: 'não se aplica',
    classe: 'text-slate-500 dark:text-slate-500',
    borda: 'border-dashed border-slate-300 dark:border-slate-700',
  },
};

/**
 * O tom de um bloqueio — que **não** é o tom do portão.
 *
 * ⚠️ "Não habilitado nesta versão" não é falha, não é ausência e não é zero. É
 * uma decisão registrada, e desenhá-la em vermelho de erro diria ao operador
 * que algo quebrou quando alguém apenas ainda não abriu uma porta.
 */
const TOM_DO_BLOQUEIO: Record<string, string> = {
  decidido: 'border-l-sky-400 dark:border-l-sky-600',
  permissao: 'border-l-amber-400 dark:border-l-amber-600',
  ausencia: 'border-l-slate-400 dark:border-l-slate-600',
  sem_prova: 'border-l-violet-400 dark:border-l-violet-600',
};

function Bloqueio({ b }: { b: BloqueadorDeCanal }) {
  return (
    <li
      className={cn(
        'border-l-2 pl-3 py-1 text-xs leading-relaxed',
        TOM_DO_BLOQUEIO[tomDoBloqueio(b.origem)] ?? TOM_DO_BLOQUEIO.ausencia,
      )}
    >
      <p className="text-slate-700 dark:text-slate-300">{b.causa}</p>
      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-500">
        {A_QUEM_PEDIR[b.origem]}
        {/* A data existe só para os bloqueios que vêm de uma LEITURA. Regra não
            tem data de observação: ela vale enquanto estiver escrita. */}
        {b.observado_em ? ` · observado em ${b.observado_em}` : ''}
      </p>
      {b.revalidacao ? (
        <p className="mt-0.5 text-[11px] italic text-slate-500 dark:text-slate-500">
          Como conferir de novo: {b.revalidacao}
        </p>
      ) : null}
      <code className="mt-1 block text-[10px] text-slate-400 dark:text-slate-600">
        {b.codigo}
      </code>
    </li>
  );
}

function Portao({ p }: { p: PortaoDeCanal }) {
  const d = DESENHO[p.estado] ?? DESENHO.INDETERMINADO;
  const { Icone } = d;
  return (
    <div className={cn('rounded-md border p-3', d.borda)}>
      <div className="flex items-start gap-2">
        <Icone className={cn('mt-0.5 h-4 w-4 shrink-0', d.classe)} aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
            {ROTULO_DO_PORTAO[p.nome]}
          </p>
          {/* A palavra vem antes da cor, e o estado cru vem junto: quem lê o
              contrato na API e quem lê a tela precisam ver o mesmo nome. */}
          <p className={cn('text-xs font-medium', d.classe)}>
            {d.palavra} <span className="font-normal opacity-70">({p.estado})</span>
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-500">
            {PERGUNTA_DO_PORTAO[p.nome]}
          </p>
        </div>
      </div>
      {p.bloqueadores.length > 0 ? (
        <ul className="mt-2 space-y-2">
          {p.bloqueadores.map((b) => (
            <Bloqueio key={`${p.nome}-${b.codigo}`} b={b} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Os quatro portões de um canal, sempre os quatro.
 *
 * ⚠️ Nenhum é escondido por estar fechado. Um portão ausente da tela seria
 * indistinguível de um portão que ninguém avaliou — e é justamente a diferença
 * entre esses dois que o contrato inteiro existe para carregar.
 */
export function PortoesDoCanal({ contrato }: { contrato: ContratoDeCanal }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {ORDEM_DOS_PORTOES.map((nome) => {
        const p = portao(contrato, nome);
        if (!p) {
          // O servidor não mandou este portão. Isso é ignorância, não recusa —
          // e dizê-lo é melhor que desenhar um portão inventado.
          return (
            <div
              key={nome}
              className="rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700"
            >
              <div className="flex items-start gap-2">
                <CircleSlash
                  className="mt-0.5 h-4 w-4 shrink-0 text-slate-400"
                  aria-hidden
                />
                <div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {ROTULO_DO_PORTAO[nome]}
                  </p>
                  <p className="text-xs text-slate-500">
                    o servidor não respondeu sobre este portão
                  </p>
                </div>
              </div>
            </div>
          );
        }
        return <Portao key={nome} p={p} />;
      })}
    </div>
  );
}

export default PortoesDoCanal;
