import React from 'react';
import {
  Ban, CircleDashed, Film, FolderArchive, Globe2, Image as ImageIcon,
  Link2Off, Search, ShieldCheck, Sparkles, Target, Users2,
} from 'lucide-react';

import type { Cockpit } from '@/types/trafego';
import type { AssetDemandGen } from '@/types/trafego';
import type { LeituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { LinhaDeFato } from '../BlocoDeEvidencia';
import { Input } from '@/components/ui/input';
import {
  AcaoDeProva, CampoDeTexto, EditorDeLista, EscolhaExplicita, IrParaEstudio, SeletorDeAsset,
} from './ControlesMulticanal';
import {
  CampoLista, CampoSelecao, CampoTexto, Interruptor, Repetidor, Secao, ErroDoCampo,
} from '../campos/Campos';
import { AvisosDaRevisao, ErrosDeForma, ResumoDoCanal } from './RevisaoDoCanal';
import { opcoesDoEsquema } from '@/lib/trafego/configuracao/esquema';
import { novoGrupoPMax } from '@/lib/trafego/configuracao/formularios';
import type { FormGrupoPMax, FormOpcoesDeUrl, FormPMax, LinhaDeCategoria } from '@/lib/trafego/configuracao/formularios';
import type { ErrosDoServidor } from '@/lib/trafego/configuracao/erros422';
import type { AvisoDaRevisao, LinhaDoResumo } from '@/lib/trafego/configuracao/revisao';
import {
  AUTOMACOES_PMAX, CATEGORIAS_DE_CONVERSAO, FONTES_DE_MARCA, MATCH_TYPES_NEGATIVA_PMAX,
  MODOS_CLIENTE_NOVO, OPERADORES_DE_EXCLUSAO_URL, OPERANDOS_DE_EXCLUSAO_URL, ORIGENS_DE_CONVERSAO,
  PLATAFORMAS_DE_VIDEO_CRAWL,
} from '@/types/trafegoCanais';
import type { AutomacaoPMax, EsquemaJson } from '@/types/trafegoCanais';

const C = 'configuracao_pmax';
type AlterarPMax = <K extends keyof FormPMax>(campo: K, valor: FormPMax[K]) => void;

const ROTULO_AUTOMACAO_PMAX: Record<string, { titulo: string; detalhe: string }> = {
  FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION: {
    titulo: 'Expansão de URL final',
    detalhe: 'O Google pode mandar o clique para outra página do domínio. Exige a automação de texto junto.',
  },
  TEXT_ASSET_AUTOMATION: { titulo: 'Automação de texto', detalhe: 'Textos gerados a partir da página e dos assets.' },
  GENERATE_IMAGE_ENHANCEMENT: { titulo: 'Melhoria de imagem', detalhe: 'Recorte e ajuste automático das imagens enviadas.' },
  GENERATE_ENHANCED_YOUTUBE_VIDEOS: { titulo: 'Vídeos aprimorados', detalhe: 'Versões geradas dos vídeos do YouTube.' },
  GENERATE_IMAGE_EXTRACTION: { titulo: 'Extração de imagem', detalhe: 'Imagens tiradas da landing page.' },
  AUTOMATED_VIDEO_CRAWL: { titulo: 'Busca automática de vídeos', detalhe: 'Exige fontes declaradas e a declaração de direitos.' },
  GENERATE_DESIGN_VERSIONS_FOR_IMAGES: { titulo: 'Versões de design das imagens', detalhe: 'Variações geradas a partir das imagens.' },
};

/** Opções de URL de um asset group (grupo 0 ou adicional). */
const EditorDeOpcoesDeUrl: React.FC<{
  id: string;
  valor: FormOpcoesDeUrl;
  onChange: (v: FormOpcoesDeUrl) => void;
  caminho: string;
}> = ({ id, valor, onChange, caminho }) => (
  <div className="grid gap-4 lg:grid-cols-3">
    <CampoLista id={`${id}-sufixo`} rotulo="Sufixo extra" valor={valor.sufixo}
                onChange={(v) => onChange({ ...valor, sufixo: v })} caminho={`${caminho}.sufixo_extra`}
                placeholder="vc_ag=geral" ajuda="chave=valor; soma-se ao sufixo da campanha" />
    <CampoTexto id={`${id}-tracking`} rotulo="Modelo de rastreamento" valor={valor.tracking}
                onChange={(v) => onChange({ ...valor, tracking: v })} caminho={`${caminho}.tracking_url_template`}
                placeholder="{lpurl}?vc_tpl={_tema}" ajuda="começa com {lpurl} ou https:// e carrega {lpurl}" />
    <CampoLista id={`${id}-params`} rotulo="Parâmetros personalizados" valor={valor.parametros}
                onChange={(v) => onChange({ ...valor, parametros: v })} caminho={`${caminho}.parametros_personalizados`}
                placeholder="tema=livres" ajuda="até 8; usados como {_chave}" />
  </div>
);

export const ParadaPMaxObjetivo: React.FC<{
  cockpit: Cockpit;
  form?: FormPMax;
  alterar?: AlterarPMax;
  esquema?: EsquemaJson | null;
}> = ({ cockpit, form, alterar, esquema = null }) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <Target className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="kicker text-muted-foreground">performance max</p>
        <h3 className="mt-1 font-display text-xl font-semibold">O objetivo vem antes da automação</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          PMax distribui a campanha por vários inventários. Sem uma meta de conversão observada, automatizar alcance não significa otimizar resultado.
        </p>
      </div>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-2">
      <LinhaDeFato rotulo="Conta" valor={cockpit.conta?.customer_id ?? null} fonte="projeto" />
      <LinhaDeFato rotulo="Meta efetiva" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
    {form && alterar && (
      <>
        <Secao titulo="Metas de conversão desta campanha" caminho={`${C}.metas_de_conversao`}
               descricao="Vazio = as metas da conta. Cada linha sobrescreve, NESTA campanha, se a categoria × origem entra no lance.">
          <Repetidor<LinhaDeCategoria>
            rotulo="Sobrescritas"
            itens={form.metas}
            onChange={(v) => alterar('metas', v)}
            caminho={`${C}.metas_de_conversao`}
            novo={() => ({ categoria: 'PURCHASE', origem: 'WEBSITE', lance: true })}
            render={(m, i, mudar) => (
              <div className="grid gap-2 sm:grid-cols-3">
                <CampoSelecao id={`pmax-meta-${i}-cat`} rotulo="categoria" valor={m.categoria}
                              caminho={`${C}.metas_de_conversao[${i}].categoria`}
                              opcoes={opcoesDoEsquema(esquema, 'metas_de_conversao[].categoria', CATEGORIAS_DE_CONVERSAO).map((v) => ({ valor: v, rotulo: v }))}
                              onChange={(v) => mudar({ ...m, categoria: v as LinhaDeCategoria['categoria'] })} />
                <CampoSelecao id={`pmax-meta-${i}-ori`} rotulo="origem" valor={m.origem}
                              caminho={`${C}.metas_de_conversao[${i}].origem`}
                              opcoes={opcoesDoEsquema(esquema, 'metas_de_conversao[].origem', ORIGENS_DE_CONVERSAO).map((v) => ({ valor: v, rotulo: v }))}
                              onChange={(v) => mudar({ ...m, origem: v as LinhaDeCategoria['origem'] })} />
                <Interruptor id={`pmax-meta-${i}-lance`} rotulo="entra no lance" marcado={m.lance}
                             onChange={(v) => mudar({ ...m, lance: v })} caminho={`${C}.metas_de_conversao[${i}].biddable`} />
              </div>
            )}
          />
        </Secao>
        <Secao titulo="Aquisição de cliente novo" caminho={`${C}.meta_cliente_novo`}
               descricao="Aceita na forma e aplicada numa SEGUNDA chamada depois da criação: o validate_only não a confere.">
          <Interruptor id="pmax-cliente-novo" rotulo="Declarar meta de cliente novo" marcado={form.clienteNovo}
                       onChange={(v) => alterar('clienteNovo', v)} />
          {form.clienteNovo && (
            <div className="grid gap-4 lg:grid-cols-2">
              <CampoTexto id="pmax-cn-goal" rotulo="Goal NEW_CUSTOMER_ACQUISITION" valor={form.cnGoal}
                          onChange={(v) => alterar('cnGoal', v)} caminho={`${C}.meta_cliente_novo.goal`}
                          placeholder="customers/123/goals/456" />
              <CampoSelecao id="pmax-cn-modo" rotulo="Modo" valor={form.cnModo} caminho={`${C}.meta_cliente_novo.modo`}
                            opcoes={opcoesDoEsquema(esquema, 'meta_cliente_novo.modo', MODOS_CLIENTE_NOVO).map((v) => ({
                              valor: v, rotulo: v === 'TARGET_ALL' ? 'Todos, com valor extra para cliente novo' : 'Só cliente novo',
                            }))}
                            onChange={(v) => alterar('cnModo', v as FormPMax['cnModo'])} />
              <CampoTexto id="pmax-cn-valor" rotulo="Valor adicional" valor={form.cnValor} numerico prefixo="R$"
                          onChange={(v) => alterar('cnValor', v)} caminho={`${C}.meta_cliente_novo.valor_adicional`} />
              <CampoTexto id="pmax-cn-mult" rotulo="Multiplicador de valor" valor={form.cnMultiplicador} numerico
                          onChange={(v) => alterar('cnMultiplicador', v)} caminho={`${C}.meta_cliente_novo.multiplicador_de_valor`} />
            </div>
          )}
        </Secao>
      </>
    )}
  </section>
);

