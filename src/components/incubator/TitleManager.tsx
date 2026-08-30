import React, { useState, useMemo, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  FileText,
  Plus,
  Trash2,
  RefreshCw,
  Search,
  ExternalLink,
  Loader2,
  Clock,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useTitles } from '@/hooks/incubator/useTitles';
import { TitleInput } from './TitleInput';
import type { IncubatorArticle, ArticleStatus, BulkInsertResult } from '@/types/incubator';
import { ARTICLE_STATUS_LABELS, ARTICLE_STATUS_COLORS } from '@/types/incubator';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface TitleManagerProps {
  siteId: number;
  articles: IncubatorArticle[];
  onRefresh: () => void;
}

type FilterStatus = 'all' | ArticleStatus;

export const TitleManager: React.FC<TitleManagerProps> = ({ siteId, articles, onRefresh }) => {
  const { toast } = useToast();
  const { insertBatch, removeTitles, retryFailed, inserting, removing, retrying } = useTitles(siteId);

  const [filter, setFilter] = useState<FilterStatus>('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showAddModal, setShowAddModal] = useState(false);

  // Status priority: in-progress first, then pending/scheduled, then done
  const STATUS_PRIORITY: Record<ArticleStatus, number> = {
    researching: 0,
    writing: 1,
    seo_optimizing: 2,
    image_generating: 3,
    publishing: 4,
    pending: 5,
    failed: 6,
    published: 7,
  };

  // Filtered + sorted articles
  const filtered = useMemo(() => {
    let list = [...articles];
    if (filter !== 'all') {
      list = list.filter(a => a.status === filter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(a => a.title.toLowerCase().includes(q));
    }
    // Sort: in-progress > pending (scheduled today first) > failed > published
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);
    list.sort((a, b) => {
      const pa = STATUS_PRIORITY[a.status] ?? 9;
      const pb = STATUS_PRIORITY[b.status] ?? 9;
      if (pa !== pb) return pa - pb;
      // Within same status, scheduled today first, then by scheduled_at ASC
      if (a.status === 'pending' && b.status === 'pending') {
        const aToday = a.scheduled_at?.slice(0, 10) === todayStr ? 0 : 1;
        const bToday = b.scheduled_at?.slice(0, 10) === todayStr ? 0 : 1;
        if (aToday !== bToday) return aToday - bToday;
        if (a.scheduled_at && b.scheduled_at) return a.scheduled_at.localeCompare(b.scheduled_at);
        if (a.scheduled_at) return -1;
        if (b.scheduled_at) return 1;
      }
      return 0;
    });
    return list;
  }, [articles, filter, search]);

  // Stats
  const stats = useMemo(() => ({
    total: articles.length,
    pending: articles.filter(a => a.status === 'pending').length,
    published: articles.filter(a => a.status === 'published').length,
    failed: articles.filter(a => a.status === 'failed').length,
    scheduled: articles.filter(a => a.scheduled_at && a.status === 'pending').length,
  }), [articles]);

  const existingTitles = useMemo(() => articles.map(a => a.title), [articles]);

  // Toggle selection
  const toggleSelect = useCallback((id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selected.size === filtered.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map(a => a.id)));
    }
  }, [filtered, selected]);

  // Actions
  const handleInsert = useCallback(async (titles: string[]): Promise<BulkInsertResult> => {
    const result = await insertBatch(titles);
    toast({
      title: 'Títulos adicionados',
      description: `${result.inserted} inserido${result.inserted !== 1 ? 's' : ''}, ${result.skipped_duplicates} duplicado${result.skipped_duplicates !== 1 ? 's' : ''} ignorado${result.skipped_duplicates !== 1 ? 's' : ''}`,
    });
    onRefresh();
    setShowAddModal(false);
    return result;
  }, [insertBatch, toast, onRefresh]);

  const handleRemove = useCallback(async () => {
    const ids = Array.from(selected);
    // Only allow removing pending/failed
    const removable = articles.filter(a => ids.includes(a.id) && ['pending', 'failed'].includes(a.status));
    if (removable.length === 0) {
      toast({ title: 'Nenhum artigo removível selecionado', description: 'Só é possível remover artigos pendentes ou com falha', variant: 'destructive' });
      return;
    }
    const count = await removeTitles(removable.map(a => a.id));
    toast({ title: `${count} artigo${count !== 1 ? 's' : ''} removido${count !== 1 ? 's' : ''}` });
    setSelected(new Set());
    onRefresh();
  }, [selected, articles, removeTitles, toast, onRefresh]);

  const handleRetry = useCallback(async () => {
    const ids = Array.from(selected);
    const failedIds = articles.filter(a => ids.includes(a.id) && a.status === 'failed').map(a => a.id);
    if (failedIds.length === 0) {
      toast({ title: 'Nenhum artigo com falha selecionado', variant: 'destructive' });
      return;
    }
    const count = await retryFailed(failedIds);
    toast({ title: `${count} artigo${count !== 1 ? 's' : ''} reenviado${count !== 1 ? 's' : ''} para a fila` });
    setSelected(new Set());
    onRefresh();
  }, [selected, articles, retryFailed, toast, onRefresh]);

  const selectedHasRemovable = useMemo(
    () => articles.some(a => selected.has(a.id) && ['pending', 'failed'].includes(a.status)),
    [articles, selected]
  );

  const selectedHasFailed = useMemo(
    () => articles.some(a => selected.has(a.id) && a.status === 'failed'),
    [articles, selected]
  );

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><FileText className="h-4 w-4" /></span>
              Títulos <span className="tabular text-muted-foreground">({stats.total})</span>
              {stats.published > 0 && (
                <Badge variant="secondary" className="text-xs">{stats.published} publicados</Badge>
              )}
              {stats.failed > 0 && (
                <Badge variant="destructive" className="text-xs">{stats.failed} falhou</Badge>
              )}
            </CardTitle>
            <div className="flex items-center gap-2">
              {stats.failed > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    const failedIds = articles.filter(a => a.status === 'failed').map(a => a.id);
                    const count = await retryFailed(failedIds);
                    toast({ title: `${count} artigo${count !== 1 ? 's' : ''} reenviado${count !== 1 ? 's' : ''} para a fila` });
                    onRefresh();
                  }}
                  disabled={retrying}
                >
                  {retrying ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                  Retentar Todos ({stats.failed})
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => setShowAddModal(true)}>
                <Plus className="h-4 w-4 mr-1" />
                Adicionar Mais
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {/* Filters */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Filtrar títulos..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-8 text-sm"
              />
            </div>
            <Select value={filter} onValueChange={(v) => setFilter(v as FilterStatus)}>
              <SelectTrigger className="h-8 w-[140px] text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="pending">Pendente</SelectItem>
                <SelectItem value="published">Publicado</SelectItem>
                <SelectItem value="failed">Falhou</SelectItem>
                <SelectItem value="researching">Pesquisando</SelectItem>
                <SelectItem value="writing">Escrevendo</SelectItem>
                <SelectItem value="publishing">Publicando</SelectItem>
              </SelectContent>
            </Select>
            {filtered.length > 0 && (
              <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={toggleAll}>
                {selected.size === filtered.length ? 'Desmarcar' : 'Selecionar'} todos
              </Button>
            )}
          </div>

          {/* Bulk actions — acima da lista para visibilidade */}
          {selected.size > 0 && (
            <div className="flex items-center gap-2 bg-muted/50 rounded-md px-3 py-2">
              <span className="text-xs font-medium">{selected.size} selecionado{selected.size !== 1 ? 's' : ''}</span>
              {selectedHasRemovable && (
                <Button
                  variant="destructive"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={handleRemove}
                  disabled={removing}
                >
                  {removing ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Trash2 className="h-3 w-3 mr-1" />}
                  Remover
                </Button>
              )}
              {selectedHasFailed && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={handleRetry}
                  disabled={retrying}
                >
                  {retrying ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <RefreshCw className="h-3 w-3 mr-1" />}
                  Retentar Falhos
                </Button>
              )}
              {!selectedHasRemovable && !selectedHasFailed && (
                <span className="text-xs text-muted-foreground">Artigos em andamento ou publicados não podem ser removidos</span>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs ml-auto"
                onClick={() => setSelected(new Set())}
              >
                Limpar seleção
              </Button>
            </div>
          )}

          {/* Articles list */}
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-1.5 py-8 text-center">
              <FileText className="h-6 w-6 text-muted-foreground/60" />
              <span className="kicker">{articles.length === 0 ? 'Sem títulos' : 'Nada encontrado'}</span>
              <p className="text-sm text-muted-foreground">
                {articles.length === 0
                  ? 'Nenhum título cadastrado — clique em "Adicionar Mais"'
                  : 'Nenhum título encontrado com este filtro'}
              </p>
            </div>
          ) : (
            <div className="border border-border rounded-md divide-y divide-border max-h-[400px] overflow-y-auto">
              {filtered.map((article) => (
                <div
                  key={article.id}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 hover:bg-muted/40 transition-colors text-sm",
                    selected.has(article.id) && "bg-primary/5"
                  )}
                >
                  <Checkbox
                    checked={selected.has(article.id)}
                    onCheckedChange={() => toggleSelect(article.id)}
                  />
                  <span className="flex-1 truncate" title={article.title}>
                    {article.title}
                  </span>
                  <span className="shrink-0 text-xs">
                    {article.scheduled_at && article.status === 'pending' ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-info/12 text-info px-2 py-0.5 tabular">
                        <Clock className="h-3 w-3" />
                        {format(new Date(article.scheduled_at), 'dd/MM HH:mm', { locale: ptBR })}
                      </span>
                    ) : (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${ARTICLE_STATUS_COLORS[article.status]?.bg} ${ARTICLE_STATUS_COLORS[article.status]?.text}`}>
                        {ARTICLE_STATUS_LABELS[article.status]}
                      </span>
                    )}
                  </span>
                  {article.wp_post_url && (
                    <a
                      href={article.wp_post_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:text-primary/80 shrink-0"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add titles modal */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="sm:max-w-[550px]">
          <DialogHeader>
            <DialogTitle>Adicionar Títulos</DialogTitle>
          </DialogHeader>
          <TitleInput
            onInsert={handleInsert}
            inserting={inserting}
            existingTitles={existingTitles}
            inline
          />
        </DialogContent>
      </Dialog>
    </>
  );
};
