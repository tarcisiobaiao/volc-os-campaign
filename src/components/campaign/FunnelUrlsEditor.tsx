import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { Plus, Trash2, Save, X, Globe, Info } from 'lucide-react';
import { CampaignFunnelUrl, CampaignFunnelUrlInput, campaignFunnelUrlsService } from '@/services/campaignFunnelUrlsService';

interface FunnelUrlsEditorProps {
  isOpen: boolean;
  onClose: () => void;
  campaignId: string;
  campaignName: string;
  onSave?: () => void;
}

interface FunnelUrlItem {
  id?: number;
  url: string;
  isNew?: boolean;
}

export const FunnelUrlsEditor: React.FC<FunnelUrlsEditorProps> = ({
  isOpen,
  onClose,
  campaignId,
  campaignName,
  onSave
}) => {
  const [urls, setUrls] = useState<FunnelUrlItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  // Carregar URLs existentes quando o dialog abrir
  useEffect(() => {
    if (isOpen && campaignId) {
      loadFunnelUrls();
    }
  }, [isOpen, campaignId]);

  const loadFunnelUrls = async () => {
    try {
      setLoading(true);
      const existingUrls = await campaignFunnelUrlsService.getFunnelUrlsByCampaign(campaignId);
      
      setUrls(existingUrls.map(url => ({
        id: url.id,
        url: url.url,
        isNew: false
      })));

      // Se não houver URLs, adicionar uma linha vazia
      if (existingUrls.length === 0) {
        setUrls([{ url: '', isNew: true }]);
      }
    } catch (error) {
      console.error('Error loading funnel URLs:', error);
      toast({
        title: "Erro ao carregar URLs",
        description: "Não foi possível carregar as URLs do funil.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const addNewUrl = () => {
    setUrls(prev => [...prev, { url: '', isNew: true }]);
  };

  const removeUrl = (index: number) => {
    setUrls(prev => prev.filter((_, i) => i !== index));
  };

  const updateUrl = (index: number, field: 'url', value: string) => {
    setUrls(prev => prev.map((item, i) => 
      i === index ? { ...item, [field]: value } : item
    ));
  };

  const validateUrls = (): { isValid: boolean; errors: string[] } => {
    const errors: string[] = [];
    
    urls.forEach((urlItem, index) => {
      if (urlItem.url.trim()) {
        const validation = campaignFunnelUrlsService.validateUrl(urlItem.url);
        if (!validation.isValid) {
          errors.push(`URL ${index + 1}: ${validation.error}`);
        }
      }
    });

    // Verificar se há pelo menos uma URL
    const hasValidUrls = urls.some(item => item.url.trim() !== '');
    if (!hasValidUrls) {
      errors.push('Adicione pelo menos uma URL válida');
    }

    return { isValid: errors.length === 0, errors };
  };

  const handleSave = async () => {
    try {
      setSaving(true);

      // Validar URLs
      const validation = validateUrls();
      if (!validation.isValid) {
        toast({
          title: "Erro de validação",
          description: validation.errors.join('\n'),
          variant: "destructive",
        });
        return;
      }

      // Filtrar URLs vazias e preparar para salvar
      const urlsToSave: CampaignFunnelUrlInput[] = urls
        .filter(item => item.url.trim() !== '')
        .map(item => ({
          campaign_id: campaignId,
          url: item.url.trim(),
          Active: true
        }));

      await campaignFunnelUrlsService.saveFunnelUrls(campaignId, urlsToSave);

      toast({
        title: "URLs salvas com sucesso",
        description: `${urlsToSave.length} URL(s) do funil foram salvas.`,
        variant: "default",
      });

      onSave?.();
      onClose();
    } catch (error) {
      console.error('Error saving funnel URLs:', error);
      toast({
        title: "Erro ao salvar",
        description: "Não foi possível salvar as URLs do funil.",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    setUrls([]);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="rounded-md bg-primary/10 text-primary p-1.5"><Globe className="h-4 w-4" /></span>
            URLs do Funil AdSense
          </DialogTitle>
          <DialogDescription>
            Configure as URLs que compõem o funil da campanha <strong>{campaignName}</strong>.
            <br />
            <span className="text-xs text-muted-foreground">
              As URLs serão automaticamente limpas (sem https://, www., etc.)
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {loading ? (
            <div className="space-y-2 py-2">
              <div className="skeleton h-9 w-full" />
              <div className="skeleton h-9 w-full" />
              <div className="skeleton h-9 w-2/3" />
            </div>
          ) : (
            <>
              {urls.map((urlItem, index) => (
                <div key={index} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-11">
                    <Label htmlFor={`url-${index}`} className="text-xs">
                      URL {index + 1}
                    </Label>
                    <Input
                      id={`url-${index}`}
                      placeholder="https://exemplo.com/pagina"
                      value={urlItem.url}
                      onChange={(e) => updateUrl(index, 'url', e.target.value)}
                      className="text-sm"
                    />
                  </div>
                  <div className="col-span-1">
                    {urls.length > 1 && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => removeUrl(index)}
                        className="h-9 w-9 p-0 text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}

              <Button
                type="button"
                variant="outline"
                onClick={addNewUrl}
                className="w-full"
              >
                <Plus className="h-4 w-4 mr-2" />
                Adicionar URL
              </Button>

              {urls.length > 0 && (
                <div className="flex items-start gap-2 text-xs text-muted-foreground bg-info/5 border border-info/20 p-3 rounded-md">
                  <Info className="h-3.5 w-3.5 mt-0.5 text-info flex-shrink-0" />
                  <span>
                    <strong className="text-foreground">Dica:</strong> As URLs serão automaticamente limpas (sem https://, www.) pelo sistema
                    e usadas para coletar métricas do AdSense associadas a esta campanha.
                  </span>
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={saving}>
            <X className="h-4 w-4 mr-2" />
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving || loading}>
            {saving ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Salvando...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Salvar URLs
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
