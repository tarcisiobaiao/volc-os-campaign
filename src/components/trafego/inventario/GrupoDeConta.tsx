/**
 * Um grupo do inventário: uma conta e o que ela respondeu.
 *
 * ## Por que a conta é o agrupador, e não o projeto
 *
 * Porque é a conta que responde. Frescor, falha e escopo de leitura são
 * propriedades DELA — uma campanha não tem idade própria, ela herda a idade da
 * leitura que a trouxe. Agrupar por projeto misturaria numa mesma seção dados
 * lidos em momentos diferentes, e a idade sumiria no meio.
 *
 * ## Os três vazios que esta tela recusa achatar
 *
 *  · a conta respondeu e não há campanha nenhuma  → fato medido;
 *  · a conta nunca foi lida                        → não perguntamos;
 *  · a conta não respondeu                         → não sabemos.
 *
 * As três levam a ações opostas. "Vazio" para as três levaria à ação errada
 * duas vezes em três.
 */
import React from 'react';
import { ChevronDown, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ContaNoInventario } from '@/types/trafego';

import { SeloDeFrescor } from './Selos';
import {
  COLUNAS_AMPLAS,
  COLUNAS_MEDIAS,
  LinhaEmLista,
  LinhaEmTabela,
  TOPO_ABAIXO_DO_CABECALHO,
  type ContagemDeLinhagem,
  type HerancaDaConta,
} from './LinhaDeCampanha';
import { horaDeLeitura } from './formato';
import type { Densidade } from './densidade';

/** O grupo sintético do servidor para linhas sem conta utilizável. */
export const SEM_CONTA = 'conta-nao-identificada';

export interface PropsDoGrupo {
  conta: ContaNoInventario;
  densidade: Densidade;
  /** Obrigatória: sem ela a linha afirmaria uma contagem que ninguém contou. */
  linhagens: ContagemDeLinhagem;
  /** Pede leitura nova DESTA conta. Ausente quando o operador não pode pedir. */
  aoPedirLeitura?: (customerId: string) => void;
  pedindoLeitura?: boolean;
  /** Resposta do servidor ao pedido — inclusive a recusa, com o motivo. */
  recadoDaLeitura?: string | null;
  /** A conta é o primeiro nível da hierarquia; campanhas só aparecem ao abrir. */
  aberta?: boolean;
  aoAlternarConta?: () => void;
}

function tituloDaConta(conta: ContaNoInventario): string {
  if (conta.customer_id === SEM_CONTA) return 'Sem conta identificada';
  return conta.nome ?? `Conta ${conta.customer_id}`;
}

/**
 * O identificador da conta, mascarado — e por que ele é mascarado.
 *
 * Esta tela é conferida em reunião, projetada, e printada para relatório. O
 * identificador inteiro de uma conta de anúncio de cliente não precisa estar em
 * nenhuma dessas três situações para que o operador saiba de qual conta se
 * trata: o nome já diz isso, e os quatro últimos dígitos resolvem o caso em que
 * duas contas do mesmo cliente aparecem lado a lado. O identificador completo
 * continua a um clique, dentro da expansão da campanha, onde quem precisa
 * copiá-lo o encontra.
 *
 * O agrupamento em três blocos é o mesmo que o painel do Google mostra, para o
 * operador reconhecer o formato sem traduzir nada de cabeça.
 */
export function mascararConta(customerId: string): string {
  const digitos = customerId.replace(/\D/g, '');
  if (digitos.length < 4) return '•'.repeat(Math.max(customerId.length, 1));
  const finais = digitos.slice(-4);
  return digitos.length === 10 ? `•••-•••-${finais}` : `•••${finais}`;
}

/**
 * A frase do vazio depende do MOTIVO do vazio — nunca é "nenhum resultado".
 *
 * ⚠️ O `else` desta função afirma um fato medido ("a conta respondeu e não há
 * campanha nenhuma"), então ele não pode ser o destino de qualquer frescor que
 * sobre. Um estado de leitura que esta tela não conhece cairia ali e viraria
 * uma medição que nunca houve — o oposto exato do que o módulo promete. Por
 * isso os estados conhecidos são enumerados, e o desconhecido tem frase
 * própria.
 */
