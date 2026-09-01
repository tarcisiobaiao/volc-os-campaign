/**
 * `/criativos/assets/:assetId` — a ficha de um ativo.
 *
 * ## As duas frases que esta tela existe para não achatar
 *
 * 1. **"uso não apurado" não é "sem uso".** Lista vazia com `usoApurado: false`
 *    significa que ninguém foi olhar; com `true`, que alguém olhou e não achou.
 *    Um ativo que parece livre e está no ar em três campanhas é a diferença
 *    entre arquivar e derrubar anúncio.
 * 2. **"aguardando revisão" não é "reprovado".** `aprovacaoVigente: null` é
 *    ausência de decisão, e a maioria dos ativos passa a maior parte da vida
 *    assim.
 *
 * ⚠️ `insumoHash` aparece rotulado como HASH DO INSUMO, nunca como prompt. O
 * prompt cru não chega ao browser por decisão de contrato, e apresentar o hash
 * como se fosse o texto faria a tela mentir sobre o que está mostrando.
 */
import React from 'react';

import { Layout } from '@/components/layout/Layout';
import { CabecalhoDoEstudio, Corpo, Ficha, Secao } from '@/components/criativos/comum/Painel';
import { Carregando, ErroDeLeitura } from '@/components/criativos/comum/Estados';
import { Preview } from '@/components/criativos/comum/Preview';
import { SeloDaAprovacao, SeloDoJob, SeloDeProcedencia } from '@/components/criativos/comum/Selo';
import { FormularioDeDecisao } from '@/components/criativos/aprovacoes/Decisao';
import {
  bytesLegiveis,
  custoLegivel,
  destinoLegivel,
  dimensoes,
  duracaoLegivel,
  hashCurto,
  instante,
  kindLegivel,
  mimeLegivel,
} from '@/components/criativos/comum/formato';
import { useCriativosAsset, useDecidirAprovacao } from '@/hooks/useCriativosBiblioteca';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';
import { ROTULO_DA_APROVACAO } from '@/types/criativos';
import { useParams } from 'react-router-dom';

