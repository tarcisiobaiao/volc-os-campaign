import React from 'react';
import {
  Activity,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  DatabaseZap,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  pautadorApi,
  PautadorApiError,
  type ContaMetaLocal,
  type ResultadoDoPreflightMetaLocal,
  type InventarioMetaPersistido,
  type ReciboMetaReadModel,
} from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';

function mensagem(erro: unknown): string {
  return erro instanceof PautadorApiError || erro instanceof Error
    ? erro.message
    : 'Não foi possível concluir a leitura Meta.';
}

const ROTULOS: Record<string, string> = {
  campaign: 'campanhas',
  adset: 'conjuntos',
  ad: 'anúncios',
  creative: 'criativos',
  insight: 'linhas de insight',
  page: 'Páginas',
  instagram: 'perfis Instagram',
  pixel: 'pixels/datasets',
  custom_conversion: 'conversões personalizadas',
  insights: 'linhas de insight hoje',
};

const ENTIDADES = ['campanhas', 'conjuntos', 'anuncios', 'criativos', 'insights', 'mensuracao'] as const;

type Etapa = 'contas' | 'prova' | 'preparo' | 'persistencia';

const Conta: React.FC<{
  conta: ContaMetaLocal;
  selecionada: boolean;
  ocupada: boolean;
  aoProvar: () => void;
}> = ({ conta, selecionada, ocupada, aoProvar }) => (
  <button
    type="button"
    onClick={aoProvar}
    disabled={ocupada}
    aria-pressed={selecionada}
    className={cn(
      'group flex min-h-16 w-full items-center justify-between gap-4 rounded-lg border px-4 py-3 text-left',
      'transition-[border-color,background-color,box-shadow,transform] duration-150',
      'hover:-translate-y-px hover:border-primary/35 hover:bg-primary/[0.025] hover:shadow-sm',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      selecionada ? 'border-primary/40 bg-primary/[0.04] shadow-sm' : 'border-border bg-card',
    )}
  >
    <span className="min-w-0">
      <span className="block truncate text-sm font-semibold text-foreground">{conta.nome}</span>
      <span className="mt-1 block truncate text-xs text-muted-foreground">
        {conta.id_mascarado ?? 'ID não informado'} · {conta.moeda ?? 'moeda não lida'} · {conta.fuso ?? 'fuso não lido'}
      </span>
    </span>
    <span className="flex shrink-0 items-center gap-2 text-xs font-medium text-primary">
      {ocupada ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />}
      provar
    </span>
  </button>
);

const Sequencia: React.FC<{ etapa: Etapa | null }> = ({ etapa }) => {
  const passos: Array<[Etapa, string]> = [
    ['contas', 'Ler contas'],
    ['prova', 'Provar'],
    ['preparo', 'Preparar sincronização'],
    ['persistencia', 'Persistir snapshot'],
  ];
  return (
    <ol className="mt-4 grid gap-2 text-xs sm:grid-cols-4">
      {passos.map(([chave, rotulo]) => (
        <li key={chave} className={cn('rounded-lg border px-3 py-2', etapa === chave ? 'border-primary/35 bg-primary/10 text-primary' : 'border-border bg-card text-muted-foreground')}>
          {rotulo}
        </li>
      ))}
    </ol>
  );
};

