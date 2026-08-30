/**
 * A mesa das palavras — o que ativa a campanha e o que a impede de gastar.
 *
 * ## O que esta peça conserta
 *
 * Até aqui a tela mostrava as keywords e um match type DERIVADO da estratégia,
 * igual para todas, e não oferecia nenhum lugar para escrever uma negativa. O
 * operador lançava sem saber que:
 *
 *   - o alcance da negativa era decidido no código (`BROAD`, fixo), e não por
 *     ele — negativar "curso gratis" matava "curso de ingles gratis" junto;
 *   - a negativa que ele declarasse por sub-intenção morria na fronteira HTTP;
 *   - uma negativa podia anular uma keyword que ele mesmo tinha marcado, e a
 *     campanha subiria com a keyword lá, sem servir consulta nenhuma.
 *
 * ## Por que a régua de alcance está em toda linha
 *
 * "PHRASE" e "BROAD" não significam nada para quem nunca leu a doc da API, e
 * `BROAD` é o mais largo dos três justamente parecendo o mais inofensivo. Cada
 * linha diz, em português, o que aquela escolha bloqueia. Sem isso a tela
 * ofereceria a escolha e esconderia a consequência dela.
 *
 * ## Por que nada aqui sugere negativa sozinho
 *
 * A doutrina da casa é que negativa sem evidência medida é PROPOSTA, não fato.
 * As listas "universais" que as ferramentas de mercado aplicam por bom senso
 * (`free`, `jobs`, `salary`) são exatamente o que produz o bloqueio excessivo
 * que a revisão aqui existe para detectar. Quem propõe termo medido é o
 * tribunal lexical sobre `search_term_view` — e ele entrega evidência junto.
 */
import React, { useMemo, useState } from 'react';
import { AlertTriangle, Ban, Plus, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  MATCH_TYPES,
  NASCE_COM_UM_CONJUNTO,
  ROTULO_DE_MATCH,
  ROTULO_DE_ORIGEM,
  chave,
  explicarAlcance,
  explicarEscopo,
  medido,
  novoCriterio,
  resumir,
} from '@/lib/trafego/criterios';
import type {
  CriterioDeKeyword,
  MatchType,
  NivelCriterio,
} from '@/types/trafego';

export interface GrupoDeKeywords {
  tipo: string;
  keywords: string[];
}

interface Props {
  /** Os grupos como o operador os marcou. As positivas são DERIVADAS daqui a
   *  cada render — nunca copiadas para estado próprio —, para que desmarcar uma
   *  keyword não deixe um critério órfão apontando para ela. */
  grupos: GrupoDeKeywords[];
  /** Volume medido por keyword, quando existe. Ausência fica ausente: a linha
   *  mostra "—", nunca zero. Zero é uma medição; ausência é a falta de uma. */
  volumePorKeyword?: Record<string, number>;
  /** O match type que a estratégia impõe como padrão. */
  matchPadrao: MatchType;
  /** Sob CPC manual, BROAD não é oferecido nas POSITIVAS: broad sem Smart
   *  Bidding não tem sinal de leilão que filtre a consulta, e o `Brief` recusa
   *  a combinação. Oferecer e depois recusar seria mentir na tela. */
  permitirBroadPositivo: boolean;
  /** Overrides de match type por keyword positiva, chaveados pelo texto
   *  normalizado. Vazio = todas seguem `matchPadrao`. */
  matchPorKeyword: Record<string, MatchType>;
  onMatchPorKeyword: (m: Record<string, MatchType>) => void;
  /** As negativas. Estado de verdade — o operador as escreveu. */
  negativas: CriterioDeKeyword[];
  onNegativas: (n: CriterioDeKeyword[]) => void;
}

export function MesaDeCriterios({
  grupos,
  volumePorKeyword,
  matchPadrao,
  permitirBroadPositivo,
  matchPorKeyword,
  onMatchPorKeyword,
  negativas,
  onNegativas,
}: Props) {
  const positivas = useMemo<CriterioDeKeyword[]>(
    () =>
      grupos.flatMap((g) =>
        g.keywords.map((texto) => ({
          texto,
          match_type: matchPorKeyword[chave(texto)] ?? matchPadrao,
          negativa: false,
          nivel: 'AD_GROUP' as const,
          grupo: g.tipo,
          origem: 'PAUTADOR' as const,
          motivo: null,
          evidencia: null,
          observado_em: null,
          aprovado_por: null,
        })),
      ),
    [grupos, matchPorKeyword, matchPadrao],
  );

  const resumo = useMemo(
    () => resumir([...positivas, ...negativas]),
    [positivas, negativas],
  );

  const trocarMatch = (texto: string, mt: MatchType) =>
    onMatchPorKeyword({ ...matchPorKeyword, [chave(texto)]: mt });

  const anuladas = useMemo(
    () => new Set(resumo.conflitos.map((c) => chave(c.positiva.texto))),
    [resumo.conflitos],
  );

  return (
    <div className="space-y-6">
      <PalavrasQueAtivam
        positivas={positivas}
        volumePorKeyword={volumePorKeyword}
        permitirBroadPositivo={permitirBroadPositivo}
        anuladas={anuladas}
        onMatch={trocarMatch}
      />
      <PalavrasAExcluir
        negativas={negativas}
        grupos={grupos.map((g) => g.tipo)}
        onNegativas={onNegativas}
      />
      <Revisao resumo={resumo} />
    </div>
  );
}

