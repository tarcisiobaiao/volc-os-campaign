import React from 'react';
import { Settings2, FileDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { pautadorApi } from '@/lib/pautadorApi';
import type { ItemMetaReadModel } from '@/lib/pautadorApi';
import type { AcaoGestaoMeta, PedidoGestaoMeta, PropostaGestaoMeta } from '@/types/metaOperacao';
import { Campo, campo } from './primitivas';
import { reaisParaMinor } from './rascunho';

const ACOES: Array<[AcaoGestaoMeta, string]> = [
  ['PAUSAR', 'Pausar entrega'], ['ORCAMENTO_DIARIO', 'Alterar orçamento diário'],
  ['LANCE', 'Alterar estratégia de lance'], ['DUPLICAR_CONJUNTO', 'Duplicar conjunto com anúncios'],
];
const ROTULOS: Record<string, string> = {
  status: 'Estado configurado', daily_budget: 'Orçamento diário (centavos)',
  lifetime_budget: 'Orçamento vitalício (centavos)', bid_strategy: 'Estratégia de lance',
  bid_amount: 'Valor de lance (centavos)', daily_budget_minor: 'Novo orçamento diário (centavos)',
  bid_amount_minor: 'Novo limite de lance (centavos)', nome: 'Nome da cópia', incluir_anuncios: 'Copiar anúncios',
  moeda_proposta: 'Moeda proposta (confirmar na conta)',
};

/** Preparation only: the server has no management dispatch route. */
export function GestaoDaCampanha({ contaRef, campanhaRef, campanha, conjuntos, completo }: {
  contaRef: string;
  campanhaRef: string;
  campanha: ItemMetaReadModel;
  conjuntos: ItemMetaReadModel[];
  completo: boolean;
}) {
  const [alvo, setAlvo] = React.useState('campanha');
  const [acao, setAcao] = React.useState<AcaoGestaoMeta>('PAUSAR');
  const [valor, setValor] = React.useState('');
  const [estrategia, setEstrategia] = React.useState<NonNullable<PedidoGestaoMeta['estrategia']>>('LOWEST_COST_WITHOUT_CAP');
  const [nome, setNome] = React.useState('');
  const [proposta, setProposta] = React.useState<PropostaGestaoMeta | null>(null);
  const [erro, setErro] = React.useState('');
  const [lendo, setLendo] = React.useState(false);
  const versao = React.useRef(0);
  const entidade = alvo === 'campanha' ? 'campanha' : 'conjunto';
  const precisaValor = acao === 'ORCAMENTO_DIARIO' || (acao === 'LANCE' && estrategia !== 'LOWEST_COST_WITHOUT_CAP');
  const minor = reaisParaMinor(valor);

  function invalidar() { versao.current += 1; setProposta(null); setErro(''); }
  React.useEffect(() => { invalidar(); }, [campanha, conjuntos, completo]);
  React.useEffect(() => () => { versao.current += 1; }, []);
  async function preparar() {
    invalidar();
    const minhaVersao = versao.current;
    setLendo(true);
    try {
      const r = await pautadorApi.planejarGestaoMeta({
        conta_ref: contaRef, campanha_ref: campanhaRef, entidade,
        referencia: entidade === 'campanha' ? campanhaRef : alvo, acao,
        ...(precisaValor ? { valor_minor: minor! } : {}),
        ...(acao === 'LANCE' ? { estrategia } : {}),
        ...(acao === 'DUPLICAR_CONJUNTO' ? { nome: nome.trim() } : {}),
      });
      if (versao.current === minhaVersao) setProposta(r);
    } catch (e) {
      if (versao.current === minhaVersao) setErro(e instanceof Error ? e.message : 'Não foi possível preparar a proposta.');
    } finally { setLendo(false); }
  }
  function baixar() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(proposta, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = 'meta-proposta-nao-executavel.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <details className="rounded-lg border border-border bg-card shadow-card">
    <summary className="flex cursor-pointer items-center gap-2 p-4 font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <Settings2 className="h-4 w-4 text-primary" aria-hidden />Gestão da campanha
      <span className="ml-auto text-xs font-normal text-muted-foreground">Preparar alteração</span>
    </summary>
    <div className="space-y-4 border-t border-border p-4">
      <p className="max-w-[72ch] text-sm text-muted-foreground">Prepare a mudança da campanha ou de um conjunto com seus valores anteriores. Esta etapa não aplica alterações na Meta. A execução de gestão ainda precisa ser integrada.</p>
      {!completo && <p role="status" className="text-sm text-warning">Carregue a leitura completa dos conjuntos antes de preparar uma alteração.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <Campo id="meta-gestao-alvo" rotulo="Onde alterar">
          <select id="meta-gestao-alvo" className={campo} value={alvo} onChange={(e) => { invalidar(); setAlvo(e.target.value); if (e.target.value === 'campanha' && acao === 'DUPLICAR_CONJUNTO') setAcao('PAUSAR'); }}>
            <option value="campanha">Campanha: {String(campanha.nome ?? 'campanha aberta')}</option>
            {conjuntos.filter(c => c.entity_ref).map(c => <option key={String(c.entity_ref)} value={String(c.entity_ref)}>Conjunto: {String(c.nome ?? c.id_mascarado ?? 'sem nome')}</option>)}
          </select>
        </Campo>
        <Campo id="meta-gestao-acao" rotulo="Alteração proposta">
          <select id="meta-gestao-acao" className={campo} value={acao} onChange={(e) => { invalidar(); setAcao(e.target.value as AcaoGestaoMeta); setValor(''); }}>
            {ACOES.filter(([a]) => a !== 'DUPLICAR_CONJUNTO' || entidade === 'conjunto').map(([a, label]) => <option key={a} value={a}>{label}</option>)}
          </select>
        </Campo>
        {acao === 'LANCE' && <Campo id="meta-gestao-lance" rotulo="Estratégia desejada" ajuda="A compatibilidade com objetivo e otimização será conferida antes da execução.">
          <select id="meta-gestao-lance" className={campo} value={estrategia} onChange={(e) => { invalidar(); setEstrategia(e.target.value as typeof estrategia); setValor(''); }}>
            <option value="LOWEST_COST_WITHOUT_CAP">Maior volume, sem limite de lance</option><option value="COST_CAP">Meta de custo por resultado</option><option value="LOWEST_COST_WITH_BID_CAP">Limite de lance</option>
          </select>
        </Campo>}
        {precisaValor && <Campo id="meta-gestao-valor" rotulo={acao === 'ORCAMENTO_DIARIO' ? 'Novo orçamento diário em R$ (proposta BRL)' : 'Limite em R$ (proposta BRL)'} ajuda="Moeda e orçamento vigente precisam ser confirmados na conta antes de executar.">
          <Input id="meta-gestao-valor" inputMode="decimal" value={valor} onChange={e => { invalidar(); setValor(e.target.value); }} placeholder="Ex.: 25,00" />
        </Campo>}
        {acao === 'DUPLICAR_CONJUNTO' && <Campo id="meta-gestao-nome" rotulo="Nome do novo conjunto" largo ajuda="A cópia terá outro ID e receita própria. O histórico permanece no conjunto original.">
          <Input id="meta-gestao-nome" value={nome} maxLength={200} onChange={e => { invalidar(); setNome(e.target.value); }} />
        </Campo>}
      </div>
      {acao === 'ORCAMENTO_DIARIO' && <p className="text-sm text-muted-foreground">CBO: orçamento na campanha. ABO: orçamento em cada conjunto. Orçamento vitalício exige uma proposta específica.</p>}
      {acao === 'DUPLICAR_CONJUNTO' && <p className="text-sm text-muted-foreground">O conjunto e seus anúncios serão propostos como pausados. As UTMs deverão usar o novo ID do conjunto, sem copiar IDs fixos da origem.</p>}
      <Button type="button" variant="outline" onClick={preparar} disabled={lendo || !completo || (precisaValor && (!minor || minor > 100_000_000)) || (acao === 'DUPLICAR_CONJUNTO' && !nome.trim())}>{lendo ? 'Preparando…' : 'Conferir proposta sem aplicar'}</Button>
      {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
      {proposta && <div aria-live="polite" className="space-y-3 border-t border-border pt-4">
        <h3 className="font-semibold">Proposta preparada, nenhuma alteração aplicada</h3>
        <p className="text-sm">{proposta.efeito_proposto}</p>
        <p className="text-xs text-muted-foreground">Estado observado em: {proposta.observado_em ?? 'data não disponível'}. Valores não observados permanecem desconhecidos.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          {([['Antes, na leitura disponível', proposta.antes], ['Depois, se autorizado e executado', proposta.depois]] as const).map(([titulo, valores]) => <div key={titulo}><h4 className="mb-2 text-sm font-medium">{titulo}</h4><dl className="divide-y divide-border text-sm">{Object.entries(valores).map(([k,v]) => <div key={k} className="flex flex-wrap justify-between gap-2 py-2"><dt className="text-muted-foreground">{ROTULOS[k] ?? k}</dt><dd className="break-all font-medium">{v == null ? 'Não observado' : v === true ? 'Sim' : String(v)}</dd></div>)}</dl></div>)}
        </div>
        <p className="text-sm text-muted-foreground">{proposta.receita}</p>
        <details><summary className="cursor-pointer text-sm font-medium">O que falta para executar</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{proposta.requisitos_para_executar.map(r => <li key={r}>{r}</li>)}</ul></details>
        <Button type="button" variant="ghost" size="sm" className="gap-2" onClick={baixar}><FileDown className="h-4 w-4" aria-hidden />Baixar proposta</Button>
        <p className="text-xs text-muted-foreground">A proposta não foi salva no banco. Baixe para guardar; ela não autoriza execução.</p>
      </div>}
    </div>
  </details>;
}
