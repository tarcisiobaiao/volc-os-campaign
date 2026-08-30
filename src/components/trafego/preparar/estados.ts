/**
 * Estados de reconciliação da aba Preparar.
 *
 * Só `reconciliacao` declarada pela fonte canônica decide o estado. Ausência
 * não vira `sem_campanha`. `campanhas_lancadas > 0` sem declaração impede
 * duplicar, mas não afirma vínculo confirmado.
 *
 * ⚠️ Nunca detectar FGTS ou Maquininha pelo nome.
 */
import {
  CircleAlert,
  CircleCheck,
  CircleDot,
  History,
  Lock,
  ShieldAlert,
} from 'lucide-react';
import type React from 'react';

import type { Tom } from '@/components/trafego/inventario/Selos';

import type { CandidatoNoQuadro } from '@/types/trafego';

import type {
  CandidatoPreparar,
  EstadoVisualDeReconciliacao,
} from '@/components/trafego/hub/contrato';

export function comoPreparar(c: CandidatoNoQuadro): CandidatoPreparar {
  return c;
}

export function estadoDeReconciliacao(c: CandidatoPreparar): EstadoVisualDeReconciliacao {
  if (!c.reconciliacao) return 'pendente';
  return c.reconciliacao.estado;
}

export interface FraseDeReconciliacao {
  estado: EstadoVisualDeReconciliacao;
  palavra: string;
  descricao: string;
  tom: Tom;
  glifo: React.ComponentType<{ className?: string }>;
  /** Se a montagem de campanha nova está permitida nesta linha. */
  podeMontar: boolean;
  /** Se o relançamento declarado está oferecido. */
  podeRelancar: boolean;
  acao: string;
}

export function fraseDeReconciliacao(c: CandidatoPreparar): FraseDeReconciliacao {
  const estado = estadoDeReconciliacao(c);
  const lancadas = c.campanhas_lancadas;

  switch (estado) {
    case 'vinculada':
      return {
        estado,
        palavra:
          lancadas == null
            ? 'campanha vinculada'
            : lancadas === 1
              ? '1 campanha no ar'
              : `${lancadas} campanhas no ar`,
        descricao:
          'este funil já tem campanha vinculada. Abrir o que existe evita um segundo ' +
          'lançamento do mesmo termo no mesmo leilão',
        tom: 'info',
        glifo: CircleDot,
        podeMontar: false,
        podeRelancar: false,
        acao: 'abrir o que existe',
      };
    case 'correspondencia_provavel':
      return {
        estado,
        palavra: 'correspondência provável',
        descricao:
          'há uma campanha na conta que parece ser deste funil, mas ninguém confirmou o vínculo. ' +
          'Confirme antes de montar outra',
        tom: 'atencao',
        glifo: CircleAlert,
        podeMontar: false,
        podeRelancar: false,
        acao: 'confirmar vínculo',
      };
    case 'conflito':
      return {
        estado,
        palavra: 'conflito',
        descricao:
          'há mais de uma leitura possível para este funil. A montagem fica bloqueada até a ' +
          'revisão — duas campanhas do mesmo termo competem no leilão',
        tom: 'ruim',
        glifo: ShieldAlert,
        podeMontar: false,
        podeRelancar: false,
        acao: 'abrir revisão',
      };
    case 'somente_historico':
      return {
        estado,
        palavra: 'somente histórico',
        descricao:
          'existe campanha deste funil só no histórico removido. Relançar é uma decisão ' +
          'declarada, não um convite automático',
        tom: 'atencao',
        glifo: History,
        podeMontar: false,
        podeRelancar: true,
        acao: 'relançar (declarado)',
      };
    case 'sem_campanha': {
      const podeMontar = c.reconciliacao?.pode_montar === true;
      const aviso = c.reconciliacao?.exige_confirmacao_humana === true;
      return {
        estado,
        palavra: aviso ? 'sem campanha — confirmação pendente' : 'sem campanha',
        descricao: aviso
          ? 'a prova não foi completa. A montagem segue liberada, mas este aviso permanece visível.'
          : 'nenhuma campanha deste funil está no ar. Pode montar.',
        tom: aviso ? 'atencao' : 'bom',
        glifo: aviso ? CircleAlert : CircleCheck,
        podeMontar,
        podeRelancar: false,
        acao: podeMontar ? 'montar campanha' : 'aguardar reconciliação',
      };
    }
    case 'pendente':
    default:
      return {
        estado: 'pendente',
        palavra: 'reconciliação ainda não concluída',
        descricao:
          lancadas != null && lancadas > 0
            ? 'há campanha lançada neste funil, mas o vínculo ainda não foi confirmado pela fonte canônica. A montagem fica bloqueada para não duplicar.'
            : 'a reconciliação não foi concluída. Sem essa declaração, a montagem fica bloqueada.',
        tom: 'atencao',
        glifo: Lock,
        podeMontar: false,
        podeRelancar: false,
        acao: 'aguardar reconciliação',
      };
  }
}

/** A tela oferece confirmação; não dispara escrita na conta de anúncio. */
export const CONFIRMAR_VINCULO_INDISPONIVEL =
  'A montagem fica bloqueada até alguém confirmar o vínculo. Esta tela não escreve na conta de anúncio.';

export const REVISAO_DE_CONFLITO =
  'A montagem está bloqueada enquanto houver conflito. Abra a revisão para decidir qual campanha permanece vinculada.';

export const RECONCILIACAO_PENDENTE =
  'A reconciliação ainda não foi concluída. Sem a declaração da fonte canônica, a montagem fica bloqueada.';

export const AVISO_CONFIRMACAO_PENDENTE =
  'A prova não foi completa. A montagem segue liberada, mas este aviso permanece visível.';

export { Lock };
