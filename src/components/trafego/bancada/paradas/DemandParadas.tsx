import React from 'react';
import {
  CircleDashed, Film, Globe2, Image as ImageIcon, LayoutTemplate,
  MessageSquareText, ScanSearch, ShieldCheck, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type {
  AssetDemandGen, CanalSelecionavelDemandGen, EstrategiaDeCanaisDemandGen,
} from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';
import { Input } from '@/components/ui/input';
import {
  AcaoDeProva, CampoDeTexto, EditorDeLista, EscolhaExplicita, IrParaEstudio, SeletorDeAsset,
} from './ControlesMulticanal';
import {
  CampoLista, CampoSelecao, CampoTexto, DecisaoSimNao, EditorDeAgenda, Interruptor, MultiEscolha,
  Repetidor, Secao, ErroDoCampo,
} from '../campos/Campos';
import { AvisosDaRevisao, ErrosDeForma, ResumoDoCanal } from './RevisaoDoCanal';
import { motivoIndisponivelPorHttp, opcoesDoEsquema } from '@/lib/trafego/configuracao/esquema';
import type { FormDemandGen, FormLookalike } from '@/lib/trafego/configuracao/formularios';
import type { ErrosDoServidor } from '@/lib/trafego/configuracao/erros422';
import type { AvisoDaRevisao, LinhaDoResumo } from '@/lib/trafego/configuracao/revisao';
import { rotuloDaEstrategia } from '@/lib/trafego/configuracao/revisao';
import {
  AUTOMACOES_DEMAND_GEN_POR_FORMATO, CTAS_DEMAND_GEN, CTAS_VIDEO_DEMAND_GEN, ESTRATEGIAS_DEMAND_GEN,
  EXPANSOES_LOOKALIKE, FORMATOS_DEMAND_GEN, GENEROS_DEMAND_GEN, IDADES_DEMAND_GEN, RENDAS_DEMAND_GEN,
  STATUS_PARENTAIS_DEMAND_GEN,
} from '@/types/trafegoCanais';
import type { EsquemaJson, FormatoDemandGen } from '@/types/trafegoCanais';

const C = 'configuracao_demand_gen';
type AlterarDemand = <K extends keyof FormDemandGen>(campo: K, valor: FormDemandGen[K]) => void;

/** Recuo literal do contrato §3, quando o esquema vivo não chegou. */
export const MOTIVO_CARROSSEL_RECUO =
  'Indisponível pela fronteira HTTP: a imagem do cartão precisa ser asset já na conta com recibo de aprovação (o cartão não resolve id temporário), e a fronteira ainda não transporta asset remoto aprovado.';

const ROTULO_FORMATO: Record<FormatoDemandGen, string> = {
  MULTI_ASSET: 'Multi-asset (imagens)',
  VIDEO_RESPONSIVO: 'Vídeo responsivo',
  CARROSSEL: 'Carrossel',
};

const ROTULO_AUTOMACAO: Record<string, string> = {
  GENERATE_DESIGN_VERSIONS_FOR_IMAGES: 'Gerar versões de design das imagens',
  GENERATE_VIDEOS_FROM_OTHER_ASSETS: 'Gerar vídeos a partir dos assets',
  GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS: 'Gerar imagens animadas',
  GENERATE_LANDING_PAGE_PREVIEW: 'Prévia da landing page',
  GENERATE_LANDING_PAGE_TEXT: 'Texto a partir da landing page',
  GENERATE_SHORTER_YOUTUBE_VIDEOS: 'Versões mais curtas do vídeo',
  GENERATE_VERTICAL_YOUTUBE_VIDEOS: 'Versões verticais do vídeo',
};

const Superficie: React.FC<{ nome: string; detalhe: string }> = ({ nome, detalhe }) => (
  <li className="flex min-h-20 items-center gap-3 border-b border-border/80 py-3 last:border-0">
    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-border bg-muted/50 text-muted-foreground">
      <CircleDashed className="h-4 w-4" aria-hidden />
    </span>
    <span>
      <span className="block text-sm font-semibold">{nome}</span>
      <span className="mt-0.5 block text-[13px] text-muted-foreground">{detalhe}</span>
    </span>
    <span className="ml-auto text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">não selecionado</span>
  </li>
);

export const ParadaDemandResultado: React.FC<{
  cockpit: Cockpit;
  destino: LeituraDoDestinoPago;
}> = ({ cockpit, destino }) => (
  <div className="space-y-6">
    <section className="destination-hero">
      <div className="destination-hero-icon" aria-hidden><Globe2 className="h-5 w-5" /></div>
      <div className="min-w-0 flex-1">
        <p className="kicker text-muted-foreground">resultado e destino</p>
        <p className="mt-1 break-all font-display text-lg font-semibold text-foreground sm:text-xl">
          {cockpit.origem?.url_final ?? 'Endereço não declarado'}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">A descoberta começa numa LP identificada — não numa URL escolhida depois.</p>
      </div>
      <span className={cn(
        'destination-status',
        destino.apto_para_campanha ? 'destination-status-ok' : 'destination-status-blocked',
      )}>
        {destino.apto_para_campanha ? <ShieldCheck className="h-4 w-4" /> : <CircleDashed className="h-4 w-4" />}
        {destino.apto_para_campanha ? 'destino apto' : 'aguarda prova'}
      </span>
    </section>
    <dl className="grid gap-4 border-t border-border pt-5 sm:grid-cols-2">
      <LinhaDeFato rotulo="Conta" valor={cockpit.conta?.customer_id ?? null} fonte="projeto" />
      <LinhaDeFato rotulo="Meta observada" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
  </div>
);

const CANAIS: Array<{ id: CanalSelecionavelDemandGen; nome: string }> = [
  { id: 'youtube_in_stream', nome: 'YouTube In-stream' },
  { id: 'youtube_in_feed', nome: 'YouTube In-feed' },
  { id: 'youtube_shorts', nome: 'YouTube Shorts' },
  { id: 'discover', nome: 'Discover' },
  { id: 'gmail', nome: 'Gmail' },
  { id: 'display', nome: 'Display' },
  { id: 'maps', nome: 'Maps' },
];

export const ParadaDemandSuperficies: React.FC<{
  estrategia: EstrategiaDeCanaisDemandGen | null;
  onEstrategia: (valor: EstrategiaDeCanaisDemandGen) => void;
  selecionados: CanalSelecionavelDemandGen[];
  onSelecionados: (valor: CanalSelecionavelDemandGen[]) => void;
}> = ({ estrategia, onEstrategia, selecionados, onSelecionados }) => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info">
        <LayoutTemplate className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">inventário nativo</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Escolha de superfícies é uma decisão explícita</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
          O contrato do canal admite combinações diferentes. Nenhuma delas foi escolhida por esta oportunidade; por isso a tela não assume “todas”.
        </p>
      </div>
    </div>
    <div className="mt-5 grid gap-2 sm:grid-cols-3" role="group" aria-label="estratégia de superfícies">
      {([
        ['ALL_CHANNELS', 'Todos os canais'],
        ['ALL_OWNED_AND_OPERATED_CHANNELS', 'Superfícies próprias'],
        ['SELECTED_CHANNELS', 'Escolher canais'],
      ] as const).map(([valor, nome]) => (
        <button
          key={valor}
          type="button"
          aria-pressed={estrategia === valor}
          onClick={() => onEstrategia(valor)}
          className={cn(
            'min-h-12 rounded-lg border px-4 py-3 text-left text-sm font-semibold transition-colors',
            estrategia === valor ? 'border-primary/45 bg-primary/[0.07]' : 'border-border bg-background text-muted-foreground hover:border-primary/25',
          )}
        >{nome}</button>
      ))}
    </div>
    {estrategia === 'SELECTED_CHANNELS' && (
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {CANAIS.map(({ id, nome }) => {
          const ativo = selecionados.includes(id);
          return (
            <button
              key={id}
              type="button"
              aria-pressed={ativo}
              onClick={() => onSelecionados(ativo ? selecionados.filter((item) => item !== id) : [...selecionados, id])}
              className={cn(
                'flex min-h-11 items-center gap-3 rounded-lg border px-3 text-sm transition-colors',
                ativo ? 'border-primary/40 bg-primary/[0.06] font-semibold' : 'border-border bg-background text-muted-foreground',
              )}
            >
              <span className={cn('h-2.5 w-2.5 rounded-full', ativo ? 'bg-primary' : 'bg-muted-foreground/30')} />
              {nome}
            </button>
          );
        })}
      </div>
    )}
  </section>
);

