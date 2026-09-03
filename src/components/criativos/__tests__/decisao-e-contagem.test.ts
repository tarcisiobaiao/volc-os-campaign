/**
 * Duas guardas que existiam e não podiam disparar.
 *
 * Elas não são a mesma coisa, mas têm a mesma forma de defeito: alguém escreveu
 * a regra, escreveu a mensagem, escreveu o ramo — e o chamador desligou a
 * pergunta. `aprovavel` chegava `true` literal nos dois lugares; a contagem por
 * estado tinha `?? 0`. Nos dois casos o código parecia cuidadoso e afirmava
 * coisas que ninguém tinha verificado.
 */
import { describe, expect, it } from 'vitest';
import { pecaEDecidivel } from '@/components/criativos/aprovacoes/regras';
import { contagemLegivel } from '@/components/criativos/comum/formato';

describe('pecaEDecidivel', () => {
  it('aprova a peça cujos bytes alguém mediu', () => {
    expect(pecaEDecidivel({ contentHash: 'a'.repeat(64), bytesTotais: 12345 })).toBe(true);
  });

  it('recusa a peça sem bytes medidos — null não é zero e não é "pronta"', () => {
    expect(pecaEDecidivel({ contentHash: 'a'.repeat(64), bytesTotais: null })).toBe(false);
  });

  it('recusa a peça sem hash de conteúdo', () => {
    expect(pecaEDecidivel({ contentHash: '', bytesTotais: 999 })).toBe(false);
  });

  it('CONTRAPROVA: um arquivo de zero byte não é ausência de medida', () => {
    // `0` aqui é uma MEDIDA — alguém abriu e o arquivo tinha zero byte. A peça
    // continua decidível, e quem decide vê `0 B` na tela em vez de "não medido".
    // Colapsar `0` com `null` aqui repetiria, do lado do cliente, exatamente o
    // defeito que o contrato do servidor existe para impedir.
    expect(pecaEDecidivel({ contentHash: 'b'.repeat(64), bytesTotais: 0 })).toBe(true);
  });
});

describe('contagemLegivel', () => {
  it('mostra o número quando alguém contou', () => {
    expect(contagemLegivel(0)).toBe('0');
    expect(contagemLegivel(7)).toBe('7');
  });

  it('CONTRAPROVA do `?? 0`: chave ausente não vira zero', () => {
    // "nenhum job falhou" e "ninguém contou os que falharam" levam a ações
    // opostas. O `?? 0` escondia a segunda atrás da primeira.
    expect(contagemLegivel(undefined)).toBe('não contado');
    expect(contagemLegivel(null)).toBe('não contado');
  });
});
