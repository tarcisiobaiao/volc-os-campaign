import React from 'react';
import { cn } from '@/lib/utils';
import {
  DECISAO_HUMANA, FORMATO_HUMANO, PROCEDENCIA_HUMANA,
  type TeseDeOportunidade,
} from '@/types/pautadorOportunidade';

/**
 * A tese: o que o operador lê ANTES das barras.
 *
 * O painel de eixos responde "o que foi medido". Esta peça responde a pergunta
 * que vem antes dela e que ninguém respondia: **vale aprofundar, e por quê?**
 *
 * ## Os invariantes
 *
 * **Três conjuntos, sempre visíveis, nunca somados.** Fato, hipótese e
 * desconhecido ficam em blocos separados com glifo e título próprios. Não há
 * aba, acordeão nem tooltip escondendo o terceiro: esconder o desconhecido
 * atrás de um clique é a forma mais barata de transformar lacuna em confiança.
 *
 * **O formato cita o que o produziu.** "Ferramenta de elegibilidade" nunca
 * aparece sozinha — vem com `max condicoes_pessoais 3`, `max ramos_de_acao 3`.
 * Uma recomendação sem o número que a gerou é palpite com cara de método.
 *
 * **Contradição não se resolve em silêncio.** Quando dois sinais discordam, o
 * bloco aparece e diz que ninguém resolveu. A tela não escolhe um lado.
 *
 * **Cor nunca decide sozinha.** Cada estado é glifo + palavra + frase. O tom
 * semântico é reforço, e a fileira de tons exclui aurora de propósito: aurora
 * é assinatura de identidade, não estado operacional.
 *
 * **Zero é diferente de vazio.** Um conjunto vazio some; um conjunto que não
 * pôde ser calculado nunca chega aqui como lista vazia — chega como
 * `sem_validacao`, que tem bloco próprio.
 */

const ESTILO = `
.tese { --tese-hair: 2px; }
/* Entrada única, curta, informativa: a tese chega antes das barras e o
   operador precisa perceber a ordem. Sem stagger, sem bounce. */
@media (prefers-reduced-motion: no-preference) {
  .tese-entra { animation: tese-entra 180ms cubic-bezier(.22,1,.36,1) both; }
}
@keyframes tese-entra {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: none; }
}
`;

const TOM_BORDA: Record<string, string> = {
  success: 'bg-success', warning: 'bg-warning', destructive: 'bg-destructive',
  info: 'bg-info', muted: 'bg-muted-foreground/40',
};
const TOM_TEXTO: Record<string, string> = {
  success: 'text-success', warning: 'text-warning', destructive: 'text-destructive',
  info: 'text-info', muted: 'text-muted-foreground',
};

/** Um grupo de procedência. Bloco, não chip: estes textos são frases. */
const Grupo: React.FC<{
  chave: keyof typeof PROCEDENCIA_HUMANA;
  itens: string[];
  destaque?: boolean;
}> = ({ chave, itens, destaque }) => {
  if (!itens.length) return null;
  const meta = PROCEDENCIA_HUMANA[chave];
  return (
    <section
      aria-labelledby={`tese-${chave}`}
      className={cn('rounded-md px-2.5 py-2',
        destaque ? 'bg-destructive/[.07] ring-1 ring-destructive/25' : 'bg-muted/25')}
    >
      <h4 id={`tese-${chave}`} className="flex items-baseline gap-1.5 mb-1">
        <span aria-hidden className={cn('text-[11px] leading-none',
          destaque ? 'text-destructive' : 'text-muted-foreground')}>{meta.glifo}</span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-foreground">
          {meta.titulo}
        </span>
        <span className="text-[10px] tabular-nums text-muted-foreground">{itens.length}</span>
        <span className="text-[10px] text-muted-foreground/80 leading-snug">{meta.explica}</span>
      </h4>
      <ul className="space-y-0.5">
        {itens.map((t) => (
          <li key={t} className="text-[11px] leading-snug text-foreground/90 flex gap-1.5">
            <span aria-hidden className="text-muted-foreground/50 select-none">–</span>
            <span className="break-words">{t}</span>
          </li>
        ))}
      </ul>
    </section>
  );
};

