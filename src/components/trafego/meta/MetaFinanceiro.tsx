import React from 'react';
import { pautadorApi, type FinanceiroMeta } from '@/lib/pautadorApi';
import { Button } from '@/components/ui/button';

const MOTIVOS: Record<string, string> = {
  SUPABASE_INDISPONIVEL: 'Banco de leitura indisponível.',
  CONTA_NAO_RESOLVIDA: 'Conta ainda não sincronizada.',
  FUSO_META_NAO_CONFIRMADO: 'Confirme o fuso da conta Meta.',
  CAMPANHA_NAO_RESOLVIDA_NO_ESCOPO: 'Campanha não encontrada nesta conta.',
  IDENTIDADE_META_NAO_CONFIRMADA: 'Identidade da campanha ainda não confirmada.',
  INSIGHTS_DIARIOS_AUSENTES_PARCIAIS_OU_INCOMPATIVEIS: 'Faltam Insights diários completos desta campanha no período.',
  SPEND_NULO_OU_INVALIDO: 'A Meta não informou um gasto válido para todos os dias.',
  VINCULO_PROJETO_META_NAO_CONFIRMADO: 'Confirme o vínculo da conta Meta com o projeto.',
  VINCULO_PROJETO_META_INVALIDO: 'O vínculo de projeto precisa ser corrigido.',
  CONTA_GAM_DO_PROJETO_NAO_UNIVOCA: 'Confirme uma única conta GAM para este projeto.',
  MOEDA_FUSO_COLUNA_GAM_NAO_CONFIRMADOS: 'Confirme moeda, fuso e coluna de receita do relatório GAM no servidor.',
  GAM_META_MOEDA_OU_FUSO_DIVERGENTE: 'GAM e Meta estão em moedas ou fusos diferentes. Não há comparação direta.',
  CAMPAIGN_ID_GAM_COM_NAMESPACE_NAO_UNIVOCO: 'Não foi possível distinguir com segurança o campaign_id entre Google e Meta.',
  ADSET_ID_GAM_COM_NAMESPACE_NAO_UNIVOCO: 'Um ID de conjunto colide com um ID de campanha do Google; não dá para saber de quem é a receita.',
  CAMPANHA_SEM_CONJUNTOS_CONHECIDOS: 'Esta campanha não tem conjuntos no read model — o grão da receita não pôde ser lido.',
  CONJUNTOS_DA_CAMPANHA_TRUNCADOS: 'A campanha tem mais conjuntos do que uma leitura comporta; o total seria parcial.',
  CONJUNTO_COM_IDENTIDADE_INVALIDA: 'Um conjunto do read model tem identidade fora do formato de ID da Meta.',
  INSIGHT_DUPLICADO_NO_MESMO_GRAO: 'O mesmo conjunto/dia apareceu duas vezes; somar contaria o dia em dobro.',
  INSIGHTS_TRUNCADOS_PELO_TETO: 'A leitura de gasto atingiu o teto de linhas e seria parcial.',
  RECEITA_GAM_TRUNCADA_PELO_TETO: 'A leitura de receita atingiu o teto de linhas e seria parcial.',
  RECEITA_GAM_DUPLICADA_NO_MESMO_GRAO: 'O mesmo conjunto/dia apareceu duas vezes no GAM.',
  RECEITA_GAM_INDISPONIVEL: 'A tabela de receita do GAM não respondeu.',
  SCHEMA_DE_CONJUNTOS_NAO_APLICADO: 'O schema de conjuntos ainda não foi aplicado neste banco.',
  SCHEMA_DE_INSIGHTS_NAO_APLICADO: 'O schema de insights ainda não foi aplicado neste banco.',
  CAMPAIGN_ID_META_NAO_UNIVOCO: 'O campaign_id está associado a mais de uma conta Meta.',
  RECEITA_GAM_AUSENTE_PARCIAL_OU_DUPLICADA: 'Faltam dias de receita GAM ou há registros duplicados no período.',
  RECEITA_GAM_NULA_OU_INVALIDA: 'O GAM não informou receita válida para todos os dias.',
};

