import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { coberturaDoContrato, estadoDaMedida, MARCA_SHADOW_FUTURO, MARCA_SHADOW_REAL, projetarBancada, valorExibido } from '../projection';
import { fotografiaDouradaBudgetLimited, PROVAS_L6, provaPorId } from '../fixtures';
import { ehResultadoDecisionLab } from '@/types/inteligenciaDecisao';

const aqui = dirname(fileURLToPath(import.meta.url));
const pasta = join(aqui, '..');

describe('projeção da bancada', () => {
  it('não transforma null em zero', () => {
    expect(estadoDaMedida(null)).toBe('ausente');
    expect(valorExibido(null, 'ausente')).not.toBe('0');
    expect(estadoDaMedida(0)).toBe('zero_medido');
    expect(valorExibido(0, 'zero_medido')).toBe('0');
  });

  it('distingue lista vazia, campo ausente, falha e não aplicável', () => {
    expect(estadoDaMedida([])).toBe('lista_vazia');
    expect(estadoDaMedida(null, { estado: 'campo_ausente' })).toBe('campo_ausente');
    expect(estadoDaMedida(null, { impedimento: 'leitura falhou' })).toBe('falha');
    expect(estadoDaMedida(null, { estado: 'nao_aplicavel' })).toBe('nao_aplicavel');
  });

  it('mapeia cobertura a partir do contrato, sem classificar suficiência', () => {
    expect(coberturaDoContrato({ estado_da_leitura: 'atual', estado_da_superficie: 'atual' })).toBe('completa');
    expect(coberturaDoContrato({ estado_da_leitura: 'parcial' })).toBe('parcial');
    expect(coberturaDoContrato({ estado_da_leitura: 'stale' })).toBe('antiga');
    expect(coberturaDoContrato({ estado_da_superficie: 'falha_sem_fotografia' })).toBe('indisponivel');
  });

  it('preserva a ordem das propostas tipadas do servidor', () => {
    const resposta = fotografiaDouradaBudgetLimited();
    if (!ehResultadoDecisionLab(resposta)) throw new Error('fixture inválida');
    const bancada = projetarBancada(resposta);
    expect(bancada.propostas.map((p) => p.id)).toEqual(resposta.propostas_tipadas.map((p) => p.proposta_id));
  });

  it('não reordena conflitos', () => {
    const prova = provaPorId('prova-l6-conflito');
    const resposta = prova?.resposta;
    if (!resposta || !ehResultadoDecisionLab(resposta)) throw new Error('fixture inválida');
    const bancada = projetarBancada(resposta);
    expect(bancada.conflitos.map((c) => c.codigo)).toEqual(resposta.conflitos.map((c) => c.codigo));
  });

  it('não inventa ausência para degrau sem evidência e sem impedimento', () => {
    const resposta = fotografiaDouradaBudgetLimited();
    if (!ehResultadoDecisionLab(resposta)) throw new Error('fixture inválida');
    const bancada = projetarBancada(resposta);
    const entrega = bancada.familias.find((familia) => familia.id === 'entrega_leilao');
    expect(entrega?.itens.some((item) => item.rotulo === 'apurado' && item.estado === 'ausente')).toBe(false);
  });
});

const AFIRMA_DADO_REAL = /dados reais|dado real|conta teste|conta-teste|leitura da conta|leitura de conta|SHADOW READ/i;

describe('fixture nunca afirma dado real', () => {
  it('nenhuma prova local declara dado real, conta teste ou leitura de conta', () => {
    const fonte = readFileSync(join(pasta, 'fixtures.ts'), 'utf8');
    expect(fonte).not.toMatch(AFIRMA_DADO_REAL);
    expect(fonte).not.toContain(MARCA_SHADOW_REAL);

    for (const prova of PROVAS_L6) {
      expect(JSON.stringify(prova), prova.prova_id).not.toMatch(AFIRMA_DADO_REAL);
      expect(prova.marca, prova.prova_id).not.toBe(MARCA_SHADOW_REAL);
      expect(prova.resposta.isolamento.aceita_volc_campaign_id, prova.prova_id).toBe(false);
    }

    const shadow = provaPorId('prova-l6-shadow-futuro');
    expect(shadow?.marca).toBe(MARCA_SHADOW_FUTURO);
    if (!shadow || !ehResultadoDecisionLab(shadow.resposta)) throw new Error('fixture inválida');
    const bancada = projetarBancada(shadow.resposta, 'shadow_futuro');
    expect(bancada.marca).toBe(MARCA_SHADOW_FUTURO);
    expect(bancada.marca).not.toBe(MARCA_SHADOW_REAL);
  });
});

describe('isolamento do bundle do laboratório', () => {
  it('não embute credencial privilegiada nem pedido Google Ads', () => {
    const arquivos = [
      'DecisionIntelligenceLab.tsx',
      'BancadaDeDecisao.tsx',
      'EstadosDaBancada.tsx',
      'projection.ts',
      'fixtures.ts',
      'SeloDePrototipo.tsx',
    ];
    const juntos = arquivos.map((nome) => readFileSync(join(pasta, nome), 'utf8')).join('\n');
    expect(juntos).not.toMatch(/SERVICE_ROLE|service_role|SUPABASE_SERVICE|GOOGLE_ADS_DEVELOPER_TOKEN|developer_token/);
    expect(juntos).not.toMatch(/googleads\.googleapis|developers\.google\.com\/google-ads/);
    expect(juntos).not.toMatch(/from '@\/lib\/diagnostico\/(escada|derivar|propor)'/);
  });
});
