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
  page: 'Páginas',
  instagram: 'perfis Instagram',
  pixel: 'pixels/datasets',
  custom_conversion: 'conversões personalizadas',
  insights: 'linhas de insight hoje',
};

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
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              {ROTULOS[chave] ?? chave}
            </p>
            <p className={cn('mt-1.5 text-xl font-semibold tabular-nums', valor == null ? 'text-warning' : 'text-foreground')}>
              {valor == null ? 'não lido' : valor.toLocaleString('pt-BR')}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" aria-hidden />
            <h4 className="text-sm font-semibold">Mensuração disponível</h4>
          </div>
          {conversoes.length ? (
            <div className="mt-3 divide-y divide-border rounded-lg border border-border">
              {conversoes.map((conversao) => (
                <div key={conversao.referencia_opaca} className="flex flex-wrap items-center justify-between gap-3 px-3 py-3 text-xs">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-foreground">{conversao.nome}</p>
                    <p className="mt-1 text-muted-foreground">
                      {conversao.custom_event_type ?? 'evento não informado'} · {conversao.id_mascarado ?? 'ID oculto'}
                    </p>
                  </div>
                  <span className={cn(
                    'rounded-full border px-2 py-1 font-medium',
                    conversao.estado === 'AVAILABLE_FIRED'
                      ? 'border-success/25 bg-success/10 text-success'
                      : 'border-warning/25 bg-warning/10 text-warning',
                  )}>
                    {conversao.estado === 'AVAILABLE_FIRED' ? 'disparando' : conversao.estado.toLocaleLowerCase('pt-BR').replaceAll('_', ' ')}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 rounded-lg border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
              Nenhuma conversão personalizada foi devolvida nesta leitura. Isso não cria nem altera conversões.
            </p>
          )}
        </div>

        <aside className="rounded-lg border border-border bg-muted/20 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Capacidades</p>
          <p className="mt-2 text-sm font-semibold text-foreground">{prova.capacidades_disponiveis.length} leituras disponíveis</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {prova.erros.length
              ? `${prova.erros.length} capacidade(s) não puderam ser lidas; as demais continuam válidas.`
              : 'Hierarquia, mensuração e insights responderam sem bloqueio nesta prova.'}
          </p>
          {prova.erros.length > 0 && (
            <ul className="mt-3 space-y-2 text-xs text-warning">
              {prova.erros.map((erro) => <li key={erro.capability}>• {erro.capability}: {erro.mensagem}</li>)}
            </ul>
          )}
        </aside>
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

  React.useEffect(() => {
    void pautadorApi.estadoMetaLocal()
      .then((estado) => setConfigurado(estado.configurado))
      .catch(() => setConfigurado(false));
  }, []);

  const carregarContas = async () => {
    setCarregando(true);
    setErro(null);
    setProva(null);
    try {
      const resposta = await pautadorApi.contasMetaLocal();
      setContas(resposta.contas);
      setConfigurado(true);
    } catch (causa) {
      setErro(mensagem(causa));
    } finally {
      setCarregando(false);
    }
  };

  const provar = async (conta: ContaMetaLocal) => {
    setProvando(conta.referencia_opaca);
    setErro(null);
    try {
      setProva(await pautadorApi.preflightMetaLocal(conta.referencia_opaca));
    } catch (causa) {
      setErro(mensagem(causa));
    } finally {
      setProvando(null);
    }
  };

  return (
    <section aria-label="Leitura real Meta" className="mb-5 rounded-xl border border-primary/15 bg-gradient-to-br from-primary/[0.055] via-card to-card p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-[68ch]">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-primary">
            <DatabaseZap className="h-4 w-4" aria-hidden /> Graph API v26.0
          </div>
          <h2 className="mt-2 font-display text-xl font-semibold text-foreground">Provar a conta real, sem alterar mídia</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            Lê contas, hierarquia, pixels/datasets, conversões personalizadas e insights. O token permanece no Keychain; não há criação, edição, ativação ou persistência no Supabase.
          </p>
        </div>
        <Button type="button" onClick={carregarContas} disabled={carregando} className="min-h-10">
          {carregando ? <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
          {contas.length ? 'Reler contas' : 'Ler contas reais'}
        </Button>
      </div>

      {configurado === false && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/5 px-3 py-3 text-xs text-warning">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Abra a engrenagem no cabeçalho e valide o token deste Mac antes da prova.
        </div>
      )}
      {erro && <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-3 text-sm text-destructive" role="alert">{erro}</div>}

      {contas.length > 0 && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {contas.map((conta) => (
            <Conta
              key={conta.referencia_opaca}
              conta={conta}
              selecionada={prova?.referencia_opaca === conta.referencia_opaca}
              ocupada={provando === conta.referencia_opaca}
              aoProvar={() => void provar(conta)}
            />
          ))}
        </div>
      )}
      {prova && <Resultado prova={prova} />}
    </section>
  );
};

export default MetaReadPreview;
