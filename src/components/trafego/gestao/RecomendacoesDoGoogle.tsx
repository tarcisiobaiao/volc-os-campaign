/**
 * Recomendações do Google para esta campanha: aplicar ou dispensar — sempre
 * como PROPOSTA, que segue o mesmo ciclo (aprovar → aplicar).
 *
 * ⚠️ A API v25 não tem ensaio (validate_only) para recomendação: aplicar é
 * escrever, e aplicar não tem reverso. A tela diz isso antes do gesto, e não
 * depois. Para recomendação de orçamento ou de alvo, o caminho melhor é propor
 * `orcamento.diario`/`lance.alvo` com o valor recomendado: há ensaio e reverso.
 *
 * A leitura é sob demanda: ela consulta o Google, e abrir a página não deve
 * gastar cota sozinha.
 */
import React from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { contagem, dinheiro } from '@/components/trafego/inventario/formato';
import { errosDe, montarRecomendacao, recomendacaoMonetaria, validarMotivo } from '@/lib/trafego/gestao/acoes';
import { erroLegivel } from '@/lib/trafego/gestao/erros';
import { usePropor, useRecomendacoes } from '@/hooks/useGestaoDeCampanha';
import type { MetricasDeImpacto, RecomendacaoDoGoogle } from '@/types/gestao';

import { AvisoDeErro, classeDeEntrada } from './partes';

export const AVISO_SEM_ENSAIO =
  'A API do Google não tem ensaio (validate_only) para recomendação: aplicar é escrever na conta, e não há reverso.';

export interface RecomendacoesProps {
  customerId: string;
  campaignId: string;
  moeda: string | null;
  /** Quando a proposta nasce: o painel decide o que fazer (ex.: importar). */
  aoErroDeProposta?: (erro: unknown) => void;
}

function daCampanha(r: RecomendacaoDoGoogle, campaignId: string): boolean {
  return r.campanha == null || r.campanha.endsWith(`/campaigns/${campaignId}`);
}

export const RecomendacoesDoGoogle: React.FC<RecomendacoesProps> = ({ customerId, campaignId, moeda, aoErroDeProposta }) => {
  const [ligado, setLigado] = React.useState(false);
  const leitura = useRecomendacoes(customerId, ligado);
  const todas = leitura.data?.recomendacoes ?? [];
  const desta = todas.filter((r) => !r.dispensada && daCampanha(r, campaignId));
  const outras = todas.length - desta.length;

  return (
    <div>
      <p className="max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground" role="note">
        {AVISO_SEM_ENSAIO} Para recomendação de orçamento ou de alvo, prefira propor o valor recomendado em
        “Orçamento diário” ou “Alvo de lance”: lá há ensaio e reverso exato.
      </p>
      {!ligado ? (
        <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => setLigado(true)}>
          Ler recomendações do Google
        </Button>
      ) : leitura.isLoading ? (
        <p className="mt-3 text-[12px] text-muted-foreground" role="status">
          lendo recomendações na conta
        </p>
      ) : leitura.error ? (
        <AvisoDeErro className="mt-3" erro={erroLegivel(leitura.error)} />
      ) : (
        <>
          <p className="mt-3 text-[12px]">
            {desta.length === 0
              ? 'Nenhuma recomendação pendente para esta campanha.'
              : `${desta.length} ${desta.length === 1 ? 'recomendação pendente' : 'recomendações pendentes'} para esta campanha ou para a conta.`}
            {outras > 0 && <span className="text-muted-foreground"> Outras {outras} são de outras campanhas.</span>}
          </p>
          <ul className="mt-2 border-t border-border" role="list" aria-label="recomendações">
            {desta.map((r) => (
              <LinhaDeRecomendacao
                key={r.recurso}
                recomendacao={r}
                customerId={customerId}
                moeda={moeda}
                aoErroDeProposta={aoErroDeProposta}
              />
            ))}
          </ul>
        </>
      )}
    </div>
  );
};

function impacto(m: MetricasDeImpacto | undefined, moeda: string | null): string {
  if (!m) return '—';
  return [
    `${contagem(m.impressoes ?? null)} impr.`,
    `${contagem(m.cliques ?? null)} cliques`,
    dinheiro(m.custo_micros ?? null, moeda),
    `${m.conversoes ?? '—'} conv.`,
  ].join(' · ');
}

