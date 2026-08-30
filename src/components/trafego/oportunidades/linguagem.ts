/**
 * A LÍNGUA das oportunidades — o que a tela diz, separado de como ela desenha.
 *
 * ## ⚠️ O PORTÃO DE CRIAÇÃO NÃO MUDOU. A PALAVRA MUDOU.
 *
 * A tela dizia "trava ABERTA/fechada" e imprimia, cru, o texto que o servidor
 * escreve para quem programa — com nome de função e nome de variável de
 * ambiente dentro. O operador não tem o que fazer com isso, e é justamente ele
 * quem precisa entender se um clique pode gastar dinheiro. O que este arquivo
 * faz é traduzir; o que ele NÃO faz é afrouxar coisa nenhuma: o estado continua
 * vindo do servidor, e nenhuma condição foi invertida.
 *
 * Estas funções moram fora do componente pelo mesmo motivo de `formato.tsx` no
 * inventário: são regras de APRESENTAÇÃO, e regra espalhada por dentro de cada
 * componente que resolver mostrar um estado já foi perdida uma vez.
 */
import type React from 'react';
import { CircleAlert, CircleCheck, CircleDot, Lock, ShieldAlert } from 'lucide-react';

import type { Tom } from '@/components/trafego/inventario/Selos';
import { AUSENTE } from '@/components/trafego/inventario/formato';
import type { CandidatoNoQuadro, EstadoDaTrava } from '@/types/trafego';

export interface FraseDoPortao {
  palavra: string;
  explicacao: string;
  tom: Tom;
  glifo: React.ComponentType<{ className?: string }>;
}

/**
 * O estado do portão de criação, dito para quem opera.
 *
 * ⚠️ O texto que o servidor manda em `explicacao` NÃO chega à tela. Ele é
 * escrito para quem programa (cita função e variável de ambiente), e o operador
 * não tem nem como agir sobre ele nem como entendê-lo no meio de uma
 * conferência. O que chega aqui são os BOOLEANOS, que são fato, traduzidos numa
 * frase que responde a única pergunta que importa: um clique nesta tela pode
 * criar campanha?
 */
export function fraseDoPortao(portao: EstadoDaTrava | null): FraseDoPortao {
  if (!portao) {
    return {
      palavra: 'permissão não verificada',
      explicacao:
        'Não foi possível confirmar se a publicação está liberada. Você pode continuar ' +
        'preparando, mas não avance para o envio até esta verificação voltar.',
      tom: 'atencao',
      glifo: CircleAlert,
    };
  }
  // `env_presente` é o estado durável da autorização neste processo.
  // `escrita_permitida` só fica true DENTRO do bloco `destravar()` executado
  // pela rota final; em repouso ele é false mesmo num servidor autorizado.
  // Usar o segundo campo aqui deixava a UI eternamente em "somente validação"
  // enquanto o backend já estava pronto para publicar.
  if (portao.env_presente || portao.escrita_permitida) {
    return {
      palavra: 'pronta para revisar e publicar',
      explicacao:
        'Esta lista apenas prepara. No cockpit, o Google confere o pedido e a sua ' +
        'confirmação final cria a campanha PAUSADA. Revise conta, orçamento e lance antes.',
      tom: 'ruim',
      glifo: ShieldAlert,
    };
  }
  return {
    palavra: 'publicação temporariamente fechada',
    explicacao:
      'Você pode montar e mandar o Google conferir o pedido. O envio final permanece ' +
      'indisponível até a permissão operacional deste servidor ser aberta.',
    tom: 'neutro',
    glifo: Lock,
  };
}


// ── a lista ─────────────────────────────────────────────────────────────────

export const COLUNAS = ['funil', 'keywords', 'volume/mês', 'procedência da mineração', 'estado'] as const;
export const NUMERICAS = new Set<string>(['keywords', 'volume/mês']);

/** Volume abreviado. `null` continua `—`: ausência nunca vira zero. */
export function compacto(n: number | null): string {
  if (n == null) return AUSENTE;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.', ',')}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace('.', ',')}k`;
  return new Intl.NumberFormat('pt-BR').format(n);
}

export interface EstadoDoCandidato {
  pronto: boolean;
  jaNoAr: number;
  chip: { palavra: string; descricao: string; tom: Tom; glifo: React.ComponentType<{ className?: string }> };
}

/**
 * O que este funil é AGORA — e por que o convite não é sempre o mesmo.
 *
 * ⚠️ O quadro oferecia "montar campanha" para funis que JÁ tinham campanha no
 * ar: ele não sabia. Doutrina P7 — um termo, uma campanha; duas competem no
 * mesmo leilão e encarecem uma à outra. O caminho continua aberto, mas a linha
 * diz o que existe ANTES de convidar.
 */
export function estadoDoCandidato(p: CandidatoNoQuadro): EstadoDoCandidato {
  const jaNoAr = p.campanhas_lancadas ?? 0;
  const pronto = p.tem_cluster && p.keywords_para_anuncio > 0;
  if (!pronto) {
    return {
      pronto,
      jaNoAr,
      chip: {
        palavra: 'sem keywords mineradas',
        descricao:
          'este funil não tem cluster de keywords triadas; passe-o pela mineração no ' +
          'Pautador antes de anunciar',
        tom: 'atencao',
        glifo: CircleAlert,
      },
    };
  }
  if (jaNoAr > 0) {
    return {
      pronto,
      jaNoAr,
      chip: {
        palavra: jaNoAr === 1 ? '1 campanha no ar' : `${jaNoAr} campanhas no ar`,
        descricao:
          'este funil já produziu campanha. Um segundo lançamento do mesmo termo compete ' +
          'com o primeiro no mesmo leilão',
        tom: 'info',
        glifo: CircleDot,
      },
    };
  }
  return {
    pronto,
    jaNoAr,
    chip: {
      palavra: 'pronto',
      descricao: 'tem página publicada e cluster de keywords triadas para anúncio',
      tom: 'bom',
      glifo: CircleCheck,
    },
  };
}
