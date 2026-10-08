/**
 * Search além do Brief — os controles de `configuracao_search`
 * (GADS-CRIACAO-CANAIS-v1 §6.1): rede, AI Max, RSA, programação, dispositivos,
 * geo, datas e meta de conversão.
 *
 * Cada controle escreve no formulário (`FormSearch`), e só a montagem
 * (`lib/trafego/configuracao/montagem.ts`) o converte em contrato. Opções de
 * enum vêm do esquema vivo quando ele chegou.
 */
import React from 'react';
import { AlertTriangle } from 'lucide-react';

import {
  CampoLista, CampoSelecao, CampoTexto, DecisaoSimNao, EditorDeAgenda, Interruptor, Repetidor, Secao,
} from '../campos/Campos';
import { opcoesDoEsquema } from '@/lib/trafego/configuracao/esquema';
import type { FormSearch, LinhaDeCategoria, LinhaDeDispositivo } from '@/lib/trafego/configuracao/formularios';
import {
  CATEGORIAS_DE_CONVERSAO, DISPOSITIVOS, ORIGENS_DE_CONVERSAO, POSICOES_DE_FIXACAO,
  TIPOS_GEO_NEGATIVO, TIPOS_GEO_POSITIVO,
} from '@/types/trafegoCanais';
import type { EsquemaJson, Fixacao } from '@/types/trafegoCanais';
import type { CopyGerada } from '@/types/trafego';

const C = 'configuracao_search';

type Alterar = <K extends keyof FormSearch>(campo: K, valor: FormSearch[K]) => void;

const ROTULO_GEO: Record<string, string> = {
  PRESENCE: 'Presença — quem está no local',
  PRESENCE_OR_INTEREST: 'Presença ou interesse no local',
  SEARCH_INTEREST: 'Interesse pela busca',
};

const ROTULO_DISPOSITIVO: Record<string, string> = { MOBILE: 'celular', TABLET: 'tablet', DESKTOP: 'computador' };

const ROTULO_POSICAO: Record<string, string> = {
  HEADLINE_1: 'título 1', HEADLINE_2: 'título 2', HEADLINE_3: 'título 3',
  DESCRIPTION_1: 'descrição 1', DESCRIPTION_2: 'descrição 2',
};

// ── Alcance: rede, AI Max, geo, programação, dispositivos, datas ───────────

