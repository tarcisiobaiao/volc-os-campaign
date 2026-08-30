/**
 * A barra de recorte do inventário.
 *
 * ---------------------------------------------------------------------------
 * POR QUE ELA EXISTE, E POR QUE FILTRA NO SERVIDOR
 * ---------------------------------------------------------------------------
 * Medido em 25/08/2026, na primeira varredura real: 84 campanhas em 3 contas, e
 * 74 delas numa conta só. A primeira página do inventário era consumida
 * inteira por essa conta, e as outras duas apareciam com zero campanhas — entre
 * elas a Crédito Up, onde vivem as únicas duas campanhas ligadas da casa.
 *
 * Sem recorte, o operador não alcançava o que precisava ver. Com recorte
 * client-side seria pior: a tela diria "nenhum resultado" sobre um universo que
 * TEM o resultado, e ele concluiria que a campanha não existe. Buscar dentro da
 * página é mentir com cara de busca.
 *
 * Por isso todo filtro daqui vira query param e é resolvido no banco. O que a
 * tela mostra é sempre um recorte do UNIVERSO, e a contagem diz os dois números
 * — quantas há no recorte e quantas há no total — para o operador nunca
 * confundir "filtrei" com "acabou".
 *
 * ---------------------------------------------------------------------------
 * O ESTADO MORA NA URL
 * ---------------------------------------------------------------------------
 * Um recorte que não sobrevive ao recarregamento não pode ser compartilhado nem
 * retomado. `?busca=FGTS&conta=801…` é o que alguém cola no chat para dizer
 * "olha isto aqui".
 */
