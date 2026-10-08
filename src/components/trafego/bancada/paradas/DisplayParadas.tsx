import React from 'react';
import {
  Aperture, Check, CircleDashed, Eye, Globe2, Image as ImageIcon,
  MapPin, ShieldAlert, ShieldCheck, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';
import { Input } from '@/components/ui/input';
import type { AssetDemandGen } from '@/types/trafego';
import {
  AcaoDeProva, CampoDeTexto, EditorDeLista, IrParaEstudio, SeletorDeAsset,
} from './ControlesMulticanal';
import {
  CampoLista, CampoSelecao, CampoTexto, EditorDeAgenda, Interruptor, MultiEscolha, Repetidor, Secao,
} from '../campos/Campos';
import { AvisosDaRevisao, ErrosDeForma, ResumoDoCanal } from './RevisaoDoCanal';
import { defaultDoEsquema, opcoesDoEsquema } from '@/lib/trafego/configuracao/esquema';
import type { FormDisplay } from '@/lib/trafego/configuracao/formularios';
import type { ErrosDoServidor } from '@/lib/trafego/configuracao/erros422';
import type { AvisoDaRevisao, LinhaDoResumo } from '@/lib/trafego/configuracao/revisao';
import { rotuloDaEstrategia } from '@/lib/trafego/configuracao/revisao';
import {
  DISPOSITIVOS, ESTRATEGIAS_DISPLAY, FORMATOS_RDA, NIVEIS_DE_FREQUENCIA, PRESENCAS_GEO_DISPLAY,
  ROTULOS_DE_CONTEUDO, UNIDADES_DE_FREQUENCIA,
} from '@/types/trafegoCanais';
import type { EsquemaJson, RotuloDeConteudo } from '@/types/trafegoCanais';

const C = 'configuracao_display';
type AlterarDisplay = <K extends keyof FormDisplay>(campo: K, valor: FormDisplay[K]) => void;

const ROTULO_DISPOSITIVO: Record<string, string> = { MOBILE: 'celular', TABLET: 'tablet', DESKTOP: 'computador' };
const ROTULO_ROTULO: Record<string, string> = {
  PARKED_DOMAIN: 'domínio estacionado', SEXUALLY_SUGGESTIVE: 'sexualmente sugestivo',
  PROFANITY: 'palavrões', TRAGEDY: 'tragédia e conflito', SOCIAL_ISSUES: 'questões sociais sensíveis',
  JUVENILE: 'conteúdo juvenil', BELOW_THE_FOLD: 'abaixo da dobra', VIDEO: 'vídeo incorporado',
  EMBEDDED_VIDEO: 'vídeo embutido', LIVE_STREAMING_VIDEO: 'transmissão ao vivo',
  BRAND_SUITABILITY_CONTENT_FOR_FAMILIES: 'conteúdo para famílias',
};

const LinhaDeRequisito: React.FC<{
  titulo: string;
  detalhe: string;
  estado?: 'presente' | 'nao_lido' | 'obrigatorio';
}> = ({ titulo, detalhe, estado = 'nao_lido' }) => {
  const Icon = estado === 'presente' ? Check : estado === 'obrigatorio' ? Aperture : CircleDashed;
  return (
    <li className="flex min-h-16 items-start gap-3 border-b border-border/80 py-3 last:border-0">
      <span className={cn(
        'mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full border',
        estado === 'presente'
          ? 'border-success/30 bg-success/10 text-success'
          : 'border-border bg-muted/50 text-muted-foreground',
      )}>
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-foreground">{titulo}</span>
        <span className="mt-0.5 block text-[13px] leading-relaxed text-muted-foreground">{detalhe}</span>
      </span>
      <span className="mt-1 whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {estado === 'presente' ? 'presente' : estado === 'obrigatorio' ? 'requerido' : 'não lido'}
      </span>
    </li>
  );
};

export const ParadaDisplayDestino: React.FC<{
  cockpit: Cockpit;
  destino: LeituraDoDestinoPago;
}> = ({ cockpit, destino }) => {
  const url = cockpit.origem?.url_final ?? null;
  return (
    <div className="space-y-6">
      <section className="destination-hero">
        <div className="destination-hero-icon" aria-hidden><Globe2 className="h-5 w-5" /></div>
        <div className="min-w-0 flex-1">
          <p className="kicker text-muted-foreground">destino comprado</p>
          <p className="mt-1 break-all font-display text-lg font-semibold text-foreground sm:text-xl">
            {url ?? 'O funil ainda não declarou um endereço'}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            A campanha Display não pode trocar este endereço silenciosamente.
          </p>
        </div>
        <span className={cn(
          'destination-status',
          destino.apto_para_campanha ? 'destination-status-ok' : 'destination-status-blocked',
        )}>
          {destino.apto_para_campanha ? <ShieldCheck className="h-4 w-4" /> : <CircleDashed className="h-4 w-4" />}
          {destino.apto_para_campanha ? 'destino apto' : 'aguarda prova'}
        </span>
      </section>

      <div className="grid gap-4 border-t border-border pt-5 sm:grid-cols-2">
        <LinhaDeFato rotulo="Conta" valor={cockpit.conta?.customer_id ?? null} fonte="projeto" />
        <LinhaDeFato rotulo="Objetivo" valor={null} fonte="ainda não declarado" />
      </div>
    </div>
  );
};

export const ParadaDisplayGeografia: React.FC<{
  cockpit: Cockpit;
  form: FormDisplay;
  alterar: AlterarDisplay;
  esquema: EsquemaJson | null;
}> = ({ cockpit, form, alterar, esquema }) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info">
        <MapPin className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <h3 className="font-display text-lg font-semibold">Onde e quando a impressão pode acontecer</h3>
        <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-muted-foreground">
          País e idioma vêm da oportunidade. Presença, agenda e dispositivos são decisão sua.
        </p>
      </div>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-2">
      <LinhaDeFato rotulo="País" valor={cockpit.origem?.pais ?? null} fonte="oportunidade" />
      <LinhaDeFato rotulo="Idioma" valor={cockpit.origem?.idioma ?? null} fonte="oportunidade" />
    </dl>
    <CampoSelecao
      id="display-presenca" rotulo="Quem conta como estando no país" valor={form.presenca}
      caminho={`${C}.presenca_geo`}
      opcoes={opcoesDoEsquema(esquema, 'presenca_geo', PRESENCAS_GEO_DISPLAY).map((v) => ({
        valor: v,
        rotulo: v === 'PRESENCE' ? 'Presença — quem está no país (padrão)' : 'Presença ou interesse no país',
      }))}
      onChange={(v) => alterar('presenca', v as FormDisplay['presenca'])}
      ajuda="O RPM do GAM é por país: interesse no local compra clique de fora. O negativo é sempre presença."
    />
    <Secao titulo="Agenda" caminho={`${C}.agenda`} descricao="Vazio = o dia todo, todos os dias.">
      <EditorDeAgenda id="display-agenda" rotulo="Janelas de veiculação" faixas={form.agenda}
                      onChange={(v) => alterar('agenda', v)} caminho={`${C}.agenda`}
                      nomesDaHora={{ inicio: 'inicio_hora', fim: 'fim_hora' }} />
    </Secao>
    <MultiEscolha
      rotulo="Dispositivos excluídos"
      opcoes={opcoesDoEsquema(esquema, 'dispositivos_excluidos[]', DISPOSITIVOS)}
      valores={form.dispositivosExcluidos}
      onChange={(v) => alterar('dispositivosExcluidos', v as FormDisplay['dispositivosExcluidos'])}
      caminho={`${C}.dispositivos_excluidos`}
      rotuloDe={(v) => ROTULO_DISPOSITIVO[v] ?? v}
      ajuda="Marcado = o anúncio não aparece nesse dispositivo."
    />
  </section>
);

