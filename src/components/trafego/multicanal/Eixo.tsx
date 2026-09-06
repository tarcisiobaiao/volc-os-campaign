/**
 * Um EIXO da visão multicanal — e as três ausências que ele não deixa colapsar.
 *
 * ## Por que ele existe, se `Fato.tsx` já é um par rótulo/valor
 *
 * `Fato` desenha um valor que pode ser desconhecido, e faz isso bem. O que ele
 * não faz é DISTINGUIR os motivos de não haver valor — ele recebe uma
 * `React.ReactNode` já pronta, e quem chama escreve `—` para todos os casos.
 *
 * Na visão multicanal isso deixa de ser aceitável, porque os três casos pedem
 * atos opostos do operador:
 *
 *   ausente        o canal NÃO TEM este fato. PMax não tem CPC, Demand Gen não
 *                  tem lance. Não há o que consertar, e um `—` cinza convida a
 *                  procurar a configuração que falta.
 *   nulo           o fato existe e a leitura devolveu VAZIO. Foi medido.
 *   desconhecido   ninguém leu. É uma pendência de leitura, não da conta.
 *
 * `design.md` chama isso pelo nome em "Truth Before Decoration": *"Absence,
 * failure, stale data and measured zero are different states"*. E `PRODUCT.md`
 * repete do lado do operador: *"declarar ausência, atraso ou falha de
 * evidência"*.
 *
 * ## A gramática
 *
 * Cada ausência tem GLIFO + PALAVRA + explicação — nunca só cor, nunca só um
 * travessão. A cor mora no glifo; a palavra é sempre `text-foreground`, pela
 * mesma razão de `ChipDeEstado`: escrever a palavra com a cor do estado torna
 * ilegível justamente o texto que decide.
 *
 * ## Movimento
 *
 * Nenhum. Um eixo é leitura, e `design.md` proíbe teatro de carga em superfície
 * de alta frequência.
 */
import React from 'react';
import { CircleHelp, CircleSlash, Minus } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * Como o valor deste eixo está ausente — quando está.
 *
 * ⚠️ `presente` é o quarto estado e ele é o normal. Ele existe no tipo para que
 * um eixo sem valor não possa ser construído sem escolher POR QUE não tem.
 */
export type Ausencia = 'presente' | 'ausente' | 'nulo' | 'desconhecido';

const GLIFO: Record<Exclude<Ausencia, 'presente'>, React.ComponentType<{ className?: string }>> = {
  // Um círculo cortado: "aqui não existe isso". Forma diferente do interrogativo.
  ausente: CircleSlash,
  // Um traço: "medido, e não há".
  nulo: Minus,
  // Interrogação: "ninguém olhou".
  desconhecido: CircleHelp,
};

const PALAVRA: Record<Exclude<Ausencia, 'presente'>, string> = {
  ausente: 'não se aplica',
  nulo: 'medido, e vazio',
  desconhecido: 'não lido',
};

const TINTA: Record<Exclude<Ausencia, 'presente'>, string> = {
  // Neutro: não é problema, é a forma do canal.
  ausente: 'text-muted-foreground',
  // Neutro também: zero medido é um fato, não um alerta.
  nulo: 'text-muted-foreground',
  // `info` — informa sem julgar. Ignorância não é erro, e pintá-la de vermelho
  // ensina o operador a ignorar o vermelho (`design.md`, vocabulário fechado).
  desconhecido: 'text-info',
};

export const Eixo: React.FC<{
  rotulo: string;
  /** O valor, quando há um. Ignorado se `ausencia !== 'presente'`. */
  valor?: React.ReactNode;
  ausencia?: Ausencia;
  /** Por que está ausente, ou o que o valor NÃO afirma. Sempre 14px. */
  ressalva?: string | null;
  /** De onde veio. Um número sem procedência não decide nada. */
  fonte?: string | null;
  className?: string;
}> = ({ rotulo, valor, ausencia = 'presente', ressalva, fonte, className }) => {
  const vazio = ausencia !== 'presente';
  const Glifo = vazio ? GLIFO[ausencia] : null;

  return (
    <div className={cn('min-w-0', className)}>
      <dt className="text-xs font-medium leading-5 text-muted-foreground">
        {rotulo}
      </dt>
      <dd className="flex min-w-0 items-baseline gap-1.5 text-sm font-medium text-foreground">
        {Glifo ? (
          <>
            <Glifo
              className={cn('h-3.5 w-3.5 shrink-0 self-center', TINTA[ausencia as Exclude<Ausencia, 'presente'>])}
              aria-hidden
            />
            {/* A palavra é o portador primário; o glifo é o segundo. Nunca só cor. */}
            <span className="min-w-0 break-words">{PALAVRA[ausencia as Exclude<Ausencia, 'presente'>]}</span>
          </>
        ) : (
          <span className="min-w-0 break-words">{valor}</span>
        )}
      </dd>
      {ressalva ? (
        <p className="mt-0.5 text-sm leading-snug text-muted-foreground text-pretty">
          {ressalva}
        </p>
      ) : null}
      {fonte ? (
        <p className="mt-0.5 text-xs text-muted-foreground">fonte: {fonte}</p>
      ) : null}
    </div>
  );
};

export default Eixo;