function frasesDoVazio(conta: ContaNoInventario): { titulo: string; explica: string } {
  switch (conta.frescor) {
    case 'nunca_lido':
      return {
        titulo: 'nunca lido',
        explica:
          'ainda não perguntamos nada a esta conta. Não sabemos se ela tem campanhas — ' +
          'e isso é diferente de saber que não tem.',
      };
    case 'falhou':
      return {
        titulo: 'sincronização falhou',
        explica:
          'a última tentativa de ler esta conta não deu certo e não há leitura boa anterior ' +
          'guardada. Não dá para afirmar presença nem ausência de campanha nenhuma.',
      };
    case 'parcial':
      return {
        titulo: 'leitura parcial e sem campanha nesta parte',
        explica:
          'parte do que esta conta tem não pôde ser lida, e o que voltou não trouxe campanha ' +
          'nenhuma. O vazio aqui é do que voltou, não da conta.',
      };
    case 'recente':
    case 'velho':
    case 'vazio_confirmado':
      return {
        titulo: 'nenhuma campanha',
        explica:
          'a conta respondeu e não há campanha nenhuma nela. Isto é um fato medido, ' +
          'não uma leitura que faltou.',
      };
    default:
      return {
        titulo: 'estado de leitura não reconhecido',
        explica:
          `o servidor informou o estado de leitura "${conta.frescor}", que esta versão da tela ` +
          'não conhece. Não dá para dizer se esta conta está vazia ou se a leitura não voltou.',
      };
  }
}

/**
 * O cabeçalho da conta — uma linha, e a SPEC §7.2 fixa 48 a 56 pixels.
 *
 * ⚠️ Media 102px. Nome, identificador e contagem numa linha; frescor e hora
 * numa segunda; e, à direita, um botão com um parágrafo de três linhas
 * explicando o que ele faz — repetido em cada conta, sempre igual. Com três
 * contas, isso custava ~150px antes da primeira campanha aparecer, e a conta
 * SEM campanha (que a ordem do servidor põe primeiro) custava outros 110px.
 *
 * A regra que passa a valer: tudo o que responde "posso confiar nesta conta
 * agora?" fica na MESMA linha. O que é condição excepcional — motivo de falha,
 * recado de leitura — ganha uma segunda linha, e só quando existe.
 */