export const ParadaDemandAudiencia: React.FC<{
  upgradedTargeting: boolean | null;
  onUpgradedTargeting: (valor: boolean) => void;
  audiencias: string;
  onAudiencias: (valor: string) => void;
  audienciasConfirmadas: boolean;
  onAudienciasConfirmadas: (valor: boolean) => void;
  form?: FormDemandGen;
  alterar?: AlterarDemand;
  esquema?: EsquemaJson | null;
}> = ({
  upgradedTargeting, onUpgradedTargeting, audiencias, onAudiencias,
  audienciasConfirmadas, onAudienciasConfirmadas, form, alterar, esquema = null,
}) => (
  <section className="space-y-5">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <Users2 className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">sinais ≠ certeza</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Audiência, intenção e exclusões viajam separadas</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
          Ainda não há resource names aprovados para esta oportunidade. Nada é convertido em lookalike, intenção ou público amplo por conveniência.
        </p>
      </div>
    </div>
    <EscolhaExplicita
      rotulo="Onde geo e idioma serão aplicados?"
      valor={upgradedTargeting}
      onChange={onUpgradedTargeting}
      positivo="No grupo (upgraded targeting ligado)"
      negativo="Na campanha (upgraded targeting desligado)"
      ajuda="É uma decisão imutável na criação; o VOLC nunca aceita o default remoto silenciosamente."
    />
    <EditorDeLista
      id="demand-audiences"
      rotulo="Audiências positivas"
      valor={audiencias}
      onChange={onAudiencias}
      placeholder="customers/123/audiences/456"
      ajuda="resource names de Audience existentes na mesma conta; vazio confirmado é aceito"
      linhas={4}
    />
    <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border bg-background px-4 text-sm">
      <input type="checkbox" checked={audienciasConfirmadas} onChange={(e) => onAudienciasConfirmadas(e.target.checked)} className="h-4 w-4 accent-primary" />
      <span><strong>Confirmo esta lista</strong> — vazia significa Demand Gen sem Audience anexada.</span>
    </label>
    {form && alterar && (
      <>
        <DecisaoSimNao
          rotulo="Segmentação otimizada do grupo"
          valor={form.segOtimizada}
          onChange={(v) => alterar('segOtimizada', v)}
          sim="Ligada" nao="Desligada"
          caminho={`${C}.segmentacao_otimizada`}
          ajuda="Sem decidir, o campo não é emitido (o default do contrato)."
        />
        <Secao titulo="Público composto (v25)" caminho={`${C}.publico`}
               descricao="Uma Audience montada no mesmo mutate e anexada ao grupo: listas, semelhantes, exclusões e demografia.">
          <Interruptor id="demand-publico" rotulo="Compor um público para esta campanha" marcado={form.publico}
                       onChange={(v) => alterar('publico', v)} />
          {form.publico && (
            <div className="space-y-4">
              <CampoTexto id="demand-publico-nome" rotulo="Nome do público" valor={form.publicoNome}
                          onChange={(v) => alterar('publicoNome', v)} caminho={`${C}.publico.nome`} />
              <div className="grid gap-4 lg:grid-cols-2">
                <CampoLista id="demand-userlists" rotulo="Listas de usuários" valor={form.userLists}
                            onChange={(v) => alterar('userLists', v)} caminho={`${C}.publico.user_lists`}
                            maximo={20} placeholder="customers/123/userLists/456" />
                <CampoLista id="demand-exclusoes" rotulo="Listas excluídas" valor={form.exclusoesUserList}
                            onChange={(v) => alterar('exclusoesUserList', v)} caminho={`${C}.publico.exclusoes_user_list`}
                            maximo={20} placeholder="customers/123/userLists/789" />
              </div>
              <Repetidor<FormLookalike>
                rotulo="Segmentos semelhantes"
                itens={form.lookalikes}
                onChange={(v) => alterar('lookalikes', v)}
                caminho={`${C}.publico.lookalikes`}
                maximo={10}
                novo={() => ({ nome: '', sementes: '', expansao: 'BALANCED', paises: 'BR' })}
                render={(l, i, mudar) => (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <CampoTexto id={`demand-lal-${i}-nome`} rotulo="nome" valor={l.nome}
                                caminho={`${C}.publico.lookalikes[${i}].nome`} onChange={(v) => mudar({ ...l, nome: v })} />
                    <CampoTexto id={`demand-lal-${i}-sementes`} rotulo="listas-semente (ids)" valor={l.sementes}
                                caminho={`${C}.publico.lookalikes[${i}].sementes`} onChange={(v) => mudar({ ...l, sementes: v })}
                                placeholder="9304580046" />
                    <CampoSelecao id={`demand-lal-${i}-exp`} rotulo="expansão" valor={l.expansao}
                                  caminho={`${C}.publico.lookalikes[${i}].expansao`}
                                  opcoes={opcoesDoEsquema(esquema, 'publico.lookalikes[].expansao', EXPANSOES_LOOKALIKE)
                                    .map((v) => ({ valor: v, rotulo: v === 'NARROW' ? 'estreita' : v === 'BALANCED' ? 'equilibrada' : 'ampla' }))}
                                  onChange={(v) => mudar({ ...l, expansao: v as FormLookalike['expansao'] })} />
                    <CampoTexto id={`demand-lal-${i}-paises`} rotulo="países" valor={l.paises}
                                caminho={`${C}.publico.lookalikes[${i}].paises`} onChange={(v) => mudar({ ...l, paises: v })}
                                placeholder="BR" />
                  </div>
                )}
              />
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-2">
                  <MultiEscolha rotulo="Idades" opcoes={opcoesDoEsquema(esquema, 'publico.idades[]', IDADES_DEMAND_GEN)}
                                valores={form.idades} onChange={(v) => alterar('idades', v)} caminho={`${C}.publico.idades`} />
                  <Interruptor id="demand-idade-ind" rotulo="Incluir idade indeterminada" marcado={form.inclIdade}
                               onChange={(v) => alterar('inclIdade', v)} />
                </div>
                <div className="space-y-2">
                  <MultiEscolha rotulo="Gêneros" opcoes={opcoesDoEsquema(esquema, 'publico.generos[]', GENEROS_DEMAND_GEN)}
                                valores={form.generos} onChange={(v) => alterar('generos', v)} caminho={`${C}.publico.generos`}
                                rotuloDe={(v) => (v === 'MALE' ? 'masculino' : 'feminino')} />
                  <Interruptor id="demand-genero-ind" rotulo="Incluir gênero indeterminado" marcado={form.inclGenero}
                               onChange={(v) => alterar('inclGenero', v)} />
                </div>
                <div className="space-y-2">
                  <MultiEscolha rotulo="Renda" opcoes={opcoesDoEsquema(esquema, 'publico.rendas[]', RENDAS_DEMAND_GEN)}
                                valores={form.rendas} onChange={(v) => alterar('rendas', v)} caminho={`${C}.publico.rendas`}
                                rotuloDe={(v) => v.replace('INCOME_RANGE_', '').replace('_', '–').replace('UP', '+')} />
                  <Interruptor id="demand-renda-ind" rotulo="Incluir renda indeterminada" marcado={form.inclRenda}
                               onChange={(v) => alterar('inclRenda', v)} />
                </div>
                <div className="space-y-2">
                  <MultiEscolha rotulo="Status parental" opcoes={opcoesDoEsquema(esquema, 'publico.status_parentais[]', STATUS_PARENTAIS_DEMAND_GEN)}
                                valores={form.parentais} onChange={(v) => alterar('parentais', v)} caminho={`${C}.publico.status_parentais`}
                                rotuloDe={(v) => (v === 'PARENT' ? 'com filhos' : 'sem filhos')} />
                  <Interruptor id="demand-parental-ind" rotulo="Incluir status indeterminado" marcado={form.inclParental}
                               onChange={(v) => alterar('inclParental', v)} />
                </div>
              </div>
            </div>
          )}
        </Secao>
      </>
    )}
  </section>
);

