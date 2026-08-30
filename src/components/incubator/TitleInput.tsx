import React, { useState, useMemo, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ListPlus, Loader2, AlertTriangle } from 'lucide-react';

interface TitleInputProps {
  onInsert: (titles: string[]) => Promise<{ inserted: number; skipped_duplicates: number }>;
  inserting?: boolean;
  existingTitles?: string[];
  /** Modo inline (sem card wrapper) para uso dentro de modais */
  inline?: boolean;
}

function parseTitles(text: string): string[] {
  return text
    .split('\n')
    .map(t => t.trim())
    .filter(t => t.length > 0);
}

export const TitleInput: React.FC<TitleInputProps> = ({
  onInsert,
  inserting = false,
  existingTitles = [],
  inline = false,
}) => {
  const [text, setText] = useState('');

  const parsed = useMemo(() => parseTitles(text), [text]);

  const existingSet = useMemo(
    () => new Set(existingTitles.map(t => t.toLowerCase().trim())),
    [existingTitles]
  );

  const analysis = useMemo(() => {
    const titles = parsed;
    const seen = new Set<string>();
    let duplicatesExisting = 0;
    let duplicatesInternal = 0;
    let tooShort = 0;
    let tooLong = 0;
    const unique: string[] = [];

    for (const t of titles) {
      const lower = t.toLowerCase();
      if (seen.has(lower)) {
        duplicatesInternal++;
        continue;
      }
      seen.add(lower);
      if (existingSet.has(lower)) {
        duplicatesExisting++;
        continue;
      }
      if (t.length < 10) tooShort++;
      if (t.length > 200) tooLong++;
      unique.push(t);
    }

    return {
      total: titles.length,
      unique,
      duplicatesExisting,
      duplicatesInternal,
      totalDuplicates: duplicatesExisting + duplicatesInternal,
      tooShort,
      tooLong,
      validCount: unique.length,
    };
  }, [parsed, existingSet]);

  const handleInsert = async () => {
    if (analysis.validCount === 0) return;
    const result = await onInsert(analysis.unique);
    if (result) {
      setText('');
    }
  };

  const content = (
    <div className="space-y-3">
      <Textarea
        placeholder="Cole os títulos aqui (um por linha)&#10;&#10;Exemplo:&#10;Como cuidar de um peixe Betta&#10;Melhores aquários para Betta 2026&#10;Alimentação ideal para peixes Betta"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={Math.min(Math.max(6, parsed.length + 2), 15)}
        className="resize-none font-mono text-sm"
      />

      {parsed.length > 0 && (
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="font-medium text-foreground tabular">
              {analysis.validCount} título{analysis.validCount !== 1 ? 's' : ''} para inserir
            </span>
            {analysis.totalDuplicates > 0 && (
              <span className="text-warning">
                {analysis.totalDuplicates} duplicado{analysis.totalDuplicates !== 1 ? 's' : ''}
              </span>
            )}
            {analysis.tooShort > 0 && (
              <span className="flex items-center gap-1 text-warning">
                <AlertTriangle className="h-3 w-3" />
                {analysis.tooShort} muito curto{analysis.tooShort !== 1 ? 's' : ''}
              </span>
            )}
            {analysis.tooLong > 0 && (
              <span className="flex items-center gap-1 text-warning">
                <AlertTriangle className="h-3 w-3" />
                {analysis.tooLong} muito longo{analysis.tooLong !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          <Button
            onClick={handleInsert}
            disabled={inserting || analysis.validCount === 0}
            size="sm"
          >
            {inserting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Inserindo...
              </>
            ) : (
              <>
                <ListPlus className="h-4 w-4 mr-2" />
                Adicionar Títulos
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );

  if (inline) return content;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <span className="rounded-md bg-primary/10 text-primary p-1.5"><ListPlus className="h-3.5 w-3.5" /></span>
          Títulos dos Artigos
        </CardTitle>
        <p className="text-xs text-muted-foreground">Cole os títulos abaixo (um por linha)</p>
      </CardHeader>
      <CardContent>{content}</CardContent>
    </Card>
  );
};
