/**
 * O que vai acontecer quando o operador clicar — dito ANTES do trabalho.
 *
 * ## O defeito que este painel conserta
 *
 * O cockpit pedia vinte minutos de triagem e só revelava o essencial DENTRO do
 * overlay de lançamento: que a campanha nasce pausada, que a trava de escrita
 * está fechada, em que conta e moeda ela entra, e para o que ela vai otimizar.
 * Descobrir a trava fechada depois de montar tudo é desperdiçar o trabalho
 * inteiro — e a única pergunta que o operador tem ao abrir a tela é "o que
 * exatamente vai acontecer se eu for até o fim".
 *
 * ## Cada linha aqui é uma decisão da API, não enfeite
 *
 * `moeda` é a unidade do lance que ele digita. `fuso` decide a que hora o dia
 * do orçamento vira. `meta` é o que o `maximize_conversions` persegue. Os ad
 * groups são o recorte que a mineração já fez. Nada disso é opinião da tela.
 */
import React from 'react';
import { AlertTriangle, Info, Lock, Target, Unlock } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { Cockpit, EstadoDaTrava, EstrategiaDeLance } from '@/types/trafego';

interface Props {
  cockpit: Cockpit;
  trava: EstadoDaTrava | null;
  gruposEscolhidos: { tipo: string; keywords: string[] }[];
  budget: string;
  /** Como a campanha nasce. O painel PRECISA saber: sob `manual_cpc` o lance do
   *  operador é o lance do leilão, e sob automático ele é ignorado. Dizer a
   *  coisa errada aqui é o defeito mais caro desta tela. */
  estrategia: EstrategiaDeLance;
}

