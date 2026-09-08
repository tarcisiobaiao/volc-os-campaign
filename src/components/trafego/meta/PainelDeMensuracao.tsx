/**
 * A etapa de mensuração, por conjunto (`F22`..`F25`).
 *
 * ## RELATAR e OTIMIZAR são contratos diferentes
 *
 * `receitas.py` diz com todas as letras: relatar "não toca `promoted_object`,
 * `objective` nem `bid_strategy`"; otimizar "muda o payload e exige fonte
 * elegível comprovada". A tela tinha uma linha só — "Pixel, conjunto de dados ou
 * conversão personalizada: Nenhum" — e nela os dois casos eram indistinguíveis.
 * Aqui eles são duas escolhas com consequências escritas, e a receita decide
 * qual delas sequer existe.
 *
 * ## ⚠️ `A12` — o tri-state, e o que ele proíbe
 *
 * `UNKNOWN` não é "disponível", não é "arquivada" e não é um amarelo genérico:
 * é a resposta que não permitiu concluir. Ele aparece na lista, com a causa, e
 * NUNCA é oferecido como escolha. O vocabulário mora em `conversoes.ts`, com
 * elegibilidade e frescor em eixos separados — um item elegível cujo carimbo de
 * disparo não veio (`UNKNOWN_FRESHNESS`) continua escolhível, e a tela diz que
 * o frescor é que está em falta.
 */
import React from 'react';
import { RefreshCw } from 'lucide-react';

import { BlocoDeEvidencia, ChipDeEstado, LinhaDeFato, PainelDeBloqueio } from '@/components/trafego/bancada';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { CatalogoDaConta } from './CatalogoDaConta';
import { lerConversao, motivoLegivel } from './conversoes';
import { Campo, GrupoDeEscolha, NomeCurto, campo } from './primitivas';
import {
  BLOQUEIOS, ConjuntoDraft, Draft, PropositoDeMensuracao, TipoDeFonteDeMensuracao,
  dominioDoDestino,
} from './rascunho';
import type {
  ConversaoPersonalizadaMetaLocal, EnvelopeDeCatalogoMeta, FonteDeMensuracaoMeta,
  ResumoDoPlanoMetaV2,
} from '@/lib/pautadorApi';

