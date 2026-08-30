/**
 * `/criativos/biblioteca` — a autoridade do patrimônio criativo.
 *
 * ## Os quatro estados, e por que eles não podem se parecer
 *
 * `leitura.ts` decide entre carregando, erro, vazio e vazio depois do filtro.
 * Cada um leva a uma ação diferente: esperar, tentar de novo, produzir algo, ou
 * afrouxar o filtro. Desenhar os quatro como a mesma caixa cinza faz o operador
 * tomar a decisão errada em três deles.
 *
 * ## A contagem diz o recorte E o universo
 *
 * "12" sozinho não responde se a busca achou pouco ou se existe pouco.
 */
import React from 'react';
import { LayoutGrid, List } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { CabecalhoDoEstudio, Corpo, Secao } from '@/components/criativos/comum/Painel';
import {
  Carregando,
  ErroDeLeitura,
  Vazio,
  VazioAposFiltro,
} from '@/components/criativos/comum/Estados';
import { PainelDeFiltros } from '@/components/criativos/biblioteca/PainelDeFiltros';
import { Grade } from '@/components/criativos/biblioteca/Grade';
import { useDensidade } from '@/components/criativos/biblioteca/densidade';
import {
  FILTROS_VAZIOS,
  contagemLegivel,
  temFiltro,
  type FiltrosDaBiblioteca,
} from '@/components/criativos/biblioteca/filtros';
import { classificarLeitura } from '@/components/criativos/comum/leitura';
import { PAGINA, useCriativosBiblioteca } from '@/hooks/useCriativosBiblioteca';
import { useCriativosBrandPacks } from '@/hooks/useCriativosCatalogo';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';

const BibliotecaPage: React.FC = () => {
  const [filtros, setFiltros] = React.useState<FiltrosDaBiblioteca>(FILTROS_VAZIOS);
  const [offset, setOffset] = React.useState(0);
  const [densidade, setDensidade] = useDensidade();
  const { brandPacks, nomeDoPack } = useCriativosBrandPacks();

  const consulta = useCriativosBiblioteca(filtros, offset);
  const assets = consulta.data?.assets ?? [];
  const total = consulta.data?.total ?? 0;
  const universo = consulta.data?.universo ?? null;
  const comFiltro = temFiltro(filtros);

  const estado = classificarLeitura({
    carregando: consulta.isLoading,
    erro: consulta.isError ? consulta.error : null,
    visiveis: assets.length,
    universo,
    temFiltro: comFiltro,
  });

  const mudarFiltros = (f: FiltrosDaBiblioteca) => {
    setFiltros(f);
    setOffset(0);
  };

  const renovar = React.useCallback(() => void consulta.refetch(), [consulta]);

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Patrimônio"
        titulo="Biblioteca"
        proposito="Todo ativo produzido ou observado, com procedência, medidas, direitos e decisão de aprovação. Esta é a autoridade; Tráfego e Conteúdo são destinos."
        voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
        acao={
          <div className="flex items-center gap-1 rounded-md border border-border p-0.5" role="group" aria-label="Densidade da lista">
            <Button
              variant={densidade === 'grade' ? 'secondary' : 'ghost'}
              size="sm"
              aria-pressed={densidade === 'grade'}
              onClick={() => setDensidade('grade')}
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
              Grade
            </Button>
            <Button
              variant={densidade === 'lista' ? 'secondary' : 'ghost'}
              size="sm"
              aria-pressed={densidade === 'lista'}
              onClick={() => setDensidade('lista')}
            >
              <List className="h-4 w-4" aria-hidden />
              Lista
            </Button>
          </div>
        }
      />

      <Corpo className="space-y-4">
        <Secao titulo="Recorte" descricao="Todo filtro ativo aparece abaixo e pode ser removido.">
          <PainelDeFiltros
            filtros={filtros}
            aoMudar={mudarFiltros}
            brandPacks={brandPacks}
            nomeDoPack={nomeDoPack}
            contagem={
              consulta.isLoading
                ? 'Contagem ainda não lida.'
                : universo === null
                  ? `${total} ${total === 1 ? 'ativo neste recorte' : 'ativos neste recorte'}. O total da biblioteca não foi informado.`
                  : contagemLegivel(total, universo, comFiltro)
            }
          />
        </Secao>

        {estado === 'carregando' && (
          <Carregando rotulo="Lendo a biblioteca" linhas={4} altura="h-32" />
        )}

        {estado === 'erro' && (
          <ErroDeLeitura
            mensagem={mensagemDaFalha(consulta.error)}
            codigo={codigoDaFalha(consulta.error)}
            ressalva="Nenhum ativo desapareceu. O que falhou foi a leitura desta lista."
            aoTentarDeNovo={renovar}
          />
        )}

        {estado === 'vazio' && (
          <Vazio
            titulo="A biblioteca ainda está vazia"
            explicacao="Cada peça produzida no Estúdio, e cada build observado da fábrica externa, é guardado aqui com procedência, medidas e direitos."
          />
        )}

        {estado === 'vazio_apos_filtro' && (
          <VazioAposFiltro
            universo={universo ?? 0}
            aoLimpar={() => mudarFiltros(FILTROS_VAZIOS)}
          />
        )}

        {estado === 'com_dados' && (
          <>
            <Grade assets={assets} densidade={densidade} aoRenovar={renovar} />
            {(offset > 0 || total > offset + assets.length) && (
              <div className="flex items-center justify-between gap-3">
                <Button
                  variant="outline"
                  onClick={() => setOffset(Math.max(0, offset - PAGINA))}
                  disabled={offset === 0}
                >
                  Página anterior
                </Button>
                <p className="text-[12px] text-muted-foreground" role="status">
                  Mostrando {offset + 1} a {offset + assets.length} de {total} neste recorte.
                </p>
                <Button
                  variant="outline"
                  onClick={() => setOffset(offset + PAGINA)}
                  disabled={offset + assets.length >= total}
                >
                  Próxima página
                </Button>
              </div>
            )}
          </>
        )}
      </Corpo>
    </Layout>
  );
};

export default BibliotecaPage;
