/**
 * Um item da fila de atenção: o que é, onde está, desde quando, e o que fazer.
 *
 * ## Por que a evidência abre inline, e não num modal
 *
 * Um modal tira o item da lista para mostrar o item. Quem está triando cinco
 * campanhas perde a posição a cada abertura e precisa reencontrar onde estava.
 * A expansão acontece no lugar, com `aria-expanded`, e o resto da fila continua
 * visível atrás dela.
 *
 * ## Por que a linha fechada já decide
 *
 * A linha fechada carrega campanha, conta, sintoma, idade, uma linha de
 * evidência e a próxima ação segura — o suficiente para o operador saber se
 * este item é o dele. A expansão traz o resto da prova para quem vai agir.
 * Uma fila que obriga a abrir tudo para saber o que é não é fila: é uma pilha.
 *
 * ## O item indicado pela notificação chega ABERTO
 *
 * Quem clicou no sino já disse qual item quer ver. Fazê-lo clicar de novo para
 * revelar o que ele veio ver seria cobrar duas vezes pela mesma decisão.
 */
import React from 'react';
import { ArrowUpRight, ChevronRight } from 'lucide-react';

import { cn } from '@/lib/utils';

import { descricaoDoSintoma, type ItemDeAtencao as Item } from './projecao';
import { visualDoSintoma } from './visual';

export interface PropsDoItem {
  item: Item;
  /** Este item foi apontado pela notificação: chega aberto e destacado. */
  indicado?: boolean;
  /** Detalhe extra, quando a origem tem prova própria a mostrar. */
  children?: React.ReactNode;
}