const Cabecalho: React.FC<PropsDoGrupo> = ({
  conta,
  aoPedirLeitura,
  pedindoLeitura,
  recadoDaLeitura,
  aberta = true,
  aoAlternarConta,
}) => {
  const hora = horaDeLeitura(conta.leitura?.lido_em ?? null);
  const identificada = conta.customer_id !== SEM_CONTA;
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {aoAlternarConta ? (
          <button
            type="button"
            onClick={aoAlternarConta}
            aria-expanded={aberta}
            aria-controls={`campanhas-da-conta-${conta.customer_id}`}
            className="group flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-md text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-border bg-card text-foreground shadow-sm">
              <ChevronDown
                className={cn(
                  'h-4 w-4 transition-transform duration-200',
                  aberta ? 'rotate-0' : '-rotate-90',
                )}
                aria-hidden
              />
            </span>
            <span className="min-w-0">
              <span className="block text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                conta de anúncios
              </span>
              <span className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
                <span className="font-display text-[17px] font-bold leading-tight tracking-tight text-foreground">
                  {tituloDaConta(conta)}
                </span>
                {identificada && (
                  <span
                    className="tabular text-[11px] text-muted-foreground"
                    title="identificador da conta, com os primeiros dígitos ocultos — o completo abre junto com a campanha"
                  >
                    {mascararConta(conta.customer_id)}
                  </span>
                )}
                <span className="rounded-full bg-foreground/[0.06] px-2 py-0.5 text-[11px] font-semibold text-foreground">
                  {conta.quantidade === 1 ? '1 campanha' : `${conta.quantidade} campanhas`}
                </span>
              </span>
            </span>
          </button>
        ) : (
          <div className="min-w-0 py-1">
            <span className="block text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              conta de anúncios
            </span>
            <span className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="font-display text-[17px] font-bold text-foreground">
                {tituloDaConta(conta)}
              </span>
              {identificada && (
                <span className="tabular text-[11px] text-muted-foreground">
                  {mascararConta(conta.customer_id)}
                </span>
              )}
              <span className="rounded-full bg-foreground/[0.06] px-2 py-0.5 text-[11px] font-semibold">
                {conta.quantidade === 1 ? '1 campanha' : `${conta.quantidade} campanhas`}
              </span>
            </span>
          </div>
        )}

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <SeloDeFrescor
            frescor={conta.frescor}
            leitura={conta.leitura}
            ultimaLeituraBoa={conta.ultima_leitura_boa}
          />
          {hora && conta.frescor !== 'nunca_lido' && (
            <span className="text-[11px] text-muted-foreground">às {hora}</span>
          )}
          {aoPedirLeitura && identificada && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-11 gap-2 px-2.5 text-[11px] md:h-8"
                disabled={pedindoLeitura}
                aria-busy={pedindoLeitura || undefined}
                aria-describedby={`o-que-faz-${conta.customer_id}`}
                title="pergunta a esta conta o que ela tem agora. Não altera campanha nenhuma."
                onClick={() => aoPedirLeitura(conta.customer_id)}
              >
                <RefreshCw
                  className={cn('h-3 w-3', pedindoLeitura && 'animate-spin motion-reduce:animate-none')}
                  aria-hidden
                />
                {pedindoLeitura ? 'pedindo leitura…' : 'ler esta conta agora'}
              </Button>
              {/* O que o botão faz, dito antes de ser clicado. Uma ação que fala
                com a conta de anúncio do cliente não pode parecer um clique
                trivial — e também não pode parecer que mexe em campanha,
                porque não mexe.

                ⚠️ Saiu do fluxo VISUAL e continua no fluxo ACESSÍVEL. Repetida
                em três contas, a frase somava três blocos de três linhas, e ela
                é a mesma em todas. Por `aria-describedby` e `title`, ela chega a
                quem usa leitor de tela e a quem passa o ponteiro, sem cobrar
                altura de quem já a leu na primeira conta. */}
              <span id={`o-que-faz-${conta.customer_id}`} className="sr-only">
                pergunta a esta conta o que ela tem agora. Não altera campanha nenhuma.
              </span>
            </>
          )}
        </div>
      </div>

      {/* Condição excepcional ganha linha própria — e só quando existe. */}
      {conta.motivo && (
        <p className="mt-1 max-w-[80ch] text-[11px] leading-snug text-muted-foreground">
          {conta.motivo}
        </p>
      )}
      {recadoDaLeitura && (
        <p className="mt-1 max-w-[80ch] text-[11px] font-medium leading-snug" role="status">
          {recadoDaLeitura}
        </p>
      )}
    </div>
  );
};

/**
 * Conta sem campanha no recorte — uma linha, nunca um banner.
 *
 * ⚠️ Media ~110px de altura e aparecia ANTES das contas que têm campanha,
 * porque a ordem é do servidor. Uma conta vazia empurrando o trabalho para
 * baixo é o que a SPEC §7.2 proíbe em uma frase: "não recebe um banner alto".
 *
 * O texto não encolheu — o título e a explicação continuam inteiros, na mesma
 * linha, porque a distinção entre "a conta respondeu e não há nada" e "não
 * consegui ler" é o conteúdo, não a decoração.
 */
const Vazio: React.FC<{ conta: ContaNoInventario }> = ({ conta }) => {
  const { titulo, explica } = frasesDoVazio(conta);
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 px-3 py-2">
      <p className="text-[13px] font-medium">{titulo}</p>
      <p className="min-w-0 max-w-[74ch] text-[12px] leading-snug text-muted-foreground">
        {explica}
      </p>
    </div>
  );
};

