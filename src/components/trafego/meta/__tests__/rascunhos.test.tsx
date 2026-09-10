// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { RascunhosMeta } from '../RascunhosMeta';
const list = vi.hoisted(() => vi.fn());
const archive = vi.hoisted(() => vi.fn());
vi.mock('@/lib/metaCampaignDraftApi', () => ({ listMetaCampaignDrafts: list, archiveMetaCampaignDraft: archive }));
const ref = '00000000-0000-4000-8000-000000000001';
beforeEach(() => { list.mockReset(); list.mockResolvedValue({items:[{draft_ref:ref, campaign_name:'Teste ABO', version:2,
  updated_at:'2026-09-09T01:00:00Z', adset_count:2, ad_count:3}],has_more:false,next_offset:null}); });
afterEach(cleanup);
it('excludes only after confirmation, preserving packs and using the shown version', async () => {
  archive.mockReset(); archive.mockResolvedValue(undefined);
  render(<RascunhosMeta currentRef="new" beforeResume={async()=>true}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Rascunhos: 1 salvos'}));
  fireEvent.click(await screen.findByRole('button',{name:'Excluir: Teste ABO'}));
  expect(archive).not.toHaveBeenCalled();
  expect(screen.getByText(/Packs, imagens e campanhas existentes/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Cancelar'}));
  expect(archive).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Excluir: Teste ABO'}));
  fireEvent.click(screen.getByRole('button',{name:'Confirmar exclusão'}));
  await waitFor(()=>expect(archive).toHaveBeenCalledWith(ref,2));
  expect(await screen.findByText(/Rascunho excluído. Imagens/)).toBeTruthy();
});
it('keeps a draft visible if the server rejects stale deletion', async () => {
  archive.mockReset(); archive.mockRejectedValue(new Error('Rascunho mudou em outra aba'));
  render(<RascunhosMeta currentRef="new" beforeResume={async()=>true}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Rascunhos: 1 salvos'}));
  fireEvent.click(await screen.findByRole('button',{name:'Excluir: Teste ABO'}));
  fireEvent.click(screen.getByRole('button',{name:'Confirmar exclusão'}));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('outra aba'));
  expect(screen.getByRole('button',{name:'Continuar: Teste ABO'})).toBeTruthy();
});
it('shows count and resumes only after current work is saved', async () => {
  const save = vi.fn().mockResolvedValue(true); const resume = vi.fn();
  render(<RascunhosMeta currentRef="new" beforeResume={save} onResume={resume} />);
  fireEvent.click(await screen.findByRole('button',{name:'Rascunhos: 1 salvos'}));
  fireEvent.click(await screen.findByRole('button',{name:'Continuar: Teste ABO'}));
  await waitFor(() => expect(resume).toHaveBeenCalledWith(ref));
  expect(save).toHaveBeenCalledTimes(1);
});
it('preserves current work if saving fails', async () => {
  const resume = vi.fn();
  render(<RascunhosMeta currentRef="new" beforeResume={async () => false} onResume={resume} />);
  fireEvent.click(await screen.findByRole('button',{name:'Rascunhos: 1 salvos'}));
  fireEvent.click(await screen.findByRole('button',{name:'Continuar: Teste ABO'}));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('Não trocamos'));
  expect(resume).not.toHaveBeenCalled();
});
it('identifies the current draft without reopening it', async () => {
  render(<RascunhosMeta currentRef={ref} beforeResume={async () => true} />);
  fireEvent.click(await screen.findByRole('button',{name:'Rascunhos: 1 salvos'}));
  expect((await screen.findByRole('button',{name:'Em edição: Teste ABO'}) as HTMLButtonElement).disabled).toBe(true);
});
it('distinguishes list failure from no saved drafts', async () => {
  list.mockRejectedValue(new Error('offline'));
  render(<RascunhosMeta currentRef="new" beforeResume={async () => true} />);
  fireEvent.click(await screen.findByRole('button',{name:'Rascunhos: consulta indisponível'}));
  await screen.findByRole('alert');
  expect(screen.queryByText(/Nenhum rascunho salvo/)).toBeNull();
});
it('does not query real data in demo', () => {
  render(<RascunhosMeta currentRef="new" beforeResume={async () => true} demo />);
  expect(list).not.toHaveBeenCalled();
});
