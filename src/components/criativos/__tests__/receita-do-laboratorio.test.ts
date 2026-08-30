/**
 * A receita do Laboratório: o que ela compila, o que ela recusa e o que ela
 * se recusa a afirmar.
 *
 * Estas provas defendem três frases que a tela diz ao operador: "custa tanto",
 * "serve para este canal" e "pode produzir agora". Cada uma delas é uma promessa,
 * e as três têm um jeito específico de virar mentira.
 */
import { describe, expect, it } from 'vitest';

import {
  RASCUNHO_VAZIO,
  canaisConhecidos,
  compilar,
  podeProduzirAgora,
  validar,
  type RascunhoDeReceita,
} from '../laboratorio/receita';
import type { Parque } from '@/types/parqueCriativo';

const PARQUE: Parque = {
  motores: [
    {
      id: 'm1',
      slug: 'gemini-imagem',
      nome: 'Gemini Imagem',
      produz: ['imagem'],
      runtime: 'volc_os',
      cofreAssetId: 'asset:engine:image-volc',
      provider: 'google',
      modelo: 'gemini-3.1-flash-image',
      versaoDoAdaptador: '1',
      custoReferenciaUsd: 0.04,
      custoUnidade: 'por imagem',
      custoFonte: 'tabela do provedor, 27/08/2026',
      capacidades: [],
      fonte: 'services/creative_engine',
      verificadoEm: '2026-08-28T00:00:00Z',
      ativo: true,
    },
    {
      id: 'm2',
      slug: 'volc-factory',
      nome: 'Fábrica de vídeo',
      produz: ['video'],
      runtime: 'externo',
      cofreAssetId: 'asset:engine:video-volc',
      provider: null,
      modelo: null,
      versaoDoAdaptador: null,
      custoReferenciaUsd: null, // não declara custo — diferente de custo zero
      custoUnidade: null,
      custoFonte: null,
      capacidades: [],
      fonte: 'volc-factory',
      verificadoEm: null,
      ativo: true,
    },
  ],
  modos: [
    {
      id: 'd1',
      slug: 'full_llm',
      nome: 'Peça inteira gerada por IA',
      descricao: '',
      exigeProviderDeImagem: true,
      renderer: 'provider',
      estadoDeProva: 'implementado_no_volc',
      prova: 'job real de 28/08/2026',
      saidasNoSnapshot: 3,
      fonte: 'x',
      ordem: 1,
    },
    {
      id: 'd2',
      slug: 'typography_only',
      nome: 'Só tipografia',
      descricao: '',
      exigeProviderDeImagem: false,
      renderer: 'prensa',
      estadoDeProva: 'executado_externo',
      prova: 'carrossel_produtividade_metodo90',
      saidasNoSnapshot: 26,
      fonte: 'y',
      ordem: 2,
    },
  ],
  formatos: [
    {
      id: 'f1', slot: '1x1', rotulo: 'Quadrado', proporcao: '1:1',
      largura: 1080, altura: 1080, tipoDeAsset: 'imagem_marketing_quadrada',
      midia: 'imagem', descricao: null, destinosTipicos: [], fonte: 'z', ativo: true, ordem: 1,
      executavelAgora: true, motivoSeNao: null,
    },
    {
      id: 'f2', slot: '1.91x1', rotulo: 'Paisagem', proporcao: '1.91:1',
      largura: 1200, altura: 628, tipoDeAsset: 'imagem_marketing',
      midia: 'imagem', descricao: null, destinosTipicos: [], fonte: 'z', ativo: true, ordem: 2,
      executavelAgora: true, motivoSeNao: null,
    },
    {
      id: 'f3', slot: 'video-9x16', rotulo: 'Vídeo vertical', proporcao: '9:16',
      largura: 1080, altura: 1920, tipoDeAsset: 'video',
      midia: 'video', descricao: null, destinosTipicos: [], fonte: 'w', ativo: true, ordem: 9,
      executavelAgora: false, motivoSeNao: 'O catálogo declara e o executor não sabe produzir.',
    },
    {
      id: 'f4', slot: 'mini', rotulo: 'Pequeno demais', proporcao: '1:1',
      largura: 200, altura: 200, tipoDeAsset: 'imagem_marketing_quadrada',
      midia: 'imagem', descricao: null, destinosTipicos: [], fonte: 'z', ativo: true, ordem: 20,
      executavelAgora: true, motivoSeNao: null,
    },
  ],
  finalidades: [
    { id: 'p1', slug: 'google_display', nome: 'Google Display', descricao: '', classe: 'midia_paga', ativo: true, ordem: 1 },
    { id: 'p2', slug: 'instagram_organic', nome: 'Instagram orgânico', descricao: '', classe: 'organica', ativo: true, ordem: 2 },
  ],
  skins: [],
  vozes: [],
  gates: [],
  exigenciasDeCanal: [
    {
      id: 'e1', canal: 'DISPLAY', tipoDeAsset: 'imagem_marketing_quadrada',
      quantidadeMinima: 1, quantidadeMaxima: 15, quantidadeRecomendada: 4,
      proporcaoAlvo: '1:1', toleranciaProporcao: 0.01,
      larguraMinima: 300, alturaMinima: 300, larguraRecomendada: 1200, alturaRecomendada: 1200,
      bytesMaximos: 5242880, mimesAceitos: ['image/png'], duracaoMinimaS: null, duracaoMaximaS: null,
      caracteresMaximos: null, caracteresDePeloMenosUm: null,
      provisorio: false, fonteDosNumeros: 'Google Ads', verificadoEm: '2026-08-01T00:00:00Z',
    },
    {
      id: 'e2', canal: 'DISPLAY', tipoDeAsset: 'imagem_marketing',
      quantidadeMinima: 1, quantidadeMaxima: 15, quantidadeRecomendada: 4,
      proporcaoAlvo: '1.91:1', toleranciaProporcao: 0.01,
      larguraMinima: 600, alturaMinima: 314, larguraRecomendada: 1200, alturaRecomendada: 628,
      bytesMaximos: 5242880, mimesAceitos: ['image/png'], duracaoMinimaS: null, duracaoMaximaS: null,
      caracteresMaximos: null, caracteresDePeloMenosUm: null,
      provisorio: true, fonteDosNumeros: 'estimativa interna', verificadoEm: null,
    },
  ],
  tetosCombinados: [
    {
      id: 't1', canal: 'DISPLAY', rotulo: 'Imagens de marketing',
      tipos: ['imagem_marketing_quadrada', 'imagem_marketing'], minimo: 1, maximo: 2,
      fonte: 'Google Ads',
    },
  ],
  naoLidas: [],
  divergencias: [],
  lidoEm: '2026-08-28T18:00:00Z',
  completa: true,
};

