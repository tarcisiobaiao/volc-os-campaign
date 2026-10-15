/**
 * A recomendação em sombra de uma campanha real — leitura, nunca execução.
 *
 * O conteúdo vem de `GET /api/trafego/recomendacao-shadow/{id}` (contrato
 * `recomendacao_shadow.v1`): um experimento do Freedom Lab que reconciliou
 * custo do Google Ads com receita JoinAds no grão campanha × dia (método da
 * v17_04, replay sem API) e foi conferido por sha256 no servidor.
 *
 * ⚠️ Não usa `MolduraDePrototipo`, de propósito. Aquela moldura afirma "nada
 * aqui vem da sua conta", e aqui os números VÊM da conta (custo lido do
 * Google, receita lida do banco). O que é sombra é a DECISÃO, e é isso que a
 * faixa desta seção diz.
 *
 * ⚠️ Não existe botão nesta seção. Nem desabilitado: um botão cinza "Pausar"
 * ensina que a recomendação é uma ação a um clique de distância, e ela não é —
 * pausar de verdade é ordem humana, fora desta tela.
 *
 * ⚠️ O ROAS nativo do Google aparece só para ser marcado como não confiável:
 * o valor de conversão da conta é fixo por conversão, não é receita.
 */
import React from 'react';
import { AlertTriangle, EyeOff, ShieldAlert } from 'lucide-react';

import { AUSENTE } from '@/components/trafego/inventario/formato';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import type { LeituraShadow } from '@/hooks/useRecomendacaoShadow';
import type {
  DiaShadow,
  DirecaoShadow,
  JanelaShadow,
  RecomendacaoShadow,
} from '@/types/recomendacaoShadow';

export const PALAVRA_DA_DIRECAO: Record<DirecaoShadow, { palavra: string; tom: Tom; frase: string }> = {
  manter: { palavra: 'manter', tom: 'bom', frase: 'A leitura não pede mudança.' },
  reduzir: { palavra: 'reduzir', tom: 'atencao', frase: 'A leitura pede menos verba.' },
  aumentar: { palavra: 'aumentar', tom: 'info', frase: 'A leitura comporta mais verba.' },
  pausar: { palavra: 'pausar', tom: 'ruim', frase: 'A campanha não paga o próprio custo na janela madura.' },
  evidencia_insuficiente: {
    palavra: 'evidência insuficiente',
    tom: 'neutro',
    frase: 'Não há evidência bastante para recomendar uma direção.',
  },
};

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const DEC = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 3 });
const INT = new Intl.NumberFormat('pt-BR');

export const reais = (v: number | null | undefined): string =>
  typeof v === 'number' && Number.isFinite(v) ? BRL.format(v) : AUSENTE;
const decimal = (v: number | null | undefined): string =>
  typeof v === 'number' && Number.isFinite(v) ? DEC.format(v) : AUSENTE;
const inteiro = (v: number | null | undefined): string =>
  typeof v === 'number' && Number.isFinite(v) ? INT.format(v) : AUSENTE;

export const RecomendacaoEmSombra: React.FC<{ leitura: LeituraShadow }> = ({ leitura }) => {
  switch (leitura.estado) {
    case 'sem_id':
      return (
        <p className="max-w-[70ch] text-[13px] text-muted-foreground" role="status">
          Esta campanha não tem id no Google declarado; sem ele não há como procurar uma
          recomendação em sombra.
        </p>
      );
    case 'carregando':
      return (
        <p className="text-[13px] text-muted-foreground" role="status">
          lendo a recomendação em sombra
        </p>
      );
    case 'ausente':
      return (
        <p className="max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground" role="status">
          Nenhum experimento em sombra olhou esta campanha.{' '}
          <strong className="font-medium text-foreground">
            Isto é ausência de análise, não recomendação de manter.
          </strong>
        </p>
      );
    case 'integridade':
      return (
        <div className="max-w-[70ch]" role="alert">
          <p className="text-[13px] font-medium">
            A recomendação existe e não passou na conferência de integridade.
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {leitura.mensagem} Ela não é exibida porque ninguém conseguiria reproduzir o número.
          </p>
        </div>
      );
    case 'falhou':
      return (
        <div className="max-w-[70ch]" role="alert">
          <p className="text-[13px] font-medium">Não consegui ler a recomendação em sombra.</p>
          <p className="mt-1 text-[12px] text-muted-foreground">{leitura.mensagem}</p>
        </div>
      );
    case 'pronta':
      return <Pronta r={leitura.recomendacao} />;
  }
};