export const ParadaDisplayAudiencia: React.FC<{
  form: FormDisplay;
  alterar: AlterarDisplay;
}> = ({ form, alterar }) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <Users2 className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">controle de alcance</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Segmentação do grupo</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
          Critérios positivos do ad group. Tudo vazio é inventário aberto — o servidor avisa no plano.
          Aceita id numérico ou resource name da MESMA conta; resource name de outra conta é bloqueio.
        </p>
      </div>
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <CampoLista id="display-seg-listas" rotulo="Listas de remarketing" valor={form.segListasDeUsuarios}
                  onChange={(v) => alterar('segListasDeUsuarios', v)} caminho={`${C}.segmentacao.listas_de_usuarios`}
                  placeholder="customers/123/userLists/456" />
      <CampoLista id="display-seg-personalizados" rotulo="Públicos personalizados" valor={form.segPublicosPersonalizados}
                  onChange={(v) => alterar('segPublicosPersonalizados', v)} caminho={`${C}.segmentacao.publicos_personalizados`}
                  placeholder="customers/123/customAudiences/456" />
      <CampoLista id="display-seg-combinados" rotulo="Públicos combinados" valor={form.segPublicosCombinados}
                  onChange={(v) => alterar('segPublicosCombinados', v)} caminho={`${C}.segmentacao.publicos_combinados`}
                  placeholder="customers/123/combinedAudiences/456" />
      <CampoLista id="display-seg-interesses" rotulo="Afinidade e in-market" valor={form.segInteresses}
                  onChange={(v) => alterar('segInteresses', v)} caminho={`${C}.segmentacao.interesses`}
                  placeholder="92000" ajuda="ex.: 92000 leitores de notícias, 80226 educação" />
      <CampoLista id="display-seg-topicos" rotulo="Tópicos" valor={form.segTopicos}
                  onChange={(v) => alterar('segTopicos', v)} caminho={`${C}.segmentacao.topicos`}
                  placeholder="369" />
      <CampoLista id="display-seg-placements" rotulo="Sites onde pode aparecer" valor={form.segPlacements}
                  onChange={(v) => alterar('segPlacements', v)} caminho={`${C}.segmentacao.placements`}
                  placeholder="g1.globo.com/educacao" />
      <div className="lg:col-span-2">
        <CampoLista id="display-seg-palavras" rotulo="Palavras-chave de conteúdo" valor={form.segPalavrasChave}
                    onChange={(v) => alterar('segPalavrasChave', v)} caminho={`${C}.segmentacao.palavras_chave`}
                    limitePorItem={80} ajuda="casam com o conteúdo da página, não com a busca" />
      </div>
    </div>
    <div className="grid gap-3 lg:grid-cols-2">
      <Interruptor id="display-seg-observacao" rotulo="Públicos em observação" marcado={form.segObservacao}
                   onChange={(v) => alterar('segObservacao', v)} caminho={`${C}.segmentacao.publicos_em_observacao`}
                   ajuda="Ligado: os públicos só medem e não restringem. Desligado: restringem quem vê." />
      <Interruptor id="display-seg-otimizada" rotulo="Segmentação otimizada" marcado={form.segOtimizada}
                   onChange={(v) => alterar('segOtimizada', v)} caminho={`${C}.segmentacao.segmentacao_otimizada`}
                   ajuda="⚠️ Ligada, o Google expande além dos critérios acima — o oposto do controle de inventário da arbitragem." />
    </div>
  </section>
);