export const ParadaAlcanceSearch: React.FC<{
  form: FormSearch;
  alterar: Alterar;
  esquema: EsquemaJson | null;
  idiomaDoBrief?: string | null;
}> = ({ form, alterar, esquema, idiomaDoBrief }) => (
  <div className="space-y-6">
    <Secao
      titulo="Rede"
      caminho={`${C}.rede`}
      descricao="Google Search é sempre ligado. Parceiros e expansão para Display são inventário diferente, com outro CPC efetivo — e com a configuração declarada, a rede deixa de ter default."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <DecisaoSimNao
          rotulo="Parceiros de pesquisa"
          valor={form.parceiros}
          onChange={(v) => alterar('parceiros', v)}
          sim="Ligar parceiros"
          nao="Só o Google Search"
          caminho={`${C}.rede.parceiros`}
        />
        <DecisaoSimNao
          rotulo="Expansão para Display"
          valor={form.expansaoDisplay}
          onChange={(v) => alterar('expansaoDisplay', v)}
          sim="Ligar a expansão"
          nao="Não expandir"
          caminho={`${C}.rede.display_expansion`}
        />
      </div>
      {(form.parceiros || form.expansaoDisplay) && (
        <p role="note" className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/[0.06] p-3 text-xs leading-relaxed text-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
          <span>
            {form.expansaoDisplay && <>A expansão para Display <b>sempre gera aviso no plano</b>. </>}
            O canário de Search continua recusando parceiros e expansão: a prova roda, mas a criação pausada não sai com esta rede.
          </span>
        </p>
      )}
    </Secao>

    <Secao titulo="AI Max" caminho={`${C}.ai_max`}
           descricao="Cada automação é declarada, nunca herdada. Desligado, o objeto não viaja e a campanha nasce como antes.">
      <Interruptor id="search-ai-max" rotulo="Usar AI Max nesta campanha" marcado={form.aiMax}
                   onChange={(v) => alterar('aiMax', v)} />
      {form.aiMax && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-3">
            <DecisaoSimNao rotulo="Correspondência de termos" valor={form.aiCorrespondencia}
                           onChange={(v) => alterar('aiCorrespondencia', v)} sim="Ligada" nao="Desligada"
                           caminho={`${C}.ai_max.correspondencia_de_termos`} />
            <DecisaoSimNao rotulo="Personalização de texto" valor={form.aiPersonalizacao}
                           onChange={(v) => alterar('aiPersonalizacao', v)} sim="Ligada" nao="Desligada"
                           caminho={`${C}.ai_max.personalizacao_de_texto`} />
            <DecisaoSimNao rotulo="Expansão de URL final" valor={form.aiExpansaoUrl}
                           onChange={(v) => alterar('aiExpansaoUrl', v)} sim="Ligada" nao="Desligada"
                           caminho={`${C}.ai_max.expansao_de_url_final`}
                           ajuda="Exige personalização de texto ligada." />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <CampoLista id="search-ai-grupos" rotulo="Grupos sem correspondência de termos"
                        valor={form.aiGruposSemCorrespondencia}
                        onChange={(v) => alterar('aiGruposSemCorrespondencia', v)}
                        caminho={`${C}.ai_max.grupos_sem_correspondencia`} ajuda="nome do grupo" />
            <CampoLista id="search-ai-exclusoes-url" rotulo="Exclusões de URL"
                        valor={form.aiExclusoesDeUrl} onChange={(v) => alterar('aiExclusoesDeUrl', v)}
                        caminho={`${C}.ai_max.exclusoes_de_url`} placeholder="/blog/"
                        ajuda="só mordem com a expansão de URL ligada" />
            <CampoLista id="search-ai-marcas-in" rotulo="Listas de marca incluídas"
                        valor={form.aiListasIncluidas} onChange={(v) => alterar('aiListasIncluidas', v)}
                        caminho={`${C}.ai_max.listas_de_marca_incluidas`}
                        placeholder="customers/123/sharedSets/456" />
            <CampoLista id="search-ai-marcas-out" rotulo="Listas de marca excluídas"
                        valor={form.aiListasExcluidas} onChange={(v) => alterar('aiListasExcluidas', v)}
                        caminho={`${C}.ai_max.listas_de_marca_excluidas`}
                        placeholder="customers/123/sharedSets/456" />
            <CampoLista id="search-ai-termos" rotulo="Termos excluídos do texto gerado"
                        valor={form.aiTermosExcluidos} onChange={(v) => alterar('aiTermosExcluidos', v)}
                        caminho={`${C}.ai_max.termos_excluidos`} maximo={25} limitePorItem={30}
                        ajuda="só guiam texto gerado" />
            <CampoLista id="search-ai-restricoes" rotulo="Restrições de mensagem"
                        valor={form.aiRestricoes} onChange={(v) => alterar('aiRestricoes', v)}
                        caminho={`${C}.ai_max.restricoes_de_mensagem`} maximo={40} limitePorItem={300}
                        placeholder="Não prometer vaga ou aprovação." />
          </div>
        </div>
      )}
    </Secao>

    <Secao titulo="Geografia e idioma" caminho={`${C}.geo`}
           descricao="Sem este bloco, a campanha usa o país e o idioma do brief. Com ele, presença e interesse viram decisão sua.">
      <Interruptor id="search-geo" rotulo="Declarar locais, exclusões e idiomas" marcado={form.geo}
                   onChange={(v) => alterar('geo', v)} />
      {form.geo && (
        <div className="grid gap-4 lg:grid-cols-2">
          <CampoSelecao id="search-geo-positivo" rotulo="Quem conta como estando no local"
                        valor={form.geoPositivo} caminho={`${C}.geo.tipo_positivo`}
                        opcoes={opcoesDoEsquema(esquema, 'geo.tipo_positivo', TIPOS_GEO_POSITIVO)
                          .map((v) => ({ valor: v, rotulo: ROTULO_GEO[v] ?? v }))}
                        onChange={(v) => alterar('geoPositivo', v as FormSearch['geoPositivo'])} />
          <CampoSelecao id="search-geo-negativo" rotulo="Quem conta como excluído"
                        valor={form.geoNegativo} caminho={`${C}.geo.tipo_negativo`}
                        opcoes={opcoesDoEsquema(esquema, 'geo.tipo_negativo', TIPOS_GEO_NEGATIVO)
                          .map((v) => ({ valor: v, rotulo: ROTULO_GEO[v] ?? v }))}
                        onChange={(v) => alterar('geoNegativo', v as FormSearch['geoNegativo'])} />
          <CampoLista id="search-geo-locais" rotulo="Locais (ids de geoTargetConstant)" valor={form.geoLocais}
                      onChange={(v) => alterar('geoLocais', v)} caminho={`${C}.geo.locais`}
                      placeholder="1001773" ajuda="do país do brief; vazio = o país inteiro" />
          <CampoLista id="search-geo-excluidos" rotulo="Locais excluídos" valor={form.geoLocaisExcluidos}
                      onChange={(v) => alterar('geoLocaisExcluidos', v)} caminho={`${C}.geo.locais_excluidos`} />
          <CampoLista id="search-geo-idiomas" rotulo="Idiomas" valor={form.geoIdiomas}
                      onChange={(v) => alterar('geoIdiomas', v)} caminho={`${C}.geo.idiomas`}
                      placeholder={idiomaDoBrief ?? 'pt'}
                      ajuda={`precisa conter o idioma do brief${idiomaDoBrief ? ` (${idiomaDoBrief})` : ''}`} />
        </div>
      )}
    </Secao>

    <Secao titulo="Programação de anúncios" caminho={`${C}.programacao`}
           descricao="Vazio = o dia todo, todos os dias. O ajuste de lance só vale em CPC manual e maximizar cliques.">
      <EditorDeAgenda id="search-programacao" rotulo="Faixas" faixas={form.programacao}
                      onChange={(v) => alterar('programacao', v)} caminho={`${C}.programacao`} comAjuste />
    </Secao>

    <Secao titulo="Dispositivos" caminho={`${C}.dispositivos`}
           descricao="Fator 0 exclui o dispositivo; entre 0,1 e 10 ajusta o lance. Sem linha, todos com o mesmo lance.">
      <Repetidor<LinhaDeDispositivo>
        rotulo="Ajustes por dispositivo"
        itens={form.dispositivos}
        onChange={(v) => alterar('dispositivos', v)}
        caminho={`${C}.dispositivos`}
        maximo={3}
        novo={() => ({ dispositivo: 'TABLET', fator: '0' })}
        render={(d, i, mudar) => (
          <div className="grid gap-2 sm:grid-cols-2">
            <CampoSelecao id={`search-disp-${i}`} rotulo="dispositivo" valor={d.dispositivo}
                          caminho={`${C}.dispositivos[${i}].dispositivo`}
                          opcoes={opcoesDoEsquema(esquema, 'dispositivos[].dispositivo', DISPOSITIVOS)
                            .map((v) => ({ valor: v, rotulo: ROTULO_DISPOSITIVO[v] ?? v }))}
                          onChange={(v) => mudar({ ...d, dispositivo: v as typeof d.dispositivo })} />
            <CampoTexto id={`search-disp-${i}-fator`} rotulo="fator" valor={d.fator} numerico
                        caminho={`${C}.dispositivos[${i}].fator`}
                        onChange={(v) => mudar({ ...d, fator: v })} />
          </div>
        )}
      />
    </Secao>

    <Secao titulo="Datas" descricao="Vazio = começa quando for ativada e não termina.">
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto id="search-inicio" rotulo="Início" tipo="date" valor={form.inicio}
                    onChange={(v) => alterar('inicio', v)} caminho={`${C}.inicio`} />
        <CampoTexto id="search-fim" rotulo="Fim" tipo="date" valor={form.fim}
                    onChange={(v) => alterar('fim', v)} caminho={`${C}.fim`} />
      </div>
    </Secao>
  </div>
);

