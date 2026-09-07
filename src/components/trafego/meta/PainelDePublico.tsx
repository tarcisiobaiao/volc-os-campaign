/**
 * A etapa de público, por conjunto (`F11`..`F21`).
 *
 * ## O que esta etapa era, e por que mudou
 *
 * Ela mostrava seis linhas de FATO — País "Brasil", Idade "18 a 65+",
 * Posicionamento "Somente Facebook", Identidade, Públicos salvos "Nenhum",
 * Advantage+ — atribuídas a "a receita provada". Aquelas seis linhas eram o
 * inventário exato do que o operador NÃO podia decidir. Cada uma virou controle
 * aqui, e a fonte de cada uma passou de "a receita provada" para "você, agora".
 *
 * ## ⚠️ `A16` — CONTROLE não é SUGESTÃO
 *
 * Com a expansão Advantage+ ligada, a Meta trata o público selecionado como
 * SUGESTÃO e entrega FORA dele. Uma tela que continuasse dizendo "só quem está
 * no público será alcançado" estaria prometendo o que o provedor não garante.
 * A frase é decidida por `promete_alcance_exclusivo` — do resumo do servidor
 * quando ele existe, da projeção local antes disso — e nunca por um `if` novo
 * escrito aqui.
 */
import React from 'react';
import { Lock, Plus, Trash2 } from 'lucide-react';

import { BlocoDeEvidencia, LinhaDeFato, PainelDeBloqueio } from '@/components/trafego/bancada';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

import { CatalogoDaConta } from './CatalogoDaConta';
import { lerConversao, motivoLegivel } from './conversoes';
import { Campo, Escolha, GrupoDeEscolha, NomeCurto, campo } from './primitivas';
import {
  BLOQUEIOS, ConjuntoDraft, Draft, LugarEscolhido, ModoDePosicionamento, ModoDePublico,
  PLATAFORMAS, PontoComRaio, paisesExcluidos, paisesIncluidos, prometeAlcanceExclusivo,
} from './rascunho';
import type {
  EnvelopeDeCatalogoMeta, LugarDoCatalogoMeta, PublicoDoCatalogoMeta, ResumoDoPlanoMetaV2,
} from '@/lib/pautadorApi';

/** O que o operador decidiu sobre UM público do catálogo. */
type DecisaoDePublico = 'nao' | 'incluir' | 'excluir';

const ROTULO_DO_TIPO: Record<string, string> = {
  region: 'região', city: 'cidade', zip: 'CEP', country: 'país',
};

const NOME_DA_PLATAFORMA = new Map(PLATAFORMAS);

function faixa(min: number, max: number): number[] {
  return Array.from({ length: max - min + 1 }, (_, i) => min + i);
}

const PONTO_NOVO: PontoComRaio = {
  latitude: '', longitude: '', raio: '10', unidade: 'kilometer',
};

