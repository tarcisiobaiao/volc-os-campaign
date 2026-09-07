/**
 * Um objeto Meta — REAL por padrão, demonstrativo só por `?modo=demo`.
 *
 * ---------------------------------------------------------------------------
 * O QUE MUDOU E POR QUÊ
 * ---------------------------------------------------------------------------
 *
 * A página inteira lia `objetoMetaDemo(tipo, id)` e, quando o identificador não
 * estava no dicionário fictício, fazia `<Navigate>` para a lista. Como o
 * dicionário fictício é a ÚNICA fonte que ela conhecia, toda identidade real —
 * um `metaobj_…` de um recibo de criação, um UUID do read model — caía no
 * redirecionamento e sumia sem uma palavra. O operador que clicasse num objeto
 * recém-criado era mandado de volta para a lista, e a única conclusão possível
 * é que o objeto não existe.
 *
 * Agora a identidade é resolvida CONTRA O READ MODEL, dentro de uma conta, e a
 * demonstração só abre quando a URL pede demonstração. Nenhuma ausência, falha
 * ou recusa de escopo leva ao cenário fictício: cada uma delas tem nome e fica
 * na tela.
 *
 * `referencia` aceita as duas identidades públicas — o UUID persistido e o
 * `metaobj_…` do recibo —, porque o servidor recalcula as duas a partir do mesmo
 * par (conta, id externo) e compara com as duas. Um handle de recibo deixa de
 * ser um beco sem saída na interface.
 *
 * ---------------------------------------------------------------------------
 * OS BOTÕES QUE SAÍRAM
 * ---------------------------------------------------------------------------
 *
 * "Editar", "Pausar" e "Alterar configuração" eram controles desabilitados com
 * um `title` explicando que o ato não existe. Um controle sem ato por trás
 * ensina que o ato está disponível — e o operador descobre que não está no
 * momento em que precisava dele. Neste marco a capacidade é LER, e a tela
 * mostra o que sabe fazer.
 */
import React from 'react';
import {
  ArrowLeft,
  BarChart3,
  GitBranch,
  Image as ImageIcon,
  Megaphone,
} from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { CirclePause, CirclePlay, FileClock, History, Info } from 'lucide-react';
import { FaixaDeDemonstracao } from '@/components/campaign/MetaDemoStatus';
import {
  EscolhaDeConta,
  EstadoDoReadModel,
  SeloDeEstadoMeta,
  useDetalheDoReadModel,
  useEscopoDeConta,
  usePaginaDoReadModel,
} from '@/components/trafego/meta/MetaCampaignReadView';
import {
  EsqueletoDoInventario,
  FalhaDoInventario,
  InventarioVazio,
} from '@/components/trafego/inventario/EstadosDoInventario';
import { AUSENTE, horaDeLeitura } from '@/components/trafego/inventario/formato';
import type { EntidadeMetaReadModel, ItemMetaReadModel } from '@/lib/pautadorApi';
import {
  META_DEMO,
  ROTULOS_META,
  objetoMetaDemo,
  type ObjetoMetaDemo,
  type TipoMeta,
} from '@/components/trafego/meta/modelo';

const TIPOS: TipoMeta[] = ['campanhas', 'conjuntos', 'anuncios', 'criativos'];

/** A chave primária persistida de cada nível — é por ela que o pai casa. */
const CHAVE_DO_TIPO: Record<TipoMeta, keyof ItemMetaReadModel> = {
  campanhas: 'meta_campaign_id',
  conjuntos: 'meta_adset_id',
  anuncios: 'meta_ad_id',
  criativos: 'meta_creative_id',
};

/** O nível abaixo, e a coluna pela qual o filho aponta para o pai. */
const FILHO_DO_TIPO: Partial<Record<TipoMeta, { tipo: TipoMeta; coluna: keyof ItemMetaReadModel }>> = {
  campanhas: { tipo: 'conjuntos', coluna: 'meta_campaign_id' },
  conjuntos: { tipo: 'anuncios', coluna: 'meta_adset_id' },
};