// ── Meta de conversão (na Economia) ───────────────────────────────────────

export const SecaoMetaDeConversaoSearch: React.FC<{
  form: FormSearch;
  alterar: Alterar;
  esquema: EsquemaJson | null;
}> = ({ form, alterar, esquema }) => {
  const categorias = opcoesDoEsquema(esquema, 'meta_de_conversao.categorias[].categoria', CATEGORIAS_DE_CONVERSAO);
  const origens = opcoesDoEsquema(esquema, 'meta_de_conversao.categorias[].origem', ORIGENS_DE_CONVERSAO);
  return (
    <Secao titulo="Para qual conversão esta campanha otimiza" caminho={`${C}.meta_de_conversao`}
           descricao="Sem declarar, a campanha herda as metas da conta. Declarar sobrescreve NESTA campanha.">
      <div className="grid gap-2 sm:grid-cols-3" role="group" aria-label="origem da meta de conversão">
        {([
          ['conta', 'As metas da conta'],
          ['personalizada', 'Meta personalizada'],
          ['acoes', 'Ações e categorias'],
        ] as const).map(([v, t]) => (
          <button key={v} type="button" aria-pressed={form.metaModo === v}
                  onClick={() => alterar('metaModo', v)}
                  className={`min-h-10 rounded-lg border px-3 text-left text-sm ${form.metaModo === v
                    ? 'border-primary/45 bg-primary/[0.07] font-semibold' : 'border-border text-muted-foreground'}`}>
            {t}
          </button>
        ))}
      </div>
      {form.metaModo === 'personalizada' && (
        <CampoTexto id="search-meta-personalizada" rotulo="Meta personalizada (resource name)"
                    valor={form.metaPersonalizada} onChange={(v) => alterar('metaPersonalizada', v)}
                    caminho={`${C}.meta_de_conversao.meta_personalizada`}
                    placeholder="customers/123/customConversionGoals/456" />
      )}
      {form.metaModo === 'acoes' && (
        <div className="space-y-4">
          <CampoLista id="search-meta-acoes" rotulo="Ações de conversão" valor={form.metaAcoes}
                      onChange={(v) => alterar('metaAcoes', v)}
                      caminho={`${C}.meta_de_conversao.acoes_de_conversao`}
                      placeholder="customers/123/conversionActions/456" />
          <Repetidor<LinhaDeCategoria>
            rotulo="Categorias (categoria × origem)"
            itens={form.metaCategorias}
            onChange={(v) => alterar('metaCategorias', v)}
            caminho={`${C}.meta_de_conversao.categorias`}
            novo={() => ({ categoria: 'PURCHASE', origem: 'WEBSITE', lance: true })}
            render={(m, i, mudar) => (
              <div className="grid gap-2 sm:grid-cols-3">
                <CampoSelecao id={`search-cat-${i}`} rotulo="categoria" valor={m.categoria}
                              caminho={`${C}.meta_de_conversao.categorias[${i}].categoria`}
                              opcoes={categorias.map((v) => ({ valor: v, rotulo: v }))}
                              onChange={(v) => mudar({ ...m, categoria: v as LinhaDeCategoria['categoria'] })} />
                <CampoSelecao id={`search-ori-${i}`} rotulo="origem" valor={m.origem}
                              caminho={`${C}.meta_de_conversao.categorias[${i}].origem`}
                              opcoes={origens.map((v) => ({ valor: v, rotulo: v }))}
                              onChange={(v) => mudar({ ...m, origem: v as LinhaDeCategoria['origem'] })} />
                <Interruptor id={`search-lance-${i}`} rotulo="entra no lance" marcado={m.lance}
                             onChange={(v) => mudar({ ...m, lance: v })}
                             caminho={`${C}.meta_de_conversao.categorias[${i}].lance`} />
              </div>
            )}
          />
        </div>
      )}
    </Secao>
  );
};