export const PainelDePublico: React.FC<{
  draft: Draft;
  conjunto: ConjuntoDraft;
  /** Limites que o servidor declarou em `/v2/receitas`. Sem catálogo, o
   *  fallback do contrato é usado — e a linha diz de onde veio. */
  idade: { min: number; max: number; motivo: string | null };
  /** O resumo do servidor para ESTE conjunto, quando existe. Autoridade da
   *  frase de alcance (`A16`). */
  resumoDoConjunto: ResumoDoPlanoMetaV2['conjuntos'][number] | null;
  onConjunto: (chave: string, patch: Partial<ConjuntoDraft>) => void;
  /** ── Catálogos da conta. `null` = ainda não lido, e a tela diz isso. ──── */
  catalogoDePublicos: EnvelopeDeCatalogoMeta<PublicoDoCatalogoMeta> | null;
  lendoPublicos: boolean;
  erroDosPublicos: string | null;
  onLerPublicos: () => void;
  catalogoDeLugares: EnvelopeDeCatalogoMeta<LugarDoCatalogoMeta> | null;
  lendoLugares: boolean;
  erroDosLugares: string | null;
  /** A BUSCA é o ato: o termo digitado nunca vira chave por conta própria. */
  onBuscarLugares: (termo: string) => void;
}> = ({
  draft, conjunto, idade, resumoDoConjunto, onConjunto,
  catalogoDePublicos, lendoPublicos, erroDosPublicos, onLerPublicos,
  catalogoDeLugares, lendoLugares, erroDosLugares, onBuscarLugares,
}) => {
  const publico = conjunto.publico;
  const incluidos = paisesIncluidos(publico.geo);
  const excluidos = paisesExcluidos(publico.geo);
  const colisao = incluidos.filter((pais) => excluidos.includes(pais));

  const mudarPublico = (patch: Partial<ConjuntoDraft['publico']>) =>
    onConjunto(conjunto.key, { publico: { ...publico, ...patch } });
  const mudarGeo = (patch: Partial<ConjuntoDraft['publico']['geo']>) =>
    mudarPublico({ geo: { ...publico.geo, ...patch } });

  // ⚠️ A AUTORIDADE É O SERVIDOR quando ele já falou. A projeção local só
  // existe para o intervalo antes da primeira compilação, e a linha de fato
  // diz qual das duas está sendo mostrada.
  const exclusivo = resumoDoConjunto
    ? resumoDoConjunto.promete_alcance_exclusivo
    : prometeAlcanceExclusivo(publico);

  const manual = conjunto.posicionamentoModo === 'MANUAL';
  const instagramEscolhido = manual && conjunto.posicionamentoValores.includes('instagram');

  const alternarPlataforma = (valor: string, ligado: boolean) => {
    const proximos = ligado
      ? [...new Set([...conjunto.posicionamentoValores, valor])]
      : conjunto.posicionamentoValores.filter((item) => item !== valor);
    onConjunto(conjunto.key, { posicionamentoValores: proximos });
  };

  const mudarPonto = (indice: number, patch: Partial<PontoComRaio>) => mudarGeo({
    pontos: publico.geo.pontos.map((item, i) => (i === indice ? { ...item, ...patch } : item)),
  });

  // ── Públicos do catálogo (`F12`, `F13`, `F14`) ────────────────────────────
  const decisaoDe = (ref: string): DecisaoDePublico => {
    if (publico.incluirRefs.includes(ref) || publico.lookalikeRefs.includes(ref)) return 'incluir';
    if (publico.excluirRefs.includes(ref)) return 'excluir';
    return 'nao';
  };

  /** ⚠️ O que viaja é `referencia_opaca` — o item do catálogo, nunca texto.
   *
   *  Semelhante e personalizado são campos DIFERENTES no contrato
   *  (`lookalike_refs` × `include_custom_refs`), e é o `subtype` que a Meta
   *  devolveu que decide para qual deles a referência vai. Perguntar isso ao
   *  operador seria pedir que ele adivinhasse uma classificação que a conta já
   *  tem. Do lado da EXCLUSÃO os dois caem no mesmo campo, como no contrato. */
  const decidirPublico = (item: PublicoDoCatalogoMeta, decisao: DecisaoDePublico) => {
    const ref = item.referencia_opaca;
    const semelhante = (item.subtype ?? '').toUpperCase().includes('LOOKALIKE');
    const incluir = publico.incluirRefs.filter((valor) => valor !== ref);
    const lookalike = publico.lookalikeRefs.filter((valor) => valor !== ref);
    const excluir = publico.excluirRefs.filter((valor) => valor !== ref);
    if (decisao === 'incluir') (semelhante ? lookalike : incluir).push(ref);
    if (decisao === 'excluir') excluir.push(ref);
    mudarPublico({ incluirRefs: incluir, lookalikeRefs: lookalike, excluirRefs: excluir });
  };

  const usaPublicoSalvo = publico.incluirRefs.length > 0
    || publico.lookalikeRefs.length > 0 || publico.excluirRefs.length > 0;

  // ── Lugares do catálogo (`F15`, `F16`) ────────────────────────────────────
  const [termo, setTermo] = React.useState('');
  const escolherLugar = (item: LugarDoCatalogoMeta, excluido: boolean) => {
    if (!item.key || !item.type) return;
    const escolhido: LugarEscolhido = {
      key: item.key,
      nome: item.name || item.key,
      tipo: item.type,
      excluido,
    };
    mudarGeo({
      lugares: [
        ...publico.geo.lugares.filter(
          (atual) => !(atual.key === escolhido.key && atual.excluido === excluido)),
        escolhido,
      ],
    });
  };
  const removerLugar = (chave: string, excluido: boolean) => mudarGeo({
    lugares: publico.geo.lugares.filter(
      (item) => !(item.key === chave && item.excluido === excluido)),
  });

  return (
    <>
      <div className="space-y-3">
        <p className="kicker text-primary">Como este conjunto escolhe gente</p>
        <GrupoDeEscolha<ModoDePublico>
          rotuloAcessivel="Modo de público"
          valor={publico.modo}
          colunas="sm:grid-cols-2 lg:grid-cols-4"
          onEscolher={(modo) => mudarPublico({ modo })}
          opcoes={[
            { id: 'BROAD', nome: 'Amplo', detalhe: 'geografia e idade, sem público salvo' },
            { id: 'MANUAL', nome: 'Manual', detalhe: 'geografia, idade e recortes seus' },
            {
              id: 'EXISTING_CUSTOM', nome: 'Público personalizado',
              detalhe: 'ao menos um público salvo da conta',
            },
            {
              id: 'EXISTING_LOOKALIKE', nome: 'Semelhante',
              detalhe: 'ao menos um semelhante da conta',
            },
          ]}
        />
        <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
          {BLOQUEIOS.catalogoDePublicos}
        </p>
      </div>

      {/* ── F12/F13/F14: públicos que JÁ EXISTEM na conta ──────────────────── */}
      <CatalogoDaConta
        titulo="Públicos salvos desta conta"
        substantivo="públicos"
        envelope={catalogoDePublicos}
        carregando={lendoPublicos}
        erro={erroDosPublicos}
        podeLer={Boolean(draft.accountRef)}
        onLer={onLerPublicos}
      >
        {catalogoDePublicos && catalogoDePublicos.items.length > 0 && (
          <ul className="space-y-2">
            {catalogoDePublicos.items.map((item) => {
              const leitura = lerConversao(item.estado);
              const causa = motivoLegivel(item.motivo_desconhecido);
              const semelhante = (item.subtype ?? '').toUpperCase().includes('LOOKALIKE');
              return (
                <li
                  key={item.referencia_opaca}
                  className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border/70 bg-background px-3 py-2"
                >
                  <div className="min-w-0">
                    <NomeCurto
                      nome={item.nome}
                      className="text-sm font-medium text-foreground"
                      ausencia="público sem nome"
                    />
                    <p className="text-sm text-muted-foreground">
                      {semelhante ? 'semelhante' : (item.subtype ?? 'tipo não informado')}
                      {' · '}{item.id_mascarado ?? 'ID protegido'}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {/* Tamanho NUNCA é inventado: sem os limites na resposta,
                          a linha diz que não foi informado, e não "0". */}
                      {item.tamanho_aproximado_min === null && item.tamanho_aproximado_max === null
                        ? 'tamanho não informado pela Meta'
                        : `tamanho aproximado: ${item.tamanho_aproximado_min ?? '?'} a ${item.tamanho_aproximado_max ?? '?'}`}
                    </p>
                    {causa && <p className="text-sm text-muted-foreground">causa: {causa}</p>}
                    {!leitura.elegivel && (
                      <p className="text-sm text-muted-foreground">não pode ser escolhido</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      className="text-sm text-muted-foreground"
                      title={leitura.descricao}
                    >
                      {leitura.palavra}
                    </span>
                    <select
                      aria-label={`Decisão sobre o público ${item.nome}`}
                      className={cn(campo, 'w-40')}
                      value={decisaoDe(item.referencia_opaca)}
                      /* ⚠️ Um público que a Meta não soube descrever não pode
                         ser escolhido: `UNKNOWN` não é "disponível" (`A12`). */
                      disabled={!leitura.elegivel}
                      onChange={(e) => decidirPublico(item, e.target.value as DecisaoDePublico)}
                    >
                      <option value="nao">não usar</option>
                      <option value="incluir">incluir</option>
                      <option value="excluir">excluir</option>
                    </select>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CatalogoDaConta>

      {usaPublicoSalvo && publico.modo === 'BROAD' && (
        <PainelDeBloqueio
          titulo="Público amplo não aceita público salvo"
          bloqueios={[{
            codigo: 'META_AUDIENCE_MODE_CONFLICT',
            severidade: 'alta',
            titulo: 'Há público salvo escolhido, e o modo continua Amplo',
            detalhe: BLOQUEIOS.publicoAmploNaoAceitaSalvos,
          }]}
        />
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Campo
          id={`meta-paises-${conjunto.key}`}
          rotulo="Países alcançados"
          ajuda={incluidos.length
            ? `A bancada entendeu ${incluidos.join(', ')}. Códigos ISO de duas letras, separados por vírgula.`
            : 'Escolha ao menos um lugar para alcançar. Use códigos ISO de duas letras (BR, PT, US).'}
        >
          <Input
            id={`meta-paises-${conjunto.key}`}
            value={publico.geo.paisesTexto}
            autoComplete="off"
            onChange={(e) => mudarGeo({ paisesTexto: e.target.value })}
          />
        </Campo>
        <Campo
          id={`meta-paises-ex-${conjunto.key}`}
          rotulo="Países excluídos"
          ajuda={excluidos.length
            ? `A bancada entendeu ${excluidos.join(', ')}.`
            : 'Opcional. Excluir é uma decisão tão material quanto incluir, e por isso tem campo próprio.'}
        >
          <Input
            id={`meta-paises-ex-${conjunto.key}`}
            value={publico.geo.exclusoesTexto}
            autoComplete="off"
            onChange={(e) => mudarGeo({ exclusoesTexto: e.target.value })}
          />
        </Campo>

        <Campo id={`meta-idade-min-${conjunto.key}`} rotulo="Idade mínima">
          <select
            id={`meta-idade-min-${conjunto.key}`}
            className={campo}
            value={publico.idadeMin}
            onChange={(e) => mudarPublico({ idadeMin: Number(e.target.value) })}
          >
            {faixa(idade.min, idade.max).map((valor) => (
              <option key={valor} value={valor}>{valor}</option>
            ))}
          </select>
        </Campo>
        <Campo
          id={`meta-idade-max-${conjunto.key}`}
          rotulo="Idade máxima"
          ajuda={idade.motivo ?? undefined}
        >
          <select
            id={`meta-idade-max-${conjunto.key}`}
            className={campo}
            value={publico.idadeMax}
            onChange={(e) => mudarPublico({ idadeMax: Number(e.target.value) })}
          >
            {faixa(idade.min, idade.max).map((valor) => (
              <option key={valor} value={valor}>
                {valor === idade.max ? `${valor}+` : valor}
              </option>
            ))}
          </select>
        </Campo>
      </div>

      {colisao.length > 0 && (
        <PainelDeBloqueio
          titulo="O mesmo país está incluído e excluído"
          bloqueios={[{
            codigo: 'META_GEO_INCLUDE_EXCLUDE_CONFLICT',
            severidade: 'alta',
            titulo: `${colisao.join(', ')} aparece nos dois campos`,
            detalhe:
              'A Meta aceitaria o plano e a entrega seria vazia, sem ninguém entender '
              + 'por quê. O backend recusa antes disso, com nome próprio.',
          }]}
        />
      )}

      {/* ── Raio (`F17`) — o único recorte fino que não depende de catálogo ── */}
      <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="kicker">Pontos com raio</p>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Latitude, longitude e distância. Coordenada não é chave de catálogo: ela pode ser
              digitada sem inventar um identificador da Meta.
            </p>
          </div>
          <Button
            type="button" variant="outline" size="sm"
            onClick={() => mudarGeo({ pontos: [...publico.geo.pontos, { ...PONTO_NOVO }] })}
          >
            <Plus className="mr-1.5 h-4 w-4" aria-hidden />Adicionar ponto
          </Button>
        </div>
        {publico.geo.pontos.map((ponto, indice) => (
          <div key={indice} className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
            <Campo id={`meta-lat-${conjunto.key}-${indice}`} rotulo="Latitude">
              <Input
                id={`meta-lat-${conjunto.key}-${indice}`} inputMode="decimal" value={ponto.latitude}
                onChange={(e) => mudarPonto(indice, { latitude: e.target.value })}
              />
            </Campo>
            <Campo id={`meta-lon-${conjunto.key}-${indice}`} rotulo="Longitude">
              <Input
                id={`meta-lon-${conjunto.key}-${indice}`} inputMode="decimal" value={ponto.longitude}
                onChange={(e) => mudarPonto(indice, { longitude: e.target.value })}
              />
            </Campo>
            <Campo id={`meta-raio-${conjunto.key}-${indice}`} rotulo="Raio">
              <Input
                id={`meta-raio-${conjunto.key}-${indice}`} inputMode="numeric" value={ponto.raio}
                onChange={(e) => mudarPonto(indice, { raio: e.target.value })}
              />
            </Campo>
            <Campo id={`meta-unidade-${conjunto.key}-${indice}`} rotulo="Unidade">
              <select
                id={`meta-unidade-${conjunto.key}-${indice}`} className={campo} value={ponto.unidade}
                onChange={(e) => mudarPonto(indice, {
                  unidade: e.target.value as PontoComRaio['unidade'],
                })}
              >
                <option value="kilometer">quilômetros</option>
                <option value="mile">milhas</option>
              </select>
            </Campo>
            <div className="flex items-end pb-1">
              <Button
                type="button" variant="ghost" size="sm"
                aria-label={`Remover o ponto ${indice + 1}`}
                onClick={() => mudarGeo({
                  pontos: publico.geo.pontos.filter((_, i) => i !== indice),
                })}
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          </div>
        ))}
        <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
          Coordenada e raio não dependem de catálogo. Região, cidade e CEP dependem, e estão logo
          abaixo.
        </p>
      </section>

      {/* ── F15/F16: região, cidade e CEP pela BUSCA no catálogo ───────────── */}
      <CatalogoDaConta
        titulo="Região, cidade e CEP"
        substantivo="lugares"
        envelope={catalogoDeLugares}
        carregando={lendoLugares}
        erro={erroDosLugares}
        podeLer={Boolean(draft.accountRef) && termo.trim().length >= 2}
        onLer={() => onBuscarLugares(termo.trim())}
      >
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <Campo
            id={`meta-busca-lugar-${conjunto.key}`}
            rotulo="Buscar um lugar no catálogo da Meta"
            ajuda={BLOQUEIOS.catalogoDeGeografia}
          >
            <Input
              id={`meta-busca-lugar-${conjunto.key}`}
              value={termo}
              autoComplete="off"
              placeholder="Curitiba, Paraná, 80000…"
              onChange={(e) => setTermo(e.target.value)}
            />
          </Campo>
        </div>

        {catalogoDeLugares && catalogoDeLugares.items.length > 0 && (
          <ul className="space-y-2">
            {catalogoDeLugares.items.map((item, indice) => {
              const utilizavel = Boolean(item.key) && lerConversao(item.estado).elegivel;
              return (
                <li
                  key={item.key ?? `ilegivel-${indice}`}
                  className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border/70 bg-background px-3 py-2"
                >
                  <div className="min-w-0">
                    <NomeCurto
                      nome={item.name}
                      className="text-sm font-medium text-foreground"
                      ausencia="lugar sem nome"
                    />
                    <p className="text-sm text-muted-foreground">
                      {ROTULO_DO_TIPO[item.type ?? ''] ?? (item.type ?? 'tipo não informado')}
                      {item.region ? ` · ${item.region}` : ''}
                      {item.country_code ? ` · ${item.country_code}` : ''}
                    </p>
                    {/* A chave canônica fica visível para quem audita — ela é o
                        que realmente viaja — sem virar o título da linha. */}
                    <p className="font-mono text-xs text-muted-foreground">
                      {item.key ?? 'sem chave utilizável'}
                    </p>
                    {!utilizavel && (
                      <p className="text-sm text-muted-foreground">
                        item ilegível: veio sem chave canônica, então não pode ser escolhido
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      type="button" variant="outline" size="sm" disabled={!utilizavel}
                      onClick={() => escolherLugar(item, false)}
                    >
                      Incluir
                    </Button>
                    <Button
                      type="button" variant="outline" size="sm" disabled={!utilizavel}
                      onClick={() => escolherLugar(item, true)}
                    >
                      Excluir
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div className="space-y-2">
          <p className="kicker">Lugares deste conjunto</p>
          {publico.geo.lugares.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum lugar escolhido. O alcance segue pelos países e pelos pontos com raio.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2" data-testid="lugares-escolhidos">
              {publico.geo.lugares.map((item) => (
                <li
                  key={`${item.key}:${item.excluido ? 'ex' : 'in'}`}
                  className="flex items-center gap-2 rounded-md border border-border/70 bg-background px-2 py-1 text-sm"
                >
                  <span className="text-foreground">
                    {item.excluido ? 'não alcançar' : 'alcançar'} · {item.nome}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{item.key}</span>
                  <Button
                    type="button" variant="ghost" size="sm"
                    aria-label={`Remover ${item.nome} de ${item.excluido ? 'excluídos' : 'incluídos'}`}
                    onClick={() => removerLugar(item.key, item.excluido)}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CatalogoDaConta>

      <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
        {BLOQUEIOS.interessesEIdiomas}
      </p>

      {/* ── Posicionamentos (`F21`) ─────────────────────────────────────────── */}
      <div className="space-y-3">
        <p className="kicker text-primary">Onde o anúncio pode aparecer</p>
        <GrupoDeEscolha<ModoDePosicionamento>
          rotuloAcessivel="Modo de posicionamento"
          valor={conjunto.posicionamentoModo}
          onEscolher={(modo) => onConjunto(conjunto.key, {
            posicionamentoModo: modo,
            posicionamentoValores: modo === 'FACEBOOK_ONLY' ? [] : conjunto.posicionamentoValores,
          })}
          opcoes={[
            {
              id: 'FACEBOOK_ONLY', nome: 'Somente Facebook',
              detalhe: 'o único posicionamento com prova nesta lane',
            },
            {
              id: 'MANUAL', nome: 'Escolher à mão',
              detalhe: 'você lista as plataformas, uma a uma',
            },
          ]}
        />
        {manual && (
          <div className="grid gap-3 md:grid-cols-2">
            {PLATAFORMAS.map(([valor, nome]) => {
              const bloqueada = valor === 'instagram' && !draft.instagramActorRef;
              return (
                <Escolha
                  key={valor}
                  marcado={conjunto.posicionamentoValores.includes(valor)}
                  desabilitado={bloqueada}
                  onChange={(ligado) => alternarPlataforma(valor, ligado)}
                  titulo={nome}
                >
                  {bloqueada
                    ? BLOQUEIOS.identidadeInstagram
                    : `Publisher platform "${valor}", transcrita do catálogo do SDK v26.`}
                </Escolha>
              );
            })}
          </div>
        )}
        {instagramEscolhido && !draft.instagramActorRef && (
          <PainelDeBloqueio
            titulo="O Instagram exige uma identidade validada"
            bloqueios={[{
              codigo: 'META_INSTAGRAM_IDENTITY_REQUIRED',
              severidade: 'alta',
              titulo: 'Nenhuma identidade do Instagram foi lida desta conta',
              detalhe: BLOQUEIOS.identidadeInstagram,
            }]}
          />
        )}
      </div>

      {/* ── Advantage+ (`F19`, `A16`) ───────────────────────────────────────── */}
      <div className="grid gap-4 md:grid-cols-2">
        <Escolha
          marcado={publico.expansao}
          onChange={(valor) => mudarPublico({ expansao: valor })}
          titulo="Aceitar o público Advantage+, deixando a Meta ampliar além do público definido"
        >
          Esta escolha viaja sempre explícita. Se a bancada omitisse o campo, a Meta assumiria
          que você aceitou e ampliaria o público sozinha — por isso não existe estado “não
          declarado” aqui. <strong className="text-foreground">Aceito, o que você escolheu vira
          SUGESTÃO</strong> e a entrega acontece fora dele; recusado, o que você escolheu é
          CONTROLE e o conjunto entrega dentro do público definido.
        </Escolha>
      </div>

      <BlocoDeEvidencia
        titulo={`O público de "${conjunto.nome || 'conjunto sem nome'}"`}
        tom={resumoDoConjunto ? 'verificado' : 'info'}
      >
        <LinhaDeFato
          rotulo="Países"
          valor={incluidos.length ? incluidos.join(', ') : null}
          fonte="você, agora"
          ausencia="nenhum lugar escolhido"
        />
        <LinhaDeFato
          rotulo="Países excluídos"
          valor={excluidos.length ? excluidos.join(', ') : null}
          fonte="você, agora"
          ausencia="nenhum"
        />
        <LinhaDeFato
          rotulo="Pontos com raio"
          valor={publico.geo.pontos.length || null}
          fonte="você, agora"
          ausencia="nenhum"
        />
        <LinhaDeFato
          rotulo="Idade"
          valor={`${publico.idadeMin} a ${publico.idadeMax === idade.max ? `${publico.idadeMax}+` : publico.idadeMax}`}
          fonte="você, agora"
        />
        <LinhaDeFato
          rotulo="Posicionamentos"
          valor={resumoDoConjunto
            ? resumoDoConjunto.posicionamentos
              .map((item) => NOME_DA_PLATAFORMA.get(item) ?? item).join(', ')
            : (conjunto.posicionamentoModo === 'FACEBOOK_ONLY'
              ? 'Facebook'
              : (conjunto.posicionamentoValores
                .map((item) => NOME_DA_PLATAFORMA.get(item) ?? item).join(', ') || null))}
          fonte={resumoDoConjunto ? 'o resumo do backend' : 'você, agora'}
          ausencia="nenhuma plataforma escolhida"
        />
        <LinhaDeFato
          rotulo="Identidade"
          valor={draft.instagramActorRef
            ? 'Página da conta e identidade do Instagram'
            : 'Página provada pela conta; Instagram não utilizado'}
          fonte="a Meta e o backend"
        />
        <LinhaDeFato
          rotulo="Públicos salvos"
          valor={resumoDoConjunto
            ? `${resumoDoConjunto.publicos_incluidos} incluídos · ${resumoDoConjunto.publicos_excluidos} excluídos`
            : `${publico.incluirRefs.length + publico.lookalikeRefs.length} incluídos · ${publico.excluirRefs.length} excluídos`}
          fonte={resumoDoConjunto ? 'o resumo do backend' : 'você, agora'}
        />
        <LinhaDeFato
          rotulo="Região, cidade e CEP"
          valor={publico.geo.lugares.length
            ? publico.geo.lugares
              .map((item) => `${item.excluido ? '−' : '+'} ${item.nome}`).join(' · ')
            : null}
          fonte="o catálogo da Meta"
          ausencia="nenhum"
        />
        <LinhaDeFato
          rotulo="Advantage+ público"
          valor={(resumoDoConjunto ? resumoDoConjunto.expansao_advantage : publico.expansao)
            ? 'Aceito (1)' : 'Recusado (0)'}
          fonte={resumoDoConjunto ? 'o resumo do backend' : 'você, agora'}
        />
        <LinhaDeFato
          rotulo="Alcance"
          // ⚠️ `A16` MORA NESTA LINHA. Ela nunca pode afirmar exclusividade
          // quando `promete_alcance_exclusivo` é falso, e quem responde isso é
          // o resumo do servidor sempre que ele existe.
          valor={exclusivo
            ? 'Somente o público selecionado será alcançado'
            : 'A Meta pode alcançar pessoas fora do público selecionado'}
          fonte={resumoDoConjunto ? 'o resumo do backend' : 'a regra do contrato, ainda não conferida'}
        />
      </BlocoDeEvidencia>

      {!exclusivo && (
        <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/30 p-4">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
            <strong className="text-foreground">Este conjunto não promete alcance exclusivo.</strong>{' '}
            Ou não há público personalizado selecionado, ou a expansão Advantage+ está aceita — e
            com ela a Meta trata a sua seleção como sugestão. Chamar isto de remarketing fechado
            seria a bancada prometendo o que o provedor não garante.
          </p>
        </div>
      )}
    </>
  );
};
