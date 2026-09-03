/**
 * As duas maneiras de o perfil de canal mentir — encontradas em 27/08/2026.
 *
 * `perfilDeCanal.ts` carregava uma segunda declaração, cravada no cliente, do
 * que cada canal sabe fazer, ao lado do manifesto do backend. Duas verdades
 * sobre o mesmo fato divergem no primeiro ajuste, e tinham divergido:
 *
 *  1. **Display ganhou construtor em 26/08** e aqui continuava `integrado:
 *     false` — a tela escondia capacidade real;
 *  2. **Vídeo e Shopping caíam no `default:`** e recebiam o perfil do Search —
 *     rótulo "Search", árvore com RSA e keyword, integrado. Selecionar Vídeo
 *     mostrava Search, e nada denunciava.
 *
 * O primeiro defeito sumiu com a separação: capacidade passou a vir do
 * manifesto. O segundo sumiu com o `switch` exaustivo. As duas provas abaixo
 * existem para que nenhum dos dois volte.
 */
import { describe, expect, it } from 'vitest';

import { CANAIS_GOOGLE } from '@/components/trafego/hub/contrato';
import { capacidadesDoCanal } from '@/components/trafego/canal/capacidades';
import { perfilDoCanal } from '@/components/trafego/hub/perfilDeCanal';
import type { ManifestoDeCanal } from '@/types/trafego';

const manifesto = (troca: Partial<ManifestoDeCanal> = {}): ManifestoDeCanal => ({
  plataforma: 'GOOGLE_ADS',
  canal: 'DISPLAY',
  rotulo: 'Display',
  hierarquia: ['campanha', 'grupo', 'anuncio', 'asset'],
  paineis: ['anuncios', 'criativos'],
  campos_do_pedido: ['copy', 'criativos', 'url_final'],
  capacidades: ['ler', 'propor'],
  provas_obrigatorias: ['politica', 'duplicidade', 'selo'],
  indisponibilidades: [],
  sabe_provar: true,
  sabe_criar: true,
  ...troca,
});

describe('nenhum canal herda o perfil de outro', () => {
  it.each(CANAIS_GOOGLE)('%s tem rótulo próprio e nunca o do Search', (canal) => {
    const perfil = perfilDoCanal('google', canal);

    expect(perfil.canal).toBe(canal);
    if (canal !== 'SEARCH') {
      expect(perfil.rotulo).not.toBe('Search');
      // A árvore do Search tem RSA e keyword. Nenhum outro canal pode
      // apresentá-las: quem vê "keyword" numa campanha de Vídeo conclui que
      // pode operar keyword ali.
      expect(perfil.estrutura).not.toContain('rsa');
      expect(perfil.estrutura).not.toContain('keyword');
    }
  });

  it('Vídeo e Shopping são nomeados, e não confundidos com Search', () => {
    expect(perfilDoCanal('google', 'VIDEO').rotulo).toBe('Vídeo');
    expect(perfilDoCanal('google', 'SHOPPING').rotulo).toBe('Shopping');
  });

  it('"todos os canais" não escolhe o Search em nome de ninguém', () => {
    const perfil = perfilDoCanal('google', null);

    expect(perfil.rotulo).toBe('Todos os canais');
    expect(perfil.estrutura).toEqual(['campanha']);
  });

  it('Meta usa o vocabulário do Meta — conjunto, nunca grupo de anúncios', () => {
    const perfil = perfilDoCanal('meta', null);

    expect(perfil.estrutura).toContain('conjunto');
    expect(perfil.estrutura).not.toContain('grupo');
  });
});

describe('leitura profunda é sobre adaptador, não sobre criar', () => {
  it('só o Search lê as entidades abaixo da campanha', () => {
    // Medido: `sincronizador._PERFIS` registra um adaptador só —
    // `adaptador_search.py`. Display sabe CRIAR e não tem adaptador de
    // leitura; colapsar as duas coisas num booleano foi o defeito original.
    expect(perfilDoCanal('google', 'SEARCH').leituraProfunda).toBe(true);
    for (const canal of CANAIS_GOOGLE.filter((c) => c !== 'SEARCH')) {
      expect(perfilDoCanal('google', canal).leituraProfunda).toBe(false);
    }
  });
});

describe('capacidade vem do manifesto, e por UMA função só', () => {
  /**
   * ⚠️ Esta correção quase criou uma TERCEIRA declaração.
   *
   * `canal/capacidades.ts` já traduz manifesto em capacidade e é o que a página
   * canônica renderiza. Um `capacidadeDoPerfil` paralelo teria as mesmas três
   * respostas com outros três nomes (`nao_opera` contra `nao_operado`), e
   * divergiria delas no primeiro ajuste — repetindo, no cliente, exatamente o
   * defeito que esta entrega foi corrigir no perfil.
   */
  it('`null` é afirmação do backend: este canal não é operado', () => {
    expect(capacidadesDoCanal(null).tipo).toBe('nao_operado');
  });

  it('manifesto com capacidades diz "operado", mesmo que não saiba criar', () => {
    expect(capacidadesDoCanal(manifesto()).tipo).toBe('operado');
    expect(capacidadesDoCanal(manifesto({ sabe_criar: false })).tipo).toBe('operado');
  });

  it('manifesto sem capacidade não é o mesmo que canal não operado', () => {
    // "não é conosco" manda o operador ao painel do Google; "é conosco e está
    // tudo travado" manda a quem cuida do Hub. Colapsar as duas manda metade
    // das pessoas ao lugar errado.
    expect(capacidadesDoCanal(manifesto({ capacidades: [] })).tipo).toBe('sem_capacidade');
  });

  it('Display operado NÃO é escondido pelo cliente', () => {
    // O defeito original, dito como prova: o front não pode ter opinião
    // própria sobre Display saber criar. Ele pergunta ao manifesto.
    expect(perfilDoCanal('google', 'DISPLAY').rotulo).toBe('Display');
    const c = capacidadesDoCanal(manifesto({ canal: 'DISPLAY', sabe_criar: true }));
    expect(c.tipo).toBe('operado');
    expect(c.tipo === 'operado' && c.sabe_criar).toBe(true);
  });
});