export const GrupoDeConta: React.FC<PropsDoGrupo> = (props) => {
  const { conta, densidade, linhagens, aberta = true, aoAlternarConta } = props;
  const [abertas, setAbertas] = React.useState<ReadonlySet<string>>(new Set());

  const alternar = React.useCallback((id: string) => {
    setAbertas((antes) => {
      const proximo = new Set(antes);
      if (proximo.has(id)) proximo.delete(id);
      else proximo.add(id);
      return proximo;
    });
  }, []);

  // O que a linha herda da conta. Montado aqui, uma vez, porque é aqui que a
  // conta é conhecida — a linha não tem como saber de que leitura ela veio.
  const heranca: HerancaDaConta = React.useMemo(
    () => ({
      nome: tituloDaConta(conta),
      identificacaoNaTela:
        conta.customer_id === SEM_CONTA ? 'sem conta utilizável' : mascararConta(conta.customer_id),
      ultimaLeituraBoa: conta.ultima_leitura_boa,
    }),
    [conta],
  );

  // A ordem é a do servidor. Reordenar a fatia já carregada discorda da
  // paginação: cada página voltaria a "atenção primeiro" no miolo de uma
  // ordem global.
  const campanhas = conta.campanhas;
  const vazio = campanhas.length === 0;

  // ⚠️ Sticky só onde ele paga: o cabeçalho da conta. No telefone gruda no
  // topo do contêiner que rola (o cabeçalho global da aplicação está fora
  // dele); na tabela desce a altura do cabeçalho de coluna, que é a única
  // outra camada grudada — empilhar uma terceira comeria a altura útil.
  //
  // A altura vem de `TOPO_ABAIXO_DO_CABECALHO`, exportado ao lado da altura do
  // `thead`: são a mesma medida, e mantê-las em dois arquivos como dois números
  // soltos é como o cabeçalho da conta acaba grudando em cima dos rótulos.
  const grudado = cn(
    'sticky z-10 bg-muted/95 backdrop-blur-[2px] [box-shadow:inset_3px_0_0_hsl(var(--primary))]',
    densidade === 'compacta' ? 'top-0' : TOPO_ABAIXO_DO_CABECALHO,
  );

  if (densidade === 'compacta') {
    return (
      <section aria-label={`conta ${tituloDaConta(conta)}`} className="border-b border-border">
        <div className={cn(grudado, 'border-b border-border/60 px-3 py-3')}>
          <Cabecalho {...props} />
        </div>
        {vazio ? (
          <Vazio conta={conta} />
        ) : aberta ? (
          <ul id={`campanhas-da-conta-${conta.customer_id}`} className="list-none">
            {campanhas.map((c) => (
              <LinhaEmLista
                key={c.volc_campaign_id}
                campanha={c}
                aberta={abertas.has(c.volc_campaign_id)}
                aoAlternar={() => alternar(c.volc_campaign_id)}
                linhagens={linhagens}
                conta={heranca}
              />
            ))}
          </ul>
        ) : null}
      </section>
    );
  }

  const fundida = densidade === 'media';
  const colunas = fundida ? COLUNAS_MEDIAS.length : COLUNAS_AMPLAS.length;

  return (
    <tbody className="border-b border-border" aria-label={`conta ${tituloDaConta(conta)}`}>
      <tr>
        <th
          scope="rowgroup"
          colSpan={colunas}
          className={cn(grudado, 'border-b border-border/60 px-3 py-3 text-left font-normal')}
        >
          <Cabecalho {...props} />
        </th>
      </tr>
      {vazio ? (
        <tr>
          <td colSpan={colunas}>
            <Vazio conta={conta} />
          </td>
        </tr>
      ) : aberta ? (
        campanhas.map((c) => (
          <LinhaEmTabela
            key={c.volc_campaign_id}
            campanha={c}
            aberta={abertas.has(c.volc_campaign_id)}
            aoAlternar={() => alternar(c.volc_campaign_id)}
            linhagens={linhagens}
            conta={heranca}
            fundida={fundida}
          />
        ))
      ) : null}
    </tbody>
  );
};
