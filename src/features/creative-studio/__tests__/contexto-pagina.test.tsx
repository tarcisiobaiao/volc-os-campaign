// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FormularioDeBriefing } from '../componentes/FormularioDeBriefing';
import { analisarPaginaCriativa } from '../api';
import type { ContextoDaPagina, FormatoDisponivel } from '../tipos';
vi.mock('../api', () => ({ MAX_PECAS: 12, analisarPaginaCriativa: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const snapshot: ContextoDaPagina = {
  schema_version: 'creative_lp_context.v1', url_solicitada: 'https://example.org/artigo',
  url_final: 'https://example.org/artigo', analisado_em: '2026-09-09T12:00:00Z',
  conteudo_sha256: 'a'.repeat(64), titulo: 'Guia informativo', assunto: 'Certificação',
  assunto_principal: 'Encceja 2026', referencias_visuais_sugeridas: 'Azul-marinho e livros, direção editorial.',
  proposta: 'Explicação das etapas', fatos: [{ ref: 'fact_lp_1234567890123456', declaracao: 'O artigo explica as etapas da prova.', trecho: 'O artigo explica as etapas da prova.', origem_url: 'https://example.org/artigo' }],
  publico_sugerido: 'Pessoas buscando entender a prova.', momento_sugerido: 'Pesquisa inicial.',
  angulos_sugeridos: ['Clareza'], informacoes_ausentes: ['Datas não informadas'], avisos: [],
};
const formatos = [{ slot: '4x5', rotulo: 'Retrato', largura: 1080, altura: 1350, proporcao: '4:5', descricao: 'Retrato', destinos_tipicos: [] }] as FormatoDisponivel[];
function abrir() { const enviar = vi.fn(); render(<FormularioDeBriefing ocupado={false} formatos={formatos} onEnviar={enviar} />); return enviar; }
function url() { fireEvent.change(screen.getByLabelText('Qual página você quer divulgar?'), { target: { value: snapshot.url_solicitada } }); }
describe('contexto revisável da página', () => {
  it('prioriza motivações como hipóteses e mantém fatos revisáveis com sua proveniência', async () => {
    const motivacoes = (['dor', 'desejo', 'sonho', 'receio'] as const).map(tipo => ({
      tipo, hipotese: `Hipótese de ${tipo}`, pergunta_latente: `Pergunta de ${tipo}?`,
      entrega_da_pagina: 'Explica as etapas, sem prometer aprovação.', fato_refs: [snapshot.fatos[0].ref],
    }));
    vi.mocked(analisarPaginaCriativa).mockResolvedValue({...snapshot, motivacoes_sugeridas: motivacoes});
    const enviar = abrir(); url(); fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByText('Por que alguém clicaria?');
    const painel = screen.getByRole('region', {name:'Motivações para o clique'});
    const fatos = screen.getByText('Revisar fatos da página', {exact:false}).closest('details')!;
    expect(painel.compareDocumentPosition(fatos) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(fatos.open).toBe(false);
    expect(screen.getByText(/Hipóteses criativas para testar, não um diagnóstico/)).toBeTruthy();
    for (const tipo of ['Dor', 'Desejo', 'Sonho', 'Receio']) expect(screen.getByRole('heading',{name:tipo})).toBeTruthy();
    expect(screen.getByText('· 1 de 1 selecionados')).toBeTruthy();
    expect(screen.queryByText('Não vai orientar o briefing: fato de apoio desmarcado.')).toBeNull();
    fireEvent.click(screen.getByText('Revisar fatos da página', {exact:false}));
    const check = screen.getByLabelText(snapshot.fatos[0].declaracao) as HTMLInputElement;
    expect(check.checked).toBe(true);
    fireEvent.click(check);
    expect(screen.getByText('· 0 de 1 selecionados')).toBeTruthy();
    expect(screen.getAllByText('Não vai orientar o briefing: fato de apoio desmarcado.')).toHaveLength(4);
    fireEvent.click(check);
    expect(screen.queryByText('Não vai orientar o briefing: fato de apoio desmarcado.')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name:'Adicionar ao briefing' }));
    fireEvent.click(screen.getByRole('button', { name:'Criar estratégia' }));
    expect(enviar).toHaveBeenCalledWith(expect.objectContaining({ contexto_da_pagina: expect.objectContaining({motivacoes_sugeridas:motivacoes}), fatos_da_oferta:[expect.objectContaining({origem:'LANDING_PAGE', evidencia_ref:snapshot.fatos[0].ref})] }));
  });
  it('não exige objetivo; analisar não aplica nem envia o briefing', async () => {
    vi.mocked(analisarPaginaCriativa).mockResolvedValue(snapshot);
    const enviar = abrir(); url();
    expect(screen.queryByLabelText('Objetivo da campanha')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByText('Guia informativo');
    expect((screen.getByLabelText('Declaração') as HTMLTextAreaElement).value).toBe('');
    expect(enviar).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar ao briefing' }));
    fireEvent.click(screen.getByRole('button', { name: 'Criar estratégia' }));
    expect(enviar).toHaveBeenCalledWith(expect.objectContaining({ assunto_principal: 'Encceja 2026', referencias_visuais: snapshot.referencias_visuais_sugeridas, objetivo_meta: null, url_destino: snapshot.url_final, contexto_da_pagina: snapshot, fatos_da_oferta: [expect.objectContaining({ origem: 'LANDING_PAGE', evidencia_ref: snapshot.fatos[0].ref })] }));
  });
  it('preserva edições humanas e não duplica fatos ao reaplicar', async () => {
    vi.mocked(analisarPaginaCriativa).mockResolvedValue(snapshot);
    abrir(); url();
    fireEvent.change(screen.getByLabelText(/Nome do trabalho/), { target: { value: 'Minha campanha' } });
    fireEvent.change(screen.getByLabelText(/Público e momento/), { target: { value: 'Meu público real' } });
    fireEvent.change(screen.getByLabelText(/Assunto principal/), { target: { value: 'Meu assunto editado' } });
    fireEvent.change(screen.getByLabelText('Referências visuais'), { target: { value: 'Minha cena e paleta' } });
    fireEvent.change(screen.getByLabelText('Declaração'), { target: { value: 'Fato informado por mim' } });
    fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByText('Guia informativo');
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar ao briefing' }));
    expect((screen.getByLabelText(/Nome do trabalho/) as HTMLInputElement).value).toBe('Minha campanha');
    expect((screen.getByLabelText(/Público e momento/) as HTMLTextAreaElement).value).toBe('Meu público real');
    expect((screen.getByLabelText(/Assunto principal/) as HTMLInputElement).value).toBe('Meu assunto editado');
    expect((screen.getByLabelText('Referências visuais') as HTMLTextAreaElement).value).toBe('Minha cena e paleta');
    expect((screen.getByLabelText('Declaração') as HTMLTextAreaElement).value).toBe('Fato informado por mim');
    expect((screen.getByLabelText('Declaração 2') as HTMLTextAreaElement).value).toBe(snapshot.fatos[0].declaracao);
  });
  it('trocar URL remove sugestões automáticas, preserva edições e exige novo assunto', async () => {
    vi.mocked(analisarPaginaCriativa).mockResolvedValue(snapshot);
    abrir(); url(); fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByText('Guia informativo');
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar ao briefing' }));
    fireEvent.change(screen.getByLabelText('Referências visuais'), { target: { value: 'Cena corrigida pelo operador' } });
    fireEvent.change(screen.getByLabelText('Qual página você quer divulgar?'), { target: { value: 'https://example.org/novo-assunto' } });
    expect((screen.getByLabelText(/Assunto principal/) as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText(/Nome do trabalho/) as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText(/Público e momento/) as HTMLTextAreaElement).value).toBe('');
    expect((screen.getByLabelText('Declaração') as HTMLTextAreaElement).value).toBe('');
    expect((screen.getByLabelText('Referências visuais') as HTMLTextAreaElement).value).toBe('Cena corrigida pelo operador');
    expect((screen.getByRole('button', { name: 'Criar estratégia' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/sugestões automáticas anteriores são removidas/)).toBeTruthy();
  });
  it('briefing manual requer assunto, independente do nome interno', () => {
    const enviar = abrir();
    fireEvent.change(screen.getByLabelText(/Nome do trabalho/), { target: { value: 'Nome interno' } });
    fireEvent.change(screen.getByLabelText(/Público e momento/), { target: { value: 'Público pesquisando' } });
    fireEvent.change(screen.getByLabelText('Declaração'), { target: { value: 'Existe uma página informativa' } });
    expect((screen.getByRole('button', { name: 'Criar estratégia' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Assunto principal/), { target: { value: '---' } });
    expect((screen.getByRole('button', { name: 'Criar estratégia' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Assunto principal/), { target: { value: 'Certificação pelo Encceja' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar estratégia' }));
    expect(enviar).toHaveBeenCalledWith(expect.objectContaining({ assunto_principal: 'Certificação pelo Encceja' }));
    expect(enviar.mock.calls[0][0]).not.toHaveProperty('referencias_visuais');
  });
  it('assunto ambíguo da página exige confirmação humana, sem usar a narrativa genérica', async () => {
    vi.mocked(analisarPaginaCriativa).mockResolvedValue({...snapshot, assunto_principal: '', assunto: 'Muitos temas secundários e navegação da página'});
    abrir(); url(); fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByText('Guia informativo');
    expect(screen.getByText('O tema principal precisa da sua confirmação no briefing.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar ao briefing' }));
    expect((screen.getByLabelText(/Assunto principal/) as HTMLInputElement).value).toBe('');
    expect((screen.getByRole('button', { name: 'Criar estratégia' }) as HTMLButtonElement).disabled).toBe(true);
  });
  it('tema e fatos editados sobrevivem à troca de URL como informações do operador', async () => {
    vi.mocked(analisarPaginaCriativa).mockResolvedValue(snapshot);
    abrir(); url(); fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByText('Guia informativo');
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar ao briefing' }));
    fireEvent.change(screen.getByLabelText(/Assunto principal/), { target: { value: 'Tema definido por mim' } });
    fireEvent.change(screen.getByLabelText('Declaração'), { target: { value: 'Fato corrigido por mim' } });
    fireEvent.change(screen.getByLabelText('Qual página você quer divulgar?'), { target: { value: 'https://example.org/outra' } });
    expect((screen.getByLabelText(/Assunto principal/) as HTMLInputElement).value).toBe('Tema definido por mim');
    expect((screen.getByLabelText('Declaração') as HTMLTextAreaElement).value).toBe('Fato corrigido por mim');
    expect(screen.getByText('Informado por mim')).toBeTruthy();
  });
  it('descarta uma resposta atrasada se a URL mudou', async () => {
    let resolver!: (v: ContextoDaPagina) => void;
    vi.mocked(analisarPaginaCriativa).mockImplementation(() => new Promise(resolve => { resolver = resolve; }));
    abrir(); url(); fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    fireEvent.change(screen.getByLabelText('Qual página você quer divulgar?'), { target: { value: 'https://example.org/outra' } });
    resolver(snapshot);
    await waitFor(() => expect(screen.queryByText('Guia informativo')).toBeNull());
  });
  it('falha de leitura mantém o preenchimento manual', async () => {
    vi.mocked(analisarPaginaCriativa).mockRejectedValue(new Error('Página indisponível.'));
    abrir(); url(); fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('manualmente'));
    expect((screen.getByLabelText('Declaração') as HTMLTextAreaElement).disabled).toBe(false);
  });
  it('falha ao reanalisar a mesma URL remove a proveniência antiga sem apagar o texto', async () => {
    vi.mocked(analisarPaginaCriativa).mockResolvedValueOnce(snapshot).mockRejectedValueOnce(new Error('Página indisponível.'));
    const enviar = abrir(); url();
    fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByText('Guia informativo');
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar ao briefing' }));
    fireEvent.click(screen.getByRole('button', { name: 'Analisar página' }));
    await screen.findByRole('alert');
    expect(screen.queryByText('Guia informativo')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Criar estratégia' }));
    expect(enviar).toHaveBeenCalledWith(expect.objectContaining({ contexto_da_pagina: null,
      fatos_da_oferta: [expect.objectContaining({ declaracao: snapshot.fatos[0].declaracao, origem: 'OPERADOR' })] }));
    expect(enviar.mock.calls[0][0].fatos_da_oferta[0]).not.toHaveProperty('evidencia_ref');
  });
});
