/**
 * A bancada de criação — uma jornada por canal, derivada do registro tipado.
 *
 * ## A regra que governa esta tela inteira
 *
 * > Nenhuma etapa aparece porque o canal existe. Ela aparece porque
 * > `apresentarCanal` a declarou, cruzando gramática oficial, manifesto do
 * > backend, permissão e trava.
 *
 * As sete etapas genéricas saíram daqui de propósito: Search não pede imagem,
 * Performance Max não tem grupo de anúncios de Search, e a Google Ads API não
 * cria campanha Video. O JSX desta tela não ramifica por `canal === …`.
 *
 * ⚠️ Esta carcaça não monta pedido, não chama `/provar` e não chama `/subir`.
 * O cockpit que de fato monta Search/Display é `NovaCampanhaPage`. O CTA
 * operacional aponta para Preparar. Demand Gen não herda esse formulário: a
 * bancada declara apenas a porta HTTP tipada enquanto não houver coletor
 * visual dos assets aprovados pelo Estúdio.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { Ban, Check, CircleDashed, Eye, Lock } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/trafego/inventario/Selos';
import { MolduraDePrototipo } from '@/components/trafego/laboratorio/SeloDePrototipo';
import { rotuloDoNo, type NoDaEstrutura } from '@/components/trafego/hub/perfilDeCanal';
import {
  PALAVRA_DO_PAPEL,
  apresentarBancada,
  type ApresentacaoDoCanal,
  type PapelDoCanal,
} from '@/components/trafego/canal/jornada';
import type { Canal, CapacidadesDoOperador, EstadoDaTrava, ManifestoDeCanal } from '@/types/trafego';

const TOM_DO_PAPEL: Record<PapelDoCanal, 'bom' | 'verificado' | 'atencao' | 'neutro' | 'info'> = {
  operacional: 'bom',
  parcial: 'verificado',
  planejado: 'info',
  pre_requisito: 'atencao',
  somente_leitura: 'neutro',
};

const DESCRICAO_DO_PAPEL: Record<PapelDoCanal, string> = {
  operacional: 'o VOLC sabe montar campanha neste canal e abre o cockpit real',
  parcial: 'há builder e prova, com limites declarados pelo manifesto',
  planejado: 'o VOLC ainda não tem construtor; o próximo desbloqueio está abaixo',
  pre_requisito: 'falta o vínculo de Merchant Center, não é erro de campanha',
  somente_leitura: 'a API só consulta e reporta; não cria nem atualiza',
};

const GLIFO_DO_PAPEL: Record<PapelDoCanal, typeof Check> = {
  operacional: Check,
  parcial: Check,
  planejado: Lock,
  pre_requisito: Ban,
  somente_leitura: Eye,
};

export interface EstudioMulticanalProps {
  manifestos: ManifestoDeCanal[];
  capacidades: CapacidadesDoOperador | null;
  trava?: EstadoDaTrava | null;
  /**
   * A leitura do vocabulário chegou? Enquanto não, esta tela não desenha os
   * seis canais por conta própria — seria a segunda cópia que o hook existe
   * para não ter.
   */
  lido?: boolean;
  canal?: string | null;
  aoMudarCanal?: (canal: string) => void;
  className?: string;
}