import React from 'react';
import { Search, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { ContaNoInventario, FiltrosDoInventario as Filtros } from '@/types/trafego';
import { BotaoDoHistorico } from '@/components/trafego/hub/HistoricoRemovido';
import { CANAIS_GOOGLE } from '@/components/trafego/hub/contrato';
import { PALAVRA_DO_CANAL } from '@/components/trafego/inventario/formato';

/** Espera antes de consultar. Curto o bastante para parecer vivo, longo o
 *  bastante para não disparar uma consulta por tecla digitada. */
export const ESPERA_DA_BUSCA_MS = 350;

const ESTADOS: ReadonlyArray<{ valor: string; rotulo: string }> = [
  { valor: 'ENABLED', rotulo: 'ligadas' },
  { valor: 'PAUSED', rotulo: 'pausadas' },
];

/**
 * Os SEIS canais canônicos — derivados do contrato, não escritos aqui.
 *
 * ⚠️ Esta lista tinha QUATRO valores e faltavam Vídeo e Shopping. Como o filtro
 * recorta o inventário, um canal ausente da lista é um canal que o operador não
 * consegue isolar — e as campanhas dele continuam aparecendo em "todos",
 * misturadas, sem caminho para separá-las. Divergência de vocabulário entre
 * front e back foi medida em cinco lugares (E-21), e esta era a quinta.
 *
 * Derivar de `CANAIS_GOOGLE` e `PALAVRA_DO_CANAL` fecha a porta: acrescentar um
 * canal ao contrato passa a acrescentá-lo aqui, sem ninguém lembrar.
 */
const CANAIS: ReadonlyArray<{ valor: string; rotulo: string }> = CANAIS_GOOGLE.map((c) => ({
  valor: c,
  rotulo: PALAVRA_DO_CANAL[c] ?? c,
}));

export interface HistoricoNaBarra {
  aberto: boolean;
  quantidade: number | null;
  aoAbrir: () => void;
  aoFechar: () => void;
}

export interface FiltrosDoInventarioProps {
  filtros: Filtros;
  aoMudar: (proximos: Filtros) => void;
  /** As contas do inventário — sempre TODAS, mesmo quando não há campanha
   *  delas na página. É por aqui que se alcança a conta que a paginação
   *  escondeu. */
  contas: ReadonlyArray<Pick<ContaNoInventario, 'customer_id' | 'nome' | 'quantidade'>>;
  /** Quantas campanhas o recorte tem. */
  noRecorte: number | null;
  /** Quantas campanhas existem no total, sem recorte. */
  noUniverso: number | null;
  /**
   * Frase da lista operacional. Sem recorte do operador, diz
   * "N campanhas operacionais" — o N vem do servidor, nunca de um 5 escrito.
   */
  fraseOperacional?: boolean;
  /** Recorte escolhido pelo operador (busca, conta, estado, atenção). */
  temRecorteUsuario?: boolean;
  /** O eixo de canal mora na moldura do Hub; a barra não o duplica. */
  ocultarCanal?: boolean;
  historico?: HistoricoNaBarra;
}

/** Um seletor de valor único, desenhado como os chips do resto da tela. */
const Escolha: React.FC<{
  rotulo: string;
  valor: string | undefined;
  opcoes: ReadonlyArray<{ valor: string; rotulo: string }>;
  aoEscolher: (v: string | undefined) => void;
  id: string;
}> = ({ rotulo, valor, opcoes, aoEscolher, id }) => (
  <div className="flex min-w-0 flex-col gap-1">
    <label htmlFor={id} className="kicker text-[10px] text-muted-foreground">
      {rotulo}
    </label>
    <select
      id={id}
      value={valor ?? ''}
      onChange={(e) => aoEscolher(e.target.value || undefined)}
      className={cn(
        'h-11 min-w-[9rem] rounded-md border border-input bg-background px-3 text-sm md:h-9',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
      )}
    >
      <option value="">todas</option>
      {opcoes.map((o) => (
        <option key={o.valor} value={o.valor}>{o.rotulo}</option>
      ))}
    </select>
  </div>
);

export const FiltrosDoInventario: React.FC<FiltrosDoInventarioProps> = ({
  filtros, aoMudar, contas, noRecorte, noUniverso,
  fraseOperacional = false,
  temRecorteUsuario,
  ocultarCanal = false,
  historico,
}) => {
  // O texto digitado vive local e só vira filtro depois da espera. Sem isso,
  // cada tecla seria uma consulta ao banco e a lista piscaria a cada letra.
  const [texto, setTexto] = React.useState(filtros.busca ?? '');
  const primeiraRenderizacao = React.useRef(true);

  React.useEffect(() => { setTexto(filtros.busca ?? ''); }, [filtros.busca]);

  React.useEffect(() => {
    if (primeiraRenderizacao.current) { primeiraRenderizacao.current = false; return; }
    const t = window.setTimeout(() => {
      if ((filtros.busca ?? '') !== texto) aoMudar({ ...filtros, busca: texto || undefined });
    }, ESPERA_DA_BUSCA_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto]);

  const temRecorte = temRecorteUsuario ?? Boolean(
    filtros.busca || filtros.conta?.length || filtros.estado_externo?.length ||
    filtros.canal?.length || filtros.atencao,
  );

  const umOuNada = (v: string | undefined) => (v ? [v] : undefined);

  return (
    <section aria-label="recorte do inventário" className="border-b border-border pb-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1 md:max-w-sm">
          <label htmlFor="busca-inventario" className="kicker text-[10px] text-muted-foreground">
            buscar
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              id="busca-inventario"
              type="search"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="nome da campanha ou ID"
              className="h-11 pl-9 md:h-9"
              aria-describedby="busca-inventario-ajuda"
            />
          </div>
          <p id="busca-inventario-ajuda" className="text-[11px] leading-relaxed text-muted-foreground">
            procura em todas as contas, não só no que já está na tela
          </p>
        </div>

        <Escolha
          id="filtro-conta" rotulo="conta"
          valor={filtros.conta?.[0]}
          opcoes={contas.map((c) => ({
            valor: c.customer_id,
            rotulo: `${c.nome ?? c.customer_id} (${c.quantidade})`,
          }))}
          aoEscolher={(v) => aoMudar({ ...filtros, conta: umOuNada(v) })}
        />
        <Escolha
          id="filtro-estado" rotulo="estado"
          valor={filtros.estado_externo?.[0]}
          opcoes={ESTADOS}
          aoEscolher={(v) => aoMudar({ ...filtros, estado_externo: umOuNada(v) })}
        />
        {!ocultarCanal && (
          <Escolha
            id="filtro-canal" rotulo="canal"
            valor={filtros.canal?.[0]}
            opcoes={CANAIS}
            aoEscolher={(v) => aoMudar({ ...filtros, canal: umOuNada(v) as Filtros['canal'] })}
          />
        )}

        <div className="flex flex-col gap-1">
          <span className="kicker text-[10px] text-muted-foreground">recorte</span>
          <Button
            type="button"
            variant={filtros.atencao ? 'default' : 'outline'}
            size="sm"
            aria-pressed={Boolean(filtros.atencao)}
            className="h-11 md:h-9"
            onClick={() => aoMudar({ ...filtros, atencao: filtros.atencao ? undefined : true })}
          >
            pede atenção
          </Button>
        </div>

        {historico && (
          <div className="flex flex-col gap-1">
            <span className="kicker text-[10px] text-muted-foreground">histórico</span>
            <BotaoDoHistorico
              quantidade={historico.quantidade}
              aberto={historico.aberto}
              aoAbrir={historico.aoAbrir}
              aoFechar={historico.aoFechar}
            />
          </div>
        )}

        {temRecorte && (
          <Button
            type="button" variant="ghost" size="sm"
            className="h-11 gap-1.5 md:h-9"
            onClick={() => aoMudar({})}
          >
            <X className="h-3.5 w-3.5" aria-hidden />
            limpar
          </Button>
        )}
      </div>

      {/*
        Os DOIS números, sempre. "12 campanhas" sozinho não diz se o operador
        está vendo tudo ou um pedaço, e é a diferença entre "acabou" e
        "filtrei" — que leva a conclusões opostas sobre a mesma tela.
      */}
      {/*
        ⚠️ Nada aqui enquanto a contagem é desconhecida. O esqueleto do
        inventário já é uma região viva anunciando "carregando", e duas regiões
        vivas na mesma tela falam por cima uma da outra: o leitor de tela lê
        "contando…" e "carregando o inventário" em sequência, e quem ouve não
        sabe qual das duas terminou.
      */}
      {noRecorte != null && (
      <p className="mt-3 text-xs text-muted-foreground" role="status">
        {temRecorte ? (
          <>
            <strong className="tabular font-medium text-foreground">{noRecorte}</strong>
            {' '}de{' '}
            <span className="tabular">{noUniverso ?? '—'}</span>
            {' '}campanhas neste recorte
          </>
        ) : fraseOperacional ? (
          <>
            <strong className="tabular font-medium text-foreground">{noRecorte}</strong>
            {' '}
            {noRecorte === 1 ? 'campanha operacional' : 'campanhas operacionais'}
          </>
        ) : (
          <>
            <strong className="tabular font-medium text-foreground">{noRecorte}</strong>
            {' '}campanhas conhecidas, sem recorte
          </>
        )}
      </p>
      )}
    </section>
  );
};

export default FiltrosDoInventario;