export const ParadaPMaxLp: React.FC<{
  cockpit: Cockpit;
  destino: LeituraDoDestinoPago;
  form?: FormPMax;
  alterar?: AlterarPMax;
  esquema?: EsquemaJson | null;
}> = ({ cockpit, destino, form, alterar, esquema = null }) => (
  <div className="space-y-6">
    <section className="destination-hero">
      <div className="destination-hero-icon" aria-hidden><Globe2 className="h-5 w-5" /></div>
      <div className="min-w-0 flex-1">
        <p className="kicker text-muted-foreground">único destino permitido</p>
        <p className="mt-1 break-all font-display text-lg font-semibold text-foreground sm:text-xl">
          {cockpit.origem?.url_final ?? 'Aguardando uma LP aprovada'}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">A URL nasce do funil e volta a ser conferida na revisão.</p>
      </div>
      <span className={cn(
        'destination-status',
        destino.apto_para_campanha ? 'destination-status-ok' : 'destination-status-blocked',
      )}>
        {destino.apto_para_campanha ? <ShieldCheck className="h-4 w-4" /> : <CircleDashed className="h-4 w-4" />}
        {destino.apto_para_campanha ? 'LP apta' : 'aguarda prova'}
      </span>
    </section>

    <div className="flex gap-4 border-y border-primary/20 bg-primary/[0.035] px-1 py-5">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Link2Off className="h-5 w-5" /></span>
      <div>
        <p className="text-sm font-semibold text-foreground">
          {form?.automacoes.includes('FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION') ? 'Expansão de URL LIGADA por você' : 'Trava de URL exclusiva'}
        </p>
        <p className="mt-1 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          {form?.automacoes.includes('FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION')
            ? 'O Google pode levar o clique para outra página do domínio. As exclusões de URL abaixo passam a morder.'
            : 'O Google não pode escolher outra página do domínio enquanto a expansão de URL final estiver desligada (parada Expansão e marca).'}
        </p>
      </div>
    </div>
    {form && alterar && (
      <>
        <Secao titulo="Opções de URL do asset group principal" caminho={`${C}.opcoes_de_url`}
               descricao="A marcação por grupo, sem duplicar campanha.">
          <EditorDeOpcoesDeUrl id="pmax-url" valor={form.url_opcoes} onChange={(v) => alterar('url_opcoes', v)}
                               caminho={`${C}.opcoes_de_url`} />
        </Secao>
        <Secao titulo="Exclusões de URL" caminho={`${C}.exclusoes_de_url`}
               descricao="Páginas para onde a expansão não pode levar. Só mordem com a expansão de URL ligada.">
          <Repetidor
            rotulo="Regras"
            itens={form.exclusoesDeUrl}
            onChange={(v) => alterar('exclusoesDeUrl', v)}
            caminho={`${C}.exclusoes_de_url`}
            novo={() => ({ nome: '', argumento: '', operando: 'URL' as const, operador: 'CONTAINS' as const })}
            render={(x, i, mudar) => (
              <div className="grid gap-2 sm:grid-cols-4">
                <CampoTexto id={`pmax-exc-${i}-nome`} rotulo="nome" valor={x.nome}
                            caminho={`${C}.exclusoes_de_url[${i}].nome`} onChange={(v) => mudar({ ...x, nome: v })} />
                <CampoSelecao id={`pmax-exc-${i}-op`} rotulo="olha" valor={x.operando}
                              caminho={`${C}.exclusoes_de_url[${i}].operando`}
                              opcoes={opcoesDoEsquema(esquema, 'exclusoes_de_url[].operando', OPERANDOS_DE_EXCLUSAO_URL).map((v) => ({ valor: v, rotulo: v === 'URL' ? 'a URL' : v === 'PAGE_TITLE' ? 'o título' : 'o conteúdo' }))}
                              onChange={(v) => mudar({ ...x, operando: v as typeof x.operando })} />
                <CampoSelecao id={`pmax-exc-${i}-opr`} rotulo="regra" valor={x.operador}
                              caminho={`${C}.exclusoes_de_url[${i}].operador`}
                              opcoes={opcoesDoEsquema(esquema, 'exclusoes_de_url[].operador', OPERADORES_DE_EXCLUSAO_URL).map((v) => ({ valor: v, rotulo: v === 'CONTAINS' ? 'contém' : 'é igual a' }))}
                              onChange={(v) => mudar({ ...x, operador: v as typeof x.operador })} />
                <CampoTexto id={`pmax-exc-${i}-arg`} rotulo="valor" valor={x.argumento} placeholder="/blog/"
                            caminho={`${C}.exclusoes_de_url[${i}].argumento`} onChange={(v) => mudar({ ...x, argumento: v })} />
              </div>
            )}
          />
        </Secao>
      </>
    )}
  </div>
);

