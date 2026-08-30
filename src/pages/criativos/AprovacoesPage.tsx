/**
 * `/criativos/aprovacoes` — a fila do que aguarda decisão.
 *
 * ## Por que a decisão acontece aqui e não numa modal
 *
 * Porque decidir exige olhar a peça, a procedência e os direitos ao mesmo tempo.
 * Uma modal cobre exatamente o que precisa ser olhado, e o DESIGN.md reserva
 * modal para o que bloqueia interação e exige uma decisão CURTA. Aqui a decisão
 * é o trabalho, não a interrupção dele.
 *
 * ## Por que cada item abre e fecha
 *
 * Porque uma fila com dez formulários abertos tem dez botões primários na
 * página, e o DESIGN.md permite um por região. Fechado, cada item é uma linha
 * de fila; aberto, é a região de decisão daquele ativo.
 */
import React from 'react';
import { ChevronDown } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { cn } from '@/lib/utils';
import { CabecalhoDoEstudio, Corpo, Secao } from '@/components/criativos/comum/Painel';
import { Carregando, ErroDeLeitura, Vazio } from '@/components/criativos/comum/Estados';
import { Preview } from '@/components/criativos/comum/Preview';
import { SeloDaAprovacao, SeloDeProcedencia } from '@/components/criativos/comum/Selo';
import { FormularioDeDecisao } from '@/components/criativos/aprovacoes/Decisao';
import { custoLegivel, dimensoes, instante, kindLegivel } from '@/components/criativos/comum/formato';
import { FILTROS_VAZIOS } from '@/components/criativos/biblioteca/filtros';
import { useCriativosBiblioteca, useDecidirAprovacao } from '@/hooks/useCriativosBiblioteca';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';
import type { AssetMaster } from '@/types/criativos';

const FILA = { ...FILTROS_VAZIOS, estado: 'aguardando' as const };

const ItemDaFila: React.FC<{ asset: AssetMaster; aoRenovar: () => void }> = ({
  asset,
  aoRenovar,
}) => {
  const [aberto, setAberto] = React.useState(false);
  const decidir = useDecidirAprovacao(asset.id);
  const idPainel = `fila-${asset.id}`;

  return (
    <li className="rounded-md border border-border bg-muted/30">
      <div className="flex items-start gap-3 p-3">
        <Preview
          url={asset.previewUrl ?? asset.posterUrl}
          alt={`${kindLegivel(asset.kind)} do trabalho ${asset.projetoTitulo}, slot ${asset.slot}, ${dimensoes(asset.largura, asset.altura)}`}
          aoRenovar={aoRenovar}
          className="h-20 w-20 shrink-0 rounded-sm border border-border"
          classNameImagem="h-20 w-20"
          denso
          motivoSemArquivo="Arquivo indisponível nesta leitura. A peça existe."
        />
        <div className="min-w-0 flex-1">
          <Link
            to={`/criativos/assets/${asset.id}`}
            className="block truncate text-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {asset.projetoTitulo}
          </Link>
          <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
            {kindLegivel(asset.kind)}, slot {asset.slot}, {dimensoes(asset.largura, asset.altura)}.
            Versão {asset.versao}. {custoLegivel(asset.procedencia.custoUsd)}. Criado em{' '}
            {instante(asset.criadoEm)}.
          </p>
          <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
            Motor {asset.procedencia.motor} {asset.procedencia.motorVersao}. Direitos:{' '}
            {asset.procedencia.licenca ?? 'licença não declarada'},{' '}
            {asset.procedencia.disclosure ?? 'sem disclosure declarado'}.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <SeloDaAprovacao decisao={asset.aprovacaoVigente?.decisao ?? null} />
            <SeloDeProcedencia procedencia={asset.procedenciaExecucao} />
          </div>
        </div>
        <button
          type="button"
          aria-expanded={aberto}
          aria-controls={idPainel}
          onClick={() => setAberto((v) => !v)}
          className={cn(
            'inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-md border border-input px-3 text-[13px] text-foreground',
            'transition-colors duration-150 ease-out hover:bg-muted/60',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          )}
        >
          {aberto ? 'Fechar' : 'Decidir'}
          <ChevronDown
            className={cn(
              'h-4 w-4 transition-transform duration-150 ease-out motion-reduce:transition-none',
              aberto && 'rotate-180',
            )}
            aria-hidden
          />
        </button>
      </div>
      {aberto && (
        <div id={idPainel} className="border-t border-border px-3 py-4">
          <FormularioDeDecisao
            prefixo={`fila-${asset.id}`}
            aprovavel
            enviando={decidir.isPending}
            erro={decidir.isError ? decidir.error : null}
            aoDecidir={(pedido) => decidir.mutate(pedido)}
          />
        </div>
      )}
    </li>
  );
};

const AprovacoesPage: React.FC = () => {
  const consulta = useCriativosBiblioteca(FILA, 0);
  const assets = consulta.data?.assets ?? [];
  const renovar = React.useCallback(() => void consulta.refetch(), [consulta]);

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Governança"
        titulo="Fila de aprovação"
        proposito="Peças prontas sem decisão registrada. Aprovar declara uma finalidade; pedir ajuste e rejeitar exigem motivo, porque quem recebe a peça de volta precisa saber o que corrigir."
        voltar={{ para: '/criativos', rotulo: 'Estúdio Criativo' }}
      />

      <Corpo>
        <Secao
          titulo="Aguardando revisão"
          descricao={
            consulta.isLoading
              ? 'Lendo a fila.'
              : `${consulta.data?.total ?? 0} ${(consulta.data?.total ?? 0) === 1 ? 'peça aguarda' : 'peças aguardam'} decisão.`
          }
        >
          {consulta.isLoading ? (
            <Carregando rotulo="Lendo a fila de aprovação" linhas={3} altura="h-28" />
          ) : consulta.isError ? (
            <ErroDeLeitura
              mensagem={mensagemDaFalha(consulta.error)}
              codigo={codigoDaFalha(consulta.error)}
              ressalva="Nenhuma decisão foi perdida. O que falhou foi a leitura da fila."
              aoTentarDeNovo={renovar}
            />
          ) : assets.length ? (
            <ul className="space-y-3">
              {assets.map((asset) => (
                <ItemDaFila key={asset.id} asset={asset} aoRenovar={renovar} />
              ))}
            </ul>
          ) : (
            <Vazio
              titulo="Nada aguardando decisão"
              explicacao="Toda peça produzida chega a esta fila sem decisão. Ela sai daqui quando alguém aprova para uma finalidade, pede ajuste ou rejeita."
            />
          )}
        </Secao>
      </Corpo>
    </Layout>
  );
};

export default AprovacoesPage;
