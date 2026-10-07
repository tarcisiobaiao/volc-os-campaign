/**
 * #7 · ausência de impressão não pode APAGAR a campanha da fila de atenção.
 *
 * `sintomaDaCampanha` fazia, para uma campanha ENABLED com leitura presente:
 *
 *     const imp = campanha.entrega.impressoes;
 *     if (imp == null) return null;      // ← saía da fila
 *
 * O comentário ao lado dizia "impressões não medidas → não afirma nada (regra
 * B: null não é zero)". Está certo sobre não afirmar; só que "não afirmar
 * nada" e "sumir da aba que responde o que quer algo de mim hoje" são a mesma
 * coisa na tela. Uma campanha LIGADA com métrica parcial é exatamente o caso
 * que pede um olho — ela pode estar gastando, e o número não veio.
 *
 * O ramo `ligada_sem_medida` já existe para "não há leitura nenhuma". Falta o
 * irmão: houve leitura, e ela veio incompleta.
 */
import { describe, expect, it } from 'vitest';

import {
  SINTOMAS,
  familiaDoSintoma,
  sintomaDaCampanha,
} from '@/components/trafego/atencao/projecao';
import { visualDoSintoma } from '@/components/trafego/atencao/visual';
import { campanhaSaudavel, maquininha } from '@/components/trafego/inventario/fixtureDeProvas';

describe('#7 · leitura parcial de entrega tem sintoma próprio', () => {
  it('ligada, com leitura, e sem impressão medida NÃO sai da fila', () => {
    const parcial = {
      ...maquininha,
      entrega: { ...maquininha.entrega, impressoes: null },
    };
    expect(sintomaDaCampanha(parcial)).toBe('ligada_com_entrega_parcial');
  });

  it('o sintoma novo tem frase, próxima ação, família e forma', () => {
    const d = SINTOMAS.ligada_com_entrega_parcial;
    expect(d.titulo).toBeTruthy();
    expect(d.proximaAcao).toBeTruthy();
    expect(d.escopo).toBe('campanha');
    expect(familiaDoSintoma('ligada_com_entrega_parcial')).toBe('entrega');
    expect(visualDoSintoma('ligada_com_entrega_parcial').tom).not.toBe('bom');
  });

  it('não confunde com `ligada_sem_medida`: lá não houve leitura nenhuma', () => {
    const semLeitura = {
      ...maquininha,
      entrega: { ...maquininha.entrega, leitura: null },
    };
    expect(sintomaDaCampanha(semLeitura)).toBe('ligada_sem_medida');
  });

  it('impressão ZERO medida continua sendo `ligada_sem_impressao`', () => {
    const zero = {
      ...maquininha,
      entrega: { ...maquininha.entrega, impressoes: 0, cliques: 0 },
    };
    expect(sintomaDaCampanha(zero)).toBe('ligada_sem_impressao');
  });

  it('campanha saudável continua fora da fila', () => {
    expect(sintomaDaCampanha(campanhaSaudavel)).toBeNull();
  });

  it('clique MEDIDO e positivo continua provando entrega, mesmo sem a impressão', () => {
    // Não é ausência: é uma medição positiva, e clique implica veiculação. Só
    // a AUSÊNCIA é que não conclui — por isso este caso fica fora da fila e o
    // de cima entra.
    const comClique = {
      ...maquininha,
      entrega: { ...maquininha.entrega, impressoes: null, cliques: 4 },
    };
    expect(sintomaDaCampanha(comClique)).toBeNull();
  });

  it('zero clique MEDIDO com impressão ausente é parcial: as duas leituras opostas cabem', () => {
    // "não apareceu" e "apareceu e ninguém clicou" pedem atos opostos — lance
    // contra anúncio. Sem a impressão, escolher um dos dois é inventar.
    const parcial = {
      ...maquininha,
      entrega: { ...maquininha.entrega, impressoes: null, cliques: 0 },
    };
    expect(sintomaDaCampanha(parcial)).toBe('ligada_com_entrega_parcial');
  });
});
