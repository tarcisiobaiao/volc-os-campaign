/**
 * A árvore do canal, dita com o vocabulário do próprio canal.
 *
 * ⚠️ A ausência aqui tem TRÊS causas diferentes, e colapsá-las num "integração
 * não configurada" único foi o defeito que este arquivo carregava:
 *
 *  · o Hub **não opera** este canal (Vídeo, Shopping — sem manifesto);
 *  · o Hub opera e **não lê as filhas** deste canal (Display, Demand Gen, PMax
 *    — a camada comum vem, lance e URL não, porque só o Search tem adaptador);
 *  · a tela **ainda não sabe**, porque navegou sem manifesto em mãos.
 *
 * As três levam a lugares distintos: a primeira ao painel do Google, a segunda
 * a quem cuida do Hub, a terceira a esperar a leitura. Uma frase só para as três
 * manda o operador para o lugar errado em dois casos de cada três.
 */
import React from 'react';

import type { ManifestoDeCanal } from '@/types/trafego';

import { capacidadesDoCanal } from '@/components/trafego/canal/capacidades';

import { perfilDoCanal, rotuloDoNo, type AbaDaCampanha } from './perfilDeCanal';
import type { CanalDoHub, RedeDoHub } from './contrato';

const RegiaoVazia: React.FC<{ titulo: string; frase: string }> = ({ titulo, frase }) => (
  <div className="rounded-md border border-dashed border-border px-4 py-6">
    <h3 className="font-display text-base font-semibold">{titulo}</h3>
    <p className="mt-2 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
      {frase} Nenhum número é inventado aqui.
    </p>
  </div>
);

const O_QUE_A_ABA_MOSTRARIA: Record<AbaDaCampanha, string> = {
  resumo: 'o resumo',
  estrutura: 'a estrutura',
  criativos: 'os criativos (RSA, anúncio ou asset) deste canal',
  segmentacao: 'a segmentação (keywords, públicos ou sinais) deste canal',
  desempenho: 'a entrega medida deste canal, com a hora em que foi lida',
  recomendacoes: 'recomendações com evidência, nunca palpite',
  historico: 'o histórico de estados observados',
};

export const EstruturaDoCanal: React.FC<{
  rede: RedeDoHub;
  canal: CanalDoHub | null;
  aba: AbaDaCampanha;
  /**
   * O manifesto do backend, quando a tela o tem. `undefined` = ainda não sabe;
   * `null` = o backend AFIRMA que não há manifesto para este canal.
   */
  manifesto?: ManifestoDeCanal | null;
}> = ({ rede, canal, aba, manifesto }) => {
  const perfil = perfilDoCanal(rede, canal);
  // ⚠️ `undefined` (ainda não sei) é tratado AQUI, e a tradução de manifesto em
  // capacidade fica com `capacidadesDoCanal` — a mesma função que a página
  // canônica já usa. Duas traduções do mesmo manifesto divergiriam no primeiro
  // ajuste, e a que estivesse errada seria a que ninguém abre.
  const naoSabe = manifesto === undefined;
  const capacidade = naoSabe ? null : capacidadesDoCanal(manifesto ?? null);
  const oQue = O_QUE_A_ABA_MOSTRARIA[aba];

  // ── o Hub não opera este canal ─────────────────────────────────────────
  //
  // Afirmação, e não falta de dado. É o que impede a tela de prometer que um
  // dia isto se preenche sozinho para Vídeo e Shopping.
  if (capacidade?.tipo === 'nao_operado') {
    return (
      <RegiaoVazia
        titulo={`${perfil.rotulo} não é operado pelo Hub`}
        frase={
          `Campanhas de ${perfil.rotulo} aparecem no inventário porque a conta ` +
          `pode tê-las, e escondê-las seria mentir sobre o que está gastando. ` +
          `O que existe delas se opera no painel do Google.`
        }
      />
    );
  }

  if (aba === 'estrutura') {
    // A árvore é vocabulário de tela e vale mesmo sem leitura das filhas: ela
    // diz quantos degraus o canal tem e como chamá-los, não quantas linhas há.
    return (
      <>
        <ol className="space-y-0 border border-border bg-card">
          {perfil.estrutura.map((no, i) => (
            <li
              key={no}
              className="flex items-baseline gap-3 border-b border-border px-4 py-3 last:border-b-0"
            >
              <span className="tabular w-6 text-[11px] text-muted-foreground">{i + 1}</span>
              <div>
                <p className="text-[13px] font-medium">{rotuloDoNo(no)}</p>
                {i < perfil.estrutura.length - 1 && (
                  <p className="text-[11px] text-muted-foreground">
                    abaixo: {rotuloDoNo(perfil.estrutura[i + 1])}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
        {!perfil.leituraProfunda && (
          <p className="mt-3 max-w-[68ch] text-[12px] leading-relaxed text-muted-foreground">
            Esta é a forma da árvore, não o conteúdo dela. A leitura das
            entidades abaixo da campanha ainda não está ligada para{' '}
            {perfil.rotulo} — o que falta aqui é ausência de leitura, não
            ausência de campanha.
          </p>
        )}
      </>
    );
  }

  if (aba === 'resumo') {
    return (
      <p className="max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
        Estrutura deste canal: {perfil.fraseDaEstrutura}.
        {!perfil.leituraProfunda &&
          ' A leitura das entidades abaixo da campanha ainda não está ligada neste canal; o que falta abaixo não é zero, é ausência.'}
      </p>
    );
  }

  if (perfil.leituraProfunda) {
    if (aba === 'historico') {
      return (
        <p className="max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
          O histórico desta campanha aparece quando a leitura traz eventos. Sem evento, esta
          região fica vazia de propósito.
        </p>
      );
    }
    return (
      <RegiaoVazia
        titulo="Ainda sem leitura para esta aba"
        frase={`Esta aba mostraria ${oQue}, e a leitura dela ainda não chegou.`}
      />
    );
  }

  return (
    <RegiaoVazia
      titulo="Leitura deste canal ainda não ligada"
      frase={
        `Esta aba mostraria ${oQue}. O Hub já lê a camada comum de ` +
        `${perfil.rotulo} — estado, orçamento e entrega —, e ainda não lê as ` +
        `entidades abaixo da campanha.`
      }
    />
  );
};

export default EstruturaDoCanal;
