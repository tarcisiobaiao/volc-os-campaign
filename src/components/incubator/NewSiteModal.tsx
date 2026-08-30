import React, { useState, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, ListPlus, AlertTriangle } from 'lucide-react';
import type { NewSiteFormData } from '@/types/incubator';

type FormFields = Omit<NewSiteFormData, 'titles' | 'site_name' | 'articles_per_batch' | 'auto_publish'>;

const schema = z.object({
  site_niche: z.string().min(2, 'Nicho obrigatório'),
  site_audience: z.string().min(2, 'Audiência obrigatória'),
  country: z.string().min(2, 'País obrigatório'),
  wp_url: z.string().url('URL inválida'),
  wp_username: z.string().min(1, 'Usuário obrigatório'),
  wp_app_password: z.string().min(1, 'App Password obrigatório'),
  site_context: z.string().min(5, 'Contexto do projeto obrigatório'),
});

function extractDomain(url: string): string {
  try {
    const hostname = new URL(url).hostname;
    return hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

interface NewSiteModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: NewSiteFormData) => Promise<void>;
}

function parseTitles(text: string): string[] {
  return text
    .split('\n')
    .map(t => t.trim())
    .filter(t => t.length > 0);
}

export const NewSiteModal: React.FC<NewSiteModalProps> = ({ open, onOpenChange, onSubmit }) => {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormFields>({
    resolver: zodResolver(schema),
    defaultValues: {
      country: 'Brasil',
    },
  });

  const [titlesText, setTitlesText] = useState('');

  const parsed = useMemo(() => parseTitles(titlesText), [titlesText]);

  const analysis = useMemo(() => {
    const seen = new Set<string>();
    let duplicates = 0;
    let tooShort = 0;
    let tooLong = 0;
    const unique: string[] = [];

    for (const t of parsed) {
      const lower = t.toLowerCase();
      if (seen.has(lower)) {
        duplicates++;
        continue;
      }
      seen.add(lower);
      if (t.length < 10) tooShort++;
      if (t.length > 200) tooLong++;
      unique.push(t);
    }

    return { total: parsed.length, unique, duplicates, tooShort, tooLong, validCount: unique.length };
  }, [parsed]);

  const handleFormSubmit = async (data: FormFields) => {
    const formData: NewSiteFormData = {
      ...data,
      site_name: extractDomain(data.wp_url),
      articles_per_batch: 5,
      auto_publish: true,
      titles: analysis.unique.length > 0 ? analysis.unique : undefined,
    };
    await onSubmit(formData);
    reset();
    setTitlesText('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Novo Site na Incubadora</DialogTitle>
          <DialogDescription>
            Configure um novo site para o pipeline de geração de conteúdo e aprovação AdSense.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
          {/* Identificação */}
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <h4 className="kicker">Identificação</h4>
              <span className="hairline-aurora flex-1" />
            </div>

            <div className="grid grid-cols-1 gap-3">
              <div>
                <Label htmlFor="site_niche">Nicho</Label>
                <Input id="site_niche" placeholder="Peixes Betta e aquário" {...register('site_niche')} />
                {errors.site_niche && <p className="text-xs text-destructive mt-1">{errors.site_niche.message}</p>}
              </div>
              <div>
                <Label htmlFor="site_audience">Audiência</Label>
                <Input id="site_audience" placeholder="pessoas que querem cuidar de peixinhos" {...register('site_audience')} />
                {errors.site_audience && <p className="text-xs text-destructive mt-1">{errors.site_audience.message}</p>}
              </div>
              <div>
                <Label htmlFor="country">País</Label>
                <Input id="country" placeholder="Brasil" {...register('country')} />
                {errors.country && <p className="text-xs text-destructive mt-1">{errors.country.message}</p>}
              </div>
            </div>
          </div>

          {/* WordPress */}
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <h4 className="kicker">WordPress</h4>
              <span className="hairline-aurora flex-1" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <Label htmlFor="wp_url">URL do WordPress</Label>
                <Input id="wp_url" placeholder="https://manualdoagora.com" {...register('wp_url')} />
                {errors.wp_url && <p className="text-xs text-destructive mt-1">{errors.wp_url.message}</p>}
              </div>
              <div>
                <Label htmlFor="wp_username">Usuário</Label>
                <Input id="wp_username" placeholder="admin" {...register('wp_username')} />
                {errors.wp_username && <p className="text-xs text-destructive mt-1">{errors.wp_username.message}</p>}
              </div>
              <div>
                <Label htmlFor="wp_app_password">Application Password</Label>
                <Input id="wp_app_password" type="password" placeholder="xxxx xxxx xxxx xxxx" {...register('wp_app_password')} />
                {errors.wp_app_password && <p className="text-xs text-destructive mt-1">{errors.wp_app_password.message}</p>}
              </div>
            </div>
          </div>

          {/* Títulos dos Artigos */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><ListPlus className="h-3.5 w-3.5" /></span>
              <h4 className="kicker">Títulos dos Artigos</h4>
              <span className="hairline-aurora flex-1" />
            </div>
            <p className="text-xs text-muted-foreground">Cole os títulos abaixo (um por linha). Você pode adicionar mais depois.</p>
            <Textarea
              placeholder="Como cuidar de um peixe Betta em apartamento&#10;Melhores aquários para Betta em 2026&#10;Alimentação ideal para peixes Betta&#10;..."
              value={titlesText}
              onChange={(e) => setTitlesText(e.target.value)}
              rows={Math.min(Math.max(5, parsed.length + 1), 10)}
              className="resize-none font-mono text-sm"
            />
            {parsed.length > 0 && (
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">
                  {analysis.validCount} título{analysis.validCount !== 1 ? 's' : ''}
                </span>
                {analysis.duplicates > 0 && (
                  <span className="text-warning">{analysis.duplicates} duplicado{analysis.duplicates !== 1 ? 's' : ''}</span>
                )}
                {analysis.tooShort > 0 && (
                  <span className="flex items-center gap-1 text-warning">
                    <AlertTriangle className="h-3 w-3" />
                    {analysis.tooShort} curto{analysis.tooShort !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Contexto do Projeto */}
          <div>
            <Label htmlFor="site_context">Contexto do Projeto</Label>
            <Textarea
              id="site_context"
              placeholder="Blog focado em benefícios sociais e direitos do cidadão brasileiro. Público: famílias de baixa renda que buscam informações práticas sobre programas do governo."
              rows={3}
              {...register('site_context')}
            />
            <p className="text-xs text-muted-foreground mt-1">Descreva o nicho, público e tom do site. Será usado como contexto nos prompts de IA.</p>
            {errors.site_context && <p className="text-xs text-destructive mt-1">{errors.site_context.message}</p>}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Criar Site
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
