// @vitest-environment jsdom
/**
 * O 422 do servidor aparece NO CAMPO certo.
 *
 * O formato vem do contrato GADS-CRIACAO-CANAIS-v1 §2: `detail[]` do FastAPI
 * com `loc` exato e, na configuração, `ctx.caminho` no formato de ponto. O
 * texto mostrado é o `msg` do servidor, inteiro — a tela só decide onde.
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { caminhoDoLoc, errosDo422, errosSob } from '../erros422';
import { ProvedorDeErros } from '@/components/trafego/bancada/campos/Campos';
import { ParadaDisplayEconomia } from '@/components/trafego/bancada/paradas/DisplayParadas';
import { FORM_DISPLAY_VAZIO } from '../formularios';
import type { Cockpit } from '@/types/trafego';

afterEach(cleanup);

/** O erro como `PautadorApiError` o entrega: status + `detail` cru em `corpo`. */
function erro422(corpo: unknown, message = 'Erro 422.') {
  return Object.assign(new Error(message), { status: 422, corpo });
}

const DETAIL_DO_CONTRATO = [{
  type: 'configuracao_invalida',
  loc: ['body', 'configuracao_display', 'frequencia', 0, 'impressoes'],
  msg: 'esperado inteiro, veio texto',
  input: null,
  ctx: { codigo: 'CONFIGURACAO_INVALIDA', caminho: 'configuracao_display.frequencia[0].impressoes' },
}];

describe('o 422 vira erro posicionado', () => {
  it('lê o exemplo literal do contrato §2', () => {
    expect(errosDo422(erro422(DETAIL_DO_CONTRATO))).toEqual({
      campos: [{
        caminho: 'configuracao_display.frequencia[0].impressoes',
        mensagem: 'esperado inteiro, veio texto',
        codigo: 'CONFIGURACAO_INVALIDA',
      }],
      gerais: [],
    });
  });

  it('sem `ctx.caminho`, deriva o caminho do `loc`', () => {
    expect(caminhoDoLoc(['body', 'configuracao_search', 'lance'])).toBe('configuracao_search.lance');
    expect(caminhoDoLoc(['body', 'configuracao_pmax', 'grupos_adicionais', 1, 'sinais']))
      .toBe('configuracao_pmax.grupos_adicionais[1].sinais');
    const e = errosDo422(erro422([{ type: 'value_error', loc: ['body', 'configuracao_search', 'lance'], msg: 'TARGET_IMPRESSION_SHARE exige teto_cpc' }]));
    expect(e?.campos[0]).toMatchObject({ caminho: 'configuracao_search.lance', mensagem: 'TARGET_IMPRESSION_SHARE exige teto_cpc' });
  });

  it('o 422 do envelope (`loc: ["body"]`) e o 422 em frase viram erro GERAL, nunca somem', () => {
    const envelope = errosDo422(erro422([{
      type: 'value_error', loc: ['body'],
      msg: 'Value error, configuracao_display: `configuracao_display` é a configuração de DISPLAY e o pedido é canal=\'SEARCH\'.',
    }]));
    expect(envelope?.campos).toEqual([]);
    expect(envelope?.gerais[0]).toMatch(/^configuracao_display: /);
    const frase = errosDo422(erro422('DISPLAY recebeu campos que o builder não materializa', 'DISPLAY recebeu campos que o builder não materializa'));
    expect(frase?.gerais).toEqual(['DISPLAY recebeu campos que o builder não materializa']);
  });

  it('403, 5xx e rede caída não são erro de campo', () => {
    expect(errosDo422(Object.assign(new Error('desabilitada'), { status: 403 }))).toBeNull();
    expect(errosDo422(new Error('rede'))).toBeNull();
  });

  it('a seção que contém o campo enxerga a combinação recusada', () => {
    const e = errosDo422(erro422(DETAIL_DO_CONTRATO))!;
    expect(errosSob(e, 'configuracao_display.frequencia')).toHaveLength(1);
    expect(errosSob(e, 'configuracao_display.frequenci')).toHaveLength(0);
  });
});

describe('o erro aparece embaixo do campo que o causou', () => {
  const cockpit = { conta: { vinculada: true }, origem: {} } as unknown as Cockpit;

  it('Display: o 422 de `frequencia[0].impressoes` marca o campo "impressões" da primeira linha', () => {
    const erros = errosDo422(erro422(DETAIL_DO_CONTRATO))!;
    render(
      <ProvedorDeErros erros={erros}>
        <ParadaDisplayEconomia
          cockpit={cockpit} orcamento={20} orcamentoBruto="20" onOrcamento={() => {}}
          form={{
            ...FORM_DISPLAY_VAZIO,
            frequencia: [
              { impressoes: 'três', unidade: 'DAY', nivel: 'AD_GROUP_AD' },
              { impressoes: '10', unidade: 'WEEK', nivel: 'CAMPAIGN' },
            ],
          }}
          alterar={() => {}} esquema={null}
        />
      </ProvedorDeErros>,
    );
    const alerta = screen.getByRole('alert');
    expect(alerta.getAttribute('data-caminho')).toBe('configuracao_display.frequencia[0].impressoes');
    expect(alerta.textContent).toContain('esperado inteiro, veio texto');
    // O alerta está DENTRO do rótulo do campo certo, e o campo está marcado.
    const campo = document.getElementById('display-freq-0') as HTMLInputElement;
    expect(campo.getAttribute('aria-invalid')).toBe('true');
    expect(within(campo.closest('label')!).getByRole('alert')).toBe(alerta);
    // A segunda linha não herda o erro da primeira.
    expect(document.getElementById('display-freq-1')!.getAttribute('aria-invalid')).toBeNull();
  });
});
