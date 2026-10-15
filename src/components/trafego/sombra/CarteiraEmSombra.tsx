/**
 * A carteira em sombra: todas as campanhas Google Ads que o motor da carteira
 * (W13) olhou, com o estado do dado e a recomendação — leitura, nunca execução.
 *
 * O conteúdo vem de `GET /api/trafego/recomendacao-shadow` (`carteira_shadow.v1`):
 * um experimento conferido por sha256 por campanha, o mais recente de cada uma.
 *
 * ⚠️ Não há botão, link nem campo nesta tela, pelo mesmo motivo da seção da
 * campanha: recomendação em sombra não é ação a um clique de distância.
 *
 * ⚠️ "sem dado" (receita ou câmbio ausente) é dito com essas palavras e o
 * ROAS fica "—". Nunca 0: uma campanha sem câmbio não é uma campanha sem
 * receita.
 */
import React from 'react';
import { CircleCheck, CircleDashed, CircleHelp, EyeOff, ShieldAlert } from 'lucide-react';

import { AUSENTE } from '@/components/trafego/inventario/formato';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { PALAVRA_DA_DIRECAO, reais } from '@/components/trafego/sombra/RecomendacaoEmSombra';
import type { LeituraCarteiraShadow } from '@/hooks/useRecomendacaoShadow';
import type {
  CarteiraShadow,
  DirecaoShadow,
  EstadoDadoShadow,
  LinhaCarteiraShadow,
} from '@/types/recomendacaoShadow';

export const PALAVRA_DO_DADO: Record<
  EstadoDadoShadow,
  { palavra: string; tom: Tom; glifo: React.ComponentType<{ className?: string }> }
> = {
  completo: { palavra: 'dado completo', tom: 'bom', glifo: CircleCheck },
  sem_dado: { palavra: 'sem dado', tom: 'atencao', glifo: CircleDashed },
  amostra_insuficiente: { palavra: 'amostra insuficiente', tom: 'neutro', glifo: CircleHelp },
};

const DEC = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 3 });
const PCT = new Intl.NumberFormat('pt-BR', { style: 'percent', maximumFractionDigits: 1 });
const decimal = (v: number | null | undefined): string =>
  typeof v === 'number' && Number.isFinite(v) ? DEC.format(v) : AUSENTE;

const ORDEM: DirecaoShadow[] = ['pausar', 'reduzir', 'manter', 'aumentar', 'evidencia_insuficiente'];

export const CarteiraEmSombra: React.FC<{ leitura: LeituraCarteiraShadow }> = ({ leitura }) => {
  switch (leitura.estado) {
    case 'carregando':
      return (
        <p className="text-[13px] text-muted-foreground" role="status">
          lendo a carteira em sombra
        </p>
      );
    case 'integridade':
      return (
        <div className="max-w-[70ch]" role="alert">
          <p className="text-[13px] font-medium">
            Um experimento da carteira não passou na conferência de integridade.
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {leitura.mensagem} A carteira não é exibida: um resultado corrompido não diz de que
            campanha é, então nenhuma linha pode ser afirmada.
          </p>
        </div>
      );
    case 'fonte_indisponivel':
      return (
        <div className="max-w-[70ch]" role="alert">
          <p className="text-[13px] font-medium">
            A fonte dos experimentos em sombra está indisponível neste servidor.
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {leitura.mensagem} Isto não quer dizer que a carteira esteja vazia.
          </p>
        </div>
      );
    case 'falhou':
      return (
        <div className="max-w-[70ch]" role="alert">
          <p className="text-[13px] font-medium">Não consegui ler a carteira em sombra.</p>
          <p className="mt-1 text-[12px] text-muted-foreground">{leitura.mensagem}</p>
        </div>
      );
    case 'pronta':
      return <Pronta carteira={leitura.carteira} />;
  }
};

const Pronta: React.FC<{ carteira: CarteiraShadow }> = ({ carteira }) => {
  const contagem = new Map<string, number>();
  for (const l of carteira.campanhas) {
    const chave = l.situacao !== 'lida' ? 'sem_leitura' : (l.direcao ?? 'evidencia_insuficiente');
    contagem.set(chave, (contagem.get(chave) ?? 0) + 1);
  }
  const semDado = carteira.campanhas.filter((l) => l.estado_dado === 'sem_dado').length;
  const defasadas = carteira.campanhas.filter((l) => l.defasada === true).length;
  return (
    <div className="space-y-5">
      <p
        className="flex max-w-[70ch] gap-2 rounded-md border border-dashed border-border p-3 text-[12px] leading-relaxed text-muted-foreground"
        data-testid="faixa-sombra-carteira"
      >
        <EyeOff className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        <span>
          <span className="font-medium text-foreground">Em sombra: </span>
          custo do Google Ads e receita com câmbio versionado são reais; as direções não. Nada foi
          executado, nenhum valor é sugerido e esta tela não tem ação.
        </span>
      </p>

      {carteira.campanhas.length === 0 ? (
        <p className="text-[13px] text-muted-foreground" role="status">
          Nenhum experimento em sombra na pasta. Isto é ausência de análise, não recomendação.
        </p>
      ) : (
        <>
          <p className="text-[13px]" data-testid="resumo-carteira">
            {carteira.campanhas.length} campanhas ·{' '}
            {ORDEM.filter((d) => contagem.has(d))
              .map((d) => `${contagem.get(d)} ${PALAVRA_DA_DIRECAO[d].palavra}`)
              .join(' · ')}
            {contagem.has('sem_leitura') ? ` · ${contagem.get('sem_leitura')} sem leitura` : ''}
            {defasadas > 0 ? ` · ${defasadas} com leitura velha` : ''}
            {semDado > 0 ? ` · ${semDado} sem dado` : ''}
          </p>
          {carteira.carteira_defasada ? (
            <p className="max-w-[70ch] text-[12px] font-medium" role="alert" data-testid="carteira-velha">
              A leitura mais nova da carteira é de {carteira.leitura_mais_nova ?? 'data desconhecida'}: a
              agenda não roda há mais de dois dias. As direções abaixo descrevem aquele dia, não hoje.
            </p>
          ) : null}
          <TabelaDaCarteira linhas={carteira.campanhas} />
        </>
      )}
    </div>
  );
};

