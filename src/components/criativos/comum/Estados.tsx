/**
 * Os quatro estados de uma lista, desenhados diferentes de propósito.
 *
 * `leitura.ts` decide QUAL é o estado; este arquivo decide como cada um se
 * parece. Eles precisam ser visualmente distintos, e não três variações da
 * mesma caixa cinza: quem vê "nada aqui" três vezes iguais não percebe que da
 * primeira vez a fonte estava vazia, da segunda o filtro estava apertado e da
 * terceira a leitura falhou.
 */
import React from 'react';
import { CircleOff, Filter, ImageOff, Inbox, WifiOff } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

const MOLDURA = 'rounded-md border border-dashed border-border px-4 py-8 text-center';

export const Vazio: React.FC<{
  titulo: string;
  /** O que vai aparecer aqui quando existir. Nunca um número inventado. */
  explicacao: string;
  acao?: React.ReactNode;
  className?: string;
}> = ({ titulo, explicacao, acao, className }) => (
  <div className={cn(MOLDURA, className)}>
    <Inbox className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden />
    <p className="mt-3 font-display text-sm font-semibold text-foreground">{titulo}</p>
    <p className="mx-auto mt-1 max-w-[52ch] text-pretty text-[13px] leading-relaxed text-muted-foreground">
      {explicacao}
    </p>
    {acao && <div className="mt-4 flex justify-center">{acao}</div>}
  </div>
);

export const VazioAposFiltro: React.FC<{
  /**
   * Quantos existem sem filtro. Sem esse número, "vazio" vira ambíguo.
   *
   * ⚠️ `null` é "o servidor não informou o total", e NÃO zero. A chamadora
   * passava `universo ?? 0`, e a caixa escrevia "A biblioteca tem 0 ativos. O
   * filtro atual é que não alcança nenhum deles." — duas afirmações que se
   * contradizem, e a primeira falsa (defeito D5 da auditoria P17).
   * `comum/leitura.ts` documenta que este estado é alcançável com universo
   * desconhecido, então o caso não é hipotético.
   */
  universo: number | null;
  aoLimpar: () => void;
  className?: string;
}> = ({ universo, aoLimpar, className }) => (
  <div className={cn(MOLDURA, 'border-solid bg-muted/40', className)}>
    <Filter className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden />
    <p className="mt-3 font-display text-sm font-semibold text-foreground">
      Nenhum ativo casa com este recorte
    </p>
    <p className="mx-auto mt-1 max-w-[52ch] text-pretty text-[13px] leading-relaxed text-muted-foreground">
      {universo === null ? (
        <>
          O servidor não informou quantos ativos a biblioteca tem, então não dá para afirmar se ela
          está vazia ou se é este recorte que não alcança nada. O que se sabe é que este recorte não
          trouxe nenhum.
        </>
      ) : (
        <>
          A biblioteca tem {universo} {universo === 1 ? 'ativo' : 'ativos'}. O filtro atual é que
          não alcança nenhum deles.
        </>
      )}
    </p>
    <div className="mt-4 flex justify-center">
      <Button variant="outline" size="sm" onClick={aoLimpar}>
        Limpar filtros
      </Button>
    </div>
  </div>
);

/**
 * O esqueleto preserva o LAYOUT, e é isso que ele existe para fazer.
 *
 * Uma tela que mostra um spinner centralizado e depois desenha a lista faz o
 * conteúdo saltar; quem já estava lendo perde a linha. As caixas têm a altura
 * das linhas reais.
 */
export const Carregando: React.FC<{
  linhas?: number;
  /** Altura de cada linha, em classe utilitária. */
  altura?: string;
  rotulo: string;
  className?: string;
}> = ({ linhas = 3, altura = 'h-16', rotulo, className }) => (
  <div className={cn('space-y-2', className)} aria-busy="true" aria-live="polite">
    <span className="sr-only">{rotulo}</span>
    {Array.from({ length: linhas }, (_, i) => (
      <div
        key={i}
        className={cn('rounded-md border border-border bg-muted/50 motion-safe:animate-pulse', altura)}
        aria-hidden
      />
    ))}
  </div>
);

export const ErroDeLeitura: React.FC<{
  /** A mensagem JÁ sanitizada que o servidor mandou. Nunca status nem stack. */
  mensagem: string;
  codigo?: string | null;
  /** O que ainda está na tela e pode estar velho. */
  ressalva?: string;
  aoTentarDeNovo?: () => void;
  className?: string;
}> = ({ mensagem, codigo, ressalva, aoTentarDeNovo, className }) => (
  <div
    role="alert"
    className={cn(
      'rounded-md border border-destructive/50 bg-destructive/[0.06] px-4 py-4',
      className,
    )}
  >
    <div className="flex items-start gap-3">
      <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-display text-sm font-semibold text-foreground">
          A leitura não chegou
        </p>
        <p className="mt-1 text-pretty text-[13px] leading-relaxed text-foreground">{mensagem}</p>
        {ressalva && (
          <p className="mt-1 text-pretty text-[13px] leading-relaxed text-muted-foreground">
            {ressalva}
          </p>
        )}
        {codigo && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Código para investigação: <span className="font-mono">{codigo}</span>
          </p>
        )}
        {aoTentarDeNovo && (
          <Button variant="outline" size="sm" className="mt-3" onClick={aoTentarDeNovo}>
            Tentar ler de novo
          </Button>
        )}
      </div>
    </div>
  </div>
);

/**
 * Arquivo indisponível: `previewUrl === null`.
 *
 * ⚠️ Isto NÃO é vazio e NÃO é erro. É "a peça existe, o arquivo não está
 * disponível agora". Desenhar um erro aqui faria o operador procurar defeito
 * onde não há; desenhar vazio faria a peça parecer inexistente.
 */
export const SemArquivo: React.FC<{
  motivo?: string;
  /** Miniatura de lista: só o glifo cabe, e a frase vai para o leitor de tela. */
  denso?: boolean;
  className?: string;
}> = ({ motivo, denso = false, className }) => {
  const frase =
    motivo ?? 'Arquivo indisponível no momento. A peça existe, o arquivo não veio nesta leitura.';
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 overflow-hidden rounded-md border border-border bg-muted/50 text-center',
        denso ? 'gap-0 p-1' : 'px-3 py-6',
        className,
      )}
      title={frase}
    >
      <ImageOff className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
      <p className={cn('leading-snug text-muted-foreground', denso ? 'sr-only' : 'text-[12px]')}>
        {frase}
      </p>
    </div>
  );
};

/** Bloco de indisponibilidade declarada, com o motivo vindo do servidor. */
export const Indisponivel: React.FC<{
  titulo: string;
  motivo: string;
  className?: string;
}> = ({ titulo, motivo, className }) => (
  <div
    className={cn('rounded-md border border-warning/55 bg-warning/[0.08] px-4 py-3', className)}
  >
    <div className="flex items-start gap-3">
      <CircleOff className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden />
      <div className="min-w-0">
        <p className="font-display text-sm font-semibold text-foreground">{titulo}</p>
        <p className="mt-1 text-pretty text-[13px] leading-relaxed text-foreground">{motivo}</p>
      </div>
    </div>
  </div>
);
