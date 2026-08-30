import { Badge } from "@/components/ui/badge";
import { CheckCircle, AlertTriangle, Clock, Info } from "lucide-react";
import { useState, useEffect } from "react";
import { systemSettingsService } from "@/services/systemSettingsService";
import { formatSaoPauloTimestamp } from "@/utils/timezone";

interface DataStatusProps {
  loading: boolean;
  error: string | null;
  lastUpdate?: string;
  showDetails?: boolean; // Optional: show GAM/Google Ads breakdown
}

export function DataStatus({ loading, error, lastUpdate, showDetails = false }: DataStatusProps) {
  const [detailedTimestamps, setDetailedTimestamps] = useState<{
    gamLastUpdate: string | null;
    googleAdsLastUpdate: string | null;
    mostRecent: string | null;
  } | null>(null);
  const [showDetailView, setShowDetailView] = useState(false);
  const [globalMostRecent, setGlobalMostRecent] = useState<string | null>(null);

  // Always fetch timestamps to determine the most recent globally
  useEffect(() => {
    const fetchTimestamps = async () => {
      try {
        // Use systemSettingsService for direct access to system_settings table
        const timestamps = await systemSettingsService.getSystemTimestamps();
        setDetailedTimestamps(timestamps);
        
        
        // Set global most recent timestamp for display
        if (timestamps.mostRecent) {
          // The timestamp from system_settings is already in Brazilian format
          setGlobalMostRecent(timestamps.mostRecent);
        } else if (lastUpdate) {
          setGlobalMostRecent(lastUpdate);
        }
      } catch (error) {
        console.error('Error fetching timestamps from system_settings:', error);
        // Fallback to provided lastUpdate
        if (lastUpdate) {
          setGlobalMostRecent(lastUpdate);
        }
      }
    };
    
    fetchTimestamps();
  }, [lastUpdate]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Clock className="h-4 w-4 animate-spin" />
        <span>Carregando dados...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="destructive" className="flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />
          Erro ao carregar
        </Badge>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      <Badge
        variant="outline"
        className="flex items-center gap-1.5 bg-success/12 text-success border-success/25 cursor-pointer whitespace-nowrap hover:bg-success/20 transition-colors"
        onClick={() => setShowDetailView(!showDetailView)}
      >
        <CheckCircle className="h-3 w-3 flex-shrink-0" />
        <span className="whitespace-nowrap">Dados atualizados</span>
        <Info className="h-3 w-3 ml-0.5 flex-shrink-0 opacity-70" />
      </Badge>

      {globalMostRecent && !showDetailView && (
        <span className="text-xs text-muted-foreground whitespace-nowrap tabular">
          {globalMostRecent}
        </span>
      )}

      {showDetailView && detailedTimestamps && (
        <div className="flex flex-col gap-1 text-xs text-muted-foreground">
          {detailedTimestamps.gamLastUpdate && (
            <div className="flex items-center gap-2">
              <span className="kicker">GAM</span>
              <span className="tabular">{detailedTimestamps.gamLastUpdate}</span>
            </div>
          )}
          {detailedTimestamps.googleAdsLastUpdate && (
            <div className="flex items-center gap-2">
              <span className="kicker">Google Ads</span>
              <span className="tabular">{detailedTimestamps.googleAdsLastUpdate}</span>
            </div>
          )}
          {!detailedTimestamps.gamLastUpdate && !detailedTimestamps.googleAdsLastUpdate && globalMostRecent && (
            <div className="flex items-center gap-2">
              <span className="kicker">Última atualização</span>
              <span className="tabular">{globalMostRecent}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}