export const ParadaPMaxAssetGroup: React.FC<{
  nomeAssetGroup: string;
  onNomeAssetGroup: (valor: string) => void;
  nomeEmpresa: string;
  onNomeEmpresa: (valor: string) => void;
  titulos: string;
  onTitulos: (valor: string) => void;
  titulosLongos: string;
  onTitulosLongos: (valor: string) => void;
  descricoes: string;
  onDescricoes: (valor: string) => void;
  videos: string;
  onVideos: (valor: string) => void;
  assets: AssetDemandGen[];
  onAssets: (assets: AssetDemandGen[]) => void;
  form?: FormPMax;
  alterar?: AlterarPMax;
  brandGuidelines?: boolean | null;
  imagensDosGrupos?: Record<string, AssetDemandGen[]>;
  onImagensDoGrupo?: (id: string, assets: AssetDemandGen[]) => void;
}> = ({
  nomeAssetGroup, onNomeAssetGroup, nomeEmpresa, onNomeEmpresa, titulos,
  onTitulos, titulosLongos, onTitulosLongos, descricoes, onDescricoes,
  videos, onVideos, assets, onAssets, form, alterar, brandGuidelines = null,
  imagensDosGrupos = {}, onImagensDoGrupo = () => {},
}) => (
  <section>
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-verified/10 text-verified"><FolderArchive className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">asset group</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Uma história completa, não uma coleção de arquivos</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">O grupo só fica elegível quando texto e mídia aprovados cobrem os formatos mínimos. Nada abaixo foi lido ainda.</p>
      </div>
    </div>
    <div className="mt-5">
      <CampoDeTexto id="pmax-asset-group-name" rotulo="Nome do asset group" valor={nomeAssetGroup} onChange={onNomeAssetGroup} limite={128} placeholder="Derivado do tema quando vazio" />
    </div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <SeletorDeAsset id="pmax-marketing" rotulo="Imagem horizontal" tipo="imagem_marketing" detalhe="1.91:1 · 1 a 20" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="pmax-square" rotulo="Imagem quadrada" tipo="imagem_marketing_quadrada" detalhe="1:1 · 1 a 20" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="pmax-portrait" rotulo="Imagem vertical" tipo="imagem_marketing_retrato" detalhe="4:5 · opcional, até 20" assets={assets} onChange={onAssets} maximo={20} />
      <SeletorDeAsset id="pmax-logo" rotulo="Logo quadrado" tipo="logo_quadrado" detalhe="1:1 · 1 a 5" assets={assets} onChange={onAssets} maximo={5} />
      <SeletorDeAsset id="pmax-landscape-logo" rotulo="Logo horizontal" tipo="logo_paisagem" detalhe="4:1 · opcional, até 20" assets={assets} onChange={onAssets} maximo={20} />
    </div>
    <div className="mt-4 flex justify-end"><IrParaEstudio canal="PERFORMANCE_MAX" /></div>
    <div className="mt-6 grid gap-5 border-t border-border pt-6 lg:grid-cols-2">
      <div className="lg:col-span-2"><CampoDeTexto id="pmax-business-name" rotulo="Nome da empresa" valor={nomeEmpresa} onChange={onNomeEmpresa} limite={25} /></div>
      <EditorDeLista id="pmax-headlines" rotulo="Títulos curtos" valor={titulos} onChange={onTitulos} minimo={3} maximo={15} limitePorItem={30} />
      <EditorDeLista id="pmax-long-headlines" rotulo="Títulos longos" valor={titulosLongos} onChange={onTitulosLongos} minimo={1} maximo={5} limitePorItem={90} />
      <EditorDeLista id="pmax-descriptions" rotulo="Descrições" valor={descricoes} onChange={onDescricoes} minimo={2} maximo={5} limitePorItem={90} ajuda="ao menos uma descrição deve ter até 60 caracteres" />
      <CampoLista id="pmax-videos" rotulo="Vídeos do YouTube (opcional)" valor={videos} onChange={onVideos}
                  maximo={15} placeholder="M7lc1UVf-VE" caminho={`${C}.videos`}
                  ajuda="id público (11 caracteres). Nasce no mesmo mutate, fora do portão de política: o servidor não tem os bytes" />
    </div>
    {form && alterar && (
      <>
        <div className="mt-6 grid gap-4 border-t border-border pt-6 sm:grid-cols-2">
          <CampoTexto id="pmax-path1" rotulo="Caminho 1" valor={form.path1} limite={15}
                      onChange={(v) => alterar('path1', v)} caminho={`${C}.path1`} placeholder="cursos" />
          <CampoTexto id="pmax-path2" rotulo="Caminho 2" valor={form.path2} limite={15}
                      onChange={(v) => alterar('path2', v)} caminho={`${C}.path2`} placeholder="senac" ajuda="exige o caminho 1" />
        </div>
        <Secao titulo="Asset groups adicionais" caminho={`${C}.grupos_adicionais`} className="mt-6"
               descricao={<>Cada grupo tem tudo que é dele, nada herdado: textos, imagens, sinais, vídeos e URL. As imagens passam pelo mesmo portão de política do grupo principal.{brandGuidelines ? ' Com brand guidelines, o logo é da campanha: o grupo adicional não leva logo.' : ''}</>}>
          <Repetidor<FormGrupoPMax>
            rotulo="Grupos"
            itens={form.grupos}
            onChange={(v) => alterar('grupos', v)}
            caminho={`${C}.grupos_adicionais`}
            maximo={99}
            rotuloDoBotao="Adicionar asset group"
            novo={novoGrupoPMax}
            render={(g, i, mudar) => {
              const base = `${C}.grupos_adicionais[${i}]`;
              const imgs = imagensDosGrupos[g.id] ?? [];
              return (
                <div className="space-y-4">
                  <p className="kicker text-muted-foreground">asset group {i + 2}</p>
                  <div className="grid gap-3 lg:grid-cols-2">
                    <CampoTexto id={`pmax-g${i}-nome`} rotulo="Nome" valor={g.nome} caminho={`${base}.nome`}
                                onChange={(v) => mudar({ ...g, nome: v })} />
                    <CampoTexto id={`pmax-g${i}-url`} rotulo="URL final" valor={g.url} caminho={`${base}.url_final`}
                                onChange={(v) => mudar({ ...g, url: v })} placeholder="https://" />
                    <CampoLista id={`pmax-g${i}-titulos`} rotulo="Títulos" valor={g.titulos} caminho={`${base}.textos.headlines`}
                                onChange={(v) => mudar({ ...g, titulos: v })} maximo={15} limitePorItem={30} />
                    <CampoLista id={`pmax-g${i}-longos`} rotulo="Títulos longos" valor={g.titulosLongos} caminho={`${base}.textos.long_headlines`}
                                onChange={(v) => mudar({ ...g, titulosLongos: v })} maximo={5} limitePorItem={90} />
                    <CampoLista id={`pmax-g${i}-desc`} rotulo="Descrições" valor={g.descricoes} caminho={`${base}.textos.descriptions`}
                                onChange={(v) => mudar({ ...g, descricoes: v })} maximo={5} limitePorItem={90} />
                    <CampoLista id={`pmax-g${i}-videos`} rotulo="Vídeos (ids)" valor={g.videos} caminho={`${base}.videos`}
                                onChange={(v) => mudar({ ...g, videos: v })} maximo={15} />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <SeletorDeAsset id={`pmax-g${i}-paisagem`} rotulo="Imagem horizontal" tipo="imagem_marketing"
                                    detalhe="1.91:1" assets={imgs} onChange={(a) => onImagensDoGrupo(g.id, a)} maximo={20} />
                    <SeletorDeAsset id={`pmax-g${i}-quadrada`} rotulo="Imagem quadrada" tipo="imagem_marketing_quadrada"
                                    detalhe="1:1" assets={imgs} onChange={(a) => onImagensDoGrupo(g.id, a)} maximo={20} />
                    {!brandGuidelines && (
                      <SeletorDeAsset id={`pmax-g${i}-logo`} rotulo="Logo quadrado" tipo="logo_quadrado"
                                      detalhe="1:1 · sem brand guidelines, o logo é do grupo" assets={imgs}
                                      onChange={(a) => onImagensDoGrupo(g.id, a)} maximo={5} />
                    )}
                  </div>
                  <ErroDoCampo caminho={`${base}.imagens`} />
                  <div className="grid gap-3 lg:grid-cols-2">
                    <CampoLista id={`pmax-g${i}-aud`} rotulo="Sinais de audiência" valor={g.audiencias}
                                onChange={(v) => mudar({ ...g, audiencias: v })} placeholder="customers/123/audiences/456" />
                    <CampoLista id={`pmax-g${i}-temas`} rotulo="Temas de pesquisa" valor={g.temas}
                                onChange={(v) => mudar({ ...g, temas: v })} />
                  </div>
                  <Interruptor id={`pmax-g${i}-sinais`} rotulo="Confirmo os sinais deste grupo"
                               marcado={g.sinaisConfirmados} onChange={(v) => mudar({ ...g, sinaisConfirmados: v })}
                               caminho={`${base}.sinais`}
                               ajuda="Vazio confirmado = sem dica (escolha). Sem confirmar = ninguém escolheu, e o servidor recusa." />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <CampoTexto id={`pmax-g${i}-p1`} rotulo="Caminho 1" valor={g.path1} limite={15} caminho={`${base}.path1`}
                                onChange={(v) => mudar({ ...g, path1: v })} />
                    <CampoTexto id={`pmax-g${i}-p2`} rotulo="Caminho 2" valor={g.path2} limite={15} caminho={`${base}.path2`}
                                onChange={(v) => mudar({ ...g, path2: v })} />
                  </div>
                  <EditorDeOpcoesDeUrl id={`pmax-g${i}-url`} valor={g.url_opcoes}
                                       onChange={(v) => mudar({ ...g, url_opcoes: v })} caminho={`${base}.opcoes_de_url`} />
                </div>
              );
            }}
          />
        </Secao>
      </>
    )}
  </section>
);