export const PainelDeMensuracao: React.FC<{
  draft: Draft;
  conjunto: ConjuntoDraft;
  /** Propósitos que a receita escolhida admite. Vazio = catálogo não lido. */
  propositosDaReceita: readonly PropositoDeMensuracao[];
  /** Motivo declarado pela receita quando `OPTIMIZE` não é admitido. */
  motivoDaReceita: string | null;
  /** Os DOIS envelopes, separados como o backend os manda: pixel/dataset e
   *  conversão personalizada são objetos diferentes. */
  catalogoDeFontes: EnvelopeDeCatalogoMeta<FonteDeMensuracaoMeta> | null;
  catalogoDeConversoes: EnvelopeDeCatalogoMeta<ConversaoPersonalizadaMetaLocal> | null;
  lendoConversoes: boolean;
  erroDasConversoes: string | null;
  resumoDoConjunto: ResumoDoPlanoMetaV2['conjuntos'][number] | null;
  onDestino: (url: string) => void;
  onConjunto: (chave: string, patch: Partial<ConjuntoDraft>) => void;
  /** Leitura REAL da conta, e por isso só por clique explícito. */
  onLerConversoes: () => void;
}> = ({
  draft, conjunto, propositosDaReceita, motivoDaReceita, catalogoDeFontes,
  catalogoDeConversoes, lendoConversoes, erroDasConversoes, resumoDoConjunto,
  onDestino, onConjunto, onLerConversoes,
}) => {
  const m = conjunto.mensuracao;
  const admiteOtimizar = propositosDaReceita.includes('OPTIMIZE');
  const conversoes = catalogoDeConversoes?.items ?? [];
  const fontes = catalogoDeFontes?.items ?? [];
  const elegiveis = conversoes.filter((item) => lerConversao(item.estado).elegivel);
  const naoElegiveis = conversoes.filter((item) => !lerConversao(item.estado).elegivel);
  const escolhida = conversoes.find((item) => item.referencia_opaca === m.conversaoRef) ?? null;
  /** ⚠️ `source_kind` NÃO é escolha de tela: ele vem do item. `PIXEL` e
   *  `DATASET` são objetos diferentes na Meta, e `UNKNOWN` é "a resposta não
   *  disse qual" — que não pode virar nenhum dos dois, e por isso não é
   *  oferecido. */
  const fontesElegiveis = fontes.filter(
    (item) => lerConversao(item.estado).elegivel && item.source_kind !== 'UNKNOWN');
  const fonteEscolhida = fontes.find((item) => item.referencia_opaca === m.fonteRef) ?? null;

  const mudarMensuracao = (patch: Partial<ConjuntoDraft['mensuracao']>) =>
    onConjunto(conjunto.key, { mensuracao: { ...m, ...patch } });

  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Campo
          id="meta-url"
          rotulo="URL final HTTPS"
          largo
          ajuda="Use a URL da página sem UTMs. Os parâmetros de atribuição por conjunto são adicionados automaticamente pelo sistema."
        >
          <Input
            id="meta-url" type="url" value={draft.destinationUrl}
            onChange={(e) => onDestino(e.target.value)}
          />
        </Campo>
      </div>

      <div className="space-y-3">
        <p className="kicker text-primary">Para que serve a conversão escolhida</p>
        <GrupoDeEscolha<PropositoDeMensuracao>
          rotuloAcessivel="Propósito da mensuração"
          valor={m.proposito}
          onEscolher={(proposito) => mudarMensuracao({
            proposito,
            // Voltar para relatório NÃO apaga a conversão escolhida: ela
            // continua sendo uma preferência de leitura legítima. O que sai é
            // a fonte, que só existe para otimizar.
            ...(proposito === 'REPORT_ONLY'
              ? { fonteTipo: '' as const, fonteRef: '', eventoPadrao: '' } : {}),
          })}
          opcoes={[
            {
              id: 'REPORT_ONLY',
              nome: 'Relatar',
              detalhe: 'aparece no relatório e NÃO muda o que a campanha otimiza',
            },
            {
              id: 'OPTIMIZE',
              nome: 'Otimizar',
              detalhe: admiteOtimizar
                ? 'muda a entrega: a Meta passa a buscar esta conversão'
                : 'esta receita não admite otimizar por conversão',
              desabilitada: !admiteOtimizar,
            },
          ]}
        />
        <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
          <strong className="text-foreground">Relatar não muda a entrega.</strong>{' '}
          A campanha continua otimizando pelo que a receita declara; a conversão escolhida entra
          como preferência de LEITURA. Otimizar é outro contrato: ele emite `promoted_object`,
          muda o que a Meta procura e exige uma fonte de evento comprovadamente elegível.
          {motivoDaReceita ? ` ${motivoDaReceita}` : ''}
        </p>
      </div>

      {/* ── Os dois catálogos, lidos por UM clique e mostrados SEPARADOS ──── */}
      <CatalogoDaConta
        titulo="Conversões personalizadas desta conta"
        substantivo="conversões"
        envelope={catalogoDeConversoes}
        carregando={lendoConversoes}
        erro={erroDasConversoes}
        podeLer={Boolean(draft.accountRef)}
        onLer={onLerConversoes}
      >
        {conversoes.length > 0 && (
          <>
            <Campo
              id={`meta-conversao-${conjunto.key}`}
              rotulo="Conversão personalizada"
              ajuda={
                naoElegiveis.length
                  ? `${naoElegiveis.length} conversão(ões) desta conta não podem ser escolhidas; elas aparecem abaixo com a causa.`
                  : undefined
              }
            >
              <select
                id={`meta-conversao-${conjunto.key}`}
                className={campo}
                value={m.conversaoRef}
                onChange={(e) => mudarMensuracao({ conversaoRef: e.target.value })}
              >
                <option value="">Nenhuma conversão declarada</option>
                {/* ⚠️ SÓ AS ELEGÍVEIS ENTRAM AQUI. Uma `UNKNOWN` nesta lista
                    seria a tela oferecendo como escolha um item que ela não
                    consegue afirmar que existe e está disponível. */}
                {elegiveis.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {lerConversao(item.estado).palavra}
                  </option>
                ))}
              </select>
            </Campo>

            <ul className="space-y-2">
              {conversoes.map((item) => {
                const leitura = lerConversao(item.estado);
                const causa = motivoLegivel(item.motivo_desconhecido);
                return (
                  <li
                    key={item.referencia_opaca}
                    className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border/70 bg-background px-3 py-2"
                  >
                    <div className="min-w-0">
                      <NomeCurto
                        nome={item.nome}
                        className="text-sm font-medium text-foreground"
                        ausencia="conversão sem nome"
                      />
                      <p className="text-sm text-muted-foreground">
                        {item.custom_event_type ?? 'evento não informado'}
                        {' · '}{item.id_mascarado ?? 'ID protegido'}
                      </p>
                      {/* Frescor é o SEGUNDO eixo, e vive na sua própria linha. */}
                      {leitura.frescor && (
                        <p className="text-sm text-muted-foreground">frescor: {leitura.frescor}</p>
                      )}
                      {causa && <p className="text-sm text-muted-foreground">causa: {causa}</p>}
                      {!leitura.elegivel && (
                        <p className="text-sm text-muted-foreground">
                          não pode ser escolhida
                        </p>
                      )}
                    </div>
                    <ChipDeEstado
                      glifo={leitura.glifo}
                      palavra={leitura.palavra}
                      descricao={leitura.descricao}
                      tom={leitura.tom}
                    />
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </CatalogoDaConta>

      {/* ⚠️ ENVELOPE PRÓPRIO. Pixel/dataset e conversão personalizada chegam
          separados do backend de propósito, e são mostrados separados pelo
          mesmo motivo: achatá-los numa lista faria o seletor de otimização
          oferecer um no lugar do outro. */}
      <CatalogoDaConta
        titulo="Pixels e datasets desta conta"
        substantivo="fontes de mensuração"
        envelope={catalogoDeFontes}
        carregando={lendoConversoes}
        erro={erroDasConversoes}
        podeLer={Boolean(draft.accountRef)}
        onLer={onLerConversoes}
      >
        {fontes.length > 0 && (
          <>
            <Campo
              id={`meta-fonte-${conjunto.key}`}
              rotulo="Fonte do evento (pixel ou dataset)"
              ajuda={fonteEscolhida
                ? `Esta fonte é um ${fonteEscolhida.source_kind === 'PIXEL' ? 'pixel' : 'dataset'}, e é a Meta quem diz isso — não a tela.`
                : 'Só é exigida para OTIMIZAR. Relatar não precisa de fonte.'}
            >
              <select
                id={`meta-fonte-${conjunto.key}`}
                className={campo}
                value={m.fonteRef}
                onChange={(e) => {
                  const alvo = fontes.find((item) => item.referencia_opaca === e.target.value);
                  mudarMensuracao({
                    fonteRef: e.target.value,
                    // O tipo acompanha o item; escolher a fonte e o tipo em
                    // dois lugares deixaria os dois divergirem.
                    fonteTipo: (alvo && alvo.source_kind !== 'UNKNOWN'
                      ? alvo.source_kind : '') as TipoDeFonteDeMensuracao | '',
                  });
                }}
              >
                <option value="">Nenhuma fonte declarada</option>
                {fontesElegiveis.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {item.source_kind === 'PIXEL' ? 'pixel' : 'dataset'}
                  </option>
                ))}
              </select>
            </Campo>

            <ul className="space-y-2">
              {fontes.map((item) => {
                const leitura = lerConversao(item.estado);
                const causa = motivoLegivel(item.motivo_desconhecido);
                const tipoIncerto = item.source_kind === 'UNKNOWN';
                return (
                  <li
                    key={item.referencia_opaca}
                    className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border/70 bg-background px-3 py-2"
                  >
                    <div className="min-w-0">
                      <NomeCurto
                        nome={item.nome}
                        className="text-sm font-medium text-foreground"
                        ausencia="fonte sem nome"
                      />
                      <p className="text-sm text-muted-foreground">
                        {tipoIncerto
                          ? 'a resposta não disse se é pixel ou dataset'
                          : (item.source_kind === 'PIXEL' ? 'pixel' : 'dataset')}
                        {' · '}{item.id_mascarado ?? 'ID protegido'}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        último disparo: {item.last_fired_time ?? 'não informado'}
                      </p>
                      {causa && <p className="text-sm text-muted-foreground">causa: {causa}</p>}
                      {(tipoIncerto || !leitura.elegivel) && (
                        <p className="text-sm text-muted-foreground">
                          não pode ser escolhida
                        </p>
                      )}
                    </div>
                    <ChipDeEstado
                      glifo={leitura.glifo}
                      palavra={leitura.palavra}
                      descricao={leitura.descricao}
                      tom={leitura.tom}
                    />
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </CatalogoDaConta>

      {m.proposito === 'OPTIMIZE' && !m.fonteRef && (
        <PainelDeBloqueio
          titulo="Otimizar por conversão exige a fonte do evento"
          bloqueios={[{
            codigo: 'META_MEASUREMENT_SOURCE_REQUIRED',
            severidade: 'alta',
            titulo: 'Nenhum pixel ou dataset foi escolhido',
            detalhe: BLOQUEIOS.fonteDeMensuracao,
          }]}
        />
      )}

      {/* ⚠️ EVENTO PADRÃO **OU** CONVERSÃO PERSONALIZADA, nunca os dois: a Meta
          trata `custom_conversion_id` e `custom_event_type` como caminhos
          distintos, e mandar os dois é pedir que o provedor escolha. */}
      {m.proposito === 'OPTIMIZE' && m.conversaoRef && m.eventoPadrao && (
        <PainelDeBloqueio
          titulo="Escolha um caminho de evento, não os dois"
          bloqueios={[{
            codigo: 'META_MEASUREMENT_EVENT_AMBIGUOUS',
            severidade: 'alta',
            titulo: 'Há um evento padrão E uma conversão personalizada declarados',
            detalhe:
              'A Meta trata os dois como caminhos distintos. Mandar ambos deixaria o '
              + 'provedor escolher, e a escolha dele não é a sua.',
          }]}
        />
      )}

      <BlocoDeEvidencia titulo="O que será medido" tom={resumoDoConjunto ? 'verificado' : 'info'}>
        <LinhaDeFato
          rotulo="Domínio do destino"
          valor={dominioDoDestino(draft.destinationUrl)}
          fonte="você, agora"
          ausencia="URL ainda inválida"
        />
        <LinhaDeFato
          rotulo="Propósito"
          valor={(resumoDoConjunto?.mensuracao_proposito ?? m.proposito) === 'OPTIMIZE'
            ? 'Otimizar · a entrega muda' : 'Relatar · a entrega NÃO muda'}
          fonte={resumoDoConjunto ? 'o resumo do backend' : 'você, agora'}
        />
        <LinhaDeFato
          rotulo="Altera a entrega"
          valor={resumoDoConjunto
            ? (resumoDoConjunto.mensuracao_altera_entrega ? 'Sim' : 'Não')
            : (m.proposito === 'OPTIMIZE' ? 'Sim' : 'Não')}
          fonte={resumoDoConjunto ? 'o resumo do backend' : 'a regra do contrato'}
        />
        <LinhaDeFato
          rotulo="Conversão declarada"
          valor={escolhida ? `${escolhida.nome} · ${lerConversao(escolhida.estado).palavra}` : null}
          fonte="você, agora"
          ausencia="nenhuma"
        />
        <LinhaDeFato
          rotulo="Fonte do evento (pixel ou dataset)"
          valor={fonteEscolhida
            ? `${fonteEscolhida.nome} · ${fonteEscolhida.source_kind === 'PIXEL' ? 'pixel' : 'dataset'}`
            : null}
          fonte="o catálogo da conta"
          ausencia="nenhuma declarada"
        />
        <LinhaDeFato
          rotulo="Otimização"
          valor="Visualizações da página de destino"
          fonte="a receita provada"
        />
        <LinhaDeFato rotulo="Janela de atribuição" valor="Padrão efetivo da conta" fonte="a Meta" />
        <LinhaDeFato
          rotulo="Domínio de conversão"
          valor="Não enviado"
          fonte="documentação Meta v26"
        />
      </BlocoDeEvidencia>

      <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
        A Meta exige o domínio de conversão quando a campanha compartilha dados com um pixel.
        Esta receita não promove nenhum pixel, então o campo não é enviado. Receitas de venda e
        de cadastro, quando forem provadas, trarão pixel, evento e domínio juntos.
      </p>
    </>
  );
};