const TabelaDaCarteira: React.FC<{ linhas: LinhaCarteiraShadow[] }> = ({ linhas }) => (
  <div className="overflow-x-auto">
    <table className="w-full min-w-[760px] text-[12px]">
      <caption className="mb-2 text-left text-[11px] text-muted-foreground">
        Uma linha por campanha, do experimento mais recente. ROAS bruto da janela madura
        (receita ÷ custo). “—” é ausência, não zero.
      </caption>
      <thead>
        <tr className="border-b border-border text-left text-muted-foreground">
          <th scope="col" className="py-1 pr-3 font-medium">campanha</th>
          <th scope="col" className="py-1 pr-3 font-medium">status</th>
          <th scope="col" className="py-1 pr-3 font-medium">dado</th>
          <th scope="col" className="py-1 pr-3 font-medium">recomendação</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">ROAS</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">custo</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">receita</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">custo sem receita</th>
          <th scope="col" className="py-1 font-medium">leitura</th>
        </tr>
      </thead>
      <tbody>
        {linhas.map((l) => (
          <Linha key={l.campanha_externa} l={l} />
        ))}
      </tbody>
    </table>
  </div>
);

const Linha: React.FC<{ l: LinhaCarteiraShadow }> = ({ l }) => {
  if (l.situacao !== 'lida') {
    return (
      <tr className="border-b border-border/50" data-campanha={l.campanha_externa}>
        <th scope="row" className="py-1 pr-3 text-left font-normal">
          <span className="tabular">{l.campanha_externa}</span>
        </th>
        <td colSpan={8} className="py-1 text-muted-foreground" role="note">
          {l.situacao === 'ambigua'
            ? 'dois experimentos igualmente recentes; nenhum é exibido.'
            : 'o experimento desta campanha não tem data legível; não é exibido.'}{' '}
          {l.mensagem}
        </td>
      </tr>
    );
  }
  const d = PALAVRA_DA_DIRECAO[l.direcao ?? 'evidencia_insuficiente'];
  const dado = l.estado_dado ? PALAVRA_DO_DADO[l.estado_dado] : null;
  const j = l.janela_madura;
  return (
    <tr className="border-b border-border/50 align-top" data-campanha={l.campanha_externa}>
      <th scope="row" className="py-1 pr-3 text-left font-normal">
        <span className="block">{l.campanha_nome ?? AUSENTE}</span>
        <span className="tabular text-[11px] text-muted-foreground">{l.campanha_externa}</span>
      </th>
      <td className="py-1 pr-3 text-muted-foreground">{l.campanha_status ?? AUSENTE}</td>
      <td className="py-1 pr-3" title={l.motivo_estado_dado ?? undefined}>
        {dado ? (
          <Chip glifo={dado.glifo} palavra={dado.palavra} descricao={l.motivo_estado_dado ?? dado.palavra} tom={dado.tom} />
        ) : (
          <span className="text-muted-foreground">não declarado</span>
        )}
      </td>
      <td className="py-1 pr-3">
        <Chip
          glifo={ShieldAlert}
          palavra={d.palavra}
          descricao={`recomendação em sombra, não executada — ${d.frase}`}
          tom={d.tom}
        />
      </td>
      <td className="tabular py-1 pr-3 text-right">{decimal(j?.roas)}</td>
      <td className="tabular py-1 pr-3 text-right">{reais(j?.custo_brl)}</td>
      <td className="tabular py-1 pr-3 text-right">{reais(j?.receita_brl)}</td>
      <td className="tabular py-1 pr-3 text-right">
        {typeof l.fracao_custo_maduro_sem_receita === 'number'
          ? PCT.format(l.fracao_custo_maduro_sem_receita)
          : AUSENTE}
      </td>
      <td className="py-1 text-[11px] text-muted-foreground">
        {l.as_of ?? AUSENTE}
        {l.defasada ? (
          <span className="block font-medium text-foreground">leitura velha: a campanha saiu da coleta?</span>
        ) : null}
        <span className="block tabular">{l.experimento_id ?? AUSENTE}</span>
      </td>
    </tr>
  );
};
