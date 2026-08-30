import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ArticleStatusBadge } from '@/components/incubator/StatusBadge';
import { ExternalLink, FileText } from 'lucide-react';
import type { IncubatorArticle } from '@/types/incubator';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface ArticlesTableProps {
  articles: IncubatorArticle[];
}

export const ArticlesTable: React.FC<ArticlesTableProps> = ({ articles }) => {
  return (
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 0 }}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="rounded-md bg-primary/10 text-primary p-1.5"><FileText className="h-4 w-4" /></span>
          Artigos
          <span className="tabular text-sm font-normal text-muted-foreground">({articles.length})</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {articles.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <span className="rounded-lg bg-muted text-muted-foreground p-2.5"><FileText className="h-5 w-5" /></span>
            <p className="kicker">Sem artigos</p>
            <p className="text-sm text-muted-foreground">Nenhum artigo registrado</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="kicker">Título</TableHead>
                  <TableHead className="kicker w-[120px]">Status</TableHead>
                  <TableHead className="kicker w-[120px]">Keyword</TableHead>
                  <TableHead className="kicker w-[120px]">Publicado</TableHead>
                  <TableHead className="w-[40px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {articles.map((article) => (
                  <TableRow key={article.id} className="border-border hover:bg-muted/40">
                    <TableCell className="font-medium max-w-[300px] truncate" title={article.title}>
                      {article.title}
                    </TableCell>
                    <TableCell>
                      <ArticleStatusBadge status={article.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground truncate" title={article.focus_keyword || ''}>
                      {article.focus_keyword || '—'}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground tabular">
                      {article.published_at
                        ? format(new Date(article.published_at), "dd/MM HH:mm", { locale: ptBR })
                        : '—'}
                    </TableCell>
                    <TableCell>
                      {article.wp_post_url && (
                        <a
                          href={article.wp_post_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex text-primary hover:text-primary/80 transition-colors"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