export const PainelDoLancamento: React.FC<Props> = ({
  cockpit, trava, gruposEscolhidos, budget, estrategia,
}) => {
  const c = cockpit.conta;
  const meta = c?.meta_conversao?.primaria ?? null;
  const semMeta = !!c?.vinculada && !!c?.meta_conversao && !meta;
  const totalKw = gruposEscolhidos.reduce((s, g) => s + g.keywords.length, 0);

  return (
    <section className="card-volc p-5 md:p-6" aria-label="o que vai ser criado">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-[15px] font-medium tracking-tight">o que vai ser criado</h2>
        <span className="hairline flex-1" />
        {/* A campanha nasce PAUSADA, e isso muda o risco de clicar. Dizer aqui
            é o que separa "vou gastar" de "vou submeter para revisão". */}
        <span className="kicker">nasce pausada</span>
      </div>

      <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        <Medida rotulo="conta">
          {c?.vinculada ? (
            <>
              <span className="block">{c.nome || c.customer_id}</span>
              <span className="tabular block text-[11px] text-muted-foreground">
                {c.customer_id}
                {c.moeda && ` · ${c.moeda}`}
                {c.teste && ' · CONTA DE TESTE'}
              </span>
            </>
          ) : (
            <span className="text-destructive">não vinculada</span>
          )}
        </Medida>

        {/* ⚠️ Este bloco contava os grupos da TRIAGEM e dizia "3 ad groups".
            Virou mentira quando a doutrina fechou em um conjunto: a
            sub-intenção é a lente com que o operador marca as keywords, não o
            recorte que vai para a conta. Contar errado aqui faria o operador
            esperar três RSAs e receber um. */}
        <Medida rotulo="conjunto">
          {totalKw === 0 ? (
            <span className="text-muted-foreground">nenhuma keyword</span>
          ) : (
            <>
              <span className="block">1 · {totalKw} keywords</span>
              <span className="block text-[11px] text-muted-foreground">
                um conjunto, um RSA — verba é da campanha, não do grupo
              </span>
            </>
          )}
        </Medida>

        <Medida rotulo="orçamento/dia">
          <span className="tabular block">
            {c?.moeda ? `${c.moeda} ` : ''}{budget || '—'}
          </span>
          {/* O fuso não é curiosidade: é ele que decide a que hora o dia do
              orçamento vira, e portanto quando a verba zera. */}
          {c?.fuso && (
            <span className="block text-[11px] text-muted-foreground">
              dia vira em {c.fuso}
            </span>
          )}
        </Medida>

        <Medida rotulo="otimiza para">
          {meta ? (
            <>
              <span className="flex items-center gap-1.5">
                <Target className="h-3 w-3 shrink-0" aria-hidden />
                {meta.nome}
              </span>
              <span className="block text-[11px] text-muted-foreground">
                {meta.categoria.toLowerCase()} · da conta
              </span>
            </>
          ) : semMeta ? (
            <span className="text-destructive">sem meta primária</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </Medida>
      </dl>

      {/* ⚠️ Conta sem ação primária + `maximize_conversions` = orçamento gasto
          sem sinal nenhum. É o pior desfecho possível e precisa ser visível
          ANTES, não depois. */}
      {semMeta && (
        <Aviso tom="ruim">
          {cockpit.conta?.meta_conversao?.por_que}
        </Aviso>
      )}

      {/* ⚠️ Este bloco dizia "o cockpit não escolhe a meta" e "nasce em
          maximize_conversions". As duas frases morreram quando a Mesa de Lance
          passou a escolher a estratégia. O que continua verdadeiro — e é o que
          o operador precisa saber — é que a META em si ainda não é aplicada:
          ligá-la exige `campaign.selective_optimization`, que o engine ainda
          não escreve. Dizer isso é diferente de deixar ele supor. */}
      {meta && (
        <Aviso tom="nota">
          A campanha nasce em{' '}
          <span className="font-mono">
            {estrategia === 'MANUAL_CPC' ? 'manual_cpc' : 'maximize_conversions'}
          </span>
          {estrategia === 'MANUAL_CPC'
            ? ' — o lance que você definiu é o lance do leilão.'
            : ' e persegue a ação primária da conta.'}{' '}
          A meta acima é a da conta; vinculá-la a esta campanha exige{' '}
          <span className="font-mono">selective_optimization</span>, que o engine
          ainda não escreve.
        </Aviso>
      )}

      {c?.auto_tagging === false && (
        <Aviso tom="nota">
          O auto-tagging da conta está <b>desligado</b>. Sem ele o Google não
          anexa o <span className="font-mono">gclid</span>, e o cruzamento entre
          custo e receita depende da marcação declarada no payload.
        </Aviso>
      )}

      {c?.detalhes_indisponiveis && (
        <Aviso tom="nota">
          Não consegui ler moeda, fuso e meta desta conta agora
          ({c.detalhes_indisponiveis}). O resto da tela continua válido.
        </Aviso>
      )}

      <div className={cn('mt-4 flex items-start gap-2 border-t border-border pt-4 text-[11px] leading-relaxed',
                         trava?.env_presente ? 'text-warning' : 'text-muted-foreground')}>
        {trava?.env_presente
          ? <Unlock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          : <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}
        <span>
          {trava?.env_presente ? (
            <>
              <b>A trava de escrita está ABERTA.</b> Lançar cria a campanha de
              verdade — pausada, mas persistida na conta.
            </>
          ) : (
            <>
              A trava de escrita está fechada. Você pode montar e provar à
              vontade: <span className="font-mono">validate_only</span> roda
              contra a conta real e não cria nada.
            </>
          )}
        </span>
      </div>

      {trava?.canario && c?.customer_id !== trava.canario.customer_id && (
        <Aviso tom="nota">
          Este pedido pode ser provado, mas a primeira criação real está
          restrita a <b>{trava.canario.customer_label}</b>{' '}
          ({trava.canario.customer_id_formatado}). A conta atual não será
          alterada.
        </Aviso>
      )}
    </section>
  );
};

const Medida: React.FC<{ rotulo: string; children: React.ReactNode }> =
  ({ rotulo, children }) => (
  <div>
    <dt className="kicker">{rotulo}</dt>
    <dd className="mt-1 text-sm">{children}</dd>
  </div>
);

const Aviso: React.FC<{ tom: 'ruim' | 'nota'; children: React.ReactNode }> =
  ({ tom, children }) => (
  <div className={cn('mt-4 flex items-start gap-2 rounded-md border p-3 text-[11px] leading-relaxed',
                     tom === 'ruim'
                       ? 'border-destructive/40 bg-destructive/[0.05] text-foreground'
                       : 'border-border text-muted-foreground')}>
    {tom === 'ruim'
      ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
      : <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}
    <span className="min-w-0">{children}</span>
  </div>
);