// ── as que ativam ───────────────────────────────────────────────────────────

function PalavrasQueAtivam({
  positivas,
  volumePorKeyword,
  permitirBroadPositivo,
  anuladas,
  onMatch,
}: {
  positivas: CriterioDeKeyword[];
  volumePorKeyword?: Record<string, number>;
  permitirBroadPositivo: boolean;
  anuladas: Set<string>;
  onMatch: (texto: string, mt: MatchType) => void;
}) {
  if (positivas.length === 0) {
    return (
      <Bloco titulo="Palavras que ativam" contagem={0}>
        <p className="text-sm text-muted-foreground">
          Nenhuma keyword marcada ainda. Marque na lista acima para que elas
          apareçam aqui com a correspondência de cada uma.
        </p>
      </Bloco>
    );
  }

  return (
    <Bloco titulo="Palavras que ativam" contagem={positivas.length}>
      <ul className="divide-y divide-border">
        {positivas.map((c) => {
          const vol = volumePorKeyword?.[chave(c.texto)];
          const morta = anuladas.has(chave(c.texto));
          return (
            <li
              key={`${c.grupo}:${c.texto}`}
              className="flex flex-col gap-2 py-3 md:flex-row md:items-center md:gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="break-words text-sm font-medium text-foreground">
                    {c.texto}
                  </span>
                  {c.grupo && (
                    <Badge variant="outline" className="text-[10px] font-normal">
                      {c.grupo}
                    </Badge>
                  )}
                  {morta && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-destructive">
                      <Ban className="h-3 w-3" aria-hidden />
                      anulada por uma exclusão
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                  {explicarAlcance(c)} · {ROTULO_DE_ORIGEM[c.origem]} ·{' '}
                  {/* Ausência de volume fica ausente. Zero é uma medição. */}
                  {vol == null ? 'volume não medido' : `${vol.toLocaleString('pt-BR')} buscas/mês`}
                </p>
              </div>
              <SeletorDeMatch
                valor={c.match_type}
                rotulo={`Correspondência de ${c.texto}`}
                opcoes={permitirBroadPositivo ? MATCH_TYPES : MATCH_TYPES.filter((m) => m !== 'BROAD')}
                onChange={(mt) => onMatch(c.texto, mt)}
              />
            </li>
          );
        })}
      </ul>
      {!permitirBroadPositivo && (
        <p className="mt-3 max-w-[74ch] text-[11px] leading-relaxed text-muted-foreground">
          <b>Ampla não está disponível</b> porque a campanha nasce com CPC
          manual. Broad sem lance automático não tem sinal de leilão que filtre
          a consulta — libera na graduação para lance automático.
        </p>
      )}
    </Bloco>
  );
}

// ── as que excluem ──────────────────────────────────────────────────────────

function PalavrasAExcluir({
  negativas,
  grupos,
  onNegativas,
}: {
  negativas: CriterioDeKeyword[];
  grupos: string[];
  onNegativas: (n: CriterioDeKeyword[]) => void;
}) {
  const [texto, setTexto] = useState('');
  const [match, setMatch] = useState<MatchType>('PHRASE');
  const [nivel, setNivel] = useState<NivelCriterio>('CAMPAIGN');
  const [grupo, setGrupo] = useState<string>('');
  const [motivo, setMotivo] = useState('');

  const limpo = texto.trim();
  const jaExiste = negativas.some(
    (n) => chave(n.texto) === chave(limpo) && n.match_type === match && n.nivel === nivel,
  );
  const podeAdicionar = limpo.length > 0 && !jaExiste;

  const adicionar = () => {
    if (!podeAdicionar) return;
    onNegativas([
      ...negativas,
      novoCriterio(limpo, {
        match_type: match,
        nivel,
        // Nível de campanha não declara grupo — a API recusaria a contradição.
        grupo: nivel === 'AD_GROUP' && grupo ? grupo : null,
        // Ausência é ausência: motivo em branco fica `null`, não `''`.
        motivo: motivo.trim() || null,
        origem: 'MANUAL',
      }),
    ]);
    setTexto('');
    setMotivo('');
  };

  return (
    <Bloco titulo="Palavras a excluir" contagem={negativas.length}>
      <form
        className="flex flex-col gap-3 rounded-md border border-border bg-background/60 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          adicionar();
        }}
      >
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <div className="min-w-0 flex-1">
            <label
              htmlFor="nova-exclusao"
              className="mb-1 block text-[11px] font-medium text-muted-foreground"
            >
              Termo a excluir
            </label>
            <Input
              id="nova-exclusao"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="ex.: simulador"
              aria-describedby="ajuda-exclusao"
            />
          </div>
          <SeletorDeMatch
            valor={match}
            rotulo="Correspondência da exclusão"
            opcoes={MATCH_TYPES}
            onChange={setMatch}
          />
          <div>
            <label
              htmlFor="nivel-exclusao"
              className="mb-1 block text-[11px] font-medium text-muted-foreground"
            >
              Onde vale
            </label>
            <select
              id="nivel-exclusao"
              value={nivel}
              onChange={(e) => setNivel(e.target.value as NivelCriterio)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="CAMPAIGN">Campanha inteira</option>
              <option value="AD_GROUP">
                {NASCE_COM_UM_CONJUNTO ? 'Só no grupo de anúncios' : 'Só um grupo'}
              </option>
            </select>
          </div>
          {/* ⚠️ O seletor de GRUPO só aparece quando a campanha pode ter mais
              de um. Sob a doutrina P7 ela nasce com um conjunto só, e escolher
              "em qual grupo" seria oferecer uma distinção sem diferença: as
              duas respostas produziriam o mesmo payload. Ver
              `NASCE_COM_UM_CONJUNTO`. O NÍVEL acima continua valendo — campanha
              e grupo são recursos diferentes da API. */}
          {nivel === 'AD_GROUP' && !NASCE_COM_UM_CONJUNTO && grupos.length > 0 && (
            <div>
              <label
                htmlFor="grupo-exclusao"
                className="mb-1 block text-[11px] font-medium text-muted-foreground"
              >
                Grupo
              </label>
              <select
                id="grupo-exclusao"
                value={grupo}
                onChange={(e) => setGrupo(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">Todos os grupos</option>
                {grupos.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <div className="min-w-0 flex-1">
            <label
              htmlFor="motivo-exclusao"
              className="mb-1 block text-[11px] font-medium text-muted-foreground"
            >
              {/* ⚠️ NÃO diz "vai para o recibo": não vai. O motivo fica na
                  revisão desta tela e viaja no pedido, mas nada o persiste —
                  nem o payload da API, nem o selo, nem o recibo, nem a linha
                  de `campaigns`. Prometer persistência que não existe é o
                  mesmo defeito que o contrato tipado veio consertar. */}
              Motivo{' '}
              <span className="font-normal">(opcional — aparece na revisão abaixo)</span>
            </label>
            <Input
              id="motivo-exclusao"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="ex.: não vendemos simulação"
            />
          </div>
          <Button type="submit" disabled={!podeAdicionar} className="shrink-0">
            <Plus className="mr-1 h-4 w-4" aria-hidden />
            Adicionar exclusão
          </Button>
        </div>
        <p id="ajuda-exclusao" className="text-[11px] leading-relaxed text-muted-foreground">
          {jaExiste
            ? 'Esta exclusão já está na lista com a mesma correspondência e o mesmo alcance.'
            : explicarAlcance(novoCriterio(limpo || 'termo', { match_type: match }))}
        </p>
      </form>

      {negativas.length === 0 ? (
        <p className="mt-3 max-w-[74ch] text-sm text-muted-foreground">
          Nenhuma exclusão declarada. Esta tela não sugere nenhuma por conta
          própria: exclusão sem evidência medida é palpite, e palpite que bloqueia
          tráfego custa o mesmo que um erro.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {negativas.map((n, i) => (
            <li
              key={`${n.texto}:${n.match_type}:${n.nivel}:${n.grupo ?? ''}`}
              className="flex items-start gap-3 py-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="break-words text-sm font-medium text-foreground">
                    {n.texto}
                  </span>
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {ROTULO_DE_MATCH[n.match_type]}
                  </Badge>
                  {/* Medido e hipótese não podem parecer a mesma coisa. */}
                  {medido(n) ? (
                    <Badge className="bg-success/15 text-[10px] font-normal text-success hover:bg-success/15">
                      medida na conta
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                      hipótese
                    </Badge>
                  )}
                </div>
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                  {explicarAlcance(n)}, {explicarEscopo(n)} ·{' '}
                  {ROTULO_DE_ORIGEM[n.origem]}
                  {n.motivo ? ` · ${n.motivo}` : ''}
                </p>
                {n.evidencia?.tipo === 'MEDIDO' && (
                  <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                    {n.evidencia.fonte} · {n.evidencia.janela_inicio} a{' '}
                    {n.evidencia.janela_fim}
                    {n.evidencia.metricas
                      ? ` · ${Object.entries(n.evidencia.metricas)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(' · ')}`
                      : ''}
                  </p>
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remover a exclusão ${n.texto}`}
                onClick={() => onNegativas(negativas.filter((_, j) => j !== i))}
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Bloco>
  );
}

// ── a revisão ───────────────────────────────────────────────────────────────

function Revisao({ resumo }: { resumo: ReturnType<typeof resumir> }) {
  return (
    <Bloco titulo="Revisão">
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Numero rotulo="palavras ativam" valor={resumo.ativam} />
        <Numero rotulo="excluídas na campanha" valor={resumo.excluidasNaCampanha} />
        <Numero rotulo="excluídas em grupo" valor={resumo.excluidasNoGrupo} />
      </dl>

      {resumo.conflitos.length > 0 && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 p-3">
          <p className="flex items-center gap-2 text-sm font-medium text-destructive">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
            {resumo.conflitos.length}{' '}
            {resumo.conflitos.length === 1 ? 'keyword anulada' : 'keywords anuladas'} por
            uma exclusão
          </p>
          <ul className="mt-2 space-y-1">
            {resumo.conflitos.map((c, i) => (
              <li
                key={`${c.negativa.texto}:${c.positiva.texto}:${i}`}
                className="max-w-[80ch] text-[11px] leading-relaxed text-muted-foreground"
              >
                <b className="text-foreground">{c.positiva.texto}</b> não vai servir
                nenhuma busca: a exclusão <b className="text-foreground">{c.negativa.texto}</b>{' '}
                ({ROTULO_DE_MATCH[c.negativa.match_type]}) a bloqueia{' '}
                {explicarEscopo(c.negativa)}.
              </li>
            ))}
          </ul>
        </div>
      )}

      {resumo.duplicatas.length > 0 && (
        <p className="mt-3 max-w-[80ch] text-[11px] leading-relaxed text-warning">
          {resumo.duplicatas.length} termo(s) repetido(s) com a mesma
          correspondência e o mesmo alcance. Só o primeiro entra — a API recusa o
          segundo, e num envio atômico isso derrubaria a campanha inteira.
        </p>
      )}

      {resumo.hipoteses > 0 && (
        <p className="mt-3 max-w-[80ch] text-[11px] leading-relaxed text-muted-foreground">
          {resumo.hipoteses} de {resumo.excluidasNaCampanha + resumo.excluidasNoGrupo}{' '}
          exclusões são <b>hipóteses</b> — ninguém mediu que elas gastam. Depois de a
          campanha rodar, os termos de busca reais dizem quais valiam.
        </p>
      )}

      <p className="mt-4 max-w-[80ch] text-[11px] leading-relaxed text-muted-foreground">
        É isto que vai para o Google quando você provar: as palavras que ativam
        entram como keywords do grupo, e cada exclusão entra no nível em que foi
        declarada. A prova valida o envio sem criar nada.
      </p>
    </Bloco>
  );
}

// ── peças ───────────────────────────────────────────────────────────────────

function Bloco({
  titulo,
  contagem,
  children,
}: {
  titulo: string;
  contagem?: number;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={titulo}>
      <div className="mb-2 flex items-baseline gap-2">
        <h3 className="text-sm font-semibold text-foreground">{titulo}</h3>
        {contagem != null && (
          <span className="tabular text-xs text-muted-foreground">{contagem}</span>
        )}
      </div>
      {children}
    </section>
  );
}

function Numero({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div className="rounded-md border border-border p-3">
      <dt className="text-[11px] text-muted-foreground">{rotulo}</dt>
      <dd className="tabular mt-0.5 text-xl font-semibold text-foreground">{valor}</dd>
    </div>
  );
}

function SeletorDeMatch({
  valor,
  rotulo,
  opcoes,
  onChange,
}: {
  valor: MatchType;
  rotulo: string;
  opcoes: MatchType[];
  onChange: (m: MatchType) => void;
}) {
  return (
    <div className="shrink-0">
      <label className="sr-only" htmlFor={`match-${rotulo}`}>
        {rotulo}
      </label>
      <select
        id={`match-${rotulo}`}
        aria-label={rotulo}
        value={valor}
        onChange={(e) => onChange(e.target.value as MatchType)}
        className={cn(
          'h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
      >
        {opcoes.map((m) => (
          <option key={m} value={m}>
            {ROTULO_DE_MATCH[m]}
          </option>
        ))}
      </select>
    </div>
  );
}

export default MesaDeCriterios;
