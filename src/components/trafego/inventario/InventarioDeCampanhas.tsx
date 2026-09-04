/**
 * O inventário: o que existe nas contas, em que estado, e quão recente é isso.
 *
 * ## A ordem dos avisos não é estética
 *
 * Primeiro o que compromete a confiança no que vem abaixo (dado antigo,
 * leitura parcial), depois o dado. Ao contrário, o operador leria os números,
 * formaria uma opinião, e só então descobriria que uma das contas não
 * respondeu — tarde demais, porque a opinião já está formada.
 *
 * ## Falha de uma conta não contamina as outras
 *
 * A conta que não respondeu aparece com o último dado bom e a idade dele; as
 * outras seguem normais. O oposto — esvaziar a tela inteira porque uma leitura
 * falhou — troca um problema conhecido por um vazio que parece calmo.
 */
import React from 'react';
import { RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useInventario, usePedirLeituraDaConta, type LeituraDoInventario } from '@/hooks/useInventario';
import type { FiltrosDoInventario } from '@/types/trafego';

import { GrupoDeConta } from './GrupoDeConta';
import {
  ALTURA_DO_CABECALHO_DE_COLUNA,
  COLUNAS_AMPLAS,
  COLUNAS_MEDIAS,
  LARGURAS_AMPLAS,
  type ContagemDeLinhagem,
} from './LinhaDeCampanha';
import {
  AvisoDeDadoAntigo,
  AvisoDeLeituraParcial,
  EsqueletoDoInventario,
  FalhaDoInventario,
  InventarioVazio,
  RecorteVazio,
} from './EstadosDoInventario';
import { ehFrescorConhecido } from './formato';
import { useDensidade } from './densidade';
import { FiltrosDoInventario as FiltrosDoInventarioBarra } from '@/components/trafego/inventario/FiltrosDoInventario';
import { FaixaDoHistorico } from '@/components/trafego/hub/HistoricoRemovido';
import { totaisOperacionais } from '@/components/trafego/hub/adaptacao';

/** Colunas cujo conteúdo é número e por isso alinha à direita. */
const NUMERICAS = new Set([
  'lance',
  'orçamento diário',
  'teto estimado',
  'impressões',
  'cliques',
  'custo',
]);

export interface HistoricoDoInventario {
  aberto: boolean;
  quantidade: number | null;
  consulta: FiltrosDoInventario;
  aoAbrir: () => void;
  aoFechar: () => void;
}

/**
 * O recorte pode vir de fora (a página, que o guarda na URL) ou nascer aqui.
 *
 * `consulta` é o recorte enviado ao servidor — pode incluir o padrão
 * operacional (ENABLED+PAUSED) que NÃO aparece como filtro escolhido.
 */