const Campo: React.FC<{ rotulo: string; valor: React.ReactNode; ajuda?: string }> = ({ rotulo, valor, ajuda }) => (
  <div className="min-w-0 border-b border-border py-3 last:border-0">
    <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{rotulo}</dt>
    <dd className="mt-1 break-words text-sm font-medium text-foreground">{valor}</dd>
    {ajuda && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{ajuda}</p>}
  </div>
);

const texto = (valor: unknown): string =>
  typeof valor === 'string' && valor.trim() !== '' ? valor : AUSENTE;

// ═══════════════════════════════════════════════════════════════════════════
// A LEITURA REAL
// ═══════════════════════════════════════════════════════════════════════════

const FilhosReais: React.FC<{
  tipo: TipoMeta;
  pai: ItemMetaReadModel;
  contaRef: string;
}> = ({ tipo, pai, contaRef }) => {
  const filho = FILHO_DO_TIPO[tipo];
  const pagina = usePaginaDoReadModel(
    (filho?.tipo ?? 'conjuntos') as EntidadeMetaReadModel,
    contaRef,
    Boolean(filho),
  );

  if (!filho) {
    return (
      <p className="rounded-md border border-dashed border-border px-4 py-6 text-[13px] text-muted-foreground">
        Este nível não tem um nível subordinado no contrato do read model.
      </p>
    );
  }
  if (pagina.leitura.fase === 'lendo') return <EsqueletoDoInventario contas={1} linhas={3} />;
  if (pagina.leitura.fase === 'falhou') {
    return (
      <FalhaDoInventario ocorrencia={pagina.leitura.ocorrencia} aoTentarDeNovo={pagina.recarregar} />
    );
  }
  if (pagina.leitura.resposta.estado !== 'COM_SNAPSHOT') {
    return (
      <EstadoDoReadModel
        estado={pagina.leitura.resposta.estado}
        aoTentarDeNovo={pagina.recarregar}
      />
    );
  }

  const chavePai = String(pai[CHAVE_DO_TIPO[tipo]] ?? '');
  const filhos = pagina.leitura.resposta.items.filter(
    (item) => String(item[filho.coluna] ?? '') === chavePai,
  );

  // A lista de filhos sai de UMA página filtrada no cliente. Se essa página não
  // é o inventário inteiro da conta, "nenhum filho apareceu" não é ausência: é
  // uma pergunta que ainda não terminou de ser respondida, e a tela precisa
  // dizer qual das duas está mostrando.
  const paginaCompleta =
    pagina.leitura.resposta.completo === true && pagina.leitura.resposta.has_more !== true;

  if (filhos.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border px-4 py-6 text-[13px] text-muted-foreground">
        {paginaCompleta ? (
          <>
            Nenhum {ROTULOS_META[filho.tipo].singular.toLocaleLowerCase('pt-BR')} deste objeto
            apareceu no que foi lido. Isso é o que o snapshot contém — não uma afirmação de que
            ele não existe na Meta.
          </>
        ) : (
          <>
            A leitura de {ROTULOS_META[filho.tipo].plural.toLocaleLowerCase('pt-BR')} desta conta
            não veio inteira, então <strong>não dá para dizer</strong> se este objeto tem filhos.
            Isto é diferente de não ter nenhum.
            {pagina.leitura.resposta.motivo ? ` Motivo: ${pagina.leitura.resposta.motivo}.` : ''}
          </>
        )}
      </p>
    );
  }

  const avisoDeParcialidade = paginaCompleta ? null : (
    <p className="rounded-md border border-dashed border-warning/40 bg-warning/5 px-4 py-3 text-[13px] text-muted-foreground">
      A leitura desta conta não veio inteira; podem existir outros
      {' '}{ROTULOS_META[filho.tipo].plural.toLocaleLowerCase('pt-BR')} além dos listados.
      {pagina.leitura.resposta.motivo ? ` Motivo: ${pagina.leitura.resposta.motivo}.` : ''}
    </p>
  );

  return (
    <div className="space-y-3">
      {avisoDeParcialidade}
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full min-w-[36rem] text-left text-sm">
        <thead className="bg-muted/60 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-semibold">Estado</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Nome</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Identidade</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Observado em</th>
          </tr>
        </thead>
        <tbody>
          {filhos.map((item, i) => {
            const ref = String(item.entity_ref ?? item[CHAVE_DO_TIPO[filho.tipo]] ?? '');
            return (
              <tr key={ref || i} className="border-t border-border align-top hover:bg-muted/20">
                <td className="px-4 py-3">
                  <SeloDeEstadoMeta estado={item.effective_status} />
                </td>
                <td className="px-4 py-3">
                  <Link
                    className="block max-w-[38ch] break-words font-medium text-primary hover:underline"
                    to={`/trafego/meta/${filho.tipo}/${encodeURIComponent(ref)}?conta=${encodeURIComponent(contaRef)}`}
                  >
                    {texto(item.nome)}
                  </Link>
                </td>
                <td className="px-4 py-3 tabular text-[12px] text-muted-foreground">
                  {texto(item.id_mascarado)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-[12px] text-muted-foreground">
                  {horaDeLeitura(item.observado_em as string | null) ?? AUSENTE}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </div>
  );
};

/** A peça vinculada a um anúncio — o único "filho" que vem por vínculo. */
const PecaDoAnuncio: React.FC<{ anuncio: ItemMetaReadModel; contaRef: string }> = ({
  anuncio,
  contaRef,
}) => {
  const vinculos = usePaginaDoReadModel('vinculos', contaRef);
  const criativos = usePaginaDoReadModel('criativos', contaRef);

  if (vinculos.leitura.fase === 'lendo' || criativos.leitura.fase === 'lendo') {
    return <EsqueletoDoInventario contas={1} linhas={1} />;
  }
  if (vinculos.leitura.fase === 'falhou') {
    return (
      <FalhaDoInventario
        ocorrencia={vinculos.leitura.ocorrencia}
        aoTentarDeNovo={vinculos.recarregar}
      />
    );
  }
  if (criativos.leitura.fase === 'falhou') {
    return (
      <FalhaDoInventario
        ocorrencia={criativos.leitura.ocorrencia}
        aoTentarDeNovo={criativos.recarregar}
      />
    );
  }
  const idDoAnuncio = String(anuncio.meta_ad_id ?? '');
  const vinculo = vinculos.leitura.resposta.items.find(
    (v) => String(v.meta_ad_id ?? '') === idDoAnuncio,
  );
  const criativo = vinculo
    ? criativos.leitura.resposta.items.find(
        (c) => String(c.meta_creative_id ?? '') === String(vinculo.meta_creative_id ?? ''),
      )
    : undefined;

  if (!criativo) {
    return (
      <p className="rounded-md border border-dashed border-border px-4 py-6 text-[13px] text-muted-foreground">
        {AUSENTE} nenhuma peça vinculada a este anúncio apareceu nesta leitura.
      </p>
    );
  }
  return (
    <div className="rounded-md border border-border px-4 py-4">
      <div className="flex items-start gap-2">
        <ImageIcon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0">
          <p className="break-words font-medium">{texto(criativo.nome)}</p>
          {/* `object_story_id` é `<page_id>_<post_id>` — identificador BRUTO da
              Meta. O backend passou a removê-lo do DTO; a tela não volta a
              exibi-lo nem se um dia ele reaparecer na resposta. */}
          <p className="mt-1 break-all text-[12px] text-muted-foreground">
            {texto(criativo.entity_ref)}
          </p>
        </div>
      </div>
    </div>
  );
};

const ObjetoReal: React.FC<{ tipo: TipoMeta; referencia: string }> = ({ tipo, referencia }) => {
  const [params, setParams] = useSearchParams();
  const escopo = useEscopoDeConta(params.get('conta'));
  const { contaRef, contas } = escopo;
  const detalhe = useDetalheDoReadModel(tipo as EntidadeMetaReadModel, referencia, contaRef);
  const rotulo = ROTULOS_META[tipo];

  const escolher = React.useCallback(
    (proxima: string) => {
      escopo.escolher(proxima);
      const proximos = new URLSearchParams(params);
      proximos.set('conta', proxima);
      setParams(proximos, { replace: true });
    },
    [escopo, params, setParams],
  );

  const item = detalhe.leitura.fase === 'respondeu' ? detalhe.leitura.resposta.item : null;

  let corpo: React.ReactNode;
  if (escopo.leitura.fase === 'lendo') {
    corpo = <EsqueletoDoInventario contas={1} linhas={3} />;
  } else if (escopo.leitura.fase === 'falhou') {
    corpo = (
      <FalhaDoInventario ocorrencia={escopo.leitura.ocorrencia} aoTentarDeNovo={escopo.recarregar} />
    );
  } else if (escopo.leitura.resposta.estado !== 'COM_SNAPSHOT') {
    corpo = (
      <EstadoDoReadModel estado={escopo.leitura.resposta.estado} aoTentarDeNovo={escopo.recarregar} />
    );
  } else if (contas.length === 0) {
    corpo = <InventarioVazio />;
  } else if (!contaRef) {
    corpo = (
      <div className="space-y-4">
        <EstadoDoReadModel
          estado={escopo.escopoDesconhecido ? 'ESCOPO_DESCONHECIDO' : 'ESCOPO_OBRIGATORIO'}
        />
        <EscolhaDeConta
          contas={contas}
          escolhida={null}
          aoEscolher={escolher}
          forcarVisibilidade={escopo.escopoDesconhecido}
        />
      </div>
    );
  } else if (detalhe.leitura.fase === 'lendo') {
    corpo = <EsqueletoDoInventario contas={1} linhas={3} />;
  } else if (detalhe.leitura.fase === 'falhou') {
    corpo = (
      <FalhaDoInventario
        ocorrencia={detalhe.leitura.ocorrencia}
        aoTentarDeNovo={detalhe.recarregar}
      />
    );
  } else if (!item) {
    corpo = (
      <div className="space-y-4">
        <EstadoDoReadModel
          estado={detalhe.leitura.resposta.estado}
          aoTentarDeNovo={detalhe.recarregar}
        />
        <EscolhaDeConta contas={contas} escolhida={contaRef} aoEscolher={escolher} />
      </div>
    );
  } else {
    corpo = (
      <>
        <EscolhaDeConta contas={contas} escolhida={contaRef} aoEscolher={escolher} />
        <Tabs defaultValue="visao" className="mt-4">
          <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-lg border border-border bg-muted p-1">
            <TabsTrigger value="visao">Visão geral</TabsTrigger>
            <TabsTrigger value="estrutura">Estrutura</TabsTrigger>
          </TabsList>

          <TabsContent value="visao" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
            <div className="flex items-center gap-2 border-b border-border pb-4">
              <BarChart3 className="h-4 w-4 text-primary" aria-hidden />
              <h2 className="font-display text-lg font-semibold">Leitura do read model</h2>
            </div>
            <dl className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
              <Campo
                rotulo="Estado efetivo"
                valor={<SeloDeEstadoMeta estado={item.effective_status} />}
                ajuda="effective_status, como a Meta o declara"
              />
              <Campo rotulo="Estado configurado" valor={texto(item.status)} />
              <Campo
                rotulo={tipo === 'conjuntos' ? 'Otimização' : 'Objetivo'}
                valor={texto(tipo === 'conjuntos' ? item.optimization_goal : item.objetivo)}
                ajuda="ausência não é convertida em zero nem em texto inventado"
              />
              <Campo
                rotulo="Identidade pública"
                valor={<span className="break-all">{texto(item.entity_ref)}</span>}
                ajuda="o identificador cru da Meta é removido no servidor e nunca chega aqui"
              />
              <Campo rotulo="Identificador mascarado" valor={texto(item.id_mascarado)} />
              <Campo
                rotulo="Observado em"
                valor={horaDeLeitura(item.observado_em as string | null) ?? AUSENTE}
                ajuda="instante da leitura que trouxe esta linha"
              />
              {tipo === 'criativos' && (
                <Campo
                  rotulo="Peça (object_story_id)"
                  valor={<span className="break-all">{texto(item.object_story_id)}</span>}
                />
              )}
            </dl>
          </TabsContent>

          <TabsContent value="estrutura" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
            <div className="mb-3 flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-primary" aria-hidden />
              <h2 className="font-display text-lg font-semibold">
                {tipo === 'anuncios' ? 'Peça vinculada' : 'Estrutura subordinada'}
              </h2>
            </div>
            {tipo === 'anuncios' ? (
              <PecaDoAnuncio anuncio={item} contaRef={contaRef} />
            ) : (
              <FilhosReais tipo={tipo} pai={item} contaRef={contaRef} />
            )}
          </TabsContent>
        </Tabs>
      </>
    );
  }

  return (
    <main className="p-4 md:p-8">
      <header className="mb-6">
        <Link
          to={`/trafego?rede=meta&nivel=${tipo}`}
          className="inline-flex min-h-9 items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden /> Meta Ads · {rotulo.plural}
        </Link>
        <div className="mt-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Megaphone className="h-3.5 w-3.5" aria-hidden />
          </span>
          {rotulo.singular} · leitura real
        </div>
        <h1 className="mt-2 max-w-4xl text-balance break-words font-display text-[2rem] font-bold leading-[1.05] tracking-tight md:text-[2.4rem]">
          {item ? texto(item.nome) : rotulo.singular}
        </h1>
        <div className="aurora-rule mt-3 w-16" aria-hidden />
        <p className="mt-3 max-w-[80ch] break-all text-sm text-muted-foreground">
          Identidade pedida: {referencia}
        </p>
        <p className="mt-1 max-w-[80ch] text-sm text-muted-foreground">
          Somente leitura. Não há ativação, edição nem ato de orçamento neste marco — e por isso
          não há botão para nenhum deles.
        </p>
      </header>
      {corpo}
    </main>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// A DEMONSTRAÇÃO — atrás de `?modo=demo`, e dizendo que é
// ═══════════════════════════════════════════════════════════════════════════

const Estado: React.FC<{ valor: ObjetoMetaDemo['status'] }> = ({ valor }) => {
  const config = valor === 'ATIVO'
    ? { variante: 'success' as const, icone: CirclePlay, texto: 'Ativo' }
    : valor === 'PAUSADO'
      ? { variante: 'outline' as const, icone: CirclePause, texto: 'Pausado' }
      : { variante: 'warning' as const, icone: FileClock, texto: 'Rascunho' };
  const Icone = config.icone;
  return <Badge variant={config.variante}><Icone className="h-3.5 w-3.5" aria-hidden />{config.texto}</Badge>;
};

function descendentes(objeto: ObjetoMetaDemo): ObjetoMetaDemo[] {
  const indice = TIPOS.indexOf(objeto.tipo);
  if (indice < 0 || indice === TIPOS.length - 1) return [];
  return META_DEMO[TIPOS[indice + 1]].filter((filho) => filho.paiId === objeto.id);
}

const Estrutura: React.FC<{ objeto: ObjetoMetaDemo }> = ({ objeto }) => {
  const filhos = descendentes(objeto);
  const proximoTipo = TIPOS[TIPOS.indexOf(objeto.tipo) + 1];
  return (
    <section aria-labelledby="estrutura-meta">
      <div className="mb-3 flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-primary" aria-hidden />
        <h2 id="estrutura-meta" className="font-display text-lg font-semibold">Estrutura subordinada</h2>
      </div>
      {filhos.length ? (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="bg-muted/60 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
              <tr><th className="px-4 py-2.5">Estado</th><th className="px-4 py-2.5">Nome</th><th className="px-4 py-2.5">Entrega</th><th className="px-4 py-2.5 text-right">Resultado</th></tr>
            </thead>
            <tbody>
              {filhos.map((filho) => (
                <tr key={filho.id} className="border-t border-border hover:bg-muted/20">
                  <td className="px-4 py-3"><Estado valor={filho.status} /></td>
                  <td className="px-4 py-3 font-medium">
                    <Link className="text-primary hover:underline" to={`/trafego/meta/${proximoTipo}/${filho.id}?modo=demo`}>{filho.nome}</Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{filho.entrega}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{filho.resultado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
          Este cenário não possui um nível subordinado para exibir.
        </div>
      )}
    </section>
  );
};

const ObjetoDemo: React.FC<{ tipo: TipoMeta; objetoId: string }> = ({ tipo, objetoId }) => {
  const objeto = objetoMetaDemo(tipo, objetoId);
  const rotulo = ROTULOS_META[tipo];

  if (!objeto) {
    return (
      <main className="space-y-4 p-4 md:p-8">
        <FaixaDeDemonstracao oQue="Esta rota foi aberta em modo demonstrativo." />
        <div className="rounded-md border border-border bg-card px-4 py-6" role="status">
          <h2 className="font-display text-base font-semibold">
            Este identificador não existe no cenário demonstrativo
          </h2>
          <p className="mt-2 max-w-[74ch] text-[13px] leading-relaxed text-muted-foreground">
            O cenário fictício tem um punhado de objetos inventados, e{' '}
            <span className="tabular break-all font-medium text-foreground">{objetoId}</span> não é
            um deles. Isto não diz nada sobre o objeto real de mesma identidade: para lê-lo, abra
            esta rota sem <code className="rounded-sm bg-muted px-1 py-0.5">modo=demo</code>.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="p-4 md:p-8">
      <header className="mb-6">
        <div className="min-w-0">
          <Link to={`/trafego?rede=meta&nivel=${tipo}`} className="inline-flex min-h-9 items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" aria-hidden /> Meta Ads · {rotulo.plural}
          </Link>
          <div className="mt-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary"><Megaphone className="h-3.5 w-3.5" aria-hidden /></span>
            {rotulo.singular} · demonstração
          </div>
          <h1 className="mt-2 max-w-4xl text-balance font-display text-[2rem] font-bold leading-[1.05] tracking-tight md:text-[2.4rem]">{objeto.nome}</h1>
          <div className="aurora-rule mt-3 w-16" aria-hidden />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Estado valor={objeto.status} />
            <span className="text-sm text-muted-foreground">{objeto.objetivo ?? objeto.detalhe}</span>
          </div>
        </div>
        <FaixaDeDemonstracao
          className="mt-5"
          oQue="A arquitetura desta página é real; identidade, entrega e métricas são fictícias e não vieram de uma conta Meta."
        />
      </header>

      <Tabs defaultValue="visao">
        <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-lg border border-border bg-muted p-1">
          <TabsTrigger value="visao">Visão geral</TabsTrigger>
          <TabsTrigger value="estrutura">Estrutura</TabsTrigger>
          <TabsTrigger value="configuracao">Configuração</TabsTrigger>
          <TabsTrigger value="historico">Histórico</TabsTrigger>
        </TabsList>

        <TabsContent value="visao" className="mt-5">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
            <div className="rounded-md border border-border bg-card p-5 shadow-card">
              <div className="flex items-center gap-2 border-b border-border pb-4">
                <BarChart3 className="h-4 w-4 text-primary" aria-hidden />
                <h2 className="font-display text-lg font-semibold">Leitura operacional</h2>
              </div>
              <dl className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
                <Campo rotulo="Entrega" valor={objeto.entrega ?? 'Não aplicável'} ajuda="effective_status no read model real" />
                <Campo rotulo="Orçamento" valor={objeto.orcamento ?? 'Não definido'} ajuda="ausência não é convertida em zero" />
                <Campo rotulo="Resultado" valor={objeto.resultado ?? AUSENTE} ajuda="cenário fictício" />
                <Campo rotulo="Custo" valor={objeto.custo ?? AUSENTE} ajuda="cenário fictício" />
                <Campo rotulo="Origem" valor="Meta Marketing API v26.0" ajuda="read model previsto; sem leitura nesta tela" />
                <Campo rotulo="Frescor" valor="Demonstração" ajuda="nenhuma data externa foi observada" />
              </dl>
              <div className="mt-6"><Estrutura objeto={objeto} /></div>
            </div>

            <aside className="rounded-md border border-border bg-card p-5 shadow-card" aria-label="O que falta para haver ato">
              <div className="flex items-center gap-2">
                <Info className="h-4 w-4 text-info" aria-hidden />
                <h2 className="font-display text-lg font-semibold">Para haver ato</h2>
              </div>
              {/* ⚠️ Os botões "Pausar" e "Alterar configuração" saíram daqui.
                  Desabilitados, eles ainda ensinavam que os atos existem — e a
                  lista abaixo diz a mesma coisa sem simular um controle. */}
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                Nenhum ato de mídia existe neste marco, nem aqui nem na leitura real. O caminho
                até o primeiro é este:
              </p>
              <ol className="mt-4 space-y-2 text-xs leading-relaxed text-muted-foreground">
                <li>1. provar token e conta em somente leitura</li>
                <li>2. sincronizar este objeto no read model</li>
                <li>3. aprovar contrato de escrita e recibo</li>
              </ol>
            </aside>
          </div>
        </TabsContent>

        <TabsContent value="estrutura" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card"><Estrutura objeto={objeto} /></TabsContent>
        <TabsContent value="configuracao" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
          <h2 className="font-display text-lg font-semibold">Contrato da configuração</h2>
          <dl className="mt-3 grid gap-x-8 sm:grid-cols-2">
            <Campo rotulo="Status configurado" valor={objeto.status} />
            <Campo rotulo="Status efetivo" valor={objeto.entrega ?? 'Não lido'} />
            <Campo rotulo="Objeto pai" valor={objeto.pai ?? 'Conta de anúncios'} />
            <Campo rotulo="Identidade externa" valor="oculta na demonstração" />
          </dl>
        </TabsContent>
        <TabsContent value="historico" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
          <div className="flex items-center gap-2"><History className="h-4 w-4 text-primary" aria-hidden /><h2 className="font-display text-lg font-semibold">Histórico e recibos</h2></div>
          <p className="mt-3 text-sm text-muted-foreground">Nenhum evento real existe neste cenário demonstrativo. A linha do tempo não inventa alterações.</p>
        </TabsContent>
      </Tabs>
    </main>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// A ROTA
// ═══════════════════════════════════════════════════════════════════════════

const MetaObjetoPage: React.FC = () => {
  const params = useParams<{ tipo: string; objetoId: string }>();
  const [busca] = useSearchParams();
  const tipo = params.tipo as TipoMeta;

  // ⚠️ Um tipo desconhecido não redireciona em silêncio: ele DIZ o que não
  // reconheceu. Trocar de página é a resposta que faz o operador acreditar que
  // o que ele pediu não existe.
  if (!TIPOS.includes(tipo)) {
    return (
      <Layout>
        <main className="p-4 md:p-8">
          <div className="rounded-md border border-border bg-card px-4 py-6" role="status">
            <h1 className="font-display text-lg font-semibold">Nível Meta não reconhecido</h1>
            <p className="mt-2 max-w-[74ch] text-[13px] leading-relaxed text-muted-foreground">
              Esta rota conhece quatro níveis — campanhas, conjuntos, anúncios e criativos — e{' '}
              <span className="break-all font-medium text-foreground">{params.tipo}</span> não é um
              deles.{' '}
              <Link to="/trafego?rede=meta" className="text-primary underline-offset-2 hover:underline">
                voltar para Meta Ads
              </Link>
            </p>
          </div>
        </main>
      </Layout>
    );
  }

  const objetoId = params.objetoId ?? '';
  const modoDemo = busca.get('modo') === 'demo';

  return (
    <Layout>
      {modoDemo ? (
        <ObjetoDemo tipo={tipo} objetoId={objetoId} />
      ) : (
        <ObjetoReal tipo={tipo} referencia={objetoId} />
      )}
    </Layout>
  );
};

export default MetaObjetoPage;
