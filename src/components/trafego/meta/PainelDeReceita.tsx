/**
 * O seletor de receita (`F03`).
 *
 * ## ⚠️ SEM PROVA NÃO É SEM ESCOLHA
 *
 * `receitas.py` fixa o padrão desta lane: "compilar e validar continuam
 * ABERTOS, porque `validate_only` não cria nada e é por ele que a prova externa
 * é obtida; o que fecha é CRIAR". Uma receita com `criar_liberado: false`
 * continua selecionável aqui — o operador monta o plano, vê o payload exato e
 * pede a validação, e é a resposta da Meta que promove a receita. Desabilitá-la
 * tornaria a lacuna permanente: sem poder validar, a prova nunca apareceria.
 *
 * O que a tela DEVE fazer é dizer, na hora da escolha, que criar está fechado e
 * por quê. Uma receita apresentada como disponível e recusada pela rota é pior
 * do que uma receita ausente.
 */
import React from 'react';
import { CircleCheck, Lock } from 'lucide-react';

import { BlocoDeEvidencia, ChipDeEstado, LinhaDeFato } from '@/components/trafego/bancada';

import { GrupoDeEscolha } from './primitivas';
import type { ReceitaMetaV2 } from '@/lib/pautadorApi';

export const PainelDeReceita: React.FC<{
  receitas: readonly ReceitaMetaV2[];
  /** Por que o catálogo não foi lido. Ausência de catálogo NÃO vira "nenhuma
   *  receita": a bancada continua com a receita padrão e diz isso. */
  erroDoCatalogo: string | null;
  escolhida: string;
  onEscolher: (id: string) => void;
}> = ({ receitas, erroDoCatalogo, escolhida, onEscolher }) => {
  const receita = receitas.find((item) => item.id === escolhida) ?? null;

  return (
    <div className="space-y-3">
      <p className="kicker text-primary">Resultado da campanha</p>
      {receitas.length > 0 ? (
        <GrupoDeEscolha<string>
          rotuloAcessivel="Receita da campanha"
          valor={escolhida}
          colunas="grid-cols-1"
          onEscolher={onEscolher}
          opcoes={receitas.map((item) => ({
            id: item.id,
            nome: item.rotulo,
            detalhe: (
              <>
                {item.exige_fonte_de_conversao ? 'Encontrar pessoas que realizam uma ação no site.' : 'Levar pessoas para ler a sua página.'}
                <span className="mt-1 block">
                  {item.criar_liberado
                    ? 'Disponível para preparação'
                    : 'Preparar e validar. Criação ainda indisponível.'}
                </span>
              </>
            ),
            // ⚠️ NUNCA `desabilitada`. Ver o cabeçalho deste arquivo.
          }))}
        />
      ) : (
        <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
          O catálogo de receitas não foi lido{erroDoCatalogo ? `: ${erroDoCatalogo}` : '.'}{' '}
          A bancada segue com a receita de tráfego provada, e nenhuma outra combinação pode ser
          escolhida enquanto o catálogo não responder.
        </p>
      )}

      <details className="text-sm"><summary className="cursor-pointer py-2 text-muted-foreground">Detalhes da configuração</summary>
      <BlocoDeEvidencia
        titulo="O que a receita fixa nesta campanha"
        tom={receita?.criar_liberado ? 'verificado' : 'info'}
        acao={receita ? (
          <ChipDeEstado
            glifo={receita.criar_liberado ? CircleCheck : Lock}
            palavra={receita.criar_liberado ? 'criar liberado' : 'criar fechado'}
            descricao={receita.criar_liberado
              ? 'esta receita admite criação; a conta e o plano ainda precisam ser validados'
              : 'compilar e validar continuam abertos; é a validação que produz a prova que falta'}
            tom={receita.criar_liberado ? 'bom' : 'atencao'}
          />
        ) : undefined}
      >
        <LinhaDeFato
          rotulo="Objetivo"
          valor={receita ? `${receita.rotulo} (${receita.objetivo})` : 'Tráfego (OUTCOME_TRAFFIC)'}
          fonte={receita ? 'o registro de receitas do backend' : 'a receita provada'}
        />
        <LinhaDeFato
          rotulo="Otimização"
          valor={receita?.otimizacao ?? 'LANDING_PAGE_VIEWS'}
          fonte={receita ? 'o registro de receitas do backend' : 'a receita provada'}
        />
        <LinhaDeFato rotulo="Compra" valor="Leilão (AUCTION)" fonte="a receita provada" />
        <LinhaDeFato
          rotulo="Exige fonte de conversão"
          valor={receita ? (receita.exige_fonte_de_conversao ? 'Sim' : 'Não') : 'Não'}
          fonte="o registro de receitas do backend"
        />
        <LinhaDeFato
          rotulo="Mensuração admitida"
          valor={receita
            ? receita.propositos_de_mensuracao
              .map((item) => (item === 'OPTIMIZE' ? 'otimizar' : 'relatar')).join(' · ')
            : 'relatar'}
          fonte="o registro de receitas do backend"
        />
        <LinhaDeFato
          rotulo="Nível de prova"
          valor={receita?.prova ?? null}
          fonte="o registro de receitas do backend"
          ausencia="catálogo não lido"
        />
        {receita?.motivo_sem_prova && <p className="text-sm text-muted-foreground">{receita.motivo_sem_prova}</p>}
        {/* ⚠️ Categoria especial: a tela AFIRMA a ausência delas, e não existe
            caminho para declarar uma. O backend recusa qualquer categoria com
            META_SPECIAL_CATEGORY_RECIPE_UNPROVEN — um seletor aqui ofereceria
            uma escolha que a rota nega. */}
        <LinhaDeFato
          rotulo="Categoria especial"
          valor="Nenhuma · a lista viaja vazia"
          fonte="você, agora"
        />
        <LinhaDeFato rotulo="Estado ao nascer" valor="PAUSED" fonte="a receita provada" />
      </BlocoDeEvidencia></details>

      {receita && !receita.criar_liberado && (
        <div className="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
          <div className="max-w-[74ch] space-y-2 text-sm leading-relaxed text-pretty text-foreground">
            <p><strong>Você pode configurar e validar esta opção.</strong></p>
            <p className="text-muted-foreground">
              A criação desta opção ainda precisa ser liberada no servidor.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