export const ParadaDisplayCriativo: React.FC<{
  nomeEmpresa: string;
  onNomeEmpresa: (valor: string) => void;
  titulos: string;
  onTitulos: (valor: string) => void;
  tituloLongo: string;
  onTituloLongo: (valor: string) => void;
  descricoes: string;
  onDescricoes: (valor: string) => void;
  videos: string;
  onVideos: (valor: string) => void;
  assets: AssetDemandGen[];
  onAssets: (assets: AssetDemandGen[]) => void;
  form?: FormDisplay;
  alterar?: AlterarDisplay;
  esquema?: EsquemaJson | null;
}> = ({
  nomeEmpresa, onNomeEmpresa, titulos, onTitulos, tituloLongo, onTituloLongo,
  descricoes, onDescricoes, videos, onVideos, assets, onAssets, form, alterar, esquema,
}) => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-verified/10 text-verified">
        <ImageIcon className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">responsive display ad</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Cobertura criativa</h3>
        <p className="mt-2 text-sm text-muted-foreground">O Estúdio precisa entregar recursos aprovados; esta bancada não substitui arquivos ausentes por placeholders.</p>
      </div>
    </div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <SeletorDeAsset id="display-marketing" rotulo="Imagem horizontal" tipo="imagem_marketing" detalhe="1.91:1 · mínimo 600×314 · obrigatória" assets={assets} onChange={onAssets} maximo={15} />
      <SeletorDeAsset id="display-square" rotulo="Imagem quadrada" tipo="imagem_marketing_quadrada" detalhe="1:1 · mínimo 300×300 · obrigatória" assets={assets} onChange={onAssets} maximo={15} />
      <SeletorDeAsset id="display-logo-landscape" rotulo="Logo horizontal" tipo="logo_paisagem" detalhe="4:1 · opcional · até 5 logos no total" assets={assets} onChange={onAssets} maximo={5} />
      <SeletorDeAsset id="display-logo-square" rotulo="Logo quadrado" tipo="logo_quadrado" detalhe="1:1 · opcional · até 5 logos no total" assets={assets} onChange={onAssets} maximo={5} />
    </div>
    <div className="mt-4 flex justify-end"><IrParaEstudio canal="DISPLAY" /></div>
    <div className="mt-6 grid gap-5 border-t border-border pt-6 lg:grid-cols-2">
      <CampoDeTexto id="display-business-name" rotulo="Nome da empresa" valor={nomeEmpresa} onChange={onNomeEmpresa} limite={25} placeholder="Ex.: Portal Mundo Mais" />
      <CampoDeTexto id="display-long-headline" rotulo="Título longo" valor={tituloLongo} onChange={onTituloLongo} limite={90} placeholder="Uma promessa editorial clara" />
      <EditorDeLista id="display-headlines" rotulo="Títulos" valor={titulos} onChange={onTitulos} minimo={1} maximo={5} limitePorItem={30} placeholder={'Título 1\nTítulo 2'} />
      <EditorDeLista id="display-descriptions" rotulo="Descrições" valor={descricoes} onChange={onDescricoes} minimo={1} maximo={5} limitePorItem={90} placeholder={'Descrição 1\nDescrição 2'} />
      <div className="lg:col-span-2">
        <CampoLista id="display-videos" rotulo="Vídeos do YouTube (opcional)" valor={videos} onChange={onVideos}
                    maximo={5} placeholder="jNQXAC9IVRw" caminho={`${C}.anuncio.videos_youtube`}
                    ajuda="id público do vídeo (11 caracteres). O vídeo nasce no mesmo mutate e fica fora do portão de política: o servidor não tem os bytes." />
      </div>
    </div>
    {form && alterar && (
      <Secao titulo="Anúncio responsivo" caminho={`${C}.anuncio`} className="mt-6"
             descricao="Campos do RDA além de texto e imagem. Melhorias e vídeo automático nascem desligados: peça aprovada é peça servida.">
        <div className="grid gap-4 lg:grid-cols-2">
          <CampoTexto id="display-cta" rotulo="Chamada para ação" valor={form.rdaCta} limite={30}
                      onChange={(v) => alterar('rdaCta', v)} caminho={`${C}.anuncio.chamada_para_acao`}
                      placeholder="Saiba mais" />
          <CampoSelecao id="display-formato" rotulo="Formato" valor={form.rdaFormato}
                        caminho={`${C}.anuncio.formato`}
                        opcoes={opcoesDoEsquema(esquema ?? null, 'anuncio.formato', FORMATOS_RDA).map((v) => ({
                          valor: v,
                          rotulo: v === 'ALL_FORMATS' ? 'Todos os formatos' : v === 'NATIVE' ? 'Só nativo' : 'Só não nativo',
                        }))}
                        onChange={(v) => alterar('rdaFormato', v as FormDisplay['rdaFormato'])} />
          <CampoTexto id="display-cor-principal" rotulo="Cor principal" valor={form.rdaCorPrincipal}
                      onChange={(v) => alterar('rdaCorPrincipal', v)} caminho={`${C}.anuncio.cor_principal`}
                      placeholder="#0A3D91" ajuda="as duas cores ou nenhuma" />
          <CampoTexto id="display-cor-destaque" rotulo="Cor de destaque" valor={form.rdaCorDestaque}
                      onChange={(v) => alterar('rdaCorDestaque', v)} caminho={`${C}.anuncio.cor_destaque`}
                      placeholder="#F2A900" />
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          <Interruptor id="display-cores-flex" rotulo="Cores flexíveis" marcado={form.rdaCoresFlexiveis}
                       onChange={(v) => alterar('rdaCoresFlexiveis', v)} caminho={`${C}.anuncio.cores_flexiveis`}
                       ajuda="Precisa ficar ligado quando não há cores." />
          <Interruptor id="display-melhorias" rotulo="Melhorias de asset" marcado={form.rdaMelhorias}
                       onChange={(v) => alterar('rdaMelhorias', v)} caminho={`${C}.anuncio.melhorias_de_asset`} />
          <Interruptor id="display-video-auto" rotulo="Vídeo automático" marcado={form.rdaVideoAutomatico}
                       onChange={(v) => alterar('rdaVideoAutomatico', v)} caminho={`${C}.anuncio.video_automatico`} />
        </div>
      </Secao>
    )}
  </section>
);

