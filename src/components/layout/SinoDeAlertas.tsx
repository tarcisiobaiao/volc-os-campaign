/**
 * O sino — a projeção global do que pede atenção agora.
 *
 * A central fica visível mesmo vazia porque esconder o sino torna impossível
 * distinguir “está tudo bem” de “a funcionalidade não existe”. E ela não varre
 * nada por conta própria: bebe da MESMA projeção da aba Atenção
 * (`atencao/useAtencao`), para que as duas superfícies não possam discordar
 * sobre o mesmo fato.
 *
 * ## ⚠️ OS CINCO ESTADOS SÃO CINCO, E NENHUM DELES É O OUTRO
 *
 *  1. **nenhuma condição ativa** — perguntei, e não há nada.
 *  2. **condições ativas** — perguntei, e há N.
 *  3. **atualização em andamento** — estou perguntando agora.
 *  4. **consulta indisponível** — não consegui perguntar.
 *  5. **último estado conhecido preservado** — perguntei de novo e falhou; o
 *     que está aqui é de antes, e está dito que é de antes.
 *
 * O erro que este arquivo existe para impedir é achatar 1 e 4. "Não consegui
 * perguntar" e "perguntei e há três problemas" levam a ações opostas, e uma
 * falha de consulta transformada em contador manda o operador procurar um
 * problema que ninguém observou — ou, pior, o silêncio de uma falha lida como
 * "tudo bem" faz ele não procurar o problema que existe.
 *
 * ## Por que "verificando" não entra no nome acessível quando já há dado
 *
 * A releitura acontece sozinha, no intervalo e ao voltar o foco para a aba.
 * Trocar o nome de um botão enquanto alguém está com o foco nele faz o controle
 * mudar de identidade debaixo da mão, e isso aconteceria a cada poucos minutos
 * sem que o operador tivesse pedido nada. O andamento aparece no glifo (visual)
 * e numa região viva DENTRO da central, que é onde ele é acionável. Na PRIMEIRA
 * consulta, quando ainda não há contagem nenhuma para dizer, ele vai ao nome —
 * ali não há o que atropelar.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Bell,
  CheckCircle2,
  CircleHelp,
  RefreshCw,
  WifiOff,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { INTERVALO_NOTIFICACOES_MS } from '@/hooks/useNotificacoes';
import { CodigoDaOcorrencia } from '@/components/trafego/inventario/EstadosDoInventario';
import { visualDoSintoma } from '@/components/trafego/atencao/visual';
import { descricaoDoSintoma } from '@/components/trafego/atencao/projecao';
import {
  estadoDoSino,
  useAtencao,
  type EstadoDoSino,
} from '@/components/trafego/atencao/useAtencao';
import { cn } from '@/lib/utils';

/** Compatibilidade com a primeira versão e prova explícita do intervalo. */
export const INTERVALO_MS = INTERVALO_NOTIFICACOES_MS;

interface SinoDeAlertasProps {
  className?: string;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
}

/**
 * O rótulo acessível do gatilho — exportado para poder ser PROVADO.
 *
 * ⚠️ O corpo do popover já dizia "nada pede atenção no que foi lido" sob
 * `lista_incompleta`, e o `aria-label`/`title` do gatilho continuavam dizendo
 * "nenhuma condição ativa" — a afirmação total que o estado existe para não
 * fazer. Para quem navega por leitor de tela o rótulo do botão É a informação:
 * a ressalva no corpo só chega a quem abre o popover.
 *
 * A cascata é derivada de `estado`, e NÃO de `quantos`, para que um estado novo
 * não herde o ramo otimista por descuido. O `default` é a prova disso.
 */
export function rotuloDoSino(estado: EstadoDoSino, quantos: number): string {
  const contagem = quantos === 1 ? '1 condição ativa' : `${quantos} condições ativas`;
  switch (estado) {
    case 'fora_de_escopo':
      return 'Notificações Google ocultas enquanto você está em Meta Ads.';
    case 'indisponivel':
      return 'Notificações: não foi possível consultar. Abrir central.';
    case 'consultando':
      return 'Notificações: consultando a operação.';
    case 'ultimo_conhecido':
      return `Notificações: ${contagem} no último estado conhecido. Abrir central.`;
    case 'com_condicao':
      return `Notificações: ${contagem}. Abrir central.`;
    case 'lista_incompleta':
      return (
        'Notificações: nada pede atenção no que foi lido, e parte do registro ' +
        'não foi carregada. Abrir central.'
      );
    case 'sem_condicao':
      return 'Notificações: nenhuma condição ativa.';
    default:
      // Estado que esta versão não conhece nunca vira "nenhuma condição ativa".
      return 'Notificações: estado não reconhecido. Abrir central.';
  }
}