function rascunho(campos: Partial<RascunhoDeReceita> = {}): RascunhoDeReceita {
  return {
    ...RASCUNHO_VAZIO,
    nome: 'Receita de teste',
    finalidadeSlug: 'google_display',
    canal: 'DISPLAY',
    motorSlug: 'gemini-imagem',
    modoSlug: 'full_llm',
    slots: ['1x1'],
    ...campos,
  };
}

describe('compilar', () => {
  it('resolve o rascunho contra o catálogo e carrega a procedência junto', () => {
    const r = compilar(rascunho(), PARQUE);
    expect(r.motor?.slug).toBe('gemini-imagem');
    expect(r.saidas).toHaveLength(1);
    expect(r.saidas[0]).toMatchObject({ largura: 1080, altura: 1080 });
    expect(r.procedencia.map((p) => p.campo)).toContain('motor');
    expect(r.procedencia.map((p) => p.campo)).toContain('formato 1x1');
  });

  it('ignora slot que o catálogo não conhece em vez de inventar dimensão', () => {
    const r = compilar(rascunho({ slots: ['1x1', 'slot-fantasma'] }), PARQUE);
    expect(r.saidas.map((s) => s.slot)).toEqual(['1x1']);
  });

  it('multiplica o custo declarado pelo número de saídas', () => {
    const r = compilar(rascunho({ slots: ['1x1', '1.91x1'] }), PARQUE);
    expect(r.custoEstimadoUsd).toBe(0.08);
    expect(r.custoFonte).toBe('tabela do provedor, 27/08/2026');
  });

  it('motor sem custo declarado devolve null, NUNCA zero', () => {
    // Esta é a mentira mais fácil desta tela: `?? 0` transformaria "não sei
    // quanto custa" em "é de graça", e a estimativa mentiria para baixo.
    const r = compilar(
      rascunho({ motorSlug: 'volc-factory', slots: ['video-9x16'] }),
      PARQUE,
    );
    expect(r.custoEstimadoUsd).toBeNull();
    expect(r.custoEstimadoUsd).not.toBe(0);
  });

  it('sem saída escolhida não há custo a estimar', () => {
    expect(compilar(rascunho({ slots: [] }), PARQUE).custoEstimadoUsd).toBeNull();
  });

  it('preserva a semente do render', () => {
    // `seed` fixo é o que impede o mesmo grifo de sair diferente em cada chunk
    // de um render paralelo.
    expect(compilar(rascunho({ seed: 42 }), PARQUE).seed).toBe(42);
  });
});

