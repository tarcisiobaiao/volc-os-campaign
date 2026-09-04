/**
 * Parada 3 — Termos. Quais termos a campanha vai comprar.
 *
 * ## A mentira de interface que esta parada remove
 *
 * A mesa anterior escrevia "o que você vê é o que vai para o Google". Não era
 * verdade. Em `/provar` a `Escolha` é montada com
 * `keywords_por_grupo(<conjunto aprovado>)`: a marcação do operador NÃO entra na
 * conta. Pior — a tela mandava as positivas no corpo do pedido
 * (`NovaCampanhaPage.tsx:367-381,413`), e `somente_negativas_do_corpo` recusa
 * qualquer critério com `negativa: false` com o código
 * `CRITERIO_POSITIVO_DO_CORPO_RECUSADO`.
 *
 * O conjunto positivo é AUTORIDADE da mineração. Aqui o operador confere,
 * declara exclusões, e — no ato que faltava até 03/09/2026 — APROVA. Nada mais.
 *
 * ## No telefone, a tabela não existe
 *
 * Abaixo de 768px a `<table>` sai do DOM e vira lista. Não é `display: none`:
 * `src/index.css:905-913` tem uma rede de segurança global
 * (`table { display: block; overflow-x: auto }`) que faz qualquer tabela perder
 * o contexto de tabela para tecnologia assistiva no telefone. Uma lista honesta
 * lê melhor que uma tabela que diz ser tabela e não é.
 */
import React, { useMemo, useState } from 'react';
import { CircleCheck, CircleHelp, Lock } from 'lucide-react';

import { BlocoDeEvidencia, LinhaDeFato } from '../BlocoDeEvidencia';
import { ChipDeEstado } from '../ChipDeEstado';
import { AcaoDominante } from '../AcaoDominante';
import { MesaDeCriterios } from '../../MesaDeCriterios';
import { useDensidade } from '../../inventario/densidade';
import { chave } from '@/lib/trafego/criterios';
import type {
  Cockpit, CriterioDeKeyword, KeywordDoConjuntoPago, MatchType, RevisaoDoConjuntoPago,
} from '@/types/trafego';

/** A frase normativa. Ela substitui "o que você vê é o que vai para o Google". */
export const FRASE_DOS_TERMOS =
  'O conjunto positivo é o aprovado na mineração. Aqui você confere a correspondência '
  + 'e declara exclusões.';

const numero = (n: number | null | undefined) =>
  n == null ? null : n.toLocaleString('pt-BR');

const dinheiro = (v: number | null | undefined, moeda: string | null | undefined) =>
  v == null ? null : `${moeda ? `${moeda} ` : ''}${v.toFixed(2).replace('.', ',')}`;

/** Uma linha da mesa, em lista — a forma do telefone. */
const ItemDeTermo: React.FC<{ k: KeywordDoConjuntoPago }> = ({ k }) => (
  <li className="flex min-h-[56px] flex-col gap-1 px-4 py-3">
    <span className="text-sm leading-snug text-foreground">{k.termo}</span>
    <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
      <span>{k.match_type}</span>
      <span className="tabular">
        {numero(k.volume) ?? 'volume não medido'}
      </span>
      <span className="tabular">
        {dinheiro(k.cpc?.valor, k.cpc?.moeda) ?? 'CPC não medido'}
      </span>
      {k.subintencao && <span>{k.subintencao}</span>}
    </span>
  </li>
);

