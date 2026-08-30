/**
 * `/criativos/laboratorio` — onde uma receita é criada e conferida antes de virar peça.
 *
 * ⚠️ Não confundir com `/criativos/novo`. Aquela rota cria uma PEÇA a partir de um
 * briefing; esta cria a RECEITA que várias peças reusam. Se o operador achar que
 * está fazendo uma coisa enquanto faz a outra, ele publica a errada.
 *
 * Casca fina, como `JobPage` e `AtivoPage`: lê, decide entre os quatro estados e
 * delega. A regra toda mora em `laboratorio/receita.ts`, sem React.
 */
import React from 'react';

import { CabecalhoDoEstudio, Corpo } from '@/components/criativos/comum/Painel';
import { Carregando, ErroDeLeitura } from '@/components/criativos/comum/Estados';
import { Laboratorio } from '@/components/criativos/laboratorio/Laboratorio';
import { useParqueCriativo } from '@/hooks/useParqueCriativo';
import { codigoDaFalha, mensagemDaFalha } from '@/lib/criativosApi';

function quandoLido(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? 'momento não registrado'
    : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

const LaboratorioPage: React.FC = () => {
  const { parque, carregando, erro, recarregar } = useParqueCriativo();

  return (
    <div className="min-h-screen bg-background">
      <CabecalhoDoEstudio
        kicker="Estúdio Criativo"
        titulo="Laboratório de Templates"
        proposito="Monte uma receita, veja o que ela produziria e o que o canal exige, antes de gastar."
        voltar={{ para: '/criativos', rotulo: 'Estúdio' }}
        situacao={
          parque ? (
            <span>
              Catálogo lido em {quandoLido(parque.lidoEm)}
              {parque.naoLidas.length > 0 && (
                <>
                  {' · '}
                  <span className="text-warning">
                    {parque.naoLidas.length} parte
                    {parque.naoLidas.length > 1 ? 's' : ''} do catálogo não respondeu
                  </span>
                </>
              )}
            </span>
          ) : undefined
        }
      />

      <Corpo>
        {carregando && <Carregando rotulo="Carregando o catálogo do parque criativo" linhas={6} />}

        {!carregando && erro && (
          <ErroDeLeitura
            mensagem={mensagemDaFalha(erro)}
            codigo={codigoDaFalha(erro)}
            ressalva="Sem o catálogo não há Laboratório: montar uma receita com uma lista escrita à mão faria a tela oferecer o que o motor não executa."
            aoTentarDeNovo={recarregar}
          />
        )}

        {!carregando && !erro && parque && <Laboratorio parque={parque} />}
      </Corpo>
    </div>
  );
};

export default LaboratorioPage;
