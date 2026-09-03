/**
 * A jornada de UM canal: os quatro portões do servidor e as treze etapas.
 *
 * ## O que faltava, e por que faltava justamente isto
 *
 * O estúdio já mostrava o MANIFESTO — o que o canal sabe fazer — e a gramática
 * de etapas por canal. O que ele não mostrava era o veredito: `GET /canais`
 * devolve quatro portões por canal, cada um com estado e bloqueadores nomeados
 * (`codigo`, `causa`, `origem`, `observado_em`, `revalidacao`), e nenhuma tela
 * os lia. A diferença é grande e é sempre a mesma pergunta:
 *
 *     manifesto  → "este canal SABE criar?"
 *     portão     → "e EU posso criar nele AGORA, e se não, por quê?"
 *
 * Display responde `sabe_criar: true` no manifesto e `criavel_pausada:
 * BLOQUEADO` no portão, porque a janela do canário só admite Search. Uma tela
 * que lesse só o manifesto ofereceria Display e o servidor recusaria no clique,
 * depois de o operador montar o pedido inteiro.
 *
 * ## Nada aqui decide
 *
 * `aberto` vem do servidor. `estado` vem do servidor. `causa` vem do servidor e
 * é renderizada como chegou — o contrato de canais diz, com todas as letras,
 * para ligar comportamento ao `codigo` e nunca a um trecho de `causa`. O que
 * este arquivo acrescenta é a pergunta que cada portão responde e a frase de
 * *a quem pedir*, ambas já escritas uma única vez em `lib/trafego/canais.ts`.
 *
 * ## O portão `ativavel` nunca vira botão
 *
 * Ele é `BLOQUEADO` em todos os canais, sempre, e o contrato do backend declara
 * que "não existe, neste contrato, campo que autorize ativação". Um controle de
 * ativar seria UI morta. Ele aparece como degrau — porque saber que o caminho
 * termina ali é informação —, nunca como ato.
 */
