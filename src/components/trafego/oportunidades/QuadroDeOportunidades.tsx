/**
 * OPORTUNIDADES — o que está pronto para virar campanha.
 *
 * ## Este arquivo é CONTEÚDO, não página
 *
 * Ele não monta cabeçalho, não monta `<Layout>` e não tem recuo de página: a
 * moldura é do Hub, e é uma só. Antes disto o Hub montava uma PÁGINA inteira
 * dentro de uma aba — duas molduras, dois recuos e, por um tempo, dois
 * `<h1>Tráfego</h1>` empilhados. Para quem navega por leitor de tela, dois
 * títulos de documento numa página só significam que a estrutura deixou de
 * dizer onde ele está.
 *
 * ## Por que linhas alinhadas e não uma grade de cartões
 *
 * A pergunta aqui é comparativa: qual funil tem mais keyword triada, qual tem
 * volume, qual já está no ar. Cartões lado a lado obrigam a ler cada um por
 * inteiro para comparar dois números; colunas alinhadas respondem na vertical.
 *
 * ## Por que não há coluna de performance, e isso é fato e não escolha estética
 *
 * `metrics.` tem zero ocorrências em todo o `volc_ads`. Não existe camada de
 * métrica, receita nem executor de ajuste. Uma coluna com ROAS seria desenhada,
 * não medida — e a própria rota devolve `sem_metrica: true` para que ninguém a
 * invente a partir de outro campo.
 *
 * ## Onde mora a língua
 *
 * As frases — o estado do portão de criação, o estado de cada candidato e o
 * formato do volume — moram em `linguagem.ts`, e não aqui. É a mesma separação
 * de `formato.tsx` no inventário: regra de apresentação espalhada por dentro de
 * cada componente que resolver mostrar um estado já foi perdida uma vez.
 */