export const ParadaDisplayInventario: React.FC<{
  form: FormDisplay;
  alterar: AlterarDisplay;
  esquema: EsquemaJson | null;
}> = ({ form, alterar, esquema }) => {
  const padrao = defaultDoEsquema(esquema, 'exclusoes.rotulos_de_conteudo');
  const rotulosPadrao = Array.isArray(padrao) ? (padrao as string[]) : null;
  return (
    <section className="space-y-6">
      <div className="flex items-start gap-4">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-warning/10 text-warning">
          <ShieldAlert className="h-5 w-5" aria-hidden />
        </span>
        <div>
          <p className="kicker text-muted-foreground">brand safety</p>
          <h3 className="mt-1 font-display text-xl font-semibold">Proteções antes de ganhar alcance</h3>
          <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
            As exclusões padrão já vêm marcadas: todos os apps e os seis rótulos de conteúdo de nascimento.
            Desmarcar é decisão sua, e entra na impressão aprovável do plano.
          </p>
        </div>
      </div>
      <Interruptor id="display-exc-apps" rotulo="Excluir todos os apps" marcado={form.excTodosOsApps}
                   onChange={(v) => alterar('excTodosOsApps', v)} caminho={`${C}.exclusoes.excluir_todos_os_apps`}
                   ajuda="Padrão ligado: clique em app é acidental demais e a sessão não cai no portal monetizado." />
      <MultiEscolha<RotuloDeConteudo>
        rotulo="Rótulos de conteúdo excluídos"
        opcoes={opcoesDoEsquema(esquema, 'exclusoes.rotulos_de_conteudo[]', ROTULOS_DE_CONTEUDO)}
        valores={form.excRotulos}
        onChange={(v) => alterar('excRotulos', v)}
        caminho={`${C}.exclusoes.rotulos_de_conteudo`}
        rotuloDe={(v) => ROTULO_ROTULO[v] ?? v}
        ajuda={rotulosPadrao ? `Padrão de nascimento (servidor): ${rotulosPadrao.join(', ')}.` : 'Padrão de nascimento: os seis marcados ao abrir.'}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <CampoLista id="display-exc-placements" rotulo="Sites excluídos" valor={form.excPlacements}
                    onChange={(v) => alterar('excPlacements', v)} caminho={`${C}.exclusoes.placements`}
                    placeholder="site-ruim.com" />
        <CampoLista id="display-exc-apps-lista" rotulo="Apps excluídos" valor={form.excApps}
                    onChange={(v) => alterar('excApps', v)} caminho={`${C}.exclusoes.apps`}
                    placeholder="2-com.exemplo.jogo" ajuda="1-<id App Store> ou 2-<pacote Android>" />
        <CampoLista id="display-exc-categorias" rotulo="Categorias de app excluídas" valor={form.excCategoriasDeApp}
                    onChange={(v) => alterar('excCategoriasDeApp', v)} caminho={`${C}.exclusoes.categorias_de_app`}
                    placeholder="mobileAppCategoryConstants/60000" />
        <CampoLista id="display-exc-topicos" rotulo="Tópicos excluídos" valor={form.excTopicos}
                    onChange={(v) => alterar('excTopicos', v)} caminho={`${C}.exclusoes.topicos`}
                    placeholder="1493" />
        <CampoLista id="display-exc-listas" rotulo="Listas de exclusão existentes" valor={form.excListasExistentes}
                    onChange={(v) => alterar('excListasExistentes', v)} caminho={`${C}.exclusoes.listas_existentes`}
                    placeholder="customers/123/sharedSets/456" />
      </div>
      <Secao titulo="Lista de exclusão nova" caminho={`${C}.exclusoes.lista_nova`}
             descricao="Criada no mesmo mutate e ligada à campanha. Vazia = nenhuma lista nova.">
        <div className="grid gap-4 lg:grid-cols-2">
          <CampoTexto id="display-lista-nome" rotulo="Nome da lista" valor={form.listaNovaNome}
                      onChange={(v) => alterar('listaNovaNome', v)} caminho={`${C}.exclusoes.lista_nova.nome`} />
          <CampoLista id="display-lista-sites" rotulo="Sites" valor={form.listaNovaPlacements}
                      onChange={(v) => alterar('listaNovaPlacements', v)} caminho={`${C}.exclusoes.lista_nova.placements`} />
          <CampoLista id="display-lista-apps" rotulo="Apps" valor={form.listaNovaApps}
                      onChange={(v) => alterar('listaNovaApps', v)} caminho={`${C}.exclusoes.lista_nova.apps`} />
          <CampoLista id="display-lista-categorias" rotulo="Categorias de app" valor={form.listaNovaCategorias}
                      onChange={(v) => alterar('listaNovaCategorias', v)} caminho={`${C}.exclusoes.lista_nova.categorias_de_app`} />
        </div>
      </Secao>
    </section>
  );
};

