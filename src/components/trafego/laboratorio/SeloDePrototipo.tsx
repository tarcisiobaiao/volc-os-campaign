/**
 * A marca do que é simulado — e a regra de que número simulado não soma.
 *
 * ## Por que um selo não basta, e mesmo assim é obrigatório
 *
 * O risco do Modo Laboratório não é o operador ver uma tela que ainda não
 * existe. É ele **decidir** com um número que ninguém mediu. Um selo bonito no
 * canto não impede isso sozinho — o que impede é a fixture nunca entrar no
 * mesmo total que o dado real, e disso quem cuida é quem soma.
 *
 * O selo existe para o outro caso: o operador que abre a tela sem contexto,
 * tira um print e manda no grupo. Sem a marca dentro da própria superfície, a
 * captura vira "o sistema já faz isso".
 *
 * ## A palavra é PROTÓTIPO, sempre a mesma
 *
 * ⚠️ Nunca "demo", "exemplo", "preview" nem "beta". Quatro palavras para o
 * mesmo fato ensinam que nenhuma delas quer dizer nada de específico — e a que
 * o operador aprender a ignorar é a que estiver na tela no dia em que importar.
 *
 * `PROTÓTIPO` afirma uma coisa só: **isto não é a sua conta.**
 */
import React from 'react';
import { FlaskConical, Info } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Chip } from '@/components/trafego/inventario/Selos';

export interface SeloDePrototipoProps {
  /**
   * De onde saiu o que está na tela. Obrigatório, e não tem padrão: uma
   * fixture sem procedência declarada é indistinguível de dado real que
   * ninguém carimbou.
   */
  fonte: string;
  className?: string;
}

export const SeloDePrototipo: React.FC<SeloDePrototipoProps> = ({ fonte, className }) => (
  <Chip
    glifo={FlaskConical}
    palavra="protótipo"
    descricao={`nada aqui vem da sua conta — ${fonte}`}
    tom="info"
    className={className}
  />
);

export interface MolduraDePrototipoProps {
  fonte: string;
  /** O que esta superfície ainda NÃO faz. Ausência declarada é conteúdo. */
  aindaNao?: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * Envolve uma superfície simulada inteira, e diz o que ela não faz.
 *
 * A borda tracejada é redundante com o selo de propósito: quem chega pela
 * captura de tela vê a moldura antes de ler qualquer palavra, e quem navega vê
 * o selo. Duas leituras do mesmo fato, porque o custo de errar é o operador
 * decidir gasto com número inventado.
 */
export const MolduraDePrototipo: React.FC<MolduraDePrototipoProps> = ({
  fonte,
  aindaNao,
  children,
  className,
}) => (
  <section
    aria-label="módulo em protótipo"
    className={cn(
      'rounded-md border border-dashed border-info/50 bg-info/[0.03] p-4',
      className,
    )}
  >
    <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <SeloDePrototipo fonte={fonte} />
      <p className="text-[11px] leading-snug text-muted-foreground">
        Desenho navegável, com dados de exemplo fixos. Nenhum número daqui entra
        em total nenhum, e nenhum botão daqui fala com o Google.
      </p>
    </header>

    <div className="mt-4">{children}</div>

    {aindaNao && (
      <p className="mt-4 flex max-w-[70ch] gap-2 border-t border-info/25 pt-3 text-[11px] leading-relaxed text-muted-foreground">
        <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
        <span>
          <span className="font-medium text-foreground">O que ainda não existe: </span>
          {aindaNao}
        </span>
      </p>
    )}
  </section>
);

/**
 * A faixa que diz, uma vez por página, que o laboratório está ligado.
 *
 * ⚠️ Ela some quando `lab_mode` é falso, e some sozinha no dia em que a escrita
 * na conta abrir — o servidor amarra as duas coisas (`capacidades.py`). Um
 * laboratório que continuasse anunciado sobre um sistema com consequência real
 * seria a pior combinação possível.
 */
export const FaixaDeLaboratorio: React.FC<{ ligado: boolean; className?: string }> = ({
  ligado,
  className,
}) => {
  if (!ligado) return null;
  return (
    <div
      role="note"
      className={cn(
        'flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-info/40',
        'bg-info/[0.06] px-3 py-2',
        className,
      )}
    >
      <span className="flex items-center gap-1.5 font-display text-[11px] font-semibold uppercase tracking-[0.08em]">
        <FlaskConical className="h-3.5 w-3.5 text-info" aria-hidden />
        Modo Laboratório
      </span>
      <p className="min-w-0 flex-1 text-[12px] leading-snug text-muted-foreground">
        Você pode percorrer jornadas que ainda não estão prontas. O que for
        simulado aparece marcado como <strong className="font-medium text-foreground">protótipo</strong>{' '}
        e não se mistura com os números reais das contas.
      </p>
    </div>
  );
};

export default SeloDePrototipo;
