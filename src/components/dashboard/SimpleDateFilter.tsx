import { useState, useEffect } from "react";
import { Calendar as CalendarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { supabaseDataService } from "@/services/supabaseDataService";

interface SimpleDateFilterProps {
  selectedPeriod: 'today' | '7d' | '30d' | 'custom';
  selectedDate?: string;
  onPeriodChange: (period: 'today' | '7d' | '30d' | 'custom') => void;
  onDateChange?: (date: string) => void;
}

export function SimpleDateFilter({ 
  selectedPeriod, 
  selectedDate, 
  onPeriodChange, 
  onDateChange 
}: SimpleDateFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [customDate, setCustomDate] = useState<Date | undefined>(
    selectedDate ? new Date(selectedDate + 'T12:00:00') : undefined
  );
  const [serverDate, setServerDate] = useState<string>('');
  const [serverYesterday, setServerYesterday] = useState<string>('');

  // Initialize server dates on component mount
  useEffect(() => {
    const initializeServerDates = async () => {
      try {
        // Get current server date (São Paulo timezone)
        const currentServerDate = await supabaseDataService.getServerDate();
        setServerDate(currentServerDate);
        
        // Calculate server yesterday
        const serverDateObj = new Date(currentServerDate + 'T00:00:00-03:00'); // São Paulo timezone
        const yesterdayObj = new Date(serverDateObj);
        yesterdayObj.setDate(yesterdayObj.getDate() - 1);
        const yesterdayStr = yesterdayObj.toISOString().split('T')[0];
        setServerYesterday(yesterdayStr);
        
        // Initialize customDate with server date if not set
        if (!selectedDate && !customDate) {
          setCustomDate(new Date(currentServerDate + 'T12:00:00'));
        }
        
        console.log('📅 SimpleDateFilter initialized with server dates:', {
          today: currentServerDate,
          yesterday: yesterdayStr
        });
      } catch (error) {
        console.error('Error initializing server dates:', error);
        // Fallback to local dates in São Paulo timezone
        const now = new Date();
        const saoPauloToday = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(now);
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        const saoPauloYesterday = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(yesterday);
        
        setServerDate(saoPauloToday);
        setServerYesterday(saoPauloYesterday);
        if (!selectedDate && !customDate) {
          setCustomDate(new Date(saoPauloToday + 'T12:00:00'));
        }
      }
    };
    
    initializeServerDates();
  }, []);

  // Update customDate when selectedDate changes
  useEffect(() => {
    if (selectedDate) {
      const newDate = new Date(selectedDate + 'T12:00:00');
      if (!customDate || customDate.getTime() !== newDate.getTime()) {
        setCustomDate(newDate);
      }
    }
  }, [selectedDate, customDate]);

  const handlePeriodChange = (period: string) => {
    const typedPeriod = period as 'today' | '7d' | '30d' | 'custom';
    onPeriodChange(typedPeriod);
    
    if (typedPeriod !== 'custom' && onDateChange && serverDate) {
      onDateChange(serverDate); // Use server date instead of local date
    }
  };

  const handleCustomDateChange = (date: Date | undefined) => {
    setCustomDate(date);
    if (onDateChange && date) {
      // Convert to São Paulo timezone and format as YYYY-MM-DD
      const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }).format(date);
      onDateChange(saoPauloDate);
    }
    setIsOpen(false);
  };

  return (
    <div className="flex items-center gap-2">
      <Select value={selectedPeriod} onValueChange={handlePeriodChange}>
        <SelectTrigger className="w-40">
          <CalendarIcon className="h-4 w-4 mr-2" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="today">📅 Hoje</SelectItem>
          <SelectItem value="7d">📊 7 dias</SelectItem>
          <SelectItem value="30d">📈 30 dias</SelectItem>
          <SelectItem value="custom">🗓️ Data específica</SelectItem>
        </SelectContent>
      </Select>

      {selectedPeriod === 'custom' && (
        <Popover open={isOpen} onOpenChange={setIsOpen}>
          <PopoverTrigger asChild>
            <Button 
              variant="outline" 
              className={cn(
                "w-[280px] justify-start text-left font-normal",
                !customDate && "text-muted-foreground"
              )}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {customDate ? (
                format(customDate, "dd/MM/yyyy", { locale: ptBR })
              ) : (
                <span>Selecione uma data</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <div className="p-3 border-b">
              <h4 className="font-medium text-sm">Data específica</h4>
            </div>
            <Calendar
              mode="single"
              selected={customDate}
              onSelect={handleCustomDateChange}
              disabled={(date) =>
                date > new Date() || date < new Date("1900-01-01")
              }
              locale={ptBR}
              initialFocus
            />
            <div className="p-3 border-t">
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    if (serverDate) {
                      handleCustomDateChange(new Date(serverDate + 'T12:00:00'));
                    }
                  }}
                  disabled={!serverDate}
                >
                  Hoje
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    if (serverYesterday) {
                      handleCustomDateChange(new Date(serverYesterday + 'T12:00:00'));
                    }
                  }}
                  disabled={!serverYesterday}
                >
                  Ontem
                </Button>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}