export const ParadaDisplayEconomia: React.FC<{
  cockpit: Cockpit;
  orcamento: number | null;
  orcamentoBruto: string;
  onOrcamento: (valor: string) => void;
  form: FormDisplay;
  alterar: AlterarDisplay;
  esquema: EsquemaJson | null;
}> = ({ cockpit, orcamento, orcamentoBruto, onOrcamento, form, alterar, esquema }) => {
  const e = form.estrategia;
  return (
    <section className="space-y-5">
      <div>
        <p className="kicker text-muted-foreground">economia da impressão</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Compra e medição</h3>
        <p className="mt-2 text-sm text-muted-foreground">Display compra de outro jeito que Search: o lance e a frequência são deste canal.</p>
      </div>
      <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-3">
        <LinhaDeFato rotulo="Conta vinculada" valor={cockpit.conta?.vinculada ? 'sim' : null} fonte="projeto" />
        <LinhaDeFato rotulo="Orçamento" valor={orcamento == null ? null : `R$ ${orcamento.toFixed(2).replace('.', ',')}/dia`} fonte="rascunho" />
        <LinhaDeFato rotulo="Conversão" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
      </dl>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="space-y-2 text-sm font-semibold">
          <span>Orçamento diário</span>
          <Input inputMode="decimal" value={orcamentoBruto} onChange={(ev) => onOrcamento(ev.target.value)} placeholder="10,00" className="h-11 bg-background" />
          <span className="block text-xs font-normal text-muted-foreground">Moeda da conta · a campanha nasce pausada.</span>
        </label>
        <CampoSelecao id="display-estrategia" rotulo="Estratégia de lance" valor={e} caminho={`${C}.lance.estrategia`}
                      opcoes={opcoesDoEsquema(esquema, 'lance.estrategia', ESTRATEGIAS_DISPLAY)
                        .map((v) => ({ valor: v, rotulo: rotuloDaEstrategia(v) }))}
                      onChange={(v) => alterar('estrategia', v as FormDisplay['estrategia'])} />
        {e === 'MAXIMIZE_CONVERSIONS' && (
          <CampoTexto id="display-tcpa" rotulo="CPA alvo (opcional)" valor={form.tcpa} numerico prefixo="R$"
                      onChange={(v) => alterar('tcpa', v)} caminho="tcpa" ajuda="Vazio = maximizar conversões sem meta." />
        )}
        {e === 'MAXIMIZE_CONVERSION_VALUE' && (
          <CampoTexto id="display-troas" rotulo="ROAS alvo (%) (opcional)" valor={form.troasPct} numerico prefixo="%"
                      onChange={(v) => alterar('troasPct', v)} caminho="target_roas" ajuda="400 = R$ 4 de valor por real." />
        )}
        {e === 'TARGET_SPEND' && (
          <CampoTexto id="display-teto" rotulo="Teto de CPC (opcional)" valor={form.tetoCpc} numerico prefixo="R$"
                      onChange={(v) => alterar('tetoCpc', v)} caminho={`${C}.lance.teto_cpc`} ajuda="Vazio = sem teto." />
        )}
        {e === 'MANUAL_CPC' && (
          <CampoTexto id="display-cpc" rotulo="Lance por clique do grupo" valor={form.cpcManual} numerico prefixo="R$"
                      onChange={(v) => alterar('cpcManual', v)} caminho="cpc_inicial"
                      ajuda="Obrigatório: em CPC manual ele É o lance do grupo, e o default do envelope não é escolha de ninguém." />
        )}
        {e === 'MANUAL_CPM' && (
          <CampoTexto id="display-cpm" rotulo="CPM visível" valor={form.cpm} numerico prefixo="R$"
                      onChange={(v) => alterar('cpm', v)} caminho={`${C}.lance.cpm_visivel`} ajuda="Obrigatório em CPM manual." />
        )}
      </div>
      <Secao titulo="Frequência máxima" caminho={`${C}.frequencia`}
             descricao="Impressões por pessoa. Sem limite, o mesmo usuário pode ver o anúncio sem teto.">
        <Repetidor<FormDisplay['frequencia'][number]>
          rotulo="Limites"
          itens={form.frequencia}
          onChange={(v) => alterar('frequencia', v)}
          caminho={`${C}.frequencia`}
          novo={() => ({ impressoes: '3', unidade: 'DAY', nivel: 'AD_GROUP_AD' })}
          render={(f, i, mudar) => (
            <div className="grid gap-2 sm:grid-cols-3">
              <CampoTexto id={`display-freq-${i}`} rotulo="impressões" valor={f.impressoes} numerico
                          caminho={`${C}.frequencia[${i}].impressoes`} onChange={(v) => mudar({ ...f, impressoes: v })} />
              <CampoSelecao id={`display-freq-${i}-un`} rotulo="por" valor={f.unidade}
                            caminho={`${C}.frequencia[${i}].unidade`}
                            opcoes={opcoesDoEsquema(esquema, 'frequencia[].unidade', UNIDADES_DE_FREQUENCIA)
                              .map((v) => ({ valor: v, rotulo: v === 'DAY' ? 'dia' : v === 'WEEK' ? 'semana' : 'mês' }))}
                            onChange={(v) => mudar({ ...f, unidade: v as typeof f.unidade })} />
              <CampoSelecao id={`display-freq-${i}-nivel`} rotulo="nível" valor={f.nivel}
                            caminho={`${C}.frequencia[${i}].nivel`}
                            opcoes={opcoesDoEsquema(esquema, 'frequencia[].nivel', NIVEIS_DE_FREQUENCIA)
                              .map((v) => ({ valor: v, rotulo: v === 'AD_GROUP_AD' ? 'anúncio' : v === 'AD_GROUP' ? 'grupo' : 'campanha' }))}
                            onChange={(v) => mudar({ ...f, nivel: v as typeof f.nivel })} />
            </div>
          )}
        />
      </Secao>
    </section>
  );
};

export const ParadaDisplayRevisao: React.FC<{
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
    <div className="flex items-start justify-between gap-4 border-b border-border pb-5">
      <div>
        <p className="kicker text-muted-foreground">revisão Display</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Pedido visual em preparação</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          A prova envia o payload com validate_only após seu clique. A API confere e descarta; criação real continua fechada.
        </p>
      </div>
      <span className="shrink-0 rounded-full border border-warning/30 bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">preparação</span>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2">
      <LinhaDeFato rotulo="Destino" valor={url} fonte="funil" />
      <LinhaDeFato rotulo="Criação real" valor={null} fonte="depende do portão do servidor" />
    </dl>
    {resumo && <ResumoDoCanal titulo="Suas escolhas de Display" linhas={resumo} />}
    <AvisosDaRevisao previstos={avisosPrevistos} doServidor={avisosDoServidor} />
    {erros && <ErrosDeForma erros={erros} />}
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
    <AcaoDeProva estado={estadoDaProva} mensagem={mensagemDaProva} desabilitada={faltas.length > 0} motivo={faltas[0] ?? null} onProvar={onProvar} />
  </section>
);