export const ParadaPMaxSinais: React.FC<{
  audiencias: string;
  onAudiencias: (valor: string) => void;
  searchThemes: string;
  onSearchThemes: (valor: string) => void;
  sinaisConfirmados: boolean;
  onSinaisConfirmados: (valor: boolean) => void;
  negativas: string;
  onNegativas: (valor: string) => void;
  negativasConfirmadas: boolean;
  onNegativasConfirmadas: (valor: boolean) => void;
  form?: FormPMax;
  alterar?: AlterarPMax;
  esquema?: EsquemaJson | null;
}> = ({
  audiencias, onAudiencias, searchThemes, onSearchThemes,
  sinaisConfirmados, onSinaisConfirmados, negativas, onNegativas,
  negativasConfirmadas, onNegativasConfirmadas, form, alterar, esquema = null,
}) => (
  <section className="space-y-6">
    <div className="flex items-start gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-info/10 text-info"><Users2 className="h-5 w-5" /></span>
      <div>
        <p className="kicker text-muted-foreground">orientação do algoritmo</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Sinais ajudam a começar; não restringem como keywords</h3>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">Audience signals e Search Themes são pistas para o sistema. Eles não são termos de correspondência e não garantem em qual busca a campanha aparece.</p>
      </div>
    </div>
    <div className="grid gap-5 border-y border-border py-5 lg:grid-cols-2">
      <EditorDeLista id="pmax-audiences" rotulo="Audience signals" valor={audiencias} onChange={onAudiencias} placeholder="customers/123/audiences/456" ajuda="dicas imutáveis; não restringem a entrega" />
      <EditorDeLista id="pmax-search-themes" rotulo="Search Themes" valor={searchThemes} onChange={onSearchThemes} ajuda="temas, não keywords positivas" />
      <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border bg-background px-4 text-sm lg:col-span-2">
        <input type="checkbox" checked={sinaisConfirmados} onChange={(e) => onSinaisConfirmados(e.target.checked)} className="h-4 w-4 accent-primary" />
        <span><strong>Confirmo estes sinais</strong> — listas vazias significam começar sem dicas.</span>
      </label>
      <div className="lg:col-span-2"><EditorDeLista id="pmax-negatives" rotulo="Keywords negativas de campanha" valor={negativas} onChange={onNegativas} maximo={10000} ajuda="único uso de keyword no PMax desta versão" /></div>
      <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border bg-background px-4 text-sm lg:col-span-2">
        <input type="checkbox" checked={negativasConfirmadas} onChange={(e) => onNegativasConfirmadas(e.target.checked)} className="h-4 w-4 accent-primary" />
        <span><strong>Confirmo estas negativas</strong> — vazio é uma escolha explícita, não ausência.</span>
      </label>
    </div>
    {form && alterar && (
      <>
        <Secao titulo="Negativas com correspondência" caminho={`${C}.negativas_tipadas`}
               descricao="Além das amplas acima: frase e exata travam só a família ou só o termo.">
          <Repetidor
            rotulo="Termos"
            itens={form.negativasTipadas}
            onChange={(v) => alterar('negativasTipadas', v)}
            caminho={`${C}.negativas_tipadas`}
            novo={() => ({ texto: '', match: 'PHRASE' as const })}
            render={(n, i, mudar) => (
              <div className="grid gap-2 sm:grid-cols-[2fr_1fr]">
                <CampoTexto id={`pmax-neg-${i}`} rotulo="termo" valor={n.texto}
                            caminho={`${C}.negativas_tipadas[${i}].texto`} onChange={(v) => mudar({ ...n, texto: v })} />
                <CampoSelecao id={`pmax-neg-${i}-match`} rotulo="correspondência" valor={n.match}
                              caminho={`${C}.negativas_tipadas[${i}].match_type`}
                              opcoes={opcoesDoEsquema(esquema, 'negativas_tipadas[].match_type', MATCH_TYPES_NEGATIVA_PMAX).map((v) => ({ valor: v, rotulo: v === 'BROAD' ? 'ampla' : v === 'PHRASE' ? 'frase' : 'exata' }))}
                              onChange={(v) => mudar({ ...n, match: v as typeof n.match })} />
              </div>
            )}
          />
          <CampoLista id="pmax-listas-negativas" rotulo="Listas de negativas existentes" valor={form.listasDeNegativas}
                      onChange={(v) => alterar('listasDeNegativas', v)} caminho={`${C}.listas_de_negativas`}
                      placeholder="customers/123/sharedSets/456" />
        </Secao>
        <Secao titulo="Exclusões de marca" caminho={`${C}.marcas_excluidas`}
               descricao="Marcas do catálogo do Google, por entidade, e listas de marca da conta.">
          <Repetidor
            rotulo="Marcas"
            itens={form.marcasExcluidas}
            onChange={(v) => alterar('marcasExcluidas', v)}
            caminho={`${C}.marcas_excluidas`}
            novo={() => ({ entity_id: '', nome: '' })}
            render={(m, i, mudar) => (
              <div className="grid gap-2 sm:grid-cols-2">
                <CampoTexto id={`pmax-marca-${i}-id`} rotulo="entidade" valor={m.entity_id} placeholder="/g/11trqcwsy6"
                            caminho={`${C}.marcas_excluidas[${i}].entity_id`} onChange={(v) => mudar({ ...m, entity_id: v })} />
                <CampoTexto id={`pmax-marca-${i}-nome`} rotulo="nome" valor={m.nome}
                            caminho={`${C}.marcas_excluidas[${i}].nome`} onChange={(v) => mudar({ ...m, nome: v })} />
              </div>
            )}
          />
          <CampoLista id="pmax-listas-marcas" rotulo="Listas de marcas excluídas" valor={form.listasDeMarcas}
                      onChange={(v) => alterar('listasDeMarcas', v)} caminho={`${C}.listas_de_marcas_excluidas`}
                      placeholder="customers/123/sharedSets/456" />
        </Secao>
        <Secao titulo="Guias de texto gerado" descricao="Valem para o texto que a automação escrever.">
          <div className="grid gap-4 lg:grid-cols-2">
            <CampoLista id="pmax-termos-excluidos" rotulo="Termos excluídos" valor={form.termosExcluidos}
                        onChange={(v) => alterar('termosExcluidos', v)} caminho={`${C}.termos_excluidos`}
                        maximo={25} limitePorItem={30} />
            <CampoLista id="pmax-restricoes" rotulo="Restrições de mensagem" valor={form.restricoes}
                        onChange={(v) => alterar('restricoes', v)} caminho={`${C}.restricoes_de_mensagem`}
                        maximo={40} limitePorItem={300} placeholder="Não prometer vaga, bolsa ou aprovação." />
          </div>
        </Secao>
      </>
    )}
  </section>
);