import React from 'react';
import {
  Ban,
  CircleCheck,
  CircleHelp,
  CircleSlash,
  Lock,
  RotateCw,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { ConversaDeCriacao } from '@/components/trafego/criacao/ConversaDeCriacao';
import { montarConversa } from '@/components/trafego/criacao/conversa';
import {
  A_QUEM_PEDIR,
  ORDEM_DOS_PORTOES,
  PERGUNTA_DO_PORTAO,
  ROTULO_DO_PORTAO,
  portao,
  tomDoEstado,
  type BloqueadorDeCanal,
  type ContratoDeCanal,
  type EstadoDePortao,
  type PortaoDeCanal,
} from '@/lib/trafego/canais';

type Glifo = React.ComponentType<{ className?: string }>;

/**
 * O tom de cada estado.
 *
 * ⚠️ `INDETERMINADO` é âmbar, nunca vermelho. As duas pedem atos opostos:
 * vermelho pede que alguém conserte ou libere algo; âmbar pede uma leitura que
 * ninguém fez. Pintar ignorância de vermelho ensina a ignorar o vermelho.
 */
const VISUAL_DO_ESTADO: Record<
  EstadoDePortao,
  { tom: Tom; glifo: Glifo; palavra: string; descricao: string }
> = {
  PERMITIDO: {
    tom: 'bom',
    glifo: CircleCheck,
    palavra: 'permitido',
    descricao: 'medido, e a resposta é sim',
  },
  BLOQUEADO: {
    tom: 'ruim',
    glifo: Lock,
    palavra: 'bloqueado',
    descricao: 'medido, e a resposta é não — com causa nomeada',
  },
  INDETERMINADO: {
    tom: 'atencao',
    glifo: CircleHelp,
    palavra: 'não apurado',
    descricao: 'ninguém olhou. Não é um não, é uma leitura que falta',
  },
  NAO_APLICAVEL: {
    tom: 'neutro',
    glifo: CircleSlash,
    palavra: 'não cabe',
    descricao: 'a pergunta não existe neste canal',
  },
};

const VISUAL_PADRAO = {
  tom: 'neutro' as Tom,
  glifo: CircleHelp as Glifo,
  palavra: 'estado desconhecido',
  descricao: 'o servidor mandou um estado que esta versão da tela não conhece',
};

const visualDoEstado = (estado: string) =>
  VISUAL_DO_ESTADO[estado as EstadoDePortao] ?? VISUAL_PADRAO;

export interface JornadaDoCanalProps {
  /** O contrato do canal escolhido. `null` = a leitura ainda não chegou. */
  contrato: ContratoDeCanal | null;
  /**
   * A trava de escrita.
   *
   * ⚠️ `null` é NÃO APURADO e nunca é tratado como aberta. Ler otimista aqui
   * custaria uma campanha criada por engano.
   */
  travaAberta: boolean | null;
  /** Se o papel desta sessão pode assinar a aprovação de gasto. */
  podeAprovar: boolean;
  carregando?: boolean;
  falhou?: boolean;
  /** Reler o contrato. Ausente = a tela não oferece releitura. */
  aoRevalidar?: () => void;
  className?: string;
}

export const JornadaDoCanal: React.FC<JornadaDoCanalProps> = ({
  contrato,
  travaAberta,
  podeAprovar,
  carregando = false,
  falhou = false,
  aoRevalidar,
  className,
}) => {
  // ⚠️ Os três casos degradados são TRÊS FRASES, e nunca a mesma. "Lendo",
  // "não consegui ler" e "este servidor não devolveu este canal" levam a lugares
  // diferentes: esperar, tentar de novo, e perguntar a quem administra.
  if (carregando) {
    return (
      <p className={cn('text-[13px] text-muted-foreground', className)}>
        Lendo o que este canal permite agora…
      </p>
    );
  }

  if (falhou) {
    return (
      <div className={cn('max-w-[70ch]', className)} role="alert">
        <p className="text-[13px] leading-relaxed">
          Não consegui ler os portões deste canal.{' '}
          <span className="text-muted-foreground">
            Isto não afirma que ele esteja bloqueado — afirma que a leitura não
            chegou. Nenhum estado abaixo pode ser tratado como veredito.
          </span>
        </p>
        {aoRevalidar && (
          <button
            type="button"
            onClick={aoRevalidar}
            className={cn(
              'mt-3 inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border px-3',
              'text-[13px] font-medium transition-volc duration-150 hover:bg-muted/50',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            )}
          >
            <RotateCw className="h-3.5 w-3.5" aria-hidden />
            Tentar ler de novo
          </button>
        )}
      </div>
    );
  }

  if (contrato == null) {
    return (
      <p className={cn('max-w-[70ch] text-[13px] leading-relaxed', className)}>
        Este servidor não devolveu contrato para o canal escolhido.{' '}
        <span className="text-muted-foreground">
          Os quatro canais do Google saem sempre na resposta; a ausência de um
          deles é um defeito do servidor, não uma recusa dirigida a você.
        </span>
      </p>
    );
  }

  const passos = montarConversa({
    manifesto: contrato.manifesto,
    respostas: {},
    travaAberta,
    podeAprovar,
  });

  return (
    <div className={cn('space-y-8', className)}>
      <EscadaDePortoes contrato={contrato} />

      <div>
        {/* ⚠️ A conversa é montada com as respostas VAZIAS, e a tela precisa
            dizer isso. Ela mostra o TAMANHO e a forma do trabalho — quais
            perguntas este canal faz, quais não faz, e onde o caminho fecha por
            papel ou por manifesto. Sem esta frase, um trilho todo pendente se
            leria como uma sessão de criação já aberta que não avança. */}
        <p className="mb-4 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
          Abaixo está o caminho inteiro deste canal, ainda sem nenhuma resposta:
          serve para ver o tamanho do trabalho antes de começar. As respostas são
          dadas no cockpit da campanha, a partir de uma oportunidade escolhida.
        </p>
        <ConversaDeCriacao passos={passos} />
      </div>
    </div>
  );
};

// ── os quatro portões ───────────────────────────────────────────────────────

const EscadaDePortoes: React.FC<{ contrato: ContratoDeCanal }> = ({ contrato }) => (
  <section aria-labelledby="portoes-titulo">
    <p className="kicker">o que este canal permite agora</p>
    <h3
      id="portoes-titulo"
      className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
    >
      Os quatro portões de {contrato.rotulo}
    </h3>
    <p className="mt-1.5 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
      Quem responde é o servidor. São degraus, e não o mesmo degrau visto de
      longe: um canal pode passar em conferir e ser recusado em criar por um
      motivo que não tem nada a ver com o construtor.
    </p>

    <ol className="mt-5 border-t border-border" role="list">
      {ORDEM_DOS_PORTOES.map((nome, i) => (
        <LinhaDePortao
          key={nome}
          posicao={i + 1}
          nome={nome}
          portao={portao(contrato, nome)}
        />
      ))}
    </ol>
  </section>
);

const LinhaDePortao: React.FC<{
  posicao: number;
  nome: (typeof ORDEM_DOS_PORTOES)[number];
  portao: PortaoDeCanal | null;
}> = ({ posicao, nome, portao: p }) => {
  // ⚠️ Portão ausente ≠ portão fechado. O contrato manda os quatro sempre; se um
  // não veio, a tela diz que não veio em vez de desenhar uma recusa que ninguém
  // fez.
  const visual = p ? visualDoEstado(p.estado) : null;
  const Glifo = visual?.glifo;

  return (
    <li className="border-b border-border">
      <div className="flex min-h-11 items-start gap-3 px-1 py-3">
        <span className="tabular mt-0.5 w-4 shrink-0 text-[11px] text-muted-foreground">
          {posicao}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-display text-[13px] font-medium">
              {ROTULO_DO_PORTAO[nome]}
            </span>
            {visual && Glifo ? (
              <Chip
                glifo={Glifo}
                palavra={visual.palavra}
                descricao={visual.descricao}
                tom={visual.tom}
              />
            ) : (
              <Chip
                glifo={CircleHelp}
                palavra="não veio"
                descricao="o servidor não mandou este portão nesta resposta"
                tom="neutro"
              />
            )}
          </span>
          <span className="mt-0.5 block max-w-[64ch] text-[12px] leading-relaxed text-muted-foreground">
            {PERGUNTA_DO_PORTAO[nome]}
          </span>

          {p && p.bloqueadores.length > 0 && (
            <ul className="mt-2.5 space-y-2.5" role="list">
              {p.bloqueadores.map((b) => (
                <Bloqueio key={b.codigo} bloqueio={b} />
              ))}
            </ul>
          )}

          {/* ⚠️ Lista de bloqueadores vazia NUNCA é permissão. Só o estado
              autoriza, e este aviso existe porque `ativavel` chega bloqueado com
              a lista vazia em alguns perfis. */}
          {p && p.estado === 'BLOQUEADO' && p.bloqueadores.length === 0 && (
            <p className="mt-2 max-w-[64ch] text-[12px] leading-relaxed text-muted-foreground">
              Fechado, e o servidor não nomeou a causa nesta resposta. Isto é uma
              lacuna do contrato, não uma permissão.
            </p>
          )}
        </span>
      </div>
    </li>
  );
};

const TOM_DA_ORIGEM: Record<string, Tom> = {
  produto: 'info',
  politica: 'info',
  servidor: 'atencao',
  operador: 'atencao',
  construtor: 'neutro',
  manifesto: 'neutro',
  mensuracao: 'verificado',
  observabilidade: 'verificado',
};

const Bloqueio: React.FC<{ bloqueio: BloqueadorDeCanal }> = ({ bloqueio }) => {
  const aQuemPedir = A_QUEM_PEDIR[bloqueio.origem];
  return (
    <li className="border-l-2 border-border pl-3">
      {/* A causa vai como o servidor a escreveu. O contrato de canais proíbe
          ligar comportamento a trechos dela — e reescrevê-la aqui seria uma
          segunda redação da mesma regra, que é o defeito com outra roupa. */}
      <p className="max-w-[64ch] text-[12px] leading-relaxed">{bloqueio.causa}</p>
      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
        <Chip
          glifo={Ban}
          palavra={bloqueio.origem}
          descricao={aQuemPedir ?? 'origem que esta versão da tela não conhece'}
          tom={TOM_DA_ORIGEM[bloqueio.origem] ?? 'neutro'}
        />
        <span className="text-[11px] leading-relaxed text-muted-foreground">
          {aQuemPedir ??
            'Origem desconhecida por esta tela — peça a quem administra o sistema.'}
        </span>
      </p>
      {bloqueio.revalidacao && (
        <p className="mt-1 max-w-[64ch] text-[11px] leading-relaxed text-muted-foreground">
          Como conferir de novo: {bloqueio.revalidacao}
        </p>
      )}
      {bloqueio.observado_em && (
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          <span className="tabular">Observado em {bloqueio.observado_em}</span> — é
          um fato lido, não uma regra: pode ter mudado desde então.
        </p>
      )}
    </li>
  );
};

export default JornadaDoCanal;
