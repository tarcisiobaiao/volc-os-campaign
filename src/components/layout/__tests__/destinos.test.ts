import { describe, expect, it } from 'vitest';

import { GRUPOS_DE_DESTINOS, estaNaSecao, gruposVisiveis, localizar } from '@/components/layout/destinos';

describe('mapa de destinos do shell', () => {
  it('o operador vê só a sala que o roteador lhe autoriza, e nenhum grupo vazio', () => {
    const grupos = gruposVisiveis('OPERATOR');
    expect(grupos.map((g) => g.titulo)).toEqual(['Mídia']);
    expect(grupos[0].itens.map((d) => d.href)).toEqual(['/settings/campaigns']);
  });

  it('papel desconhecido é tratado como operador, nunca como admin', () => {
    expect(gruposVisiveis(undefined).flatMap((g) => g.itens).every((d) => !d.adminOnly)).toBe(true);
  });

  it('o admin vê os quatorze destinos, nos quatro grupos', () => {
    const grupos = gruposVisiveis('ADMIN');
    expect(grupos.map((g) => g.titulo)).toEqual(['Visão', 'Mídia', 'Produção', 'Sistema']);
    expect(grupos.flatMap((g) => g.itens)).toHaveLength(14);
  });

  it('nenhum destino se repete', () => {
    const hrefs = GRUPOS_DE_DESTINOS.flatMap((g) => g.itens.map((d) => d.href));
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it('casa por segmento, não por prefixo de texto', () => {
    expect(estaNaSecao('/settings/costs', '/settings/co')).toBe(false);
    expect(estaNaSecao('/trafego/campanhas/9', '/trafego')).toBe(true);
    expect(estaNaSecao('/reports', '/')).toBe(false);
  });

  it('localiza rota filha e a rota duplicada de projetos no mesmo lugar', () => {
    expect(localizar('/trafego/campanhas/9')).toMatchObject({ grupo: { titulo: 'Mídia' }, destino: { title: 'Tráfego' }, profundo: true });
    expect(localizar('/settings/projects')).toMatchObject({ destino: { href: '/dashboard/projects' }, profundo: false });
    expect(localizar('/login')).toBeNull();
  });
});