const AtivoPage: React.FC = () => {
  const { assetId } = useParams<{ assetId: string }>();
  const consulta = useCriativosAsset(assetId);
  const decidir = useDecidirAprovacao(assetId);
  const renovar = React.useCallback(() => void consulta.refetch(), [consulta]);

  if (consulta.isLoading) {
    return (
      <Layout>
        <CabecalhoDoEstudio
          kicker="Ativo"
          titulo="Carregando o ativo"
          proposito="Lendo procedência, medidas, direitos e decisões deste ativo."
          voltar={{ para: '/criativos/biblioteca', rotulo: 'Biblioteca' }}
        />
        <Corpo>
          <Carregando rotulo="Lendo o ativo" linhas={3} altura="h-32" />
        </Corpo>
      </Layout>
    );
  }

  if (consulta.isError || !consulta.data) {
    return (
      <Layout>
        <CabecalhoDoEstudio
          kicker="Ativo"
          titulo="Ativo não lido"
          proposito="A leitura deste ativo não chegou. Isso não significa que ele deixou de existir."
          voltar={{ para: '/criativos/biblioteca', rotulo: 'Biblioteca' }}
        />
        <Corpo>
          <ErroDeLeitura
            mensagem={mensagemDaFalha(consulta.error)}
            codigo={codigoDaFalha(consulta.error)}
            aoTentarDeNovo={renovar}
          />
        </Corpo>
      </Layout>
    );
  }

  const { asset, versoes, aprovacoes, job } = consulta.data;
  const p = asset.procedencia;

  return (
    <Layout>
      <CabecalhoDoEstudio
        kicker="Ativo"
        titulo={asset.projetoTitulo}
        proposito={`${kindLegivel(asset.kind)} do slot ${asset.slot}, versão ${asset.versao}. Toda medida ausente aparece como não medida, nunca como zero.`}
        voltar={{ para: '/criativos/biblioteca', rotulo: 'Biblioteca' }}
        situacao={
          <div className="flex flex-wrap items-center gap-2">
            <SeloDaAprovacao decisao={asset.aprovacaoVigente?.decisao ?? null} />
            <SeloDeProcedencia procedencia={asset.procedenciaExecucao} />
            <SeloDoJob estado={job.estado} />
          </div>
        }
      />

      <Corpo className="space-y-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Secao titulo="Prévia" descricao="Arquivo assinado pelo servidor, com validade curta.">
            <Preview
              url={asset.previewUrl ?? asset.posterUrl}
              alt={`${kindLegivel(asset.kind)} do trabalho ${asset.projetoTitulo}, slot ${asset.slot}, ${dimensoes(asset.largura, asset.altura)}`}
              aoRenovar={renovar}
              className="w-full rounded-md border border-border"
              classNameImagem="mx-auto max-h-[28rem] w-auto max-w-full"
            />
            {asset.previewUrl && (
              <a
                href={asset.previewUrl}
                download
                className="mt-3 inline-flex min-h-9 items-center rounded-md border border-input px-3 text-[13px] text-foreground transition-colors duration-150 ease-out hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                Baixar o arquivo
              </a>
            )}
          </Secao>

          <Secao titulo="Ficha técnica" descricao="O que foi medido no arquivo final.">
            <Ficha
              itens={[
                { rotulo: 'Tipo', valor: kindLegivel(asset.kind) },
                { rotulo: 'Formato do arquivo', valor: mimeLegivel(asset.mime) },
                { rotulo: 'Dimensões', valor: dimensoes(asset.largura, asset.altura) },
                { rotulo: 'Tamanho', valor: bytesLegiveis(asset.bytesTotais) },
                { rotulo: 'Duração', valor: duracaoLegivel(asset.duracaoMs) },
                { rotulo: 'Slot', valor: asset.slot },
                { rotulo: 'Versão', valor: `versão ${asset.versao}` },
                {
                  rotulo: 'Hash do conteúdo',
                  valor: (
                    <span className="font-mono" title={asset.contentHash}>
                      {hashCurto(asset.contentHash)}
                    </span>
                  ),
                },
                { rotulo: 'Criado em', valor: instante(asset.criadoEm) },
                {
                  rotulo: 'Arquivado em',
                  valor: asset.arquivadoEm ? instante(asset.arquivadoEm) : 'não arquivado',
                },
              ]}
            />
          </Secao>
        </div>

        <Secao
          titulo="Procedência"
          descricao="Quem produziu, com o quê, sob qual identidade e a que custo."
        >
          <Ficha
            itens={[
              { rotulo: 'Motor', valor: `${p.motor} ${p.motorVersao}` },
              {
                // ⚠️ TRÊS valores, não dois. `procedenciaExecucao` é
                // `ProcedenciaDeExecucao | null`, e o `null` significa **não
                // apurada**: o servidor não leu o job desta peça. A versão
                // anterior ramificava `=== 'observado' ? A : B`, então o `null`
                // caía no `else` e esta ficha afirmava "Produzida pelo motor do
                // VOLC O.S." para um ativo cuja autoria ninguém verificou —
                // exatamente a frase que o comentário do contrato existe para
                // impedir. Com `strict: false` no tsconfig, o compilador não
                // acusa; a guarda tem de ser esta.
                rotulo: 'Execução',
                valor:
                  asset.procedenciaExecucao === 'observado'
                    ? 'Observada. O VOLC O.S. leu um build externo, não o produziu.'
                    : asset.procedenciaExecucao === 'volc_os'
                      ? 'Produzida pelo motor do VOLC O.S.'
                      : 'Não apurada. O servidor não informou quem executou este trabalho, e ausência de resposta não é declaração de autoria.',
              },
              {
                rotulo: 'Hash do insumo',
                valor: (
                  <span className="font-mono" title={p.insumoHash}>
                    {hashCurto(p.insumoHash)}
                  </span>
                ),
              },
              {
                rotulo: 'Brand pack',
                valor: p.brandPackId
                  ? `${p.brandPackId}, versão ${p.brandPackVersao ?? 'não registrada'}`
                  : 'nenhum',
              },
              { rotulo: 'Custo', valor: custoLegivel(p.custoUsd) },
              { rotulo: 'Licença', valor: p.licenca ?? 'não declarada' },
              { rotulo: 'Crédito', valor: p.credito ?? 'não declarado' },
              { rotulo: 'Disclosure', valor: p.disclosure ?? 'não declarado' },
              {
                rotulo: 'Conteúdo sintético',
                valor: p.sintetico
                  ? 'Sim. Gerado por modelo.'
                  : 'Não declarado como sintético.',
              },
              { rotulo: 'Registrado em', valor: instante(p.criadoEm) },
            ]}
          />
          <p className="mt-3 text-[12px] leading-relaxed text-muted-foreground">
            O hash do insumo é a prova de que dois pedidos foram iguais. Ele não é o texto do
            pedido: o prompt não chega ao navegador por decisão de contrato.
          </p>
        </Secao>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Secao
            titulo="Usos conhecidos"
            descricao="Onde este ativo apareceu, segundo o que já foi apurado."
          >
            {asset.usos.length ? (
              <ul className="space-y-2">
                {asset.usos.map((uso, i) => (
                  <li key={`${i}-${uso.referencia}`} className="border-b border-border/60 pb-2 last:border-b-0">
                    <p className="text-[13px] text-foreground">{destinoLegivel(uso.destino)}</p>
                    <p className="text-[12px] text-muted-foreground">
                      Referência {uso.referencia}, em {instante(uso.em)}.
                    </p>
                  </li>
                ))}
              </ul>
            ) : asset.usoApurado ? (
              <p className="text-[13px] leading-relaxed text-foreground">
                Uso apurado e nenhum encontrado. Alguém foi olhar e não achou este ativo em uso.
              </p>
            ) : (
              <p className="text-[13px] leading-relaxed text-foreground">
                Uso não apurado. Ninguém verificou onde este ativo está sendo usado, e isso não é o
                mesmo que dizer que ele não está em uso.
              </p>
            )}
          </Secao>

          <Secao titulo="Versões" descricao="Correção não sobrescreve: cada versão continua inteira.">
            {versoes.length ? (
              <ul className="space-y-2">
                {versoes.map((v) => (
                  <li key={v.id} className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-2 last:border-b-0">
                    <span className="text-[13px] text-foreground">
                      Versão {v.versao}, {dimensoes(v.largura, v.altura)}, {instante(v.criadoEm)}
                    </span>
                    <SeloDaAprovacao decisao={v.aprovacaoVigente?.decisao ?? null} />
                    {v.id === asset.id && (
                      <span className="text-[12px] text-muted-foreground">versão aberta</span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] leading-relaxed text-muted-foreground">
                Nenhuma outra versão registrada. Esta é a única.
              </p>
            )}
          </Secao>
        </div>

        <Secao
          titulo="Aprovações"
          descricao="Histórico de decisões. Uma decisão revogada continua no registro."
        >
          {aprovacoes.length ? (
            <ul className="mb-5 space-y-2">
              {aprovacoes.map((a) => (
                <li key={a.id} className="border-b border-border/60 pb-2 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeloDaAprovacao decisao={a.decisao} />
                    <span className="text-[13px] text-foreground">
                      {ROTULO_DA_APROVACAO[a.decisao].palavra} para {a.finalidade}, versão {a.versao}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
                    Por {a.atorNome ?? 'ator não identificado'} em {instante(a.decididoEm)}.
                    {a.motivo ? ` Motivo: ${a.motivo}.` : ' Sem motivo registrado.'}
                    {a.revogadaEm ? ` Revogada em ${instante(a.revogadaEm)}.` : ''}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-5 text-[13px] leading-relaxed text-muted-foreground">
              Nenhuma decisão registrada para este ativo. Aguardando revisão não é reprovação.
            </p>
          )}

          <FormularioDeDecisao
            prefixo={`ativo-${asset.id}`}
            aprovavel
            enviando={decidir.isPending}
            erro={decidir.isError ? decidir.error : null}
            aoDecidir={(pedido) => decidir.mutate(pedido)}
          />
        </Secao>
      </Corpo>
    </Layout>
  );
};

export default AtivoPage;