// ── RSA: caminho exibido e fixações (no Anúncio) ──────────────────────────

export const SecaoRsaSearch: React.FC<{
  form: FormSearch;
  alterar: Alterar;
  copy: CopyGerada | null;
}> = ({ form, alterar, copy }) => {
  const textos = [
    ...(copy?.headlines ?? []).map((t) => ({ t, tipo: 'título' })),
    ...(copy?.descriptions ?? []).map((t) => ({ t, tipo: 'descrição' })),
  ];
  return (
    <Secao titulo="Caminho exibido e fixações" caminho={`${C}.anuncio`}
           descricao="O caminho aparece depois do domínio na URL exibida. Fixar prende um texto da copy a uma posição; sem fixação, o Google combina.">
      <div className="grid gap-4 sm:grid-cols-2">
        <CampoTexto id="search-path1" rotulo="Caminho 1" valor={form.path1} limite={15}
                    onChange={(v) => alterar('path1', v)} caminho={`${C}.anuncio.path1`} placeholder="cursos" />
        <CampoTexto id="search-path2" rotulo="Caminho 2" valor={form.path2} limite={15}
                    onChange={(v) => alterar('path2', v)} caminho={`${C}.anuncio.path2`}
                    placeholder="senac" ajuda="exige o caminho 1" />
      </div>
      <Repetidor<Fixacao>
        rotulo="Fixações"
        itens={form.fixacoes}
        onChange={(v) => alterar('fixacoes', v)}
        caminho={`${C}.anuncio.fixacoes`}
        novo={() => ({ texto: textos[0]?.t ?? '', posicao: 'HEADLINE_1' })}
        render={(f, i, mudar) => (
          <div className="grid gap-2 sm:grid-cols-[2fr_1fr]">
            <CampoSelecao id={`search-fix-${i}-texto`} rotulo="texto da copy" valor={f.texto}
                          caminho={`${C}.anuncio.fixacoes[${i}].texto`} vazio="escolha um texto"
                          opcoes={textos.map(({ t, tipo }) => ({ valor: t, rotulo: `${tipo}: ${t}` }))}
                          onChange={(v) => mudar({ ...f, texto: v })} />
            <CampoSelecao id={`search-fix-${i}-pos`} rotulo="posição" valor={f.posicao}
                          caminho={`${C}.anuncio.fixacoes[${i}].posicao`}
                          opcoes={POSICOES_DE_FIXACAO.map((p) => ({ valor: p, rotulo: ROTULO_POSICAO[p] }))}
                          onChange={(v) => mudar({ ...f, posicao: v as Fixacao['posicao'] })} />
          </div>
        )}
      />
      {textos.length === 0 && (
        <p className="text-xs text-muted-foreground">A fixação escolhe entre os textos da copy escrita; escreva o anúncio primeiro.</p>
      )}
    </Secao>
  );
};