export const ParadaPMaxMarca: React.FC<{
  brandGuidelines: boolean | null;
  onBrandGuidelines: (valor: boolean) => void;
  form?: FormPMax;
  alterar?: AlterarPMax;
  esquema?: EsquemaJson | null;
}> = ({ brandGuidelines, onBrandGuidelines, form, alterar, esquema = null }) => {
  const automacoes = opcoesDoEsquema(esquema, 'automacoes_optadas[]', AUTOMACOES_PMAX) as AutomacaoPMax[];
  const optadas = form?.automacoes ?? [];
  const alternar = (a: AutomacaoPMax) => {
    if (!form || !alterar) return;
    alterar('automacoes', optadas.includes(a) ? optadas.filter((x) => x !== a) : [...optadas, a]);
  };
  return (
    <section className="space-y-6">
      <div>
        <p className="kicker text-muted-foreground">controles de automação</p>
        <h3 className="mt-1 font-display text-xl font-semibold">O Google pode combinar assets, não trocar o destino</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          As sete automações que a API aceita viajam sempre: as que você não ligar vão como OPTED_OUT.
        </p>
      </div>
      <ul className="divide-y divide-border border-y border-border">
        {automacoes.map((a) => {
          const ligada = optadas.includes(a);
          const r = ROTULO_AUTOMACAO_PMAX[a] ?? { titulo: a, detalhe: '' };
          return (
            <li key={a} className="flex items-center gap-4 py-3">
              <span className={cn('grid h-9 w-9 shrink-0 place-items-center rounded-full',
                ligada ? 'bg-warning/10 text-warning' : 'bg-success/10 text-success')}>
                {ligada ? <Sparkles className="h-4 w-4" /> : <Ban className="h-4 w-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{r.titulo}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{r.detalhe} <code className="text-[11px]">{a}</code></p>
              </div>
              <button type="button" aria-pressed={ligada} disabled={!form}
                      aria-label={`${ligada ? 'Desligar' : 'Ligar'} ${r.titulo}`}
                      onClick={() => alternar(a)}
                      className={cn('rounded-full border px-3 py-1 text-xs font-bold',
                        ligada ? 'border-warning/30 bg-warning/10 text-warning' : 'border-success/30 bg-success/10 text-success')}>
                {ligada ? 'LIGADA' : 'DESLIGADA'}
              </button>
            </li>
          );
        })}
      </ul>
      <ErroDoCampo caminho={`${C}.automacoes_optadas`} />
      {form && alterar && (
        <Secao titulo="Busca automática de vídeos" caminho={`${C}.video_crawl`}
               descricao="URLs onde o Google pode buscar vídeo. Com a automação ligada, exige fontes e a declaração de direitos.">
          <Repetidor
            rotulo="Fontes"
            itens={form.videoCrawl}
            onChange={(v) => alterar('videoCrawl', v)}
            caminho={`${C}.video_crawl`}
            novo={() => ({ url: '', plataforma: 'LANDING_PAGE' as const, habilitada: true })}
            render={(f, i, mudar) => (
              <div className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr]">
                <CampoTexto id={`pmax-crawl-${i}-url`} rotulo="URL" valor={f.url} placeholder="https://"
                            caminho={`${C}.video_crawl[${i}].url`} onChange={(v) => mudar({ ...f, url: v })} />
                <CampoSelecao id={`pmax-crawl-${i}-plat`} rotulo="plataforma" valor={f.plataforma}
                              caminho={`${C}.video_crawl[${i}].plataforma`}
                              opcoes={opcoesDoEsquema(esquema, 'video_crawl[].plataforma', PLATAFORMAS_DE_VIDEO_CRAWL).map((v) => ({ valor: v, rotulo: v === 'LANDING_PAGE' ? 'landing page' : v === 'SOCIAL' ? 'rede social' : 'YouTube' }))}
                              onChange={(v) => mudar({ ...f, plataforma: v as typeof f.plataforma })} />
                <Interruptor id={`pmax-crawl-${i}-on`} rotulo="habilitada" marcado={f.habilitada}
                             onChange={(v) => mudar({ ...f, habilitada: v })} />
              </div>
            )}
          />
          <Interruptor id="pmax-direitos" marcado={form.direitosDeclarados}
                       onChange={(v) => alterar('direitosDeclarados', v)}
                       caminho={`${C}.video_crawl_direitos_declarados`}
                       rotulo="Declaro que a casa tem direito sobre os vídeos encontrados nessas fontes"
                       ajuda="Obrigatória com a busca automática de vídeos. A declaração entra na impressão aprovável." />
        </Secao>
      )}
      <EscolhaExplicita
        rotulo="Brand guidelines"
        valor={brandGuidelines}
        onChange={onBrandGuidelines}
        positivo="Ligadas — nome e logo no nível da campanha"
        negativo="Desligadas — nome e logo no asset group"
        ajuda="Esta escolha é imutável na criação. A interface exige uma decisão em vez de herdar o default remoto."
      />
      {form && alterar && brandGuidelines && (
        <Secao titulo="Diretrizes de marca" caminho={`${C}.diretrizes_de_marca`}
               descricao="Só com brand guidelines ligadas.">
          <div className="grid gap-4 sm:grid-cols-3">
            <CampoTexto id="pmax-cor-principal" rotulo="Cor principal" valor={form.corPrincipal} placeholder="#0B3D91"
                        onChange={(v) => alterar('corPrincipal', v)} caminho={`${C}.diretrizes_de_marca.cor_principal`} />
            <CampoTexto id="pmax-cor-destaque" rotulo="Cor de destaque" valor={form.corDestaque} placeholder="#F2A900"
                        onChange={(v) => alterar('corDestaque', v)} caminho={`${C}.diretrizes_de_marca.cor_destaque`} />
            <CampoSelecao id="pmax-fonte" rotulo="Fonte" valor={form.fonte} caminho={`${C}.diretrizes_de_marca.fonte`}
                          opcoes={opcoesDoEsquema(esquema, 'diretrizes_de_marca.fonte', FONTES_DE_MARCA).map((v) => ({ valor: v, rotulo: v || 'sem fonte' }))}
                          onChange={(v) => alterar('fonte', v)} />
          </div>
        </Secao>
      )}
    </section>
  );
};

