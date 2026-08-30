/**
 * Campanha ligada que não gastou — o cartão que diz isso antes de o dia acabar.
 *
 * ## O defeito que ele conserta
 *
 * Medido em 20/08/2026: duas campanhas `ENABLED` na conta, R$ 0,00 gastas, uma
 * delas havia 22 horas e com UMA impressão. Nenhuma tela do VOLC OS dizia isso.
 * O operador via "ativa" no painel do Google e supunha entrega; descobrir custou
 * sete consultas GAQL escritas à mão.
 *
 * ## ⚠️ POR QUE ELE NÃO DIZ QUAL DEVERIA SER O LANCE
 *
 * A tentação era comparar o lance com o CPC que o cluster do Pautador traz do
 * DataForSEO. Na maquininha isso daria "R$ 0,12 contra mediana de R$ 10,54" —
 * uma frase devastadora, e exatamente o tipo de número que não pode entrar num
 * alerta: é estimativa de TERCEIRO, infla, e no dia em que estiver errada o
 * alerta vira ruído. Depois disso o operador ignora todos os outros.
 *
 * Aqui só entram fatos da conta — lance, orçamento, impressões, o texto do
 * próprio Google — e uma ordem de revisão. Quem decide o número é quem olha o
 * leilão real.
 *
 * A única conta exibida é `orçamento ÷ lance`, que vem pronta do módulo: divisão
 * de dois números da conta, sem estimativa de ninguém no meio.
 *
 * ## Os dois sintomas pedem olhares opostos
 *
 * `sem_impressao` não entrou no leilão → lance, aprovação, volume.
 * `sem_clique`    entrou e ninguém clicou → anúncio e página. Subir lance aqui
 * seria pagar mais caro para continuar não sendo clicado.
 */
import React from 'react';
import { AlertTriangle, ArrowUpRight, History } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { AlertaDeEntrega as Alerta } from '@/types/trafego';

const reais = (v: number | null): string =>
  v == null ? '—' : `R$ ${v.toFixed(2).replace('.', ',')}`;

/** "22,5h" abaixo de um dia; "2 dias" acima. Hora exata em dia e meio não ajuda. */
export function tempoLigada(horas: number | null): string {
  if (horas == null) return 'há tempo desconhecido';
  if (horas < 48) return `há ${horas.toFixed(1).replace('.', ',')}h`;
  return `há ${Math.floor(horas / 24)} dias`;
}

const AlertaDeEntrega: React.FC<{
  alerta: Alerta;
  className?: string;
}> = ({ alerta: a, className }) => {
  const semImpressao = a.sintoma === 'sem_impressao';
  const url = a.customer_id
    ? `https://ads.google.com/aw/campaigns?campaignId=${a.campaign_id}&__c=${a.customer_id}`
    : `https://ads.google.com/aw/campaigns?campaignId=${a.campaign_id}`;

  return (
    <article
      id={`alerta-${a.customer_id}-${a.campaign_id}`}
      tabIndex={-1}
      className={cn(
        'scroll-mt-6 rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 space-y-3',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/70',
        className,
      )}
      // Não é `role="alert"`: isto não chega durante a interação, já está na
      // página quando ela abre. `role="alert"` interromperia o leitor de tela
      // a cada render por uma informação que não é urgente nesse sentido.
      aria-labelledby={`alerta-${a.campaign_id}`}
    >
      <header className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-500" aria-hidden />
        <div className="min-w-0">
          <h3 id={`alerta-${a.campaign_id}`} className="text-sm font-medium leading-snug">
            {a.campaign_name || `Campanha ${a.campaign_id}`}
          </h3>
          <p className="text-[11px] text-muted-foreground">
            ligada {tempoLigada(a.horas_ligada)} e não gastou nada
          </p>
          {(a.customer_name || a.customer_id) && (
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {a.customer_name || a.customer_id}
            </p>
          )}
        </div>
      </header>

      {/* Os fatos. Nenhum deles é opinião nossa. */}
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5 text-[11px]">
        <Fato rotulo="gasto" valor={reais(a.custo)} />
        <Fato rotulo="impressões" valor={String(a.impressoes)} />
        <Fato rotulo="cliques" valor={String(a.cliques)} />
        <Fato rotulo="lance" valor={reais(a.lance)} />
        <Fato rotulo="orçamento" valor={a.orcamento == null ? '—' : `${reais(a.orcamento)}/dia`} />
        <Fato
          rotulo="teto de cliques/dia"
          valor={a.teto_de_cliques == null ? '—' : String(a.teto_de_cliques)}
          // Dizer de onde vem a conta evita que ela pareça previsão.
          titulo="orçamento ÷ lance — divisão de dois números da conta"
        />
      </dl>

      <p className="text-[11px] text-muted-foreground">
        <span className="font-medium text-foreground">Google:</span>{' '}
        {a.razoes.length > 0 ? a.razoes.join(' · ') : 'nenhuma observação'}
        {a.aprovacao_do_anuncio ? ` · anúncio ${a.aprovacao_do_anuncio}` : ''}
      </p>

      {a.alteracoes.length > 0 && (
        <div className="text-[11px] text-muted-foreground space-y-0.5">
          {a.alteracoes.slice(0, 3).map((m, i) => (
            <p key={`${m.quando}-${m.campo}-${i}`} className="flex items-start gap-1.5">
              <History className="h-3 w-3 mt-0.5 shrink-0" aria-hidden />
              <span>{m.resumo}</span>
            </p>
          ))}
        </div>
      )}

      <div className="text-[11px]">
        <p className="font-medium mb-1">
          {semImpressao
            ? 'Não entrou no leilão. Revise nesta ordem:'
            : 'Entrou no leilão e ninguém clicou. Revise nesta ordem:'}
        </p>
        <ol className="list-decimal list-inside text-muted-foreground space-y-0.5">
          {a.revisar.map((passo) => (
            <li key={passo}>{passo}</li>
          ))}
        </ol>
      </div>

      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
      >
        abrir no Google Ads
        <ArrowUpRight className="h-3 w-3" aria-hidden />
      </a>
    </article>
  );
};

const Fato: React.FC<{ rotulo: string; valor: string; titulo?: string }> = ({
  rotulo, valor, titulo,
}) => (
  <div title={titulo}>
    <dt className="text-muted-foreground">{rotulo}</dt>
    {/* Tabular: sem isso a coluna dança quando um número troca de largura. */}
    <dd className="font-medium tabular-nums">{valor}</dd>
  </div>
);

export default AlertaDeEntrega;
