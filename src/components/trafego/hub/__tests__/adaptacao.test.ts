import { describe, expect, it } from 'vitest';

import {
  abaDaUrl,
  canalDaUrl,
  canalParaContrato,
  canalParaUrl,
  consultaDoHistorico,
  consultaOperacional,
  escreverEstadoDoHub,
  filtrosDaBarra,
  lerEstadoDoHub,
} from '@/components/trafego/hub/adaptacao';
import { ESTADO_PADRAO } from '@/components/trafego/hub/contrato';

describe('URL ↔ estado do Hub', () => {
  it('Google é o padrão, e campanhas é a tarefa padrão', () => {
    const estado = lerEstadoDoHub(new URLSearchParams());
    expect(estado.rede).toBe('google');
    expect(estado.aba).toBe('campanhas');
    expect(estado.historico).toBe(false);
    expect(estado.canal).toBeNull();
  });

  it('aceita plataforma=meta como alias de entrada e só emite rede=meta', () => {
    const legado = new URLSearchParams('plataforma=meta');
    expect(lerEstadoDoHub(legado).rede).toBe('meta');

    const canonico = escreverEstadoDoHub(legado, {});
    expect(canonico.get('rede')).toBe('meta');
    expect(canonico.get('plataforma')).toBeNull();
  });

  it('aba=oportunidades continua abrindo Preparar', () => {
    expect(abaDaUrl('oportunidades')).toBe('preparar');
    expect(abaDaUrl('preparar')).toBe('preparar');
  });

  it('antessalas técnicas antigas agora desembocam em Preparar', () => {
    expect(abaDaUrl('criar')).toBe('preparar');
    expect(abaDaUrl('canais')).toBe('preparar');
  });

  it('o canal canônico é PERFORMANCE_MAX; PMAX só entra como alias legado', () => {
    expect(canalDaUrl('PERFORMANCE_MAX')).toBe('PERFORMANCE_MAX');
    expect(canalDaUrl('PMAX')).toBe('PERFORMANCE_MAX');
    expect(canalDaUrl('SEARCH')).toBe('SEARCH');
    expect(canalParaUrl('PERFORMANCE_MAX')).toBe('PERFORMANCE_MAX');
    expect(escreverEstadoDoHub(new URLSearchParams(), {
      ...ESTADO_PADRAO,
      canal: 'PERFORMANCE_MAX',
    }).get('canal')).toBe('PERFORMANCE_MAX');
    expect(lerEstadoDoHub(new URLSearchParams('canal=PMAX')).canal).toBe('PERFORMANCE_MAX');
    expect(canalParaContrato('PERFORMANCE_MAX')).toBe('PERFORMANCE_MAX');
    expect(consultaOperacional(lerEstadoDoHub(new URLSearchParams('canal=PERFORMANCE_MAX'))).canal)
      .toEqual(['PERFORMANCE_MAX']);
  });

  it('a consulta operacional não pede histórico, e isso não vive na URL', () => {
    const estado = { ...ESTADO_PADRAO };
    const consulta = consultaOperacional(estado);
    expect(consulta.incluir_historico).toBeUndefined();
    expect(consulta.estado_externo).toBeUndefined();
    const params = escreverEstadoDoHub(new URLSearchParams(), estado);
    expect(params.get('estado')).toBeNull();
    expect(params.get('historico')).toBeNull();
  });

  it('limpar a barra não apaga o canal da moldura', () => {
    const estado = lerEstadoDoHub(new URLSearchParams('canal=SEARCH&busca=FGTS'));
    expect(filtrosDaBarra(estado).canal).toBeUndefined();
    expect(estado.canal).toBe('SEARCH');
    expect(consultaOperacional(estado).canal).toEqual(['SEARCH']);
  });

  it('o histórico é uma consulta só de removidas', () => {
    const estado = lerEstadoDoHub(new URLSearchParams('canal=DISPLAY'));
    expect(consultaDoHistorico(estado)).toEqual({
      canal: ['DISPLAY'],
      incluir_historico: true,
      estado_externo: ['REMOVED'],
    });
  });

  it('Meta preserva o recorte comum, mas remove o canal exclusivo do Google', () => {
    const params = escreverEstadoDoHub(new URLSearchParams(), {
      ...ESTADO_PADRAO,
      rede: 'meta',
      canal: 'SEARCH',
      historico: true,
      filtros: { busca: 'FGTS', atencao: true, conta: ['8017851692'] },
    });
    expect(params.get('rede')).toBe('meta');
    expect(params.get('canal')).toBeNull();
    expect(params.get('historico')).toBe('1');
    expect(params.get('busca')).toBe('FGTS');
    expect(params.get('atencao')).toBe('1');
    expect(params.get('conta')).toBe('8017851692');
  });

  it('ignora canal Google recebido junto de uma URL Meta', () => {
    const estado = lerEstadoDoHub(new URLSearchParams('rede=meta&canal=SEARCH'));
    expect(estado.rede).toBe('meta');
    expect(estado.canal).toBeNull();
    expect(estado.filtros.canal).toBeUndefined();
    expect(consultaOperacional(estado).canal).toBeUndefined();
  });

  it('VIDEO e SHOPPING são reconhecidos; HOTEL não', () => {
    expect(canalDaUrl('VIDEO')).toBe('VIDEO');
    expect(canalDaUrl('SHOPPING')).toBe('SHOPPING');
    expect(canalDaUrl('HOTEL')).toBeNull();
    expect(consultaOperacional(lerEstadoDoHub(new URLSearchParams('canal=VIDEO'))).canal)
      .toEqual(['VIDEO']);
  });
});