export const ParadaPMaxEconomia: React.FC<{
  cockpit: Cockpit;
  orcamento: number | null;
  orcamentoBruto: string;
  onOrcamento: (valor: string) => void;
  estrategia: 'MAXIMIZE_CONVERSIONS' | 'MAXIMIZE_CONVERSION_VALUE';
  onEstrategia: (valor: 'MAXIMIZE_CONVERSIONS' | 'MAXIMIZE_CONVERSION_VALUE') => void;
  meta: string;
  onMeta: (valor: string) => void;
}> = ({ cockpit, orcamento, orcamentoBruto, onOrcamento, estrategia, onEstrategia, meta, onMeta }) => (
  <section className="space-y-5">
    <div>
      <p className="kicker text-muted-foreground">economia automatizada</p>
      <h3 className="mt-1 font-display text-xl font-semibold">Bidding depende de uma meta confiável</h3>
      <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">Esta bancada não reutiliza CPC manual do Search. Alvo e estratégia só podem nascer do contrato PMax.</p>
    </div>
    <dl className="grid gap-4 border-y border-border py-5 sm:grid-cols-3">
      <LinhaDeFato rotulo="Orçamento" valor={orcamento == null ? null : `R$ ${orcamento.toFixed(2).replace('.', ',')}/dia`} fonte="rascunho" />
      <LinhaDeFato rotulo="Estratégia" valor={estrategia} fonte="você, agora" />
      <LinhaDeFato rotulo="Meta efetiva" valor={cockpit.conta?.meta_conversao?.primaria?.nome ?? null} fonte="conta" />
    </dl>
    <div className="grid gap-5 sm:grid-cols-2">
      <label className="space-y-2 text-sm font-semibold">
        <span>Orçamento diário</span>
        <Input inputMode="decimal" value={orcamentoBruto} onChange={(e) => onOrcamento(e.target.value)} placeholder="10,00" className="h-11 bg-background" />
      </label>
      <label className="space-y-2 text-sm font-semibold">
        <span>Estratégia de lance</span>
        <select value={estrategia} onChange={(e) => onEstrategia(e.target.value as typeof estrategia)} className="flex h-11 w-full rounded-md border border-input bg-background px-3 text-sm">
          <option value="MAXIMIZE_CONVERSIONS">Maximizar conversões</option>
          <option value="MAXIMIZE_CONVERSION_VALUE">Maximizar valor de conversão</option>
        </select>
      </label>
      <label className="space-y-2 text-sm font-semibold sm:col-span-2">
        <span>{estrategia === 'MAXIMIZE_CONVERSION_VALUE' ? 'ROAS-alvo em % (opcional)' : 'CPA-alvo (opcional)'}</span>
        <Input inputMode="decimal" value={meta} onChange={(e) => onMeta(e.target.value)} placeholder="Deixe vazio para maximização sem meta numérica" className="h-11 max-w-sm bg-background" />
        <span className="block text-xs font-normal text-muted-foreground">O recibo de mensuração vem da conta e não pode ser digitado. Maximizar valor exige ações que carreguem valor. ROAS em %: 400 = R$ 4 de valor por real.</span>
      </label>
    </div>
  </section>
);