const Resultado: React.FC<{ prova: ResultadoDoPreflightMetaLocal }> = ({ prova }) => {
  const conversoes = prova.mensuracao?.conversoes_personalizadas ?? [];
  return (
    <div className="mt-5 overflow-hidden rounded-xl border border-border bg-card shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border bg-muted/25 px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
            <h3 className="font-display text-base font-semibold">Leitura real concluída</h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {prova.conta.nome} · Graph {prova.api_version} · {prova.paginas_lidas} página{prova.paginas_lidas === 1 ? '' : 's'} lida{prova.paginas_lidas === 1 ? '' : 's'}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-success/25 bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden /> somente leitura
        </span>
      </div>

      <div className="grid gap-px bg-border sm:grid-cols-3 lg:grid-cols-5">
        {Object.entries(prova.contagens).map(([chave, valor]) => (
          <div key={chave} className="bg-card px-4 py-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{ROTULOS[chave] ?? chave}</p>
            <p className={cn('mt-1.5 text-xl font-semibold tabular-nums', valor == null ? 'text-warning' : 'text-foreground')}>
              {valor == null ? 'não lido' : valor.toLocaleString('pt-BR')}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div>
          <div className="flex items-center gap-2"><Activity className="h-4 w-4 text-primary" aria-hidden /><h4 className="text-sm font-semibold">Mensuração disponível</h4></div>
          {conversoes.length ? (
            <div className="mt-3 divide-y divide-border rounded-lg border border-border">
              {conversoes.map((conversao) => (
                <div key={conversao.referencia_opaca} className="flex flex-wrap items-center justify-between gap-3 px-3 py-3 text-xs">
                  <div className="min-w-0"><p className="truncate font-medium text-foreground">{conversao.nome}</p><p className="mt-1 text-muted-foreground">{conversao.custom_event_type ?? 'evento não informado'} · {conversao.id_mascarado ?? 'ID oculto'}</p></div>
                  <span className={cn('rounded-full border px-2 py-1 font-medium', conversao.estado === 'AVAILABLE_FIRED' ? 'border-success/25 bg-success/10 text-success' : 'border-warning/25 bg-warning/10 text-warning')}>{conversao.estado === 'AVAILABLE_FIRED' ? 'disparando' : conversao.estado.toLocaleLowerCase('pt-BR').replaceAll('_', ' ')}</span>
                </div>
              ))}
            </div>
          ) : <p className="mt-3 rounded-lg border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">Nenhuma conversão personalizada foi devolvida nesta leitura. Isso não cria nem altera conversões.</p>}
        </div>
        <aside className="rounded-lg border border-border bg-muted/20 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Capacidades</p>
          <p className="mt-2 text-sm font-semibold text-foreground">{prova.capacidades_disponiveis.length} leituras disponíveis</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{prova.erros.length ? `${prova.erros.length} capacidade(s) não puderam ser lidas; as demais continuam válidas.` : 'Hierarquia, mensuração e insights responderam sem bloqueio nesta prova.'}</p>
        </aside>
      </div>
    </div>
  );
};

const SnapshotPersistido: React.FC<{ inventario: InventarioMetaPersistido | null; recibo: InventarioMetaPersistido | null }> = ({ inventario, recibo }) => {
  if (!inventario?.has_snapshot) {
    const semSchema = inventario?.motivo === 'meta_schema_not_applied';
    return <div className="mt-5 rounded-xl border border-dashed border-border bg-muted/10 px-4 py-4 text-sm text-muted-foreground">{semSchema ? 'Persistência Meta ainda não instalada no Supabase oficial. A leitura local continua disponível, mas nenhum snapshot pode ser gravado até uma migration separadamente autorizada.' : 'Ainda não sincronizado. Nenhum dado fictício substitui a ausência de snapshot real.'}</div>;
  }
  const contas = inventario.contas ?? [];
  return (
    <div className="mt-5 rounded-xl border border-success/25 bg-success/5 px-4 py-4">
      <h3 className="text-sm font-semibold text-foreground">Snapshot persistido real disponível</h3>
      <p className="mt-1 text-xs text-muted-foreground">{contas.length} conta(s) no read model. Último recibo: {recibo?.recibo ? 'encontrado' : 'não lido'}.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {ENTIDADES.map((entidade) => <span key={entidade} className="rounded-md border border-border bg-card px-2 py-1 text-xs text-muted-foreground">{entidade}</span>)}
      </div>
    </div>
  );
};

export const MetaReadPreview: React.FC = () => {
  const [configurado, setConfigurado] = React.useState<boolean | null>(null);
  const [contas, setContas] = React.useState<ContaMetaLocal[]>([]);
  const [carregando, setCarregando] = React.useState(false);
  const [provando, setProvando] = React.useState<string | null>(null);
  const [prova, setProva] = React.useState<ResultadoDoPreflightMetaLocal | null>(null);
  const [erro, setErro] = React.useState<string | null>(null);
  const [etapa, setEtapa] = React.useState<Etapa | null>(null);
  const [inventario, setInventario] = React.useState<InventarioMetaPersistido | null>(null);
  const [recibo, setRecibo] = React.useState<InventarioMetaPersistido | null>(null);
  const [persistencia, setPersistencia] = React.useState<ReciboMetaReadModel | null>(null);

  const carregarPersistido = React.useCallback(async () => {
    try {
      const [contasPersistidas, ultimo] = await Promise.all([
        pautadorApi.contasMetaReadModel(),
        pautadorApi.ultimoReciboMetaLocal(),
      ]);
      setInventario(contasPersistidas);
      setRecibo(ultimo);
    } catch {
      setInventario({ ok: true, has_snapshot: false, motivo: 'backend_indisponivel' });
    }
  }, []);

  React.useEffect(() => {
    void pautadorApi.estadoMetaLocal().then((estado) => setConfigurado(estado.configurado)).catch(() => setConfigurado(false));
    void carregarPersistido();
  }, [carregarPersistido]);

  const carregarContas = async () => {
    setEtapa('contas'); setCarregando(true); setErro(null); setProva(null); setPersistencia(null);
    try { const resposta = await pautadorApi.contasMetaLocal(); setContas(resposta.contas); setConfigurado(true); }
    catch (causa) { setErro(mensagem(causa)); }
    finally { setCarregando(false); }
  };

  const provar = async (conta: ContaMetaLocal) => {
    setEtapa('prova'); setProvando(conta.referencia_opaca); setErro(null); setPersistencia(null);
    try { setProva(await pautadorApi.preflightMetaLocal(conta.referencia_opaca)); }
    catch (causa) { setErro(mensagem(causa)); }
    finally { setProvando(null); }
  };

  const preparar = async () => {
    if (!prova) return;
    setEtapa('preparo'); setErro(null);
    try { await pautadorApi.prepararSyncMetaLocal(prova.referencia_opaca); }
    catch (causa) { setErro(mensagem(causa)); }
  };

  const persistir = async () => {
    if (!prova) return;
    setEtapa('persistencia'); setErro(null); setPersistencia(null);
    try {
      const resultado = await pautadorApi.persistirSnapshotMetaLocal(prova.referencia_opaca);
      setPersistencia(resultado);
      await carregarPersistido();
    } catch (causa) {
      const corpo = (causa as { corpo?: unknown })?.corpo;
      if (typeof corpo === 'object' && corpo) {
        setPersistencia(corpo as ReciboMetaReadModel);
      } else {
        setErro(mensagem(causa));
      }
    }
  };

  return (
    <section aria-label="Leitura real Meta" className="mb-5 rounded-xl border border-primary/15 bg-gradient-to-br from-primary/[0.055] via-card to-card p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-[68ch]">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-primary"><DatabaseZap className="h-4 w-4" aria-hidden /> Graph API v26.0</div>
          <h2 className="mt-2 font-display text-xl font-semibold text-foreground">Meta real: ler, provar, preparar e persistir snapshot</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">O token permanece no Keychain/backend. A persistência é bloqueada por padrão e só executa com <code>META_READ_MODEL_WRITE_ENABLED=1</code> no servidor.</p>
        </div>
        <Button type="button" onClick={carregarContas} disabled={carregando} className="min-h-10">{carregando ? <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}{contas.length ? 'Reler contas' : 'Ler contas reais'}</Button>
      </div>
      <Sequencia etapa={etapa} />
      {configurado === false && <div className="mt-4 flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/5 px-3 py-3 text-xs text-warning"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />Abra a engrenagem no cabeçalho e valide o token deste Mac antes da prova.</div>}
      {erro && <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-3 text-sm text-destructive" role="alert">{erro}</div>}
      {contas.length > 0 && <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{contas.map((conta) => <Conta key={conta.referencia_opaca} conta={conta} selecionada={prova?.referencia_opaca === conta.referencia_opaca} ocupada={provando === conta.referencia_opaca} aoProvar={() => void provar(conta)} />)}</div>}
      {prova && <><Resultado prova={prova} /><div className="mt-4 flex flex-wrap gap-3"><Button type="button" variant="secondary" onClick={() => void preparar()}>Preparar sincronização</Button><Button type="button" variant="outline" onClick={() => void persistir()}>Persistir snapshot</Button></div></>}
      {persistencia && <div className="mt-4 rounded-lg border border-warning/25 bg-warning/5 px-3 py-3 text-xs text-warning">Persistência {persistencia.escrita ?? 'bloqueada'} · hash {persistencia.snapshot_hash ?? 'não emitido'} · sem token/ID cru no recibo.</div>}
      <SnapshotPersistido inventario={inventario} recibo={recibo} />
    </section>
  );
};

export default MetaReadPreview;
