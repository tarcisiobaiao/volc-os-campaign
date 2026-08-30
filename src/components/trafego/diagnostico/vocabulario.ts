/**
 * O vocabulário da escada de entrega: glifo + palavra + descrição.
 *
 * A mesma lei dos selos do inventário. Nenhum estado desta tela é comunicado
 * por cor: o glifo dá a forma, a palavra dá o nome, e a descrição diz o que o
 * nome AFIRMA. `não apurado` e `sem impedimento` parecem vizinhos e são
 * opostos — um diz que a prova falhou, o outro que a prova passou.
 */
import {
  CircleCheck,
  CircleHelp,
  CircleOff,
  TriangleAlert,
  Banknote,
  Megaphone,
  Layers,
  FileText,
  Search,
  Crosshair,
  Target,
  Gavel,
  Wallet,
} from 'lucide-react';
import type React from 'react';

import type { Tom } from '@/components/trafego/inventario/Selos';
import type { EixoDeEntrega, EstadoDoDegrau, VereditoDaEscada } from '@/types/diagnostico';

type Glifo = React.ComponentType<{ className?: string }>;

/** Cada eixo, com a pergunta que ele responde. */
export const EIXO: Record<
  EixoDeEntrega,
  { rotulo: string; pergunta: string; glifo: Glifo }
> = {
  conta: {
    rotulo: 'Conta',
    pergunta: 'a conta de anúncio pode veicular alguma coisa?',
    glifo: Banknote,
  },
  campanha: {
    rotulo: 'Campanha',
    pergunta: 'a campanha está ligada e elegível?',
    glifo: Megaphone,
  },
  orcamento: {
    rotulo: 'Orçamento',
    pergunta: 'a verba está segurando a entrega?',
    glifo: Wallet,
  },
  grupo: {
    rotulo: 'Grupo',
    pergunta: 'há grupo ligado para pendurar anúncio e keyword?',
    glifo: Layers,
  },
  anuncio: {
    rotulo: 'Anúncio',
    pergunta: 'há anúncio aprovado para mostrar?',
    glifo: FileText,
  },
  keyword: {
    rotulo: 'Keyword',
    pergunta: 'as keywords disputam alguma consulta?',
    glifo: Search,
  },
  segmentacao: {
    rotulo: 'Segmentação',
    pergunta: 'o recorte deixa alguém ser alcançado?',
    glifo: Crosshair,
  },
  conversao: {
    rotulo: 'Conversão',
    pergunta: 'dá para saber o que a campanha produziu?',
    glifo: Target,
  },
  leilao: {
    rotulo: 'Leilão',
    pergunta: 'a campanha chegou a disputar, e ganhou quanto?',
    glifo: Gavel,
  },
};

export const ESTADO: Record<
  EstadoDoDegrau,
  { palavra: string; descricao: string; tom: Tom; glifo: Glifo }
> = {
  bloqueia: {
    palavra: 'impede',
    descricao: 'este degrau impede a entrega — resolver aqui vem antes de tudo acima',
    tom: 'ruim',
    glifo: CircleOff,
  },
  limita: {
    palavra: 'limita',
    descricao: 'a entrega acontece, e abaixo do que seria possível',
    tom: 'atencao',
    glifo: TriangleAlert,
  },
  ok: {
    palavra: 'sem impedimento',
    descricao: 'este degrau foi medido e não impede nada',
    tom: 'bom',
    glifo: CircleCheck,
  },
  nao_apurado: {
    palavra: 'não apurado',
    descricao:
      'a leitura deste degrau falhou — não é o mesmo que estar bem, e o que está ' +
      'acima dele não sustenta conclusão',
    tom: 'atencao',
    glifo: CircleHelp,
  },
};

/**
 * Consulta tolerante. O servidor pode ganhar um eixo ou um estado antes deste
 * pacote, e uma tela que apaga a escada inteira por causa de uma palavra
 * desconhecida é pior que uma que diz não reconhecer a palavra.
 */
export function eixoLegivel(valor: string): { rotulo: string; pergunta: string; glifo: Glifo } {
  return (
    EIXO[valor as EixoDeEntrega] ?? {
      rotulo: 'degrau não reconhecido',
      pergunta: `o sistema informou "${valor}", que esta versão da tela não conhece`,
      glifo: CircleHelp,
    }
  );
}

export function estadoLegivel(valor: string): {
  palavra: string;
  descricao: string;
  tom: Tom;
  glifo: Glifo;
} {
  return (
    ESTADO[valor as EstadoDoDegrau] ?? {
      palavra: 'estado não reconhecido',
      // ⚠️ Nunca `bom`. Estado que a tela não conhece degradando para "sem
      // impedimento" é a forma mais silenciosa de esta superfície mentir.
      descricao: `o sistema informou "${valor}", que esta versão da tela não conhece`,
      tom: 'atencao' as Tom,
      glifo: CircleHelp,
    }
  );
}

/** O veredito em uma frase de título, e o que ele afirma. */
export function fraseDoVeredito(v: VereditoDaEscada): {
  titulo: string;
  descricao: string;
  tom: Tom;
} {
  switch (v.tipo) {
    case 'bloqueada':
      return {
        titulo: `Não entrega — impedida em ${EIXO[v.eixo]?.rotulo.toLowerCase() ?? v.eixo}`,
        descricao:
          'a escada é causal: resolver este degrau vem antes de mexer em qualquer ' +
          'coisa acima dele.',
        tom: 'ruim',
      };
    case 'limitada':
      return {
        titulo: `Entrega abaixo do possível — ${EIXO[v.eixo]?.rotulo.toLowerCase() ?? v.eixo}`,
        descricao: 'nada impede a veiculação, e algo a está segurando.',
        tom: 'atencao',
      };
    case 'nao_apurado':
      return {
        titulo: `Não foi possível apurar — parou em ${EIXO[v.eixo]?.rotulo.toLowerCase() ?? v.eixo}`,
        descricao:
          'a leitura falhou neste degrau. O que está acima dele pode ter vindo, e ' +
          'não sustenta conclusão enquanto este não for lido.',
        tom: 'atencao',
      };
    case 'sem_impedimento':
    default:
      return {
        titulo: 'Nenhum impedimento medido',
        descricao:
          'todos os degraus foram apurados e nenhum impede ou limita a entrega ' +
          'nesta janela.',
        tom: 'bom',
      };
  }
}

/** A origem de uma evidência, dita — porque ela muda o que a evidência autoriza. */
export const ORIGEM: Record<string, { palavra: string; descricao: string }> = {
  conta: {
    palavra: 'lido na conta',
    descricao: 'a conta de anúncio respondeu este valor nesta leitura',
  },
  declarado: {
    palavra: 'declarado por nós',
    descricao: 'este valor é o que o VOLC O.S. registrou — pode estar mais velho que a conta',
  },
  derivado: {
    palavra: 'derivado',
    descricao: 'conta feita a partir de dois fatos lidos; vale o mais fraco dos dois',
  },
};

export function origemLegivel(valor: string): { palavra: string; descricao: string } {
  return (
    ORIGEM[valor] ?? {
      palavra: 'origem não reconhecida',
      descricao: `o sistema informou "${valor}", que esta versão da tela não conhece`,
    }
  );
}