export const InventarioDeCampanhas: React.FC<{
  filtros?: FiltrosDoInventario;
  recorte?: FiltrosDoInventario;
  consulta?: FiltrosDoInventario;
  aoMudarRecorte?: (proximos: FiltrosDoInventario) => void;
  fraseOperacional?: boolean;
  historico?: HistoricoDoInventario;
  /** Leituras já feitas pelo Hub. Sem elas, o inventário lê sozinho. */
  situacao?: LeituraDoInventario;
  operacional?: LeituraDoInventario;
  universoFiltros?: LeituraDoInventario;
  leituraHistorico?: LeituraDoInventario;
}> = ({
  filtros,
  recorte: recorteExterno,
  consulta: consultaExterna,
  aoMudarRecorte,
  fraseOperacional = false,
  historico,
  situacao: situacaoExterna,
  operacional: operacionalExterna,
  universoFiltros: universoFiltrosExterno,
  leituraHistorico: historicoExterno,
}) => {
  const densidade = useDensidade();
  const [recorteLocal, setRecorteLocal] = React.useState<FiltrosDoInventario>({});
  const recorteEscolhido = recorteExterno ?? recorteLocal;
  const aplicar = aoMudarRecorte ?? setRecorteLocal;

  const recorte = React.useMemo(
    () => ({ ...(filtros ?? {}), ...recorteEscolhido }),
    [filtros, recorteEscolhido],
  );
  const consulta = consultaExterna ?? recorte;

  const temRecorteUsuario = Boolean(
    recorte.busca || recorte.conta?.length || recorte.estado_externo?.length || recorte.atencao,
  );

  // Quando o Hub já trouxe as quatro leituras, estes hooks ficam desligados:
  // a tela não depende de uma segunda chamada idêntica para funcionar.
  const consultaUniversoOperacional = React.useMemo(() => {
    if (!fraseOperacional) return undefined;
    const { busca: _busca, conta: _conta, atencao: _atencao, ...resto } = consulta;
    return resto;
  }, [fraseOperacional, consulta]);
  const universoInterno = useInventario(undefined, { habilitado: situacaoExterna == null });
  const leituraInterna = useInventario(consulta, { habilitado: operacionalExterna == null });
  const universoOperacionalInterno = useInventario(consultaUniversoOperacional, {
    habilitado: universoFiltrosExterno == null && consultaUniversoOperacional != null,
  });
  const historicoInterno = useInventario(historico?.consulta, {
    habilitado: historicoExterno == null && Boolean(historico?.aberto),
  });
  const universo = situacaoExterna ?? universoInterno;
  const leitura = operacionalExterna ?? leituraInterna;
  const universoOperacional = universoFiltrosExterno ?? universoOperacionalInterno;
  const leituraHistorico = historicoExterno ?? historicoInterno;
  const pedido = usePedirLeituraDaConta();
  const { inventario } = leitura;
  const [contaEscolhida, setContaEscolhida] = React.useState<string | null | undefined>(undefined);

  const primeiraContaComCampanhas = React.useMemo(
    () => inventario?.contas.find((conta) => conta.campanhas.length > 0)?.customer_id ?? null,
    [inventario],
  );
  const contaAberta = React.useMemo(() => {
    if (contaEscolhida === null) return null;
    if (
      contaEscolhida != null &&
      inventario?.contas.some((conta) => conta.customer_id === contaEscolhida)
    ) {
      return contaEscolhida;
    }
    return primeiraContaComCampanhas;
  }, [contaEscolhida, inventario, primeiraContaComCampanhas]);

  // Quantas instâncias da mesma intenção estão carregadas. É contagem sobre o
  // que está na mão — por isso a frase na tela diz "neste inventário", e não
  // afirma um total histórico que esta resposta não conhece.
  const linhagens: ContagemDeLinhagem = React.useMemo(() => {
    const contagem: ContagemDeLinhagem = {};
    for (const conta of inventario?.contas ?? []) {
      for (const campanha of conta.campanhas) {
        if (!campanha.campaign_lineage_id) continue;
        contagem[campanha.campaign_lineage_id] = (contagem[campanha.campaign_lineage_id] ?? 0) + 1;
      }
    }
    return contagem;
  }, [inventario]);

  const barra = (
    <FiltrosDoInventarioBarra
      filtros={recorte}
      aoMudar={aplicar}
      contas={(universo.inventario?.contas ?? []).map((c) => ({
        customer_id: c.customer_id, nome: c.nome, quantidade: c.quantidade,
      }))}
      noRecorte={totaisOperacionais(inventario?.totais)}
      noUniverso={
        fraseOperacional
          ? totaisOperacionais(universoOperacional.inventario?.totais)
          : totaisOperacionais(universo.inventario?.totais)
      }
      fraseOperacional={fraseOperacional}
      temRecorteUsuario={temRecorteUsuario}
      ocultarCanal
      historico={
        historico
          ? {
              aberto: historico.aberto,
              quantidade: historico.quantidade,
              aoAbrir: historico.aoAbrir,
              aoFechar: historico.aoFechar,
            }
          : undefined
      }
    />
  );

  const gruposDe = (fonte: typeof inventario) =>
    (fonte?.contas ?? []).map((conta) => (
      <GrupoDeConta
        key={conta.customer_id}
        conta={conta}
        densidade={densidade}
        linhagens={linhagens}
        aoPedirLeitura={pedido.pedir}
        pedindoLeitura={pedido.contaEmLeitura === conta.customer_id}
        recadoDaLeitura={pedido.recados[conta.customer_id] ?? null}
        aberta={contaAberta === conta.customer_id}
        aoAlternarConta={
          conta.campanhas.length > 0
            ? () => setContaEscolhida((atual) => {
                const abertaAgora = atual === undefined ? primeiraContaComCampanhas : atual;
                return abertaAgora === conta.customer_id ? null : conta.customer_id;
              })
            : undefined
        }
      />
    ));

  const renderLista = (fonte: typeof inventario, grupos: React.ReactNode) => {
    if (!fonte || fonte.contas.length === 0) return null;
    const ampla = densidade === 'ampla';
    const colunas = ampla ? COLUNAS_AMPLAS : COLUNAS_MEDIAS;
    if (densidade === 'compacta') {
      return (
        <div className="rounded-lg border border-border bg-card shadow-[var(--shadow-card)] [&>section:last-child]:border-b-0">
          {grupos}
        </div>
      );
    }
    return (
      <div className="overflow-hidden rounded-lg border border-border bg-card shadow-[var(--shadow-card)]">
        <table
          className={cn(
            'w-full border-collapse text-left',
            ampla ? 'table-fixed' : 'table-auto',
          )}
        >
          <caption className="sr-only">
            Campanhas conhecidas, agrupadas pela conta de anúncio que as respondeu
          </caption>
          {ampla && (
            <colgroup>
              {LARGURAS_AMPLAS.map((largura, i) => (
                <col key={colunas[i]} style={{ width: largura }} />
              ))}
            </colgroup>
          )}
          <thead className="sticky top-0 z-20 bg-card">
            <tr className="border-b border-border">
              {colunas.map((c) => (
                <th
                  key={c}
                  scope="col"
                  className={cn(
                    'kicker px-2 pb-2 align-bottom leading-tight',
                    // ⚠️ Quebra só em ESPAÇO, e sem o espaçamento de letra.
                    //
                    // Medido a 1440px: com `table-fixed`, "IMPRESSÕES" era mais
                    // largo que a própria célula e encostava em "CLIQUES" — a
                    // captura lia "IMPRESSÕESCLIQUES", e o operador leria o
                    // número de impressões na coluna de cliques.
                    //
                    // A primeira tentativa foi `break-words`, e ela ficou pior:
                    // partia no meio da palavra ("ORÇAME/NTO", "IMPRESSÕ/ES"),
                    // que é ilegível de um jeito novo. O que resolve é tirar o
                    // `letter-spacing` de 0.08em que a classe `kicker` aplica:
                    // ele sozinho custava ~8px por rótulo, o bastante para
                    // "IMPRESSÕES" não caber. Uppercase continua sendo auxílio
                    // de navegação; o espaçamento decorativo é que não cabe numa
                    // grade de onze colunas.
                    'break-normal tracking-normal',
                    ALTURA_DO_CABECALHO_DE_COLUNA,
                    NUMERICAS.has(c) && 'text-right',
                  )}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          {grupos}
        </table>
      </div>
    );
  };

  if (leitura.carregando) return <>{barra}<EsqueletoDoInventario /></>;

  if (!inventario) {
    return (
      <>
        {barra}
        {leitura.falhou ? (
          <FalhaDoInventario motivo={leitura.motivoDaFalha} aoTentarDeNovo={leitura.recarregar} />
        ) : (
          <InventarioVazio />
        )}
      </>
    );
  }

  const frescorEstranho = !ehFrescorConhecido(inventario.frescor);
  const dadoAntigo = leitura.falhou || inventario.frescor === 'velho' || frescorEstranho;
  const grupos = gruposDe(inventario);
  const vazia = inventario.contas.length === 0;
  const historicoAberto = Boolean(historico?.aberto);
  const gruposHistorico = historicoAberto ? gruposDe(leituraHistorico.inventario) : null;

  return (
    <div className="space-y-4">
      {barra}
      {dadoAntigo && (
        <AvisoDeDadoAntigo
          idadeSegundos={inventario.leitura?.idade_s ?? null}
          aAtualizacaoFalhou={leitura.falhou}
          frescorNaoReconhecido={frescorEstranho ? inventario.frescor : null}
        />
      )}

      {leitura.atualizando && (
        <p className="flex items-center justify-end gap-1.5 text-[11px] text-muted-foreground">
          <RefreshCw className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden />
          conferindo o registro…
        </p>
      )}

      {inventario.parcial && <AvisoDeLeituraParcial faltou={inventario.faltou} />}

      {vazia ? (
        temRecorteUsuario || consulta.canal?.length ? (
          <RecorteVazio />
        ) : (
          <InventarioVazio />
        )
      ) : (
        renderLista(inventario, grupos)
      )}

      {leitura.temMais && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-11 gap-2 px-4 text-xs md:h-10"
            disabled={leitura.carregandoMais}
            onClick={leitura.carregarMais}
          >
            <RefreshCw
              className={cn(
                'h-3 w-3',
                leitura.carregandoMais && 'animate-spin motion-reduce:animate-none',
              )}
              aria-hidden
            />
            {leitura.carregandoMais ? 'carregando…' : 'Carregar mais'}
          </Button>
        </div>
      )}

      {historicoAberto && historico && (
        <FaixaDoHistorico quantidade={historico.quantidade}>
          {leituraHistorico.carregando && <EsqueletoDoInventario contas={1} linhas={2} />}
          {!leituraHistorico.carregando &&
            renderLista(leituraHistorico.inventario, gruposHistorico)}
        </FaixaDoHistorico>
      )}
    </div>
  );
};

export default InventarioDeCampanhas;