const TabelaDeTermos: React.FC<{ termos: KeywordDoConjuntoPago[] }> = ({ termos }) => (
  <div className="overflow-x-auto rounded-lg border border-border bg-card">
    <table className="w-full text-sm">
      <caption className="sr-only">
        Termos do conjunto positivo aprovado, com volume, CPC e correspondência
      </caption>
      <thead className="bg-muted">
        <tr>
          <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Termo</th>
          <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Correspondência</th>
          <th scope="col" className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Volume</th>
          <th scope="col" className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">CPC</th>
          <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Sub-intenção</th>
        </tr>
      </thead>
      <tbody>
        {termos.map((k) => (
          <tr key={`${k.termo}:${k.match_type}`} className="border-t border-border">
            <td className="px-3 py-2 text-foreground">{k.termo}</td>
            <td className="px-3 py-2 text-muted-foreground">{k.match_type}</td>
            {/* ⚠️ "não medido", nunca 0. Zero é uma medição — diz que ninguém
                procura por isto — e o servidor parou de inventá-la. */}
            <td className="tabular px-3 py-2 text-right text-foreground">
              {numero(k.volume) ?? <span className="text-muted-foreground">não medido</span>}
            </td>
            <td className="tabular px-3 py-2 text-right text-foreground">
              {dinheiro(k.cpc?.valor, k.cpc?.moeda)
                ?? <span className="text-muted-foreground">não medido</span>}
            </td>
            <td className="px-3 py-2 text-muted-foreground">{k.subintencao ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export const ParadaTermos: React.FC<{
  cockpit: Cockpit;
  conjunto: RevisaoDoConjuntoPago | null;
  erroDoConjunto: string | null;
  aprovando: boolean;
  onAprovar: (motivo: string) => void;
  matchPadrao: MatchType;
  permitirBroadPositivo: boolean;
  matchPorKeyword: Record<string, MatchType>;
  onMatchPorKeyword: (m: Record<string, MatchType>) => void;
  negativas: CriterioDeKeyword[];
  onNegativas: (n: CriterioDeKeyword[]) => void;
}> = ({
  cockpit, conjunto, erroDoConjunto, aprovando, onAprovar,
  matchPadrao, permitirBroadPositivo, matchPorKeyword, onMatchPorKeyword,
  negativas, onNegativas,
}) => {
  const densidade = useDensidade();
  // ⚠️ NASCE VAZIO. É o mesmo motivo do motivo de lançamento: um default de
  // máquina no campo que justifica um ato humano esvazia o próprio ato.
  const [motivo, setMotivo] = useState('');

  const aprovado = Boolean(conjunto?.approved_set_sha256);
  const t = cockpit.triagem;

  const volumePorKeyword = useMemo(() => {
    const m: Record<string, number> = {};
    for (const g of cockpit.grupos ?? []) {
      for (const k of g.keywords) {
        // Ausência fica AUSENTE. A mesa mostra "não medido", nunca zero.
        if (k.volume != null) m[chave(k.texto)] = k.volume;
      }
    }
    return m;
  }, [cockpit]);

  // Os grupos que a mesa de exclusões usa saem do CONJUNTO APROVADO quando ele
  // existe — não da marcação livre do operador, que não tem voz sobre positivas.
  const gruposDoConjunto = useMemo(() => {
    if (!conjunto) return [];
    const por = new Map<string, string[]>();
    for (const k of conjunto.selecionadas) {
      const g = k.subintencao || 'CAMPANHA';
      por.set(g, [...(por.get(g) ?? []), k.termo]);
    }
    return [...por].map(([tipo, keywords]) => ({ tipo, keywords }));
  }, [conjunto]);

  const faltasParaAprovar: string[] = [];
  if (!conjunto) faltasParaAprovar.push('carregar o conjunto pago');
  else if (!conjunto.pode_aprovar) {
    faltasParaAprovar.push(conjunto.porque_nao ?? 'o servidor não liberou a aprovação');
  }
  if (motivo.trim().length < 10) faltasParaAprovar.push('escrever o motivo (pelo menos 10 caracteres)');

  return (
    <div className="space-y-4">
      <p className="max-w-[70ch] text-sm leading-6 text-foreground text-pretty">
        {FRASE_DOS_TERMOS}
      </p>

      {erroDoConjunto && (
        <div role="alert"
             className="rounded-lg border border-destructive/40 bg-destructive/[0.06] p-4 text-sm leading-6 text-foreground">
          {erroDoConjunto}
        </div>
      )}

      <BlocoDeEvidencia
        titulo="O conjunto positivo"
        tom={aprovado ? 'bom' : conjunto ? 'atencao' : 'neutro'}
      >
        <div className="mb-3">
          {aprovado ? (
            <ChipDeEstado
              glifo={CircleCheck} palavra="aprovado" tom="bom"
              descricao={`congelado por ${conjunto?.aprovado_por ?? 'alguém'}; daqui em diante o portão exige esta impressão`}
            />
          ) : conjunto ? (
            <ChipDeEstado
              glifo={Lock} palavra="não aprovado" tom="atencao"
              descricao="o portão recusa provar e criar enquanto o conjunto não for congelado"
            />
          ) : (
            <ChipDeEstado
              glifo={CircleHelp} palavra="não lido" tom="atencao"
              descricao="o conjunto pago desta oportunidade não foi lido do servidor"
            />
          )}
        </div>

        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <LinhaDeFato
            rotulo="positivas no conjunto"
            valor={conjunto ? conjunto.selecionadas.length : null}
            fonte="a mineração"
          />
          <LinhaDeFato
            rotulo="analisadas"
            valor={numero(t?.analisadas)}
            fonte="a triagem"
          />
          <LinhaDeFato
            rotulo="descartadas"
            valor={numero(t?.descartadas)}
            fonte="a triagem"
          />
          <LinhaDeFato
            rotulo="volume da fila"
            valor={numero(t?.volume_da_fila)}
            fonte="a mineração"
            ausencia="nenhum termo declara volume"
          />
          <LinhaDeFato
            rotulo="procedência"
            valor={cockpit.procedencia?.servicos_declarados?.join(' · ') || null}
            fonte="o cluster"
          />
          <LinhaDeFato
            rotulo="impressão do conjunto"
            valor={conjunto ? <code className="break-all">{conjunto.selected_set_sha256.slice(0, 16)}…</code> : null}
            fonte="a mineração"
          />
        </dl>

        {/* ⚠️ A ressalva de procedência do CPC vai colada, sempre. `keyword_info.cpc`
            do DataForSEO superestima o CPC real em 7,4x e INVERTE a ordem dentro
            do cluster — medido com 96 chamadas. Um número desses apresentado
            como medição é o defeito que os portões existem para impedir. */}
        {cockpit.procedencia?.aviso && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-warning text-pretty">
            {cockpit.procedencia.aviso}
          </p>
        )}

        {conjunto && conjunto.alertas.length > 0 && (
          <ul className="mt-3 space-y-1.5 text-sm leading-6 text-muted-foreground">
            {conjunto.alertas.map((a) => <li key={a}>{a}</li>)}
          </ul>
        )}
      </BlocoDeEvidencia>

      {conjunto && conjunto.selecionadas.length > 0 && (
        densidade === 'compacta'
          ? (
            <ul className="divide-y divide-border rounded-lg border border-border bg-card">
              {conjunto.selecionadas.map((k) => (
                <ItemDeTermo key={`${k.termo}:${k.match_type}`} k={k} />
              ))}
            </ul>
          )
          : <TabelaDeTermos termos={conjunto.selecionadas} />
      )}

      {conjunto && conjunto.excluidas.length > 0 && (
        <BlocoDeEvidencia titulo={`Descartadas pela mineração (${conjunto.excluidas.length})`}>
          <ul className="space-y-1.5 text-sm leading-6 text-muted-foreground">
            {conjunto.excluidas.slice(0, 12).map((k) => (
              <li key={k.termo}>
                <span className="text-foreground">{k.termo}</span>
                {k.motivo ? ` — ${k.motivo}` : ''}
              </li>
            ))}
          </ul>
          {conjunto.excluidas.length > 12 && (
            <p className="mt-2 text-sm text-muted-foreground">
              e mais {conjunto.excluidas.length - 12}.
            </p>
          )}
        </BlocoDeEvidencia>
      )}

      {/* O ATO. Só aparece enquanto o conjunto não está congelado. */}
      {conjunto && !aprovado && (
        <BlocoDeEvidencia titulo="Aprovar o conjunto" tom="atencao">
          <p className="max-w-[70ch] text-sm leading-6 text-foreground text-pretty">
            Aprovar congela estas {conjunto.selecionadas.length} positivas contra a
            impressão acima. Depois disso, nem esta tela nem o corpo do pedido podem
            acrescentar ou trocar positivas — só declarar exclusões.
          </p>
          <label className="mt-3 block">
            <span className="text-sm font-medium text-foreground">por que você aprova este conjunto</span>
            <input
              type="text"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="escreva a razão da aprovação"
              className="tabular mt-1.5 h-11 w-full rounded-md border border-[hsl(var(--input))] bg-card px-3 text-sm text-foreground md:h-10"
            />
          </label>
          <div className="mt-3">
            <AcaoDominante
              pode={faltasParaAprovar.length === 0}
              faltas={faltasParaAprovar}
              enviando={aprovando}
              onClick={() => onAprovar(motivo)}
            >
              Aprovar o conjunto positivo
            </AcaoDominante>
          </div>
        </BlocoDeEvidencia>
      )}

      {/* As exclusões que o operador declara. Só NEGATIVAS saem daqui para o
          corpo do pedido — as positivas ficam com a mineração. */}
      <MesaDeCriterios
        grupos={gruposDoConjunto}
        volumePorKeyword={volumePorKeyword}
        matchPadrao={matchPadrao}
        permitirBroadPositivo={permitirBroadPositivo}
        matchPorKeyword={matchPorKeyword}
        onMatchPorKeyword={onMatchPorKeyword}
        negativas={negativas}
        onNegativas={onNegativas}
      />
    </div>
  );
};