describe('validar', () => {
  it('receita completa e compatível não gera impedimento', () => {
    const achados = validar(compilar(rascunho(), PARQUE), PARQUE);
    expect(achados.filter((a) => a.gravidade === 'impede')).toEqual([]);
    expect(podeProduzirAgora(achados)).toBe(true);
  });

  it('modo que não produz aqui impede, e diz onde está a evidência', () => {
    const achados = validar(
      compilar(rascunho({ modoSlug: 'typography_only' }), PARQUE),
      PARQUE,
    );
    const impedimento = achados.find((a) => a.oQue.includes('Só tipografia'));
    expect(impedimento?.gravidade).toBe('impede');
    expect(impedimento?.fonte).toBe('carrossel_produtividade_metodo90');
    expect(podeProduzirAgora(achados)).toBe(false);
  });

  it('motor de imagem pedindo vídeo impede', () => {
    // O slot é marcado executável aqui de propósito: senão a prova mediria a
    // executabilidade e não a incompatibilidade de mídia, e continuaria verde
    // mesmo se a checagem de mídia sumisse.
    const parque = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) =>
        f.slot === 'video-9x16' ? { ...f, executavelAgora: true, motivoSeNao: null } : f,
      ),
    };
    const achados = validar(compilar(rascunho({ slots: ['video-9x16'] }), parque), parque);
    expect(
      achados.some((a) => a.gravidade === 'impede' && a.oQue.includes('não produz video')),
    ).toBe(true);
  });

  it('largura abaixo do piso impede, medida sozinha', () => {
    // ⚠️ A primeira versão desta prova usava um formato 200×200 contra pisos
    // 300/300 e procurava UM achado contendo "200px". Isso gerava dois achados
    // idênticos no texto, e apagar a guarda de largura OU a de altura deixava o
    // outro satisfazendo o `find` — a prova ficava verde com metade da regra
    // removida. Agora cada piso é medido com a outra dimensão em conformidade.
    const parque = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) =>
        f.slot === 'mini' ? { ...f, largura: 200, altura: 1080 } : f,
      ),
    };
    const achados = validar(compilar(rascunho({ slots: ['mini'] }), parque), parque);
    const largura = achados.filter((a) => a.oQue.includes('de largura'));
    expect(largura).toHaveLength(1);
    expect(largura[0].gravidade).toBe('impede');
    expect(largura[0].oQue).toContain('300px');
    expect(largura[0].fonte).toBe('Google Ads');
  });

  it('altura abaixo do piso impede, medida sozinha', () => {
    const parque = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) =>
        f.slot === 'mini' ? { ...f, largura: 1080, altura: 200 } : f,
      ),
    };
    const achados = validar(compilar(rascunho({ slots: ['mini'] }), parque), parque);
    const altura = achados.filter((a) => a.oQue.includes('de altura'));
    expect(altura).toHaveLength(1);
    expect(altura[0].gravidade).toBe('impede');
    expect(altura[0].oQue).toContain('300px');
  });

  it('proporção fora do alvo impede, sem depender dos pisos', () => {
    // Isola a checagem de proporção: dimensões acima dos dois pisos, razão errada.
    const parque = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) =>
        f.slot === '1x1' ? { ...f, largura: 1600, altura: 900 } : f,
      ),
    };
    const achados = validar(compilar(rascunho({ slots: ['1x1'] }), parque), parque);
    const prop = achados.filter((a) => a.oQue.includes('proporção 1:1'));
    expect(prop).toHaveLength(1);
    expect(prop[0].gravidade).toBe('impede');
  });

  it('tolerância de proporção é respeitada, não ignorada', () => {
    // Sem esta prova, alargar a tolerância para infinito passava despercebido.
    const quase = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) =>
        f.slot === '1x1' ? { ...f, largura: 1085, altura: 1080 } : f,
      ),
    };
    expect(
      validar(compilar(rascunho({ slots: ['1x1'] }), quase), quase).filter((a) =>
        a.oQue.includes('proporção'),
      ),
    ).toHaveLength(0);
  });

  it('mínimo do teto combinado impede quando não é alcançado', () => {
    const parque = {
      ...PARQUE,
      tetosCombinados: [{ ...PARQUE.tetosCombinados![0], minimo: 2, maximo: 5 }],
    };
    const achados = validar(compilar(rascunho({ slots: ['1x1'] }), parque), parque);
    expect(
      achados.some((a) => a.gravidade === 'impede' && a.oQue.includes('no mínimo 2')),
    ).toBe(true);
  });

  it('exigência provisória AVISA e não impede', () => {
    // Um número que nós mesmos marcamos como não conferido não pode virar
    // parede. Se virasse, o operador aprenderia a ignorar a diferença entre
    // aviso e impedimento — que é exatamente a informação que o aviso carrega.
    const parque = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) =>
        f.slot === '1.91x1' ? { ...f, largura: 100, altura: 52 } : f,
      ),
    };
    const achados = validar(
      compilar(rascunho({ slots: ['1.91x1'] }), parque),
      parque,
    );
    const sobre = achados.filter((a) => a.oQue.includes('Paisagem'));
    expect(sobre.length).toBeGreaterThan(0);
    expect(sobre.every((a) => a.gravidade === 'avisa')).toBe(true);
    expect(sobre[0].fonte).toContain('ainda não conferido');
    expect(podeProduzirAgora(achados)).toBe(true);
  });

  it('teto combinado excedido impede', () => {
    const parque = {
      ...PARQUE,
      tetosCombinados: [{ ...PARQUE.tetosCombinados![0], maximo: 1 }],
    };
    const achados = validar(
      compilar(rascunho({ slots: ['1x1', '1.91x1'] }), parque),
      parque,
    );
    expect(achados.some((a) => a.gravidade === 'impede' && a.oQue.includes('no máximo 1'))).toBe(true);
  });

  it('canal sem exigência registrada AVISA em vez de aprovar em silêncio', () => {
    // "Nenhuma regra encontrada" não é "passou em todas as regras".
    const achados = validar(compilar(rascunho({ canal: 'TIKTOK' }), PARQUE), PARQUE);
    const aviso = achados.find((a) => a.oQue.includes('TIKTOK'));
    expect(aviso?.gravidade).toBe('avisa');
    expect(aviso?.oQue).toContain('não foi conferida');
    expect(podeProduzirAgora(achados)).toBe(true);
  });

  it('tipo de peça sem exigência declarada não vira reprovação nem aprovação', () => {
    const parque = { ...PARQUE, tetosCombinados: [] };
    const achados = validar(
      compilar(rascunho({ slots: ['video-9x16'], motorSlug: 'volc-factory' }), parque),
      parque,
    );
    const aviso = achados.find((a) => a.oQue.includes('não dá para dizer') || a.oQue.includes('Não dá para dizer'));
    expect(aviso?.gravidade).toBe('avisa');
  });

  it('receita sem nome, sem finalidade, sem motor e sem formato lista os quatro', () => {
    const achados = validar(compilar(RASCUNHO_VAZIO, PARQUE), PARQUE);
    expect(achados.filter((a) => a.gravidade === 'impede')).toHaveLength(4);
    expect(podeProduzirAgora(achados)).toBe(false);
  });
});

