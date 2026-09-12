import React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { ConjuntoFinanceiroMeta, FinanceiroMeta } from '@/lib/pautadorApi';
import { comoNumero, contagemMeta, decimalMeta, dinheiroMeta } from './MetaCampaignReadView';
import { useDensidade } from '@/components/trafego/inventario/densidade';

/**
 * A seção "Conjuntos de anúncios" — o grão em que a receita foi MEDIDA.
 *
 * ## Por que esta tela existe
 *
 * Até 08/09/2026 o frontend não mostrava nenhum número por conjunto. A seção de
 * conjuntos era só um agrupador estrutural (estado, nome, objetivo), e a regra
 * "receita da campanha = SOMA dos conjuntos filhos" não tinha sequer os insumos
 * para ser conferida na tela. O operador via um total e precisava acreditar.
 *
 * Agora o total é CONFERÍVEL: cada conjunto traz o que foi medido nele, e o
 * rodapé soma na frente de quem olha, ao lado do total que veio do servidor.
 * Se os dois divergirem, a tela DIZ que divergiram em vez de escolher um.
 *
 * ## O que ela recusa fazer
 *
 * - não repete a receita do conjunto em cada anúncio: a receita aparece SÓ no
 *   grão em que foi medida, e abaixo do conjunto ela é explicitamente ausente;
 * - não transforma ausência em zero. `—` é "não medido"; `R$ 0,00` só aparece
 *   quando o zero foi medido;
 * - não soma alcance, porque alcance é gente e a mesma pessoa aparece em dois
 *   dias. A coluna nem existe aqui.
 */

const Celula: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <td className={`px-3 py-2 align-middle tabular ${className}`}>{children}</td>
);

/**
 * Soma com a MESMA semântica do servidor — e são duas, não uma.
 *
 * ⚠️ Achado do revisor adversarial: a primeira versão usava uma só regra
 * (qualquer `null` derruba a soma) para os DOIS campos, e o servidor não faz
 * isso. No servidor, GASTO exige todas as parcelas (`_somar`) e RECEITA soma o
 * que foi atribuído levando a razão junto (`_somar_ignorando_ausentes`). Com a
 * regra errada aplicada à receita, filhos `15` e `null` faziam a tela acusar
 * divergência contra um backend que estava certo.
 */
function somarExigindoTodas(conjuntos: ConjuntoFinanceiroMeta[],
                            campo: 'spend'): number | null {
  let total = 0;
  for (const c of conjuntos) {
    const valor = comoNumero(c[campo]);
    if (valor === null) return null;
    total += valor;
  }
  return conjuntos.length ? total : null;
}

function somarMedidas(conjuntos: ConjuntoFinanceiroMeta[],
                      campo: 'revenue_brl'): number | null {
  const medidas = conjuntos
    .map((c) => comoNumero(c[campo]))
    .filter((v): v is number => v !== null);
  return medidas.length ? medidas.reduce((a, b) => a + b, 0) : null;
}

const FraseDaRazao: React.FC<{ razao: ConjuntoFinanceiroMeta['razao'] | null | undefined }> = ({ razao }) => {
  if (!razao) return null;
  const partes: string[] = [];
  if (razao.linhas_sem_utm > 0) {
    partes.push(`${razao.linhas_sem_utm} conjunto/dia sem UTM no GAM (receita desconhecida, não zero)`);
  }
  if (razao.linhas_sem_leitura_gam > 0) {
    partes.push(`${razao.linhas_sem_leitura_gam} conjunto/dia sem leitura do GAM`);
  }
  if (razao.linhas_sem_entrega > 0) {
    partes.push(`${razao.linhas_sem_entrega} conjunto/dia sem entrega medida`);
  }
  if (!partes.length) return null;
  return (
    <p className="text-xs text-muted-foreground">{partes.join(' · ')}</p>
  );
};

const ESTADO_DA_EVIDENCIA = {
  OBSERVED_COMPLETE: ['Evidência completa', 'Gasto e receita do período estão completos.'],
  PROVISIONAL: ['Dados provisórios', 'O período inclui o dia corrente e ainda pode consolidar.'],
  UNRECONCILED: ['Leituras divergentes', 'A soma dos conjuntos diverge da leitura da campanha.'],
  INCOMPLETE: ['Evidência incompleta', 'Falta gasto ou receita em parte do período.'],
} as const;