import React from 'react';
import { ArrowUpRight, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { Chip } from '@/components/trafego/inventario/Selos';
import { CodigoDaOcorrencia } from '@/components/trafego/inventario/EstadosDoInventario';
import { ocorrenciaDaFrase } from '@/components/trafego/inventario/erros';
import { AUSENTE, idade } from '@/components/trafego/inventario/formato';
import { useDensidade } from '@/components/trafego/inventario/densidade';
import type { CandidatoNoQuadro } from '@/types/trafego';
import {
  AVISO_CONFIRMACAO_PENDENTE,
  CONFIRMAR_VINCULO_INDISPONIVEL,
  RECONCILIACAO_PENDENTE,
  REVISAO_DE_CONFLITO,
  comoPreparar,
  fraseDeReconciliacao,
} from '@/components/trafego/preparar/estados';
import type { CandidatoPreparar } from '@/components/trafego/hub/contrato';

import {
  COLUNAS,
  NUMERICAS,
  compacto,
  estadoDoCandidato,
  fraseDoPortao,
  type EstadoDoCandidato,
} from './linguagem';
import { useOportunidades } from './useOportunidades';

// ── o quadro ────────────────────────────────────────────────────────────────

/** Segundos desde que ESTA tela recebeu o que está mostrando. */
function idadeDaLeitura(lidoEm: number | null, agora: number): number | null {
  if (!lidoEm) return null;
  return Math.max(0, Math.round((agora - lidoEm) / 1000));
}

export const QuadroDeOportunidades: React.FC = () => {
  const leitura = useOportunidades();
  const densidade = useDensidade();
  const { quadro, portao } = leitura;

  // O relógio da tela avança sozinho para o selo de frescor não congelar num
  // "lido agora" enquanto alguém deixa a aba aberta a tarde inteira.
  const [agora, setAgora] = React.useState(() => Date.now());
  React.useEffect(() => {
    const t = setInterval(() => setAgora(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  const segundos = idadeDaLeitura(leitura.lidoEm, agora);
  const portaoLegivel = fraseDoPortao(portao);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="max-w-[68ch] text-sm leading-relaxed text-muted-foreground">
          O Pautador minera as keywords e o Redator escreve o funil. Aqui o clique é
          comprado — e cada candidato é conferido contra a conta real antes de existir
          campanha.
        </p>
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-[11px] text-muted-foreground">
            {leitura.lidoEm ? `lido ${idade(segundos)}` : 'sem data de leitura'}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 gap-2 px-3 text-xs"
            disabled={leitura.atualizando}
            onClick={leitura.recarregar}
          >
            <RefreshCw
              className={cn(
                'h-3 w-3',
                leitura.atualizando && 'animate-spin motion-reduce:animate-none',
              )}
              aria-hidden
            />
            {leitura.atualizando ? 'conferindo…' : 'conferir de novo'}
          </Button>
        </div>
      </div>

      {/* O portão fica no topo e sempre visível. Ele não é detalhe técnico: é a
          diferença entre uma tela que confere e uma tela que gasta. */}
      <section
        aria-label="permissão para criar campanha"
        className={cn(
          'flex max-w-[80ch] items-start gap-3 rounded-md border px-4 py-3',
          portaoLegivel.tom === 'ruim'
            ? 'border-destructive/45 bg-destructive/[0.06]'
            : portaoLegivel.tom === 'atencao'
              ? 'border-warning/45 bg-warning/[0.06]'
              : 'border-border bg-card',
        )}
      >
        <portaoLegivel.glifo
          className={cn(
            'mt-0.5 h-4 w-4 shrink-0',
            portaoLegivel.tom === 'ruim'
              ? 'text-destructive'
              : portaoLegivel.tom === 'atencao'
                ? 'text-warning'
                : 'text-muted-foreground',
          )}
          aria-hidden
        />
        <div className="min-w-0">
          {/* ⚠️ `h2`: este é o primeiro título do conteúdo da aba Preparar,
              logo abaixo do `h1` da moldura do Hub. Medido em 27/08/2026, a
              árvore da aba era h1 → h3 — quem navega por títulos perdia o nível
              do meio, e o leitor de tela anunciava uma subseção de algo que não
              existe. O nível é semântica; o tamanho continua o mesmo. */}
          <h2 className="text-[13px] font-semibold">{portaoLegivel.palavra}</h2>
          <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
            {portaoLegivel.explicacao}
          </p>
        </div>
      </section>

      {leitura.carregando && <Esqueleto />}

      {leitura.falhou && !quadro && (
        <FalhaDoQuadro aoTentarDeNovo={leitura.recarregar} />
      )}

      {leitura.falhou && quadro && (
        <p
          className="rounded-md border border-warning/40 bg-warning/[0.06] px-4 py-3 text-[12px] leading-snug text-muted-foreground"
          role="status"
        >
          A atualização mais recente falhou. O que está abaixo é a última leitura boa.
        </p>
      )}

      {quadro && (
        <>
          {/* Totais numa linha declarativa, não numa faixa de números grandes:
              o dado que decide é a LISTA, e um agregado gigante no topo come a
              primeira olhada com algo que ninguém perguntou. */}
          <p className="flex flex-wrap gap-x-5 gap-y-1 border-y border-border py-3 text-[12px] text-muted-foreground">
            <span>
              <span className="tabular font-medium text-foreground">
                {quadro.totais.funis_publicados}
              </span>{' '}
              funis publicados
            </span>
            <span>
              <span className="tabular font-medium text-foreground">
                {quadro.totais.com_cluster}
              </span>{' '}
              com keywords mineradas
            </span>
            <span>
              <span className="tabular font-medium text-foreground">
                {quadro.totais.keywords_disponiveis}
              </span>{' '}
              keywords triadas para anúncio
            </span>
          </p>

          <section aria-label="funis prontos para anunciar" className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="kicker">prontos para anunciar</h3>
              <span className="tabular text-xs text-muted-foreground">
                {quadro.prontos.length}
              </span>
            </div>
            <p className="max-w-[74ch] text-[12px] leading-relaxed text-muted-foreground">
              Funis do Redator que já publicaram página. Os que têm cluster de keywords no
              Pautador podem virar campanha sem digitação nenhuma.
            </p>

            {quadro.prontos.length === 0 ? (
              <Vazio />
            ) : densidade === 'compacta' ? (
              <ul className="rounded-md border border-border bg-card">
                {quadro.prontos.map((p) => (
                  <LinhaCompacta key={`${p.opportunity_id}:${p.run_id}`} candidato={p} />
                ))}
              </ul>
            ) : (
              <div className="rounded-md border border-border bg-card">
                <table className="w-full table-auto border-collapse text-left">
                  <caption className="sr-only">
                    Funis publicados, com quantas keywords foram triadas para anúncio e se
                    já existe campanha no ar
                  </caption>
                  <thead>
                    <tr className="border-b border-border">
                      {COLUNAS.map((c) => (
                        <th
                          key={c}
                          scope="col"
                          className={cn(
                            'kicker h-9 px-3 align-middle',
                            NUMERICAS.has(c) && 'text-right',
                          )}
                        >
                          {c}
                        </th>
                      ))}
                      <th scope="col" className="kicker h-9 px-3 text-right align-middle">
                        ação
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {quadro.prontos.map((p) => (
                      <LinhaEmTabela key={`${p.opportunity_id}:${p.run_id}`} candidato={p} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Dito na tela porque a ausência de métrica é uma DECISÃO, e uma
                decisão não declarada parece esquecimento. */}
            <p className="max-w-[74ch] border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
              Não há performance aqui. {quadro.por_que}
            </p>
          </section>
        </>
      )}
    </div>
  );
};

// ── o estado de cada candidato ──────────────────────────────────────────────

const linkDaAcao = cn(
  'inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-xs font-medium',
  'text-primary hover:underline',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
);

const Acao: React.FC<{ candidato: CandidatoNoQuadro; estado: EstadoDoCandidato }> = ({
  candidato: p,
  estado,
}) => {
  const frase = fraseDeReconciliacao(comoPreparar(p));

  if (frase.estado === 'conflito') {
    return (
      <span className="block max-w-[36ch] text-right">
        <span className="text-[12px] font-medium text-foreground">{frase.acao}</span>
        <span className="mt-1 block text-[11px] leading-snug text-muted-foreground">
          {REVISAO_DE_CONFLITO}
        </span>
      </span>
    );
  }

  if (frase.estado === 'correspondencia_provavel') {
    return (
      <span className="block max-w-[36ch] text-right">
        <button
          type="button"
          disabled
          className="inline-flex min-h-11 items-center rounded-md border border-border px-2 text-xs text-muted-foreground"
        >
          {frase.acao}
        </button>
        <span className="mt-1 block text-[11px] leading-snug text-muted-foreground">
          {CONFIRMAR_VINCULO_INDISPONIVEL}
        </span>
      </span>
    );
  }

  if (frase.podeRelancar) {
    return (
      <Link to={`/trafego/nova/${p.opportunity_id}?run=${p.run_id}&relancar=1`} className={linkDaAcao}>
        {frase.acao}
        <ArrowUpRight className="h-3 w-3" aria-hidden />
      </Link>
    );
  }

  if (!estado.pronto) {
    return (
      <span className="text-[11px] leading-snug text-muted-foreground">
        minerar no Pautador antes
      </span>
    );
  }

  if (frase.estado === 'pendente') {
    return (
      <span className="block max-w-[36ch] text-right">
        <span className="text-[12px] font-medium text-foreground">{frase.acao}</span>
        <span className="mt-1 block text-[11px] leading-snug text-muted-foreground">
          {RECONCILIACAO_PENDENTE}
        </span>
      </span>
    );
  }

  if (frase.estado === 'vinculada') {
    return (
      <Link to={`/trafego/nova/${p.opportunity_id}?run=${p.run_id}`} className={linkDaAcao}>
        abrir o que existe
        <ArrowUpRight className="h-3 w-3" aria-hidden />
      </Link>
    );
  }

  if (!frase.podeMontar) {
    return (
      <span className="text-[11px] leading-snug text-muted-foreground">{frase.acao}</span>
    );
  }

  return (
    <span className="block max-w-[36ch] text-right">
      <Link to={`/trafego/nova/${p.opportunity_id}?run=${p.run_id}`} className={linkDaAcao}>
        montar campanha
        <ArrowUpRight className="h-3 w-3" aria-hidden />
      </Link>
      {p.reconciliacao?.exige_confirmacao_humana === true && (
        <span className="mt-1 block text-[11px] leading-snug text-muted-foreground">
          {AVISO_CONFIRMACAO_PENDENTE}
        </span>
      )}
    </span>
  );
};

const Procedencia: React.FC<{ candidato: CandidatoNoQuadro }> = ({ candidato: p }) => {
  // A procedência viaja desde o quadro. Um número sem ela é o defeito que este
  // módulo inteiro existe para não cometer.
  if (p.servicos_declarados.length === 0) {
    return <span className="text-[11px] text-muted-foreground">não declarada</span>;
  }
  return (
    <span className="text-[11px] text-muted-foreground">
      minerado por {p.servicos_declarados.join(', ')}
    </span>
  );
};

function chipDoCandidato(p: CandidatoPreparar, estado: EstadoDoCandidato) {
  if (!estado.pronto) return estado.chip;
  const frase = fraseDeReconciliacao(p);
  return {
    glifo: frase.glifo,
    palavra: frase.palavra,
    descricao: frase.descricao,
    tom: frase.tom,
  };
}

const LinhaEmTabela: React.FC<{ candidato: CandidatoNoQuadro }> = ({ candidato: p }) => {
  const estado = estadoDoCandidato(p);
  const preparar = comoPreparar(p);
  const chip = chipDoCandidato(preparar, estado);
  return (
    <tr className="border-b border-border/60 last:border-b-0 hover:bg-muted/40">
      <th scope="row" className="max-w-[38ch] px-3 py-3 text-left align-top font-normal">
        <span className="block text-[13px] font-medium leading-snug">{p.titulo}</span>
        <span className="tabular mt-0.5 block truncate text-[11px] text-muted-foreground">
          {p.dominio}
        </span>
      </th>
      <td className="tabular px-3 py-3 text-right align-top text-[13px]">
        {/* Sem cluster o número não é zero: é ausência de triagem. */}
        {p.tem_cluster ? p.keywords_para_anuncio : AUSENTE}
      </td>
      <td className="tabular px-3 py-3 text-right align-top text-[13px]">
        {compacto(p.volume_total)}
      </td>
      <td className="px-3 py-3 align-top">
        <Procedencia candidato={p} />
      </td>
      <td className="px-3 py-3 align-top">
        <Chip
          glifo={chip.glifo}
          palavra={chip.palavra}
          descricao={chip.descricao}
          tom={chip.tom}
        />
      </td>
      <td className="px-3 py-3 text-right align-top">
        <Acao candidato={p} estado={estado} />
      </td>
    </tr>
  );
};

const LinhaCompacta: React.FC<{ candidato: CandidatoNoQuadro }> = ({ candidato: p }) => {
  const estado = estadoDoCandidato(p);
  const chip = chipDoCandidato(comoPreparar(p), estado);
  return (
    <li className="border-b border-border last:border-b-0 px-3 py-3">
      <p className="text-[13px] font-medium leading-snug">{p.titulo}</p>
      <p className="tabular mt-0.5 truncate text-[11px] text-muted-foreground">{p.dominio}</p>
      <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
        <div className="flex items-baseline gap-1.5">
          <dt className="kicker text-muted-foreground">keywords</dt>
          <dd className="tabular font-medium">
            {p.tem_cluster ? p.keywords_para_anuncio : AUSENTE}
          </dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="kicker text-muted-foreground">volume/mês</dt>
          <dd className="tabular font-medium">{compacto(p.volume_total)}</dd>
        </div>
      </dl>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <Chip
          glifo={chip.glifo}
          palavra={chip.palavra}
          descricao={chip.descricao}
          tom={chip.tom}
        />
        <Acao candidato={p} estado={estado} />
      </div>
      <div className="mt-1">
        <Procedencia candidato={p} />
      </div>
    </li>
  );
};

// ── os estados sem lista ────────────────────────────────────────────────────

const Esqueleto: React.FC = () => (
  <div role="status" aria-live="polite" className="rounded-md border border-border bg-card">
    <span className="sr-only">conferindo os funis publicados</span>
    {[0, 1, 2].map((i) => (
      <div key={i} className="flex items-center gap-4 border-b border-border/50 px-3 py-3 last:border-b-0">
        <Skeleton className="h-4 flex-1 motion-reduce:animate-none" />
        <Skeleton className="h-4 w-16 motion-reduce:animate-none" />
        <Skeleton className="h-4 w-16 motion-reduce:animate-none" />
        <Skeleton className="h-4 w-28 motion-reduce:animate-none" />
      </div>
    ))}
  </div>
);

/** O vazio ENSINA: diz o que apareceria aqui e o que fazer para preencher. */
const Vazio: React.FC = () => (
  <div className="rounded-md border border-dashed border-border px-4 py-8 text-center">
    <h4 className="font-display text-base font-semibold">Nenhum funil publicado ainda</h4>
    <p className="mx-auto mt-2 max-w-[62ch] text-[13px] leading-relaxed text-muted-foreground">
      Esta lista mostra os funis que já publicaram página e podem virar campanha. Escreva
      um no{' '}
      <Link to="/redator" className="underline underline-offset-2">
        Redator
      </Link>{' '}
      e publique a página para ele aparecer aqui. Vazio aqui não significa que não há
      trabalho em andamento — significa que nada chegou a publicar.
    </p>
  </div>
);

const FalhaDoQuadro: React.FC<{ aoTentarDeNovo: () => void }> = ({ aoTentarDeNovo }) => {
  // Memo pela identidade da função: sem ele o código seria sorteado a cada
  // render e o operador veria um identificador diferente a cada piscada da
  // tela — nenhum deles servindo para achar nada.
  const ocorrencia = React.useMemo(() => ocorrenciaDaFrase(null, 'oportunidades'), []);
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/[0.05] px-4 py-5">
      <div role="alert">
        <h3 className="font-display text-base font-semibold">
          Não consegui ler os funis prontos
        </h3>
        <p className="mt-1 max-w-[62ch] text-[13px] leading-relaxed">{ocorrencia.mensagem}</p>
        <p className="mt-1 max-w-[62ch] text-[13px] leading-relaxed text-muted-foreground">
          {ocorrencia.proximoPasso}
        </p>
        <p className="mt-2 max-w-[62ch] text-[13px] leading-relaxed text-muted-foreground">
          Nenhuma campanha foi criada nem alterada por causa disto — o que faltou foi
          conseguir olhar.
        </p>
      </div>
      <CodigoDaOcorrencia ocorrencia={ocorrencia} />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-3 h-9 px-3 text-xs"
        onClick={aoTentarDeNovo}
      >
        tentar de novo
      </Button>
    </div>
  );
};

export default QuadroDeOportunidades;