const LinhaDeRecomendacao: React.FC<{
  recomendacao: RecomendacaoDoGoogle;
  customerId: string;
  moeda: string | null;
  aoErroDeProposta?: (erro: unknown) => void;
}> = ({ recomendacao: r, customerId, moeda, aoErroDeProposta }) => {
  const [gesto, setGesto] = React.useState<null | 'recomendacao.aplicar' | 'recomendacao.dispensar'>(null);
  const [motivo, setMotivo] = React.useState('');
  const [erroLocal, setErroLocal] = React.useState<string | null>(null);
  const propor = usePropor(customerId);
  const idMotivo = `rec-motivo-${r.recurso.replace(/[^\w]/g, '-')}`;
  const monetaria = recomendacaoMonetaria(r.tipo);

  const enviar = () => {
    if (!gesto) return;
    const m = validarMotivo(motivo);
    const montagem = montarRecomendacao(gesto, r.recurso);
    const errosDaMontagem = errosDe(montagem);
    if (m || errosDaMontagem || !montagem.ok) {
      setErroLocal(m ?? Object.values(errosDaMontagem ?? {})[0] ?? null);
      return;
    }
    setErroLocal(null);
    propor.mutate(
      { customer_id: customerId, acao: montagem.acao, motivo: motivo.trim() },
      { onError: (e) => aoErroDeProposta?.(e) },
    );
    setGesto(null);
  };

  return (
    <li className="border-b border-border py-3">
      <p className="text-[13px] font-semibold">{r.tipo}</p>
      <p className="mt-0.5 break-all text-[11px] text-muted-foreground">{r.recurso}</p>
      {r.impacto && (
        <dl className="mt-1 grid gap-x-3 text-[11px] sm:grid-cols-[auto_minmax(0,1fr)]">
          <dt className="text-muted-foreground">hoje</dt>
          <dd className="tabular">{impacto(r.impacto.base, moeda)}</dd>
          <dt className="text-muted-foreground">potencial</dt>
          <dd className="tabular">{impacto(r.impacto.potencial, moeda)}</dd>
        </dl>
      )}
      {monetaria && (
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground" role="note">
          Recomendação de verba, alvo ou estratégia não é aplicada como recomendação: monte o valor em
          “Orçamento diário”, “Alvo de lance” ou “Troca de estratégia”, onde há ensaio e reverso.
        </p>
      )}
      {!gesto && (
        <div className="mt-2 flex gap-2">
          {!monetaria && (
            <Button type="button" size="sm" variant="outline" disabled={propor.isPending} onClick={() => setGesto('recomendacao.aplicar')}>
              Aplicar recomendação
            </Button>
          )}
          <Button type="button" size="sm" variant="ghost" disabled={propor.isPending} onClick={() => setGesto('recomendacao.dispensar')}>
            Dispensar
          </Button>
        </div>
      )}
      {gesto && (
        <div className="mt-2 rounded-md border border-border bg-muted/30 px-3 py-2.5" role="group" aria-label="confirmar recomendação">
          <p className="text-[12px]">
            {gesto === 'recomendacao.aplicar'
              ? `Vira proposta de aplicar. ${AVISO_SEM_ENSAIO}`
              : 'Vira proposta de dispensar: depois de aplicada, o Google não volta a mostrar esta recomendação.'}
          </p>
          <label htmlFor={idMotivo} className="mt-2 block text-[12px] font-medium">
            motivo
          </label>
          <textarea
            id={idMotivo}
            rows={2}
            className={cn(classeDeEntrada, 'mt-1')}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
          />
          {erroLocal && (
            <p className="mt-1 text-[11px] text-destructive" role="alert">
              {erroLocal}
            </p>
          )}
          <div className="mt-2 flex gap-2">
            <Button type="button" size="sm" onClick={enviar}>
              Enviar proposta
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setGesto(null)}>
              Voltar
            </Button>
          </div>
        </div>
      )}
      {propor.data && (
        <p className="mt-2 text-[12px]" role="status">
          {propor.data.ja_existia ? 'Esta proposta já existia na fila.' : 'Proposta registrada; aguarda aprovação.'}
        </p>
      )}
      {propor.error && <AvisoDeErro className="mt-2" erro={erroLegivel(propor.error)} />}
    </li>
  );
};