export function useFinanceiroMeta(referencia: string, contaRef: string | null) {
  const [periodo, setPeriodo] = React.useState({ inicio: '', fim: '' });
  const [versao, atualizar] = React.useReducer((n: number) => n + 1, 0);
  const [leitura, setLeitura] = React.useState<{
    chave: string; dados: FinanceiroMeta | null; erro: boolean;
  } | null>(null);
  const chave = JSON.stringify([referencia, contaRef, periodo, versao]);
  React.useEffect(() => {
    if (!contaRef) return;
    let vivo = true;
    pautadorApi.financeiroMeta(referencia, contaRef, periodo.inicio || undefined, periodo.fim || undefined)
      .then((dados) => vivo && setLeitura({ chave, dados, erro: false }))
      .catch(() => vivo && setLeitura({ chave, dados: null, erro: true }));
    return () => { vivo = false; };
  }, [chave, referencia, contaRef, periodo.inicio, periodo.fim]);
  // Dados de outra conta/campanha/período não sobrevivem nem por um render.
  return { dados: leitura?.chave === chave ? leitura.dados : null,
    erro: leitura?.chave === chave && leitura.erro,
    carregando: !!contaRef && leitura?.chave !== chave,
    setPeriodo, atualizar };
}

export function PeriodoFinanceiroMeta({ financeiro }: {
  financeiro: ReturnType<typeof useFinanceiroMeta>;
}) {
  const [inicio, setInicio] = React.useState('');
  const [fim, setFim] = React.useState('');
  const { dados, erro, carregando } = financeiro;
  return <div className="space-y-3">
    <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => {
      event.preventDefault();
      financeiro.setPeriodo({ inicio, fim });
      financeiro.atualizar();
    }}>
      <label className="text-sm">De
        <input aria-label="Início do período financeiro" className="mt-1 block rounded-md border bg-background p-2" type="date"
          required value={inicio} onChange={(event) => setInicio(event.target.value)} />
      </label>
      <label className="text-sm">Até
        <input aria-label="Fim do período financeiro" className="mt-1 block rounded-md border bg-background p-2" type="date"
          required min={inicio || undefined} value={fim} onChange={(event) => setFim(event.target.value)} />
      </label>
      <Button type="submit" variant="outline" disabled={carregando}>Aplicar período</Button>
      <Button type="button" variant="ghost" disabled={carregando} onClick={() => {
        setInicio(''); setFim(''); financeiro.setPeriodo({ inicio: '', fim: '' }); financeiro.atualizar();
      }}>Ontem · fuso da conta</Button>
    </form>
    <p className="text-sm text-muted-foreground" role="status">
      {carregando ? 'Lendo o período no banco…' : erro ? 'Não foi possível ler as métricas. Tente novamente.' :
        dados?.periodo_inicio ? `${dados.periodo_inicio} → ${dados.periodo_fim} · ${dados.timezone ?? 'fuso não informado'}${dados.provisorio ? ' · período provisório' : ''}` : 'Aguardando dados desta campanha.'}
    </p>
    <p className="max-w-[80ch] text-[13px] leading-relaxed text-muted-foreground">
      Investimento: Meta Insights por conjunto. Receita: GAM pelo conjunto (utm_campaign leva o ID do conjunto),
      dentro do projeto e da conta GAM confirmados. <strong>A receita é atribuída ao conjunto; a campanha soma os conjuntos.</strong>{' '}
      Ausência permanece —; zero só aparece quando foi medido.
    </p>
    {dados && <p className="text-xs text-muted-foreground">
      Última leitura · Meta: {dados.frescor ?? 'sem carimbo'} · GAM: {dados.receita_frescor ?? 'sem carimbo'}.
      Valores exibidos são o último snapshot, não uma leitura ao vivo dos provedores.
    </p>}
    {!!dados?.impedimentos.length && <details className="text-sm text-muted-foreground">
      <summary className="cursor-pointer py-2">O que falta para completar estas métricas ({dados.impedimentos.length})</summary>
      <ul className="list-disc space-y-1 pl-5">{dados.impedimentos.map((codigo) =>
        <li key={codigo}>{MOTIVOS[codigo] ?? 'O contrato de leitura exige uma confirmação adicional.'}</li>)}</ul>
    </details>}
  </div>;
}