describe('canaisConhecidos', () => {
  it('oferece só canais que o banco de fato declara', () => {
    expect(canaisConhecidos(PARQUE)).toEqual(['DISPLAY']);
  });

  it('parque não lido não inventa canal', () => {
    const vazio = { ...PARQUE, exigenciasDeCanal: null, tetosCombinados: null };
    expect(canaisConhecidos(vazio)).toEqual([]);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Achados da auditoria adversarial de 28/08/2026 — cada um vira prova
// ═══════════════════════════════════════════════════════════════════════════

describe('o que a auditoria adversarial derrubou', () => {
  it('slot que o executor não produz IMPEDE, e não apenas avisa', () => {
    // Era o pior defeito da fatia: a rota `GET /parque` foi escrita com um
    // comentário dizendo que apontar `/formatos` para o banco faria "a tela
    // oferecer um formato que o motor recusa depois do clique". O Laboratório
    // era essa tela: listava os 7 slots do banco, o executor conhece 4, e o
    // selo estampava "Nada impede".
    const achados = validar(
      compilar(rascunho({ slots: ['video-9x16'], motorSlug: 'volc-factory' }), PARQUE),
      PARQUE,
    );
    const bloqueio = achados.find((a) => a.oQue.includes('executor'));
    expect(bloqueio?.gravidade).toBe('impede');
    expect(podeProduzirAgora(achados)).toBe(false);
  });

  it('campo de executabilidade ausente NÃO autoriza', () => {
    // `?? true` num servidor antigo autorizaria todo slot. Ausência é "não sei",
    // e não saber não libera gasto.
    const parque = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) =>
        f.slot === '1x1' ? ({ ...f, executavelAgora: undefined } as never) : f,
      ),
    };
    expect(podeProduzirAgora(validar(compilar(rascunho(), parque), parque))).toBe(false);
  });

  it('formato desativado no catálogo impede, mesmo já escolhido', () => {
    // A tela filtra por `ativo`; a regra não filtrava. Bastava desativar entre a
    // escolha e o refetch para a receita seguir somando custo e ficando verde.
    const parque = {
      ...PARQUE,
      formatos: PARQUE.formatos!.map((f) => (f.slot === '1x1' ? { ...f, ativo: false } : f)),
    };
    const achados = validar(compilar(rascunho(), parque), parque);
    expect(achados.some((a) => a.gravidade === 'impede' && a.oQue.includes('saiu do catálogo'))).toBe(true);
  });

  it('motor desativado impede', () => {
    const parque = {
      ...PARQUE,
      motores: PARQUE.motores!.map((m) =>
        m.slug === 'gemini-imagem' ? { ...m, ativo: false } : m,
      ),
    };
    const achados = validar(compilar(rascunho(), parque), parque);
    expect(achados.some((a) => a.gravidade === 'impede' && a.oQue.includes('desativado'))).toBe(true);
  });

  it('estado de prova desconhecido falha FECHADO', () => {
    // `if (prova && !prova.podeProduzir)` deixava passar um estado que esta
    // versão não conhece: a tela desabilitava a opção e a regra liberava. Das
    // duas pontas que leem a mesma coluna, quem discordava a favor do gasto era
    // justamente a regra.
    const parque = {
      ...PARQUE,
      modos: PARQUE.modos!.map((m) =>
        m.slug === 'full_llm' ? ({ ...m, estadoDeProva: 'em_prova' } as never) : m,
      ),
    };
    const achados = validar(compilar(rascunho(), parque), parque);
    expect(achados.some((a) => a.gravidade === 'impede' && a.oQue.includes('não conhece'))).toBe(true);
    expect(podeProduzirAgora(achados)).toBe(false);
  });

  it('finalidade orgânica em canal de mídia paga impede', () => {
    // Dos três defeitos de negócio caros, era o que a fatia deixava aberto: a
    // tela imprimia "mídia paga e orgânico têm obrigações diferentes" e a
    // validação não sustentava a frase.
    const achados = validar(
      compilar(rascunho({ finalidadeSlug: 'instagram_organic' }), PARQUE),
      PARQUE,
    );
    const bloqueio = achados.find((a) => a.oQue.includes('orgânica'));
    expect(bloqueio?.gravidade).toBe('impede');
    expect(podeProduzirAgora(achados)).toBe(false);
  });

  it('finalidade paga no mesmo canal continua passando', () => {
    // A trava acima não pode virar uma parede que bloqueia o caso normal.
    expect(podeProduzirAgora(validar(compilar(rascunho(), PARQUE), PARQUE))).toBe(true);
  });

  it('proporção que a regra não sabe ler AVISA em vez de aprovar calada', () => {
    // `proporcao_alvo` é texto livre no banco, sem CHECK de forma. "1,91:1" com
    // vírgula desligava a conferência em silêncio, e ausência de leitura virava
    // aprovação.
    const parque = {
      ...PARQUE,
      exigenciasDeCanal: PARQUE.exigenciasDeCanal!.map((e) =>
        e.tipoDeAsset === 'imagem_marketing_quadrada'
          ? { ...e, proporcaoAlvo: '1,91:1', provisorio: false }
          : e,
      ),
    };
    const achados = validar(compilar(rascunho(), parque), parque);
    const aviso = achados.find((a) => a.oQue.includes('não sabe interpretar'));
    expect(aviso?.gravidade).toBe('avisa');
    expect(aviso?.oQue).toContain('NÃO foi conferida');
  });
});

describe('S1: o catálogo muda debaixo da escolha', () => {
  it('slot que sai do catálogo entre a escolha e a compilação IMPEDE', () => {
    // Antes: a compilação filtrava em silêncio. O custo caía de 0,08 para 0,04,
    // a lista de saídas encolhia e nenhum achado aparecia. O React Query refaz a
    // leitura a cada 5 minutos.
    const antes = compilar(rascunho({ slots: ['1x1', '1.91x1'] }), PARQUE);
    expect(antes.custoEstimadoUsd).toBe(0.08);
    expect(antes.slotsPerdidos).toEqual([]);

    const depois = {
      ...PARQUE,
      formatos: PARQUE.formatos!.filter((f) => f.slot !== '1.91x1'),
    };
    const receita = compilar(rascunho({ slots: ['1x1', '1.91x1'] }), depois);
    expect(receita.slotsPerdidos).toEqual(['1.91x1']);
    expect(receita.custoEstimadoUsd).toBe(0.04);

    const achados = validar(receita, depois);
    const perdido = achados.find((a) => a.oQue.includes('não está mais no catálogo'));
    expect(perdido?.gravidade).toBe('impede');
    expect(podeProduzirAgora(achados)).toBe(false);
  });

  it('catálogo não lido não acusa slot perdido', () => {
    // Banco fora do ar não é "o formato foi aposentado".
    const semLeitura = { ...PARQUE, formatos: null };
    const receita = compilar(rascunho({ slots: ['1x1'] }), semLeitura);
    // Sem catálogo tudo é desconhecido; o que não pode é passar como se estivesse ok.
    expect(podeProduzirAgora(validar(receita, semLeitura))).toBe(false);
  });
});
