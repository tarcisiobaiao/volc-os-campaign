/**
 * `/criativos` — a entrada operacional do Estúdio.
 *
 * ## O que esta tela é, e o que ela recusa ser
 *
 * SPEC §7: "retomar trabalho e identificar bloqueios, não exibir métricas
 * decorativas". Então não há faixa de números grandes no topo, não há gráfico e
 * não há total que ninguém pediu. O que há são quatro perguntas com resposta
 * acionável: o que está rodando, o que espera decisão minha, o que falhou e
 * precisa de escolha, e o que acabou de ser aprovado.
 *
 * ## Vazio honesto
 *
 * Quando uma lista não tem nada, ela DIZ o que vai aparecer ali. Não mostra
 * zero grande, não mostra ilustração, não inventa métrica. Zero exibido antes
 * de a leitura chegar seria uma afirmação feita sem resposta do servidor, e é
 * por isso que o esqueleto existe.
 */
import React from 'react';
import {
  Boxes,
  FlaskConical,
  Palette,
  Plus,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { CabecalhoDoEstudio, Corpo, Secao } from '@/components/criativos/comum/Painel';
import {
  Carregando,
  ErroDeLeitura,
  Indisponivel,
  Vazio,
} from '@/components/criativos/comum/Estados';
import { LinhaDeAtivo, LinhaDeJob } from '@/components/criativos/home/Linhas';
import { SeletorDeCriacao } from '@/components/criativos/home/SeletorDeCriacao';
import { useCriativosResumo } from '@/hooks/useCriativosResumo';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';
import { ROTULO_DO_JOB, type EstadoDoJob } from '@/types/criativos';
import { contagemLegivel } from '@/components/criativos/comum/formato';

const ORDEM_DOS_ESTADOS: EstadoDoJob[] = [
  'running',
  'queued',
  'partial',
  'failed',
  'succeeded',
  'cancelled',
  'draft',
];

export interface PropsDaHome {
  /** `/criativos/novo` entra por aqui: a escolha já aparece aberta. */
  abrirSeletor?: boolean;
}

const EstudioHomePage: React.FC<PropsDaHome> = ({ abrirSeletor = false }) => {
  const [seletorAberto, setSeletorAberto] = React.useState(abrirSeletor);
  const seletorRef = React.useRef<HTMLDivElement>(null);
  const consulta = useCriativosResumo();
  const resumo = consulta.data;

  React.useEffect(() => {
    if (abrirSeletor) setSeletorAberto(true);
  }, [abrirSeletor]);

  const abrir = () => {
    setSeletorAberto(true);
    // O foco vai para a escolha: quem navega por teclado não deve ter que
    // procurar onde a tela mudou depois de acionar a ação primária.
    window.requestAnimationFrame(() => {
      seletorRef.current?.querySelector<HTMLElement>('a')?.focus();
    });
  };

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Produção"
        titulo="Estúdio Criativo"
        proposito="Onde as peças são produzidas, revisadas e aprovadas antes de virarem anúncio ou publicação. Cada trabalho guarda motor, custo e procedência."
        acao={
          <Button onClick={abrir} aria-expanded={seletorAberto} aria-controls="escolha-do-estudio">
            <Plus className="h-4 w-4" aria-hidden />
            Criar
          </Button>
        }
      />

      <Corpo className="space-y-6">
        {seletorAberto && (
          <div ref={seletorRef}>
            <SeletorDeCriacao
              id="escolha-do-estudio"
              videoDisponivel={resumo ? resumo.videoDisponivel : null}
            />
          </div>
        )}

        {resumo?.motorConfigurado === false && (
          <Indisponivel
            titulo="O servidor está sem credencial de provedor"
            motivo="Enquanto isso durar, pedir peça nova falha na hora. Você continua podendo abrir o briefing, ler a biblioteca, revisar e aprovar o que já existe."
          />
        )}

        {consulta.isError && (
          <ErroDeLeitura
            mensagem={mensagemDaFalha(consulta.error)}
            codigo={codigoDaFalha(consulta.error)}
            ressalva="Nada nesta página foi lido nesta tentativa. O que você vê abaixo pode não existir."
            aoTentarDeNovo={() => void consulta.refetch()}
          />
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-6">
            <Secao
              titulo="Em andamento"
              descricao="Trabalhos que o motor ainda está produzindo. Você pode sair desta tela."
            >
              {consulta.isLoading ? (
                <Carregando rotulo="Lendo os trabalhos em andamento" linhas={2} />
              ) : resumo?.emAndamento.length ? (
                <div className="-mx-3 -my-3">
                  {resumo.emAndamento.map((job) => (
                    <LinhaDeJob key={job.id} job={job} />
                  ))}
                </div>
              ) : (
                <Vazio
                  titulo="Nenhum trabalho em produção agora"
                  explicacao="Quando você pedir uma peça, ela aparece aqui com a etapa real do motor e o custo apurado até o momento."
                  acao={
                    <div className="flex flex-wrap justify-center gap-2">
                      <Button asChild variant="outline" size="sm">
                        <Link to="/criativos/imagens/novo">Criar imagem</Link>
                      </Button>
                      <Button asChild variant="outline" size="sm">
                        <Link to="/criativos/videos/novo">Criar vídeo</Link>
                      </Button>
                    </div>
                  }
                />
              )}
            </Secao>

            <Secao
              titulo="Falhas que pedem decisão"
              descricao="Trabalhos que pararam. Cada um mostra o motivo já sanitizado e o que é seguro fazer."
            >
              {consulta.isLoading ? (
                <Carregando rotulo="Lendo as falhas" linhas={1} />
              ) : resumo?.falhas.length ? (
                <div className="-mx-3 -my-3">
                  {resumo.falhas.map((job) => (
                    <LinhaDeJob key={job.id} job={job} />
                  ))}
                </div>
              ) : (
                <Vazio
                  titulo="Nenhuma falha aguardando decisão"
                  explicacao="Trabalhos que falharam por inteiro, ou que ficaram com peça faltando, aparecem aqui até alguém decidir repetir ou descartar."
                />
              )}
            </Secao>

            <Secao
              titulo="Aguardando sua revisão"
              descricao="Peças prontas sem decisão registrada. Prontas não é o mesmo que autorizadas."
              acao={
                <Button asChild variant="outline" size="sm">
                  <Link to="/criativos/aprovacoes">Abrir a fila</Link>
                </Button>
              }
            >
              {consulta.isLoading ? (
                <Carregando rotulo="Lendo o que aguarda revisão" linhas={2} />
              ) : resumo?.aguardandoRevisao.length ? (
                <div className="-mx-3 -my-3">
                  {resumo.aguardandoRevisao.map((asset) => (
                    <LinhaDeAtivo key={asset.id} asset={asset} />
                  ))}
                </div>
              ) : (
                <Vazio
                  titulo="Nada aguardando revisão"
                  explicacao="Toda peça produzida chega aqui sem decisão. Ela sai desta lista quando alguém aprova, pede ajuste ou rejeita."
                />
              )}
            </Secao>

            <Secao
              titulo="Aprovados recentemente"
              descricao="Decisões positivas registradas, com ator e instante guardados pelo servidor."
            >
              {consulta.isLoading ? (
                <Carregando rotulo="Lendo os aprovados recentes" linhas={1} />
              ) : resumo?.aprovadosRecentes.length ? (
                <div className="-mx-3 -my-3">
                  {resumo.aprovadosRecentes.map((asset) => (
                    <LinhaDeAtivo key={asset.id} asset={asset} />
                  ))}
                </div>
              ) : (
                <Vazio
                  titulo="Nenhuma aprovação registrada ainda"
                  explicacao="Quando uma peça for aprovada, ela aparece aqui com a finalidade declarada e a versão que recebeu a decisão."
                />
              )}
            </Secao>
          </div>

          <div className="min-w-0 space-y-6">
            <Secao
              titulo="Trabalhos por estado"
              descricao="Contagem lida do servidor. Estado sem trabalho aparece como zero medido, não como ausência."
            >
              {consulta.isLoading ? (
                <Carregando rotulo="Lendo a contagem por estado" linhas={3} altura="h-8" />
              ) : resumo ? (
                <dl className="space-y-2">
                  {ORDEM_DOS_ESTADOS.map((estado) => (
                    <div
                      key={estado}
                      className="flex items-baseline justify-between gap-3 border-b border-border/60 pb-2 last:border-b-0 last:pb-0"
                    >
                      <dt className="min-w-0">
                        <span className="block text-[13px] font-medium text-foreground">
                          {ROTULO_DO_JOB[estado].palavra}
                        </span>
                        <span className="block text-[12px] leading-snug text-muted-foreground">
                          {ROTULO_DO_JOB[estado].descricao}
                        </span>
                      </dt>
                      <dd className="shrink-0 font-display text-sm font-semibold tabular-nums text-foreground">
                        {contagemLegivel(resumo.contagemPorEstado[estado])}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  A contagem não foi lida nesta tentativa.
                </p>
              )}
            </Secao>

            <Secao titulo="Patrimônio" descricao="Onde o que já foi produzido fica guardado.">
              <div className="space-y-2">
                <Link
                  to="/criativos/biblioteca"
                  className="flex min-h-11 items-center gap-3 rounded-md border border-border px-3 py-2 transition-colors duration-150 ease-out hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  <Boxes className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium text-foreground">Biblioteca</span>
                    <span className="block text-[12px] text-muted-foreground">
                      {consulta.isLoading
                        ? 'contagem ainda não lida'
                        : resumo
                          ? `${resumo.totalAssets} ${resumo.totalAssets === 1 ? 'ativo guardado' : 'ativos guardados'}`
                          : 'contagem não lida nesta tentativa'}
                    </span>
                  </span>
                </Link>
                {/* O Laboratório trata a RECEITA, não a peça. Por isso ele fica
                    em "Patrimônio", ao lado da biblioteca, e não no seletor de
                    criação, que é onde se pede uma peça avulsa. */}
                <Link
                  to="/criativos/laboratorio"
                  className="flex min-h-11 items-center gap-3 rounded-md border border-border px-3 py-2 transition-colors duration-150 ease-out hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  <FlaskConical className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium text-foreground">
                      Laboratório de Templates
                    </span>
                    <span className="block text-[12px] text-muted-foreground">
                      receitas reutilizáveis, conferidas antes de gastar
                    </span>
                  </span>
                </Link>
                <Link
                  to="/criativos/brand-packs"
                  className="flex min-h-11 items-center gap-3 rounded-md border border-border px-3 py-2 transition-colors duration-150 ease-out hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  <Palette className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium text-foreground">
                      Brand packs
                    </span>
                    <span className="block text-[12px] text-muted-foreground">
                      {consulta.isLoading
                        ? 'contagem ainda não lida'
                        : resumo
                          ? `${resumo.brandPacks} ${resumo.brandPacks === 1 ? 'pack cadastrado' : 'packs cadastrados'}`
                          : 'contagem não lida nesta tentativa'}
                    </span>
                  </span>
                </Link>
              </div>
            </Secao>
          </div>
        </div>
      </Corpo>
    </Layout>
  );
};

export default EstudioHomePage;