export const ItemDeAtencao: React.FC<PropsDoItem> = ({ item, indicado = false, children }) => {
  const descricao = descricaoDoSintoma(item.sintoma);
  const { glifo: Glifo, tom } = visualDoSintoma(item.sintoma);

  // O item indicado nasce aberto; os outros nascem fechados e o operador
  // decide. `useState` com valor inicial e não efeito: abrir num segundo passo
  // faria a lista pular depois de já estar na tela.
  const [aberto, setAberto] = React.useState(indicado);

  // ⚠️ Valor inicial não basta: o operador pode clicar num SEGUNDO alerta do
  // sino sem sair da aba, e aí este componente já existe — o estado inicial já
  // passou. Sem isto, o item novo continuaria fechado, o alvo do foco não
  // existiria no DOM e a vinda do sino terminaria em lugar nenhum.
  //
  // Ajuste durante o render (e não em efeito) de propósito: o efeito que move o
  // foco roda depois da pintura, e precisa encontrar o detalhe já montado.
  const indicadoAntes = React.useRef(indicado);
  if (indicadoAntes.current !== indicado) {
    indicadoAntes.current = indicado;
    // Só ABRE. Deixar de ser o item indicado não fecha o que o operador estava
    // lendo: fechar debaixo da mão de quem está lendo é pior que deixar aberto.
    if (indicado && !aberto) setAberto(true);
  }
  const detalhe = `alerta-${item.chave}`;
  const titulo = `atencao-titulo-${item.chave}`;

  // Sujeito da frase: a campanha quando o fato é dela, a conta quando o fato é
  // da leitura da conta inteira. Nomear a conta como se fosse campanha faria a
  // fila afirmar coisa que não foi observada.
  const sujeito = item.campanha ?? item.conta;

  return (
    <li
      className={cn(
        'border-b border-border last:border-b-0',
        indicado && 'bg-primary/[0.06] ring-1 ring-inset ring-primary/40',
      )}
    >
      <div className="flex items-start gap-2 px-3 py-3">
        <button
          type="button"
          aria-expanded={aberto}
          aria-controls={detalhe}
          onClick={() => setAberto((antes) => !antes)}
          title={`${descricao.titulo} — ${descricao.afirma}`}
          className={cn(
            'group -m-1 flex min-h-11 flex-1 items-start gap-2.5 rounded-md p-1 text-left',
            'transition-colors hover:bg-muted/50',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
          )}
        >
          <ChevronRight
            className={cn(
              'mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200',
              'motion-reduce:transition-none',
              aberto && 'rotate-90',
            )}
            aria-hidden
          />
          <span className="min-w-0 flex-1">
            {/* ⚠️ O glifo do sintoma aparece, a PALAVRA não se repete.
                Quem nomeia a condição é o cabeçalho do grupo, uma vez para as
                doze linhas que estão nele — repetir o mesmo rótulo em cada
                linha é o ruído que faz o olho parar de ler o rótulo. A palavra
                continua no nome acessível de cada item, para quem ouve a linha
                fora do contexto do cabeçalho, e no `title` para quem passa o
                ponteiro. */}
            <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <Glifo
                className={cn(
                  'h-3.5 w-3.5 shrink-0 translate-y-0.5',
                  tom === 'ruim'
                    ? 'text-destructive'
                    : tom === 'neutro'
                      ? 'text-muted-foreground'
                      : 'text-warning',
                )}
                aria-hidden
              />
              <span id={titulo} className="text-[13px] font-medium leading-snug">
                {sujeito}
              </span>
              {/* Fora do elemento que rotula o detalhe: ele é o NOME curto da
                  região expandida, e engolir a explicação inteira ali faria o
                  leitor de tela recitar o parágrafo antes de cada leitura. */}
              <span className="sr-only">{descricao.titulo}. {descricao.afirma}</span>
            </span>
            <span className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
              {item.campanha && (
                <>
                  <span className="tabular">{item.conta}</span>
                  <span aria-hidden>·</span>
                </>
              )}
              <span>{item.desdeQuando}</span>
              {item.evidencia[0] && (
                <>
                  <span aria-hidden>·</span>
                  <span>{item.evidencia[0]}</span>
                </>
              )}
            </span>
            {/* A próxima ação fica na linha fechada de propósito: é a única
                frase que responde "e agora?", e escondê-la atrás de um clique
                transformaria a fila numa lista de problemas sem saída. */}
            <span className="mt-1.5 block max-w-[74ch] text-[12px] leading-snug">
              <span className="kicker text-muted-foreground">próxima ação segura</span>{' '}
              <span className="text-foreground">{descricao.proximaAcao}</span>
            </span>
          </span>
        </button>

        {item.urlExterna && (
          <a
            href={item.urlExterna}
            target="_blank"
            rel="noreferrer"
            className={cn(
              'inline-flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 text-[11px] font-medium',
              'text-primary hover:underline',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            )}
          >
            abrir no Google Ads
            <ArrowUpRight className="h-3 w-3" aria-hidden />
          </a>
        )}
      </div>

      {aberto && (
        <div
          id={detalhe}
          // Alvo do foco quando a notificação aponta para cá. `tabIndex={-1}`
          // porque ele recebe foco por programa, não por Tab: uma parada de
          // teclado a mais por item encareceria a navegação de quem só quer
          // chegar ao fim da lista.
          tabIndex={-1}
          aria-labelledby={titulo}
          className="scroll-mt-6 px-3 pb-4 pl-[2.1rem] focus-visible:outline-none"
        >
          {indicado && (
            <p className="sr-only">Este é o item indicado pela notificação.</p>
          )}
          {children ?? (
            <dl className="max-w-[76ch] space-y-1.5 border-l-2 border-border pl-3 text-[12px] leading-snug">
              <dt className="kicker text-muted-foreground">o que foi observado</dt>
              <dd className="text-muted-foreground">{descricao.afirma}</dd>
              <dt className="kicker pt-1.5 text-muted-foreground">evidência</dt>
              <dd>
                <ul className="space-y-0.5 text-muted-foreground">
                  {item.evidencia.map((linha, i) => (
                    <li key={`${item.chave}-ev-${i}`}>{linha}</li>
                  ))}
                </ul>
              </dd>
            </dl>
          )}
        </div>
      )}
    </li>
  );
};

export default ItemDeAtencao;