const SinoDeAlertas: React.FC<SinoDeAlertasProps> = ({
  className,
  side = 'right',
  align = 'start',
}) => {
  const [aberto, setAberto] = React.useState(false);
  const atencao = useAtencao();
  const quantos = atencao.itens.length;
  const estado = estadoDoSino({ ...atencao, quantos });

  // O contador só aparece quando é uma AFIRMAÇÃO. Sem consulta boa não há o que
  // contar, e um `0` ali diria "não há nada" sobre algo que não foi apurado.
  const contagemVale = estado === 'com_condicao' || estado === 'ultimo_conhecido';

  const rotulo = rotuloDoSino(estado, quantos);

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'relative inline-flex h-9 w-9 items-center justify-center rounded-md',
            'text-muted-foreground transition-colors duration-200',
            'hover:bg-muted/60 hover:text-foreground',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            aberto && 'bg-muted/70 text-foreground',
            className,
          )}
          aria-label={rotulo}
          title={rotulo}
        >
          {/* O glifo troca com o estado: sino para "perguntei", antena cortada
              para "não consegui perguntar". A forma distingue os dois antes de
              qualquer cor, e sobrevive a um print em preto e branco. */}
          {estado === 'indisponivel' ? (
            <WifiOff className="h-4 w-4 text-destructive" aria-hidden />
          ) : estado === 'fora_de_escopo' ? (
            <CircleHelp className="h-4 w-4 text-muted-foreground" aria-hidden />
          ) : (
            <Bell className="h-4 w-4" aria-hidden />
          )}

          {contagemVale && quantos > 0 && (
            <span
              className={cn(
                'absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center',
                'rounded-full px-1 text-[10px] font-bold leading-none',
                // O último estado conhecido é contagem VELHA: ela continua
                // visível e fica em tinta neutra, para não se passar por
                // apuração de agora.
                estado === 'ultimo_conhecido'
                  ? 'border border-border bg-muted text-foreground'
                  // `warning-foreground` e não uma cor cravada: o token já
                  // acompanha o tema, e um `slate-950` fixo aqui pareceria
                  // certo no claro e sumiria de vista no escuro.
                  : 'bg-warning text-warning-foreground',
              )}
              aria-hidden
            >
              {quantos > 9 ? '9+' : quantos}
            </span>
          )}

          {/* Andamento: visual, e só visual, quando já há contagem na tela. */}
          {atencao.atualizando && estado !== 'indisponivel' && (
            <RefreshCw
              className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 animate-spin text-muted-foreground motion-reduce:animate-none"
              aria-hidden
            />
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent
        side={side}
        align={align}
        sideOffset={8}
        className="w-[min(26rem,calc(100vw-2rem))] overflow-hidden rounded-md p-0"
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold">Atenção</h2>
            <p className="text-[11px] text-muted-foreground">
              {estado === 'fora_de_escopo'
                ? 'central Google fora desta rede'
                : estado === 'indisponivel'
                ? 'não foi possível consultar'
                : estado === 'consultando'
                  ? 'consultando a operação'
                  : quantos > 0
                    ? `${quantos} ${quantos === 1 ? 'condição ativa' : 'condições ativas'}${
                        estado === 'ultimo_conhecido' ? ' no último estado conhecido' : ''
                      }`
                    : 'nenhuma condição ativa'}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9"
            onClick={atencao.conferirDeNovo}
            disabled={atencao.atualizando}
            aria-label="Conferir de novo"
            title="Conferir de novo"
          >
            <RefreshCw
              className={cn(
                'h-3.5 w-3.5',
                atencao.atualizando && 'animate-spin motion-reduce:animate-none',
              )}
              aria-hidden
            />
          </Button>
        </div>

        {/* Região viva onde o andamento é dito sem trocar o nome de um botão. */}
        <p role="status" className="sr-only">
          {atencao.atualizando ? 'Conferindo a operação.' : ''}
        </p>

        <div className="max-h-[min(26rem,60vh)] overflow-y-auto">
          {estado === 'consultando' && <Carregando />}

          {estado === 'fora_de_escopo' && (
            <div className="px-4 py-5" role="status">
              <CircleHelp className="mb-3 h-5 w-5 text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">Você está operando Meta Ads</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Esta central acompanha condições do Google Ads e fica neutra nesta rede.
                Isso não indica que o VOLC O.S. esteja offline.
              </p>
            </div>
          )}

          {estado === 'indisponivel' && (
            <div className="px-4 py-5" role="alert">
              <WifiOff className="mb-3 h-5 w-5 text-destructive" aria-hidden />
              <p className="text-sm font-medium">Não foi possível verificar a operação</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {atencao.ocorrencia?.proximoPasso ??
                  'Tente de novo em alguns minutos. Enquanto isso, não decida gasto por esta tela: o que está nas contas de anúncio continua como estava.'}
              </p>
              {/* ⚠️ Esta frase separa o estado 4 do estado 1. Sem ela, uma
                  central silenciosa por falha é lida como central silenciosa
                  por calmaria — e as duas pedem coisas opostas. */}
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                Isto não quer dizer que está tudo bem: quer dizer que não deu para perguntar.
              </p>
              {atencao.ocorrencia && <CodigoDaOcorrencia ocorrencia={atencao.ocorrencia} />}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4 h-9 text-xs"
                onClick={atencao.conferirDeNovo}
                disabled={atencao.atualizando}
              >
                tentar novamente
              </Button>
            </div>
          )}

          {estado === 'ultimo_conhecido' && (
            <p
              className="border-b border-border bg-warning/[0.08] px-4 py-2.5 text-[11px] leading-relaxed text-muted-foreground"
              role="status"
            >
              A atualização falhou. O último estado conhecido continua visível — ele é de
              antes, não de agora.
            </p>
          )}

          {estado === 'lista_incompleta' && (
            <div className="px-4 py-7">
              <CircleHelp className="mb-3 h-5 w-5 text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">
                Nada pede atenção no que foi lido
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Parte do registro ainda não foi carregada nesta sessão, então
                este zero vale para o que foi conferido — não para a conta
                inteira.{' '}
                <strong className="font-medium text-foreground">
                  Isto não é o mesmo que "está tudo bem".
                </strong>
              </p>
            </div>
          )}

          {estado === 'sem_condicao' && (
            <div className="px-4 py-7">
              <CheckCircle2 className="mb-3 h-5 w-5 text-success" aria-hidden />
              <p className="text-sm font-medium">Nenhuma condição ativa</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {atencao.verificadas != null && atencao.verificadas > 0
                  ? `${atencao.verificadas} ${atencao.verificadas === 1 ? 'campanha ligada foi verificada' : 'campanhas ligadas foram verificadas'} e nada pede atenção agora.`
                  : 'Nada pede atenção entre o que foi lido.'}
              </p>
            </div>
          )}

          {quantos > 0 && estado !== 'indisponivel' && (
            <ul className="divide-y divide-border" aria-label="condições ativas">
              {atencao.itens.map((item) => {
                const descricao = descricaoDoSintoma(item.sintoma);
                const { glifo: Glifo, tom } = visualDoSintoma(item.sintoma);
                return (
                  <li key={item.chave}>
                    <Link
                      // Leva à aba Atenção com o item apontado. O sino mostra as
                      // condições; a lista com evidência e próxima ação mora lá.
                      // Ter as duas completas nas duas superfícies criaria duas
                      // verdades para manter em dia.
                      to={`/trafego?aba=atencao&foco=${item.chave}`}
                      onClick={() => setAberto(false)}
                      className={cn(
                        'group flex items-start gap-3 px-4 py-3',
                        'transition-colors duration-200 hover:bg-muted/50',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                      )}
                    >
                      <span
                        className={cn(
                          'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
                          tom === 'ruim' ? 'bg-destructive/10' : 'bg-warning/10',
                        )}
                      >
                        <Glifo
                          className={cn(
                            'h-3.5 w-3.5',
                            tom === 'ruim' ? 'text-destructive' : 'text-warning',
                          )}
                          aria-hidden
                        />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-medium">
                          {item.campanha ?? item.conta}
                        </span>
                        {/* Palavra do sintoma junto do nome: sem ela o sino
                            diria "há três coisas" sem dizer de que tipo, e três
                            tipos diferentes pedem três ações diferentes. */}
                        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">
                          {descricao.titulo} · {item.desdeQuando}
                        </span>
                        {item.campanha && (
                          <span className="mt-0.5 block truncate text-[10px] text-muted-foreground/80">
                            {item.conta}
                          </span>
                        )}
                      </span>
                      <ArrowRight
                        className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
                        aria-hidden
                      />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}

          {/* Indisponibilidade de leitura: informação, nunca condição ativa.
              Ela fica DEPOIS da lista e fora do contador de propósito. */}
          {estado !== 'indisponivel' &&
            (atencao.semLeitura.length > 0 || atencao.parcial) && (
              <div
                className="border-t border-border bg-muted/40 px-4 py-3 text-[11px] leading-relaxed text-muted-foreground"
                role="status"
              >
                {atencao.semLeitura.length > 0 && (
                  <p>
                    {atencao.semLeitura.length === 1
                      ? 'Uma conta não pôde ser verificada.'
                      : `${atencao.semLeitura.length} contas não puderam ser verificadas.`}{' '}
                    Sobre ela não há condição ativa nem ausência de condição: há ausência de
                    leitura.
                  </p>
                )}
                {atencao.parcial && atencao.motivos.length > 0 && (
                  <p className={cn(atencao.semLeitura.length > 0 && 'mt-1.5')}>
                    A lista pode estar incompleta: {atencao.motivos.join('; ')}.
                  </p>
                )}
              </div>
            )}
        </div>

        <div className="border-t border-border px-4 py-2.5">
          <Link
            to="/trafego?aba=atencao"
            onClick={() => setAberto(false)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
          >
            abrir a aba Atenção
            <ArrowRight className="h-3 w-3" aria-hidden />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
};

const Carregando: React.FC = () => (
  <div className="space-y-3 px-4 py-5" aria-label="Consultando a operação">
    <div className="flex gap-3">
      <Skeleton className="h-7 w-7 shrink-0 rounded-full motion-reduce:animate-none" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-3 w-3/4 motion-reduce:animate-none" />
        <Skeleton className="h-2.5 w-full motion-reduce:animate-none" />
        <Skeleton className="h-2.5 w-1/2 motion-reduce:animate-none" />
      </div>
    </div>
  </div>
);

export default SinoDeAlertas;