const PercursoAteMonetizacao: React.FC<{ financeiro: FinanceiroMeta }> = ({ financeiro }) => {
  const moeda = financeiro.currency ?? null;
  const evidencia = financeiro.evidence;
  const estado = evidencia ? ESTADO_DA_EVIDENCIA[evidencia.state] : null;
  const etapas = [
    ['Cliques no link', contagemMeta(financeiro.inline_link_clicks ?? null)],
    ['Chegadas à página', contagemMeta(financeiro.landing_page_views ?? null)],
    ['Impressões GAM', contagemMeta(financeiro.gam_impressions ?? null)],
    ['Receita GAM', dinheiroMeta(financeiro.revenue, moeda)],
  ];
  const pontes = [
    ['Página carregada / clique no link', decimalMeta(financeiro.landing_page_load_rate_pct ?? null, 2, '%')],
    ['Custo por chegada à página', dinheiroMeta(financeiro.cost_per_landing_page_view ?? null, moeda)],
    ['Impressões GAM / chegada', decimalMeta(financeiro.gam_impressions_per_landing_page_view ?? null, 2, '×')],
  ];
  const percursoIncompleto = etapas.some(([, valor]) => valor === '—');

  return (
    <section
      aria-labelledby="percurso-ate-monetizacao"
      className="rounded-lg border border-border bg-card p-4 shadow-card"
      data-testid="percurso-ate-monetizacao"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 id="percurso-ate-monetizacao" className="font-display text-base font-semibold">
            Percurso até a monetização
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Compra de tráfego → chegada à página → inventário publicitário → receita.
          </p>
        </div>
        <div className="text-left sm:text-right">
          <p className="text-xs text-muted-foreground">Contribuição observada</p>
          <p className="tabular text-lg font-semibold">
            {dinheiroMeta(financeiro.contribution_observed ?? financeiro.profit_gross, moeda)}
          </p>
          <p className="text-xs text-muted-foreground">Receita GAM menos mídia Meta; outros custos não modelados.</p>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-1 divide-y divide-border sm:grid-cols-2 sm:gap-y-3 sm:divide-y-0 lg:grid-cols-4 lg:divide-x">
        {etapas.map(([rotulo, valor], indice) => (
          <div key={rotulo} className="flex items-baseline justify-between gap-3 py-2 sm:block sm:px-3 sm:py-0 first:sm:pl-0 last:lg:pr-0">
            <dt className="text-xs text-muted-foreground">{indice + 1}. {rotulo}</dt>
            <dd className="tabular text-base font-semibold">{valor}</dd>
          </div>
        ))}
      </dl>

      <dl className="mt-3 grid grid-cols-1 gap-x-6 border-t border-border pt-3 text-xs sm:grid-cols-3">
        {pontes.map(([rotulo, valor]) => (
          <div key={rotulo} className="flex items-baseline justify-between gap-3 py-1">
            <dt className="text-muted-foreground">{rotulo}</dt>
            <dd className="tabular font-medium">{valor}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
        <p>
          Impressões GAM podem incluir múltiplos slots e refresh; não representam pessoas nem retenção.
        </p>
        <p className="mt-1" data-testid="estado-da-evidencia">
          <strong className="text-foreground">{estado?.[0] ?? 'Estado de evidência não informado'}.</strong>{' '}
          {estado?.[1] ?? 'Atualize a leitura antes de decidir.'}
          {percursoIncompleto ? ' Há etapas do percurso ainda sem medida.' : ''}
        </p>
      </div>
    </section>
  );
};

export const ConjuntosFinanceiros: React.FC<{
  financeiro: FinanceiroMeta | null;
  /** Render do drill-down de um conjunto: anúncios e criativos daquele conjunto. */
  aoAbrirConjunto?: (adsetRef: string) => React.ReactNode;
}> = ({ financeiro, aoAbrirConjunto }) => {
  const [aberto, setAberto] = React.useState<string | null>(null);
  const densidade = useDensidade();
  const conjuntos = financeiro?.conjuntos ?? [];
  const moeda = financeiro?.currency ?? null;

  if (!financeiro) return null;

  if (!conjuntos.length) {
    // ⚠️ Uma campanha sem conjuntos NÃO é uma campanha com gasto zero. A frase
    // precisa dizer qual das duas coisas está acontecendo.
    return (
      <section aria-labelledby="conjuntos-financeiros" className="space-y-2">
        <h3 id="conjuntos-financeiros" className="kicker">Conjuntos de anúncios</h3>
        <p className="text-sm text-muted-foreground">
          {financeiro.estado === 'SEM_CONJUNTOS_NO_READ_MODEL'
            ? 'Esta campanha não tem conjuntos no read model. Sem conjunto conhecido não há grão de receita — o que falta é leitura, não dinheiro.'
            : 'Nenhum conjunto com medida no período.'}
        </p>
      </section>
    );
  }

  const somaGasto = somarExigindoTodas(conjuntos, 'spend');
  const somaReceita = somarMedidas(conjuntos, 'revenue_brl');
  const totalGasto = comoNumero(financeiro.spend);
  const totalReceita = comoNumero(financeiro.revenue);
  // A prova aritmética que a missão pede: o total da campanha É a soma dos
  // conjuntos. Comparação em centavos para não brigar com ponto flutuante.
  const centavos = (n: number | null) => (n === null ? null : Math.round(n * 100));
  // ⚠️ `null === null` NÃO é prova de nada. Dois desconhecidos iguais fariam a
  // tela afirmar "a soma é exatamente o total" sobre uma campanha da qual não
  // se sabe nada — que é o oposto do que esta frase existe para dizer. Só há
  // prova quando os DOIS lados são números.
  const comparavel = (a: number | null, b: number | null) =>
    a !== null && b !== null;
  const gastoComparavel = comparavel(somaGasto, totalGasto);
  const receitaComparavel = comparavel(somaReceita, totalReceita);
  const gastoBate = gastoComparavel && centavos(somaGasto) === centavos(totalGasto);
  const receitaBate = receitaComparavel && centavos(somaReceita) === centavos(totalReceita);
  const haOQueProvar = gastoComparavel || receitaComparavel;
  const divergiu = (gastoComparavel && !gastoBate) || (receitaComparavel && !receitaBate);

  const linhas = conjuntos.map((c) => {
    const expandido = aberto === c.adset_ref;
    return (
      <React.Fragment key={c.adset_ref}>
        <tr className="border-t border-border/60">
          <Celula className="text-left">
            {aoAbrirConjunto ? (
              <button
                type="button"
                className="inline-flex items-center gap-1 text-left hover:underline"
                aria-expanded={expandido}
                onClick={() => setAberto(expandido ? null : c.adset_ref)}
              >
                {expandido ? <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                           : <ChevronRight className="h-3.5 w-3.5" aria-hidden />}
                <span className="font-mono text-xs">{c.id_mascarado ?? c.adset_ref}</span>
              </button>
            ) : (
              <span className="font-mono text-xs">{c.id_mascarado ?? c.adset_ref}</span>
            )}
          </Celula>
          <Celula>{dinheiroMeta(c.spend, moeda)}</Celula>
          <Celula>{dinheiroMeta(c.revenue_brl, moeda)}</Celula>
          <Celula>{decimalMeta(c.roas_ratio, 2)}</Celula>
          <Celula>{dinheiroMeta(c.profit_gross, moeda)}</Celula>
          <Celula>{contagemMeta(c.impressions)}</Celula>
          <Celula>{contagemMeta(c.clicks)}</Celula>
          <Celula>{decimalMeta(c.ctr, 2, '%')}</Celula>
          <Celula>{dinheiroMeta(c.cpc, moeda)}</Celula>
        </tr>
        {expandido && aoAbrirConjunto && (
          <tr>
            <td colSpan={9} className="bg-muted/20 px-3 py-3">
              <p className="mb-2 text-xs text-muted-foreground">
                Anúncios e criativos deste conjunto. <strong>A receita não desce até aqui</strong> —
                ela foi medida no conjunto, e repeti-la por anúncio contaria o mesmo dinheiro
                várias vezes.
              </p>
              {aoAbrirConjunto(c.adset_ref)}
            </td>
          </tr>
        )}
      </React.Fragment>
    );
  });

  const cabecalho = ['Conjunto', 'Gasto', 'Receita GAM', 'ROAS', 'Lucro bruto',
                     'Impressões', 'Cliques', 'CTR', 'CPC'];

  return (
    <section aria-labelledby="conjuntos-financeiros" className="space-y-3">
      <PercursoAteMonetizacao financeiro={financeiro} />
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="conjuntos-financeiros" className="kicker">
          Conjuntos de anúncios ({conjuntos.length})
        </h3>
        <p className="text-xs text-muted-foreground">
          Receita atribuída ao conjunto; a campanha soma os conjuntos.
        </p>
      </div>

      {densidade === 'compacta' ? (
        // No telefone é LISTA, não tabela espremida com arrasto lateral.
        <ul className="space-y-2">
          {conjuntos.map((c) => (
            <li key={c.adset_ref} className="rounded-lg border border-border/60 p-3">
              {aoAbrirConjunto ? <button type="button"
                className="flex min-h-11 w-full items-center gap-2 text-left text-sm font-medium hover:underline"
                aria-expanded={aberto === c.adset_ref}
                onClick={() => setAberto(aberto === c.adset_ref ? null : c.adset_ref)}>
                {aberto === c.adset_ref ? <ChevronDown className="h-4 w-4 shrink-0" aria-hidden /> : <ChevronRight className="h-4 w-4 shrink-0" aria-hidden />}
                {c.id_mascarado ?? c.adset_ref}
              </button> : <p className="font-mono text-xs">{c.id_mascarado ?? c.adset_ref}</p>}
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Gasto</dt>
                <dd className="tabular text-right">{dinheiroMeta(c.spend, moeda)}</dd>
                <dt className="text-muted-foreground">Receita GAM</dt>
                <dd className="tabular text-right">{dinheiroMeta(c.revenue_brl, moeda)}</dd>
                <dt className="text-muted-foreground">ROAS</dt>
                <dd className="tabular text-right">{decimalMeta(c.roas_ratio, 2)}</dd>
                <dt className="text-muted-foreground">Lucro bruto</dt>
                <dd className="tabular text-right">{dinheiroMeta(c.profit_gross, moeda)}</dd>
                <dt className="text-muted-foreground">Impressões</dt>
                <dd className="tabular text-right">{contagemMeta(c.impressions)}</dd>
                <dt className="text-muted-foreground">Cliques</dt>
                <dd className="tabular text-right">{contagemMeta(c.clicks)}</dd>
                <dt className="text-muted-foreground">CTR</dt>
                <dd className="tabular text-right">{decimalMeta(c.ctr, 2, '%')}</dd>
                <dt className="text-muted-foreground">CPC</dt>
                <dd className="tabular text-right">{dinheiroMeta(c.cpc, moeda)}</dd>
              </dl>
              <FraseDaRazao razao={c.razao} />
              {aberto === c.adset_ref && aoAbrirConjunto && <div className="mt-3 border-t border-border pt-3">
                <p className="mb-2 text-xs text-muted-foreground">Anúncios deste conjunto. A receita é medida no conjunto, não por anúncio.</p>
                {aoAbrirConjunto(c.adset_ref)}
              </div>}
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Financeiro por conjunto de anúncios, no período selecionado
            </caption>
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                {cabecalho.map((titulo, i) => (
                  <th key={titulo} scope="col" className={`px-3 py-2 ${i === 0 ? '' : 'text-left'}`}>
                    {titulo}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>{linhas}</tbody>
            <tfoot>
              <tr className="border-t-2 border-border font-medium">
                <Celula className="text-left">Total da campanha</Celula>
                <Celula>{dinheiroMeta(financeiro.spend, moeda)}</Celula>
                <Celula>{dinheiroMeta(financeiro.revenue, moeda)}</Celula>
                <Celula>{decimalMeta(financeiro.roas_ratio, 2)}</Celula>
                <Celula>{dinheiroMeta(financeiro.profit_gross, moeda)}</Celula>
                <Celula>{contagemMeta(financeiro.impressions ?? null)}</Celula>
                <Celula>{contagemMeta(financeiro.clicks ?? null)}</Celula>
                <Celula>{decimalMeta(financeiro.ctr ?? null, 2, '%')}</Celula>
                <Celula>{dinheiroMeta(financeiro.cpc ?? null, moeda)}</Celula>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* A prova aritmética, escrita. Ela não é enfeite: é o que permite ao
          operador confiar no total sem abrir o banco. */}
      <p className="text-xs text-muted-foreground" data-testid="prova-da-soma">
        {!haOQueProvar
          ? 'Sem medida suficiente para conferir a soma: o total e as parcelas '
            + 'estão desconhecidos. Ausência não é prova de igualdade.'
          : divergiu
            ? 'ATENÇÃO: a soma dos conjuntos não bate com o total da campanha. '
              + 'Nenhum dos dois foi ajustado — a divergência está sendo mostrada como é.'
            : `A soma dos ${conjuntos.length} conjuntos é exatamente o total da campanha`
              + (gastoComparavel && receitaComparavel
                  ? '.'
                  : gastoComparavel
                    ? ' no gasto; a receita ainda não tem medida para conferir.'
                    : ' na receita; o gasto ainda não tem medida para conferir.')}
      </p>
      <FraseDaRazao razao={financeiro.razao} />

      {financeiro.reconciliacao && financeiro.reconciliacao.reconciliado === false && (
        <p className="text-xs text-amber-600 dark:text-amber-500">
          A leitura campaign-level da Meta diverge da soma dos conjuntos
          ({dinheiroMeta(financeiro.reconciliacao.diferenca, moeda)}). Ela serve para
          reconciliar e <strong>não</strong> entra no total — somá-la contaria a mesma
          despesa duas vezes.
        </p>
      )}
    </section>
  );
};

export default ConjuntosFinanceiros;