export const EstudioMulticanal: React.FC<EstudioMulticanalProps> = ({
  manifestos,
  capacidades,
  trava = null,
  lido = true,
  canal,
  aoMudarCanal,
  className,
}) => {
  const bancada = React.useMemo(
    () => apresentarBancada(manifestos, { capacidades, trava }),
    [manifestos, capacidades, trava],
  );
  const padrao = bancada.find((c) => c.cta.tipo === 'cockpit')?.canal ?? bancada[0]?.canal ?? null;
  const aberto = (canal as Canal | null) ?? padrao;
  const atual = bancada.find((c) => c.canal === aberto) ?? null;
  const emLaboratorio = capacidades?.lab_mode ?? false;
  const manifestoAtual = manifestos.find((m) => m.plataforma === 'GOOGLE_ADS' && m.canal === aberto) ?? null;

  if (!lido) {
    return (
      <section className={cn('max-w-[70ch]', className)} aria-label="estúdio de criação">
        <p className="kicker">criar campanha</p>
        <p className="mt-2 text-pretty text-[13px] leading-relaxed text-muted-foreground" role="status">
          Ainda não sei quais canais este servidor opera. Isto não é o mesmo que
          não haver canal nenhum — é a leitura do vocabulário que não chegou.
        </p>
      </section>
    );
  }

  return (
    <section className={cn(className)} aria-labelledby="estudio-titulo">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-[74ch]">
          <p className="kicker">criar campanha</p>
          <h2
            id="estudio-titulo"
            className="mt-1 text-balance font-display text-lg font-semibold tracking-tight md:text-xl"
          >
            Escolha o canal e veja somente o que ele exige
          </h2>
          <p className="mt-1.5 text-pretty text-[13px] leading-relaxed text-muted-foreground">
            A jornada muda com o canal. Onde existe formulário correspondente,
            esta bancada abre o cockpit real. Onde há somente uma porta HTTP,
            observação ou planejamento, a tela diz isso antes de qualquer ação.
          </p>
        </div>
      </div>

      <div
        role="group"
        aria-label="canal do estúdio"
        className="mt-5 flex flex-wrap gap-2"
      >
        {bancada.map((c) => {
          const ativo = c.canal === aberto;
          return (
            <button
              key={c.canal}
              type="button"
              aria-pressed={ativo}
              onClick={() => aoMudarCanal?.(c.canal)}
              className={cn(
                'inline-flex min-h-11 items-center gap-2 rounded-md border px-3 text-[13px]',
                'transition-colors duration-150 ease-out',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
                'active:scale-[0.96] motion-reduce:active:scale-100 motion-reduce:transition-none',
                ativo
                  ? 'border-primary/40 bg-primary text-primary-foreground shadow-sm'
                  : 'border-border bg-card text-foreground hover:border-foreground/25 hover:bg-muted/60',
              )}
            >
              <span className="font-medium">{c.rotulo}</span>
              <span
                className={cn(
                  'text-[11px] leading-none',
                  ativo ? 'text-primary-foreground/80' : 'text-muted-foreground',
                )}
              >
                {PALAVRA_DO_PAPEL[c.papel]}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-6">
        {atual ? (
          <WorkspaceDoCanal
            apresentacao={atual}
            manifesto={manifestoAtual}
            emLaboratorio={emLaboratorio}
          />
        ) : (
          <p className="text-[13px] text-muted-foreground" role="status">
            Este canal não está no vocabulário deste servidor.
          </p>
        )}
      </div>
    </section>
  );
};

const WorkspaceDoCanal: React.FC<{
  apresentacao: ApresentacaoDoCanal;
  manifesto: ManifestoDeCanal | null;
  emLaboratorio: boolean;
}> = ({ apresentacao, manifesto, emLaboratorio }) => {
  const avancadas = apresentacao.etapas.filter((e) => e.avancada);
  const principais = apresentacao.etapas.filter((e) => !e.avancada);

  return (
    <article className="overflow-hidden rounded-lg border border-border bg-card shadow-[var(--shadow-card)]">
      <header className="border-b border-border bg-muted/40 px-4 py-4 md:px-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h3
            id={`jornada-${apresentacao.canal}`}
            className="text-balance font-display text-base font-semibold tracking-tight"
          >
            {apresentacao.rotulo}
          </h3>
          <Chip
            glifo={GLIFO_DO_PAPEL[apresentacao.papel]}
            palavra={PALAVRA_DO_PAPEL[apresentacao.papel]}
            descricao={DESCRICAO_DO_PAPEL[apresentacao.papel]}
            tom={TOM_DO_PAPEL[apresentacao.papel]}
          />
        </div>
        <p className="mt-2 max-w-[70ch] text-pretty text-[13px] leading-relaxed text-foreground">
          {apresentacao.frase}
        </p>
      </header>

      <div className="px-4 py-4 md:px-5">
        <AcaoDoCanal apresentacao={apresentacao} />

        {apresentacao.recusa && apresentacao.cta.tipo !== 'cockpit' && (
          <p className="mt-4 max-w-[70ch] text-pretty text-[13px] leading-relaxed">
            {apresentacao.recusa}
          </p>
        )}

        {apresentacao.alternativas.length > 0 && (
          <div className="mt-4">
            <p className="font-display text-[12px] font-semibold">Rotas programáticas de vídeo</p>
            <ul className="mt-1.5 space-y-1.5 text-[13px] leading-relaxed text-muted-foreground" role="list">
              {apresentacao.alternativas.map((alt) => (
                <li key={alt.canal}>
                  <span className="font-medium text-foreground">{alt.rotulo}</span>
                  {' — '}
                  {alt.porque}
                </li>
              ))}
            </ul>
          </div>
        )}

        <ol className="mt-5 border-t border-border" role="list">
          {principais.map((e, i) => (
            <li key={e.chave} className="flex items-start gap-3 border-b border-border px-1 py-3">
              <span className="tabular mt-0.5 w-4 shrink-0 text-[11px] text-muted-foreground">
                {i + 1}
              </span>
              <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block font-display text-[13px] font-medium">{e.titulo}</span>
                <span className="mt-0.5 block text-pretty text-[12px] leading-relaxed text-muted-foreground">
                  {e.pergunta}
                </span>
                {e.detalhes && e.detalhes.length > 0 && (
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[12px] leading-snug text-muted-foreground">
                    {e.detalhes.map((d) => (
                      <li key={d}>{d}</li>
                    ))}
                  </ul>
                )}
              </span>
            </li>
          ))}
        </ol>

        {avancadas.length > 0 && (
          <details className="mt-4 rounded-md border border-border bg-muted/30 px-3 py-2">
            <summary className="cursor-pointer font-display text-[12px] font-semibold">
              Requisitos avançados ({avancadas.length})
            </summary>
            <ul className="mt-2 space-y-2 text-[12px] leading-relaxed" role="list">
              {avancadas.map((e) => (
                <li key={e.chave}>
                  <span className="font-medium">{e.titulo}</span>
                  <span className="mt-0.5 block text-muted-foreground">{e.pergunta}</span>
                </li>
              ))}
            </ul>
          </details>
        )}

        {apresentacao.provas.length > 0 && apresentacao.etapasComoFormulario && (
          <div className="mt-5 rounded-md border border-border bg-muted/40 p-3">
            <p className="font-display text-[12px] font-semibold">Provas exigidas nesta porta</p>
            <ul className="mt-1.5 space-y-1 text-[12px] leading-relaxed" role="list">
              {apresentacao.provas.map((p) => (
                <li key={p} className="flex gap-1.5">
                  <span aria-hidden className="text-muted-foreground">
                    ·
                  </span>
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {apresentacao.limites.length > 0 && (
          <div className="mt-5">
            <p className="font-display text-[12px] font-semibold">O que esta primeira fatia NÃO monta</p>
            <ul className="mt-1.5 space-y-1.5 text-[12px] leading-relaxed text-muted-foreground" role="list">
              {apresentacao.limites.map((frase) => (
                <li key={frase} className="flex gap-1.5">
                  <span aria-hidden>·</span>
                  <span>{frase}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {apresentacao.cta.tipo !== 'cockpit' && !(manifesto?.sabe_provar ?? manifesto?.sabe_criar) && (
          <p className="mt-4 max-w-[70ch] text-pretty text-[12px] leading-relaxed text-muted-foreground">
            Construir o que falta é engenharia nova — grafo, validação e
            taxonomia próprias —, não uma tela que falta. Campanhas deste canal
            continuam no inventário, porque escondê-las mentiria sobre o que
            está gastando.
          </p>
        )}
      </div>

      {emLaboratorio && manifesto && !(manifesto.sabe_provar ?? manifesto.sabe_criar) && (
        <MolduraDePrototipo
          className="m-4 mt-0"
          fonte={`a árvore que ${apresentacao.rotulo} declara, sem dado de conta nenhuma`}
          aindaNao={
            manifesto.indisponibilidades[0] ??
            `não há construtor de campanha para ${apresentacao.rotulo}.`
          }
        >
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            Se este canal ganhasse construtor, a jornada montaria esta árvore.
            Os degraus são os que o servidor declara para {apresentacao.rotulo} —
            não os do Search.
          </p>
          <ol className="mt-3 border-t border-info/25" role="list">
            {manifesto.hierarquia.map((no, i) => (
              <li
                key={no}
                className="flex items-start gap-3 border-b border-info/25 px-1 py-2.5 last:border-b-0"
              >
                <span className="tabular mt-0.5 w-4 shrink-0 text-[11px] text-muted-foreground">
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1 font-display text-[13px] font-medium">
                  {rotuloDoNo(no as NoDaEstrutura)}
                </span>
              </li>
            ))}
          </ol>
        </MolduraDePrototipo>
      )}
    </article>
  );
};

/**
 * A ação dominante deste canal — botão primário, ou a frase do desbloqueio.
 *
 * Um canal planejado nunca ganha botão cinza mudo. A recusa ensina; o
 * desbloqueio diz o que falta. Vídeo observa. Search abre o cockpit.
 */
const AcaoDoCanal: React.FC<{ apresentacao: ApresentacaoDoCanal }> = ({ apresentacao }) => {
  const { cta, intersecao } = apresentacao;

  if (cta.tipo === 'cockpit' && cta.destino) {
    return (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button asChild className="min-h-11 px-5 font-semibold shadow-sm">
          <Link to={cta.destino}>{cta.rotulo}</Link>
        </Button>
        <p className="max-w-[52ch] text-pretty text-[12px] leading-snug text-muted-foreground">
          {intersecao.escritaLiberada
            ? 'Abre o cockpit real a partir de um funil publicado. A campanha nasce pausada; ligá-la é outra decisão.'
            : cta.porque ??
              'Abre o cockpit real. A escrita na conta só sai se a permissão e a trava estiverem abertas.'}
        </p>
      </div>
    );
  }

  if (cta.tipo === 'observar' && cta.destino) {
    return (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button asChild variant="outline" className="min-h-11 px-5 font-semibold">
          <Link to={cta.destino}>{cta.rotulo}</Link>
        </Button>
        <p className="max-w-[52ch] text-pretty text-[12px] leading-snug text-muted-foreground">
          Lê as campanhas Video que já existem. Não cria campanha Video pela API.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border bg-muted/50 px-3 py-3">
      <p className="font-display text-[13px] font-semibold">{cta.rotulo}</p>
      <p className="mt-1 max-w-[70ch] text-pretty text-[13px] leading-relaxed text-muted-foreground">
        {cta.porque}
      </p>
    </div>
  );
};

export default EstudioMulticanal;