export const ParadaPMaxRevisao: React.FC<{
  url: string | null;
  faltas: string[];
  estadoDoPlano: 'ociosa' | 'provando' | 'aprovada' | 'recusada';
  mensagemDoPlano: string | null;
  onPlanejar: () => void;
  estadoDaProva?: 'ociosa' | 'provando' | 'aprovada' | 'recusada';
  mensagemDaProva?: string | null;
  onProvar?: () => void;
  resumo?: LinhaDoResumo[];
  avisosPrevistos?: AvisoDaRevisao[];
  avisosDoServidor?: AvisoDaRevisao[] | null;
  erros?: ErrosDoServidor;
  expansaoDeUrl?: boolean;
}> = ({
  url, faltas, estadoDoPlano, mensagemDoPlano, onPlanejar, estadoDaProva, mensagemDaProva, onProvar,
  resumo, avisosPrevistos = [], avisosDoServidor = null, erros, expansaoDeUrl = false,
}) => (
  <section className="space-y-6">
    <div className="flex items-start justify-between gap-4 border-b border-border pb-5">
      <div>
        <p className="kicker text-muted-foreground">revisão PMax</p>
        <h3 className="mt-1 font-display text-xl font-semibold">Prova no Google, criação ainda fechada</h3>
        <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted-foreground">
          A prova roda validate_only com a configuração completa (grupos adicionais, automações, exclusões).
          Ela é fechada por chave do servidor: desligada, a resposta é uma recusa sem nenhuma chamada. Nenhum botão de mutate é exibido.
        </p>
      </div>
      <span className="shrink-0 rounded-full border border-info/30 bg-info/10 px-3 py-1 text-xs font-semibold text-info">validate_only</span>
    </div>
    <dl className="grid gap-4 sm:grid-cols-2">
      <LinhaDeFato rotulo="URL do grupo principal" valor={url} fonte="funil" />
      <LinhaDeFato rotulo="Expansão de URL" valor={expansaoDeUrl ? 'ligada' : 'desligada'} fonte="automações optadas" />
    </dl>
    {resumo && <ResumoDoCanal titulo="Suas escolhas de Performance Max" linhas={resumo} />}
    <AvisosDaRevisao previstos={avisosPrevistos} doServidor={avisosDoServidor} />
    {erros && <ErrosDeForma erros={erros} />}
    {faltas.length > 0 && <p className="text-sm text-muted-foreground">Próximo: {faltas[0]}</p>}
    {onProvar && (
      <AcaoDeProva
        estado={estadoDaProva ?? 'ociosa'}
        mensagem={mensagemDaProva ?? null}
        desabilitada={faltas.length > 0}
        motivo={faltas[0] ?? null}
        onProvar={onProvar}
      />
    )}
    <details className="rounded-lg border border-border p-4">
      <summary className="cursor-pointer text-sm font-semibold">Só o plano local, sem a configuração v25</summary>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        `/planejar-pmax` não lê a conta nem chama o Google, e não aceita `configuracao_pmax`: confere só a base (grupo principal, sinais, negativas amplas).
      </p>
      <div className="mt-3">
        <AcaoDeProva
          estado={estadoDoPlano}
          mensagem={mensagemDoPlano}
          desabilitada={faltas.length > 0}
          motivo={faltas[0] ?? null}
          onProvar={onPlanejar}
          somenteLocal
        />
      </div>
    </details>
  </section>
);