/** O formato e o que só o vídeo tem. Carrossel aparece DESABILITADO com o
 *  motivo que o próprio esquema declara (`x-volc-indisponivel-por-http`). */
export const FormatoDemandGenControle: React.FC<{
  form: FormDemandGen;
  alterar: AlterarDemand;
  esquema: EsquemaJson | null;
}> = ({ form, alterar, esquema }) => {
  const motivoCarrossel = motivoIndisponivelPorHttp(esquema, 'carrossel') ?? MOTIVO_CARROSSEL_RECUO;
  const formatos = opcoesDoEsquema(esquema, 'formato', FORMATOS_DEMAND_GEN);
  return (
    <div className="space-y-4">
      <fieldset className="space-y-2">
        <legend className="text-sm font-semibold">Formato do anúncio</legend>
        <div className="grid gap-2 sm:grid-cols-3" role="group" aria-label="formato do anúncio">
          {formatos.map((f) => {
            const indisponivel = f === 'CARROSSEL';
            return (
              <button key={f} type="button" aria-pressed={form.formato === f} disabled={indisponivel}
                      title={indisponivel ? motivoCarrossel : undefined}
                      onClick={() => alterar('formato', f)}
                      className={cn('min-h-11 rounded-lg border px-3 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                        form.formato === f ? 'border-primary/45 bg-primary/[0.07] font-semibold' : 'border-border bg-background text-muted-foreground')}>
                {ROTULO_FORMATO[f] ?? f}
                {indisponivel && <span className="mt-0.5 block text-[11px] font-normal">indisponível pela fronteira HTTP</span>}
              </button>
            );
          })}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground" data-testid="motivo-carrossel">
          <b>Carrossel:</b> {motivoCarrossel}
        </p>
        <ErroDoCampo caminho={`${C}.formato`} />
      </fieldset>
      {form.formato === 'VIDEO_RESPONSIVO' && (
        <Secao titulo="Vídeo responsivo" caminho={`${C}.video`}
               descricao="O vídeo entra por id público e fica fora do portão de política: o servidor não tem os bytes. O kit de imagem se reduz a exatamente um logo quadrado.">
          <CampoLista id="demand-video-ids" rotulo="Vídeos do YouTube" valor={form.videoIds} maximo={5}
                      onChange={(v) => alterar('videoIds', v)} caminho={`${C}.video.youtube_ids`}
                      placeholder="M7lc1UVf-VE" ajuda="id de 11 caracteres; de 1 a 5" />
          <div className="grid gap-4 sm:grid-cols-3">
            <CampoSelecao id="demand-video-cta" rotulo="Chamada para ação" valor={form.videoCta} vazio="sem CTA"
                          caminho={`${C}.video.call_to_action`}
                          opcoes={opcoesDoEsquema(esquema, 'video.call_to_action', CTAS_VIDEO_DEMAND_GEN).map((v) => ({ valor: v, rotulo: v }))}
                          onChange={(v) => alterar('videoCta', v)} />
            <CampoTexto id="demand-bc1" rotulo="Breadcrumb 1" valor={form.breadcrumb1} limite={15}
                        onChange={(v) => alterar('breadcrumb1', v)} caminho={`${C}.video.breadcrumb1`} />
            <CampoTexto id="demand-bc2" rotulo="Breadcrumb 2" valor={form.breadcrumb2} limite={15}
                        onChange={(v) => alterar('breadcrumb2', v)} caminho={`${C}.video.breadcrumb2`}
                        ajuda="exige o breadcrumb 1" />
          </div>
        </Secao>
      )}
    </div>
  );
};

export const ParadaDemandKit: React.FC<{
  assets: AssetDemandGen[];
  onAssets: (assets: AssetDemandGen[]) => void;
  form?: FormDemandGen;
  alterar?: AlterarDemand;
  esquema?: EsquemaJson | null;
}> = ({ assets, onAssets, form, alterar, esquema = null }) => (
  <section>
    {form && alterar && (
      <div className="mb-6"><FormatoDemandGenControle form={form} alterar={alterar} esquema={esquema} /></div>
    )}
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-verified/10 text-verified">
        <ImageIcon className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">kit de mídia</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Uma família visual, vários enquadramentos</h3>
        <p className="mt-2 text-sm text-muted-foreground">A cobertura só será medida quando o Estúdio entregar assets com recibo e geometria válidos.</p>
      </div>
    </div>
    {form?.formato === 'VIDEO_RESPONSIVO' ? (
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <SeletorDeAsset id="demand-logo" rotulo="Logo quadrado" tipo="logo_quadrado" detalhe="1:1 · exatamente um no vídeo responsivo" assets={assets} onChange={onAssets} maximo={1} />
      </div>
    ) : (
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <SeletorDeAsset id="demand-marketing" rotulo="Paisagem" tipo="imagem_marketing" detalhe="1.91:1 · compõe o mínimo de marketing" assets={assets} onChange={onAssets} maximo={20} />
        <SeletorDeAsset id="demand-square" rotulo="Quadrado" tipo="imagem_marketing_quadrada" detalhe="1:1 · compõe o mínimo de marketing" assets={assets} onChange={onAssets} maximo={20} />
        <SeletorDeAsset id="demand-portrait" rotulo="Retrato" tipo="imagem_marketing_retrato" detalhe="4:5 · inventário vertical" assets={assets} onChange={onAssets} maximo={20} />
        <SeletorDeAsset id="demand-tall" rotulo="Retrato alto" tipo="imagem_marketing_retrato_alto" detalhe="9:16 · Shorts" assets={assets} onChange={onAssets} maximo={20} />
        <SeletorDeAsset id="demand-logo" rotulo="Logo quadrado" tipo="logo_quadrado" detalhe="1:1 · ao menos um obrigatório" assets={assets} onChange={onAssets} maximo={5} />
      </div>
    )}
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-sm text-muted-foreground">
      <span className="flex items-center gap-3"><Film className="h-4 w-4" aria-hidden /> {form?.formato === 'VIDEO_RESPONSIVO'
        ? 'No vídeo responsivo, a imagem de marketing não viaja: só o logo.'
        : 'Vídeo responsivo é outro formato: escolha-o acima.'}</span>
      <IrParaEstudio canal="DEMAND_GEN" />
    </div>
  </section>
);

export const ParadaDemandMensagem: React.FC<{
  nomeEmpresa: string;
  onNomeEmpresa: (valor: string) => void;
  titulos: string;
  onTitulos: (valor: string) => void;
  descricoes: string;
  onDescricoes: (valor: string) => void;
  form?: FormDemandGen;
  alterar?: AlterarDemand;
  esquema?: EsquemaJson | null;
}> = ({ nomeEmpresa, onNomeEmpresa, titulos, onTitulos, descricoes, onDescricoes, form, alterar, esquema = null }) => (
  <section className="space-y-5">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info">
        <MessageSquareText className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">mensagem nativa</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Copy criada para descoberta, não transplantada do Search</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          Business name, headlines, descriptions e CTA ainda aguardam o contrato do Estúdio. A UI não reaproveita automaticamente uma RSA.
        </p>
      </div>
    </div>
    <div className="grid gap-5 border-t border-border pt-5 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <CampoDeTexto id="demand-business-name" rotulo="Nome da empresa" valor={nomeEmpresa} onChange={onNomeEmpresa} limite={25} placeholder="Ex.: Portal Mundo Mais" />
      </div>
      <EditorDeLista id="demand-headlines" rotulo="Títulos" valor={titulos} onChange={onTitulos} minimo={1} maximo={5} limitePorItem={30} placeholder={'Título 1\nTítulo 2'} />
      <EditorDeLista id="demand-descriptions" rotulo="Descrições" valor={descricoes} onChange={onDescricoes} minimo={1} maximo={5} limitePorItem={90} placeholder={'Descrição 1\nDescrição 2'} />
      {form && alterar && form.formato === 'VIDEO_RESPONSIVO' && (
        <div className="lg:col-span-2">
          <CampoLista id="demand-long-headlines" rotulo="Títulos longos do vídeo" valor={form.titulosLongos}
                      onChange={(v) => alterar('titulosLongos', v)} caminho="copy.long_headlines"
                      maximo={5} limitePorItem={90} ajuda="só o vídeo responsivo aceita; de 1 a 5" />
        </div>
      )}
      {form && alterar && form.formato === 'MULTI_ASSET' && (
        <CampoSelecao id="demand-cta" rotulo="Chamada para ação" valor={form.cta} vazio="sem CTA"
                      caminho={`${C}.call_to_action`}
                      opcoes={opcoesDoEsquema(esquema, 'call_to_action', CTAS_DEMAND_GEN).map((v) => ({ valor: v, rotulo: v }))}
                      onChange={(v) => alterar('cta', v)} ajuda="No vídeo, o CTA mora no próprio vídeo." />
      )}
    </div>
  </section>
);

export const ParadaDemandEconomia: React.FC<{
  cockpit: Cockpit;
  orcamento: number | null;
  orcamentoBruto: string;
  onOrcamento: (valor: string) => void;
  form?: FormDemandGen;
  alterar?: AlterarDemand;
  esquema?: EsquemaJson | null;
}> = ({ cockpit, orcamento, orcamentoBruto, onOrcamento, form, alterar, esquema = null }) => (
  <section className="space-y-5">
    <div>
      <p className="kicker text-muted-foreground">prova antes da criação</p>
      <h3 className="mt-1 font-display text-xl font-semibold">Economia e medição</h3>
      <p className="mt-2 text-sm text-muted-foreground">Demand Gen pode ser preparado para conferência; a criação real permanece fechada nesta onda. Sem limite de frequência: a API recusa em Demand Gen v25.</p>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-3">
      <LinhaDeFato rotulo="Conta vinculada" valor={cockpit.conta?.vinculada ? 'sim' : null} fonte="projeto" />
      <LinhaDeFato rotulo="Orçamento" valor={orcamento == null ? null : `R$ ${orcamento.toFixed(2).replace('.', ',')}/dia`} fonte="rascunho" />
      <LinhaDeFato rotulo="Mutação real" valor="fechada" fonte="contrato do canal" />
    </dl>
    <div className="grid gap-5 sm:grid-cols-2">
      <label className="block space-y-2 text-sm font-semibold">
        <span>Orçamento diário</span>
        <Input inputMode="decimal" value={orcamentoBruto} onChange={(e) => onOrcamento(e.target.value)} placeholder="10,00" className="h-11 bg-background" />
      </label>
      {form && alterar && (
        <CampoSelecao id="demand-estrategia" rotulo="Estratégia de lance" valor={form.estrategia}
                      caminho={`${C}.lance.estrategia`}
                      opcoes={opcoesDoEsquema(esquema, 'lance.estrategia', ESTRATEGIAS_DEMAND_GEN)
                        .map((v) => ({ valor: v, rotulo: rotuloDaEstrategia(v) }))}
                      onChange={(v) => alterar('estrategia', v as FormDemandGen['estrategia'])}
                      ajuda="O envelope leva a MESMA estratégia; divergir é 422." />
      )}
      {form && alterar && form.estrategia === 'MAXIMIZE_CONVERSIONS' && (
        <CampoTexto id="demand-tcpa" rotulo="CPA alvo (opcional)" valor={form.tcpa} numerico prefixo="R$"
                    onChange={(v) => alterar('tcpa', v)} caminho={`${C}.lance.target_cpa`} />
      )}
      {form && alterar && form.estrategia === 'MAXIMIZE_CONVERSION_VALUE' && (
        <CampoTexto id="demand-troas" rotulo="ROAS alvo (%) (opcional)" valor={form.troasPct} numerico prefixo="%"
                    onChange={(v) => alterar('troasPct', v)} caminho={`${C}.lance.target_roas`}
                    ajuda="Exige histórico de valor na conta." />
      )}
      {form && alterar && form.estrategia === 'TARGET_CPC' && (
        <CampoTexto id="demand-tcpc" rotulo="CPC alvo" valor={form.tcpc} numerico prefixo="R$"
                    onChange={(v) => alterar('tcpc', v)} caminho={`${C}.lance.target_cpc`} ajuda="Obrigatório nesta estratégia." />
      )}
    </div>
    {form && alterar && (
      <>
        <Secao titulo="Automações do formato" caminho={`${C}.automacoes`}
               descricao="Só as do formato escolhido viajam; as não marcadas vão como OPTED_OUT, explicitamente.">
          {(AUTOMACOES_DEMAND_GEN_POR_FORMATO[form.formato] ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Este formato não tem automação.</p>
          ) : (
            <div className="grid gap-2 lg:grid-cols-2">
              {(AUTOMACOES_DEMAND_GEN_POR_FORMATO[form.formato] ?? []).map((t) => (
                <Interruptor key={t} id={`demand-auto-${t}`} rotulo={ROTULO_AUTOMACAO[t] ?? t}
                             marcado={Boolean(form.automacoes[t])}
                             onChange={(v) => alterar('automacoes', { ...form.automacoes, [t]: v })}
                             caminho={`${C}.automacoes.${t}`} ajuda={t} />
              ))}
            </div>
          )}
        </Secao>
        <Secao titulo="Agenda" caminho={`${C}.agenda`} descricao="Fuso da conta. Vazio = o dia todo.">
          <EditorDeAgenda id="demand-agenda" rotulo="Faixas" faixas={form.agenda}
                          onChange={(v) => alterar('agenda', v)} caminho={`${C}.agenda`} />
        </Secao>
      </>
    )}
  </section>
);

export const ParadaDemandRevisao: React.FC<{
  url: string | null;
  faltas: string[];
  estadoDaProva: 'ociosa' | 'provando' | 'aprovada' | 'recusada';
  mensagemDaProva: string | null;
  onProvar: () => void;
  resumo?: LinhaDoResumo[];
  avisosPrevistos?: AvisoDaRevisao[];
  avisosDoServidor?: AvisoDaRevisao[] | null;
  erros?: ErrosDoServidor;
}> = ({ url, faltas, estadoDaProva, mensagemDaProva, onProvar, resumo, avisosPrevistos = [], avisosDoServidor = null, erros }) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4 border-b border-border pb-5">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><ScanSearch className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">revisão Demand Gen</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Preparar para validar, sem criar</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">O próximo produto é um pedido provável e um kit de mídia completo. A CTA de criação permanece ausente enquanto o mutate estiver fechado.</p>
      </div>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2">
      <LinhaDeFato rotulo="Destino" valor={url} fonte="funil" />
      <LinhaDeFato rotulo="Ato disponível" valor="validate_only" fonte="Google Ads; nada é criado" />
    </dl>
    {resumo && <ResumoDoCanal titulo="Suas escolhas de Demand Gen" linhas={resumo} />}
    <AvisosDaRevisao previstos={avisosPrevistos} doServidor={avisosDoServidor} />
    {erros && <ErrosDeForma erros={erros} />}
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
    <AcaoDeProva estado={estadoDaProva} mensagem={mensagemDaProva} desabilitada={faltas.length > 0} motivo={faltas[0] ?? null} onProvar={onProvar} />
  </section>
);
