/**
 * A FORMA de cada sintoma — glifo e tom, sem uma linha de JSX.
 *
 * Mora fora do componente de item porque o sino também precisa dela, e o sino
 * não precisa da linha inteira: importar `ItemDeAtencao` só para pegar um
 * ícone arrastaria o botão de expansão, a lista de evidência e o link externo
 * para dentro da moldura da aplicação, que está montada em toda página.
 *
 * A cor é o TERCEIRO sinal, nunca o primeiro: o glifo dá a forma, a palavra dá
 * o nome (no cabeçalho do grupo e no nome acessível do item), e a descrição diz
 * o que aquele nome afirma. Um print em preto e branco comunica o mesmo estado.
 */
import type React from 'react';
import {
  Ban,
  CircleDashed,
  CircleHelp,
  CircleOff,
  CircleSlash,
  Clock,
  Eye,
  MousePointerClick,
  TriangleAlert,
  WifiOff,
} from 'lucide-react';

import type { Tom } from '@/components/trafego/inventario/Selos';

import type { Sintoma } from './projecao';

type Glifo = React.ComponentType<{ className?: string }>;

/**
 * Glifo e tom por sintoma.
 *
 * A cor é o TERCEIRO sinal, nunca o primeiro: o glifo dá a forma, a palavra dá
 * o nome, a descrição diz o que aquele nome afirma. Um print em preto e branco
 * precisa comunicar o mesmo estado.
 */
const VISUAL: Record<Sintoma, { glifo: Glifo; tom: Tom }> = {
  ligada_sem_impressao: { glifo: Eye, tom: 'atencao' },
  ligada_sem_clique: { glifo: MousePointerClick, tom: 'atencao' },
  ligada_sem_medida: { glifo: CircleHelp, tom: 'atencao' },
  sincronizacao_falhou: { glifo: WifiOff, tom: 'ruim' },
  campanha_nao_encontrada: { glifo: CircleOff, tom: 'atencao' },
  estado_desconhecido: { glifo: CircleHelp, tom: 'atencao' },
  conta_nao_identificada: { glifo: CircleHelp, tom: 'atencao' },
  campanha_removida: { glifo: CircleSlash, tom: 'neutro' },
  conta_fora_de_escopo: { glifo: Ban, tom: 'neutro' },
  legado_nao_reconciliado: { glifo: CircleDashed, tom: 'neutro' },
  leitura_desatualizada: { glifo: Clock, tom: 'atencao' },
  condicao_nao_reconhecida: { glifo: TriangleAlert, tom: 'atencao' },
};

export function visualDoSintoma(sintoma: string): { glifo: Glifo; tom: Tom } {
  // Consulta tolerante: sintoma novo no servidor não pode derrubar a fila.
  return VISUAL[sintoma as Sintoma] ?? { glifo: TriangleAlert, tom: 'atencao' as Tom };
}