export const TeseDaOportunidade: React.FC<{
  tese?: TeseDeOportunidade | null;
  className?: string;
}> = ({ tese, className }) => {
  if (!tese) return null;

  const d = DECISAO_HUMANA[tese.decisao] ?? DECISAO_HUMANA.sem_validacao;
  const formato = tese.formato_de_funil ? FORMATO_HUMANO[tese.formato_de_funil] : null;

  return (
    <article
      className={cn('tese tese-entra relative overflow-hidden rounded-lg border border-border bg-card', className)}
      aria-label={`Tese de oportunidade: ${d.palavra}`}
    >
      <style>{ESTILO}</style>
      {/* Hairline SUPERIOR de 2px — nunca faixa lateral. */}
      <div aria-hidden className={cn('absolute inset-x-0 top-0 h-0.5', TOM_BORDA[d.tom])} />

      <div className="p-3 space-y-3">
        {/* ── a decisão ─────────────────────────────────────────────── */}
        <header className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
            Tese de oportunidade
          </p>
          <h3 className="flex items-center gap-2 font-display text-[19px] font-bold leading-tight tracking-tight text-foreground">
            <span aria-hidden className={cn('text-[15px] leading-none', TOM_TEXTO[d.tom])}>{d.glifo}</span>
            {d.palavra}
          </h3>
          <p className="text-[12px] leading-snug text-foreground/85 max-w-[62ch]">{tese.porque}</p>
        </header>

        {/* ── o formato, com os observáveis que o produziram ─────────── */}
        {formato ? (
          <div className="rounded-md bg-muted/25 px-2.5 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Formato sugerido
            </p>
            <p className="text-[13px] font-semibold text-foreground mt-0.5">{formato.nome}</p>
            <p className="text-[11px] leading-snug text-muted-foreground mt-0.5">{formato.explica}</p>
            {tese.observaveis_do_formato.length > 0 && (
              <ul className="mt-1.5 flex flex-wrap gap-1">
                {tese.observaveis_do_formato.map((o) => (
                  <li key={o}
                    className="rounded bg-background px-1.5 py-0.5 text-[10px] tabular-nums text-foreground/80 border border-border">
                    {o}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <p className="text-[11px] leading-snug text-muted-foreground rounded-md bg-muted/25 px-2.5 py-2">
            Nenhum formato de funil recomendado. O motivo está na decisão acima —
            não é falta de dado.
          </p>
        )}

        {/* ── procedência: três conjuntos, sempre à vista ────────────── */}
        <div className="space-y-1.5">
          <Grupo chave="contradicoes" itens={tese.contradicoes} destaque />
          <Grupo chave="fatos" itens={tese.fatos} />
          <Grupo chave="hipoteses" itens={tese.hipoteses} />
          <Grupo chave="desconhecidos" itens={tese.desconhecidos} />
        </div>

        {/* ── o menor experimento ────────────────────────────────────── */}
        {tese.proximo_experimento && (
          <div className="rounded-md border border-info/30 bg-info/[.07] px-2.5 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-info">
              Próximo experimento
            </p>
            <p className="text-[11px] leading-snug text-foreground/90 mt-0.5">
              {tese.proximo_experimento}
            </p>
          </div>
        )}

        {/* ── o rodapé de procedência: o que a tese CITA, não recalcula ─ */}
        <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-2
                           text-[10px] text-muted-foreground">
          <span>
            cobertura{' '}
            <span className="tabular-nums text-foreground/80">
              {tese.cobertura != null ? `${Math.round(tese.cobertura * 100)}%` : '—'}
            </span>
          </span>
          <span>
            índice{' '}
            <span className="tabular-nums text-foreground/80">
              {tese.indice_citado != null ? tese.indice_citado.toFixed(3) : '—'}
            </span>
          </span>
          {tese.perfil_citado && <span>quadrante {tese.perfil_citado}</span>}
          {!tese.comparavel && tese.motivo_incomparavel && (
            <span className="text-warning">fora do ranking: {tese.motivo_incomparavel}</span>
          )}
          <span className="ml-auto text-muted-foreground/60">
            derivado do que já foi medido · {tese.versao_do_contrato}
          </span>
        </footer>
      </div>
    </article>
  );
};