const Pronta: React.FC<{ r: RecomendacaoShadow }> = ({ r }) => {
  const d = PALAVRA_DA_DIRECAO[r.direcao] ?? PALAVRA_DA_DIRECAO.evidencia_insuficiente;
  return (
    <div className="space-y-5">
      <p
        className="flex max-w-[70ch] gap-2 rounded-md border border-dashed border-border p-3 text-[12px] leading-relaxed text-muted-foreground"
        data-testid="faixa-sombra"
      >
        <EyeOff className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        <span>
          <span className="font-medium text-foreground">Em sombra: </span>
          os números são reais (custo do Google Ads, receita JoinAds), a decisão não. Nada foi
          executado, nenhum valor é sugerido e esta seção não tem ação.
        </span>
      </p>

      <div>
        <p className="kicker">recomendação</p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Chip
            glifo={ShieldAlert}
            palavra={d.palavra}
            descricao={`recomendação em sombra, não executada — ${d.frase}`}
            tom={d.tom}
          />
          <span className="text-[13px]">{d.frase}</span>
        </div>
        {r.motivos.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-[13px] leading-relaxed">
            {r.motivos.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
      </div>

      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        <Janela titulo="janela madura" j={r.janela_madura} />
        <Janela titulo="janela madura recente" j={r.janela_madura_recente} />
      </dl>
      <p className="text-[11px] text-muted-foreground">
        ROAS bruto (receita ÷ custo, sem revshare nem imposto). Sob estresse (receita ×
        {decimal(r.parametros?.estresse_receita ?? null)}, câmbio ×
        {decimal(r.parametros?.estresse_cambio ?? null)}): {decimal(r.roas_sob_estresse)}.
        Maduro até {r.corte_maturidade ?? AUSENTE} (exclusive); leitura de {r.as_of ?? AUSENTE}.
      </p>

      <RoasNativo r={r} />

      <TabelaDeDias dias={r.dias} />

      {r.ressalvas.length > 0 && (
        <div>
          <p className="kicker">ressalvas</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] leading-relaxed text-muted-foreground">
            {r.ressalvas.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        experimento {r.origem.experimento_id} · integridade {r.origem.integridade} · código{' '}
        <code className="tabular">{(r.origem.codigo_sha256 ?? AUSENTE).slice(0, 12)}</code> ·
        snapshot <code className="tabular">{(r.origem.snapshot_sha256 ?? AUSENTE).slice(0, 12)}</code>
        {r.origem.replay_sem_api ? ' · replay sem API' : ''}
      </p>
    </div>
  );
};

const Janela: React.FC<{ titulo: string; j: JanelaShadow | null }> = ({ titulo, j }) => (
  <div>
    <dt className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">{titulo}</dt>
    <dd className="mt-1 text-[13px] leading-relaxed">
      {j ? (
        <>
          <span className="tabular font-medium">ROAS {decimal(j.roas)}</span> · {inteiro(j.dias)} dias ·{' '}
          custo {reais(j.custo_brl)} · receita {reais(j.receita_brl)} · contribuição{' '}
          {reais(j.contribuicao_bruta)} · {inteiro(j.cliques)} cliques
        </>
      ) : (
        AUSENTE
      )}
    </dd>
  </div>
);

const RoasNativo: React.FC<{ r: RecomendacaoShadow }> = ({ r }) => (
  <div
    className="flex max-w-[70ch] gap-2 rounded-md border border-warning/40 p-3 text-[12px] leading-relaxed"
    role="note"
    aria-label="ROAS nativo do Google não confiável"
  >
    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
    <span>
      <span className="font-medium">ROAS nativo do Google: não confiável.</span>{' '}
      Valor de conversão no período: {reais(r.roas_nativo_google.valor_conversao_total)}.{' '}
      <span className="text-muted-foreground">{r.roas_nativo_google.motivo}</span>
    </span>
  </div>
);

const TabelaDeDias: React.FC<{ dias: DiaShadow[] }> = ({ dias }) => (
  <div className="overflow-x-auto">
    <table className="w-full min-w-[520px] text-[12px]">
      <caption className="mb-2 text-left text-[11px] text-muted-foreground">
        Grão campanha × dia. “—” é ausência, não zero; dias imaturos podem ser reescritos pelo
        conector D-1.
      </caption>
      <thead>
        <tr className="border-b border-border text-left text-muted-foreground">
          <th scope="col" className="py-1 pr-3 font-medium">dia</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">custo</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">cliques</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">receita</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">contribuição</th>
          <th scope="col" className="py-1 font-medium">maturidade</th>
        </tr>
      </thead>
      <tbody>
        {dias.map((dia) => (
          <tr key={dia.data} className="border-b border-border/50" data-maduro={dia.maduro}>
            <th scope="row" className="tabular py-1 pr-3 text-left font-normal">{dia.data}</th>
            <td className="tabular py-1 pr-3 text-right">{reais(dia.custo_brl)}</td>
            <td className="tabular py-1 pr-3 text-right">{inteiro(dia.cliques)}</td>
            <td className="tabular py-1 pr-3 text-right">{reais(dia.receita_brl)}</td>
            <td className="tabular py-1 pr-3 text-right">{reais(dia.contribuicao_brl)}</td>
            <td className="py-1 text-muted-foreground">{dia.maduro ? 'madura' : 'imatura'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
