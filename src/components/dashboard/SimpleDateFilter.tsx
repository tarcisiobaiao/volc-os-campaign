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
  selectedPeriod: 'today' | 'yesterday' | 'custom';
  selectedDate?: string;
  onPeriodChange: (period: 'today' | 'yesterday' | 'custom') => void;
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

        console.log({
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
    const typedPeriod = period as 'today' | 'yesterday' | 'custom';
    onPeriodChange(typedPeriod);

    if (typedPeriod === 'today' && onDateChange && serverDate) {
      onDateChange(serverDate); // Use server date for today
    } else if (typedPeriod === 'yesterday' && onDateChange && serverYesterday) {
      onDateChange(serverYesterday); // Use server yesterday date
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

  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  
  return (
    <div className={`flex ${isMobile ? 'flex-col w-full' : 'items-center'} gap-2 flex-shrink-0`}>
      <Select value={selectedPeriod} onValueChange={handlePeriodChange}>
        <SelectTrigger className={isMobile ? "w-full touch-target" : "w-40"}>
          <CalendarIcon className="h-4 w-4 mr-2" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="today" className="touch-target">Hoje</SelectItem>
          <SelectItem value="yesterday" className="touch-target">Ontem</SelectItem>
          <SelectItem value="custom" className="touch-target">Data específica</SelectItem>
        </SelectContent>
      </Select>

      {selectedPeriod === 'custom' && (
        <Popover open={isOpen} onOpenChange={setIsOpen}>
          <PopoverTrigger asChild>
            <Button 
              variant="outline" 
              className={cn(
                isMobile ? "w-full touch-target" : "w-[280px]",
                "justify-start text-left font-normal",
                !customDate && "text-muted-foreground"
              )}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {customDate ? (
                <span className="tabular">{format(customDate, "dd/MM/yyyy", { locale: ptBR })}</span>
              ) : (
                <span>Selecione uma data</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className={cn("w-auto p-0", isMobile && "w-[95vw] max-w-[400px]")} align={isMobile ? "center" : "start"}>
            <div className="p-3 border-b">
              <span className="kicker">Data específica</span>
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
              <div className={`flex ${isMobile ? 'flex-col' : 'gap-2'}`}>
                <Button
                  size="sm"
                  variant="outline"
                  className={isMobile ? "w-full touch-target mb-2" : "flex-1 touch-target"}
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
                  className={isMobile ? "w-full touch-target" : "flex-1 touch-target"}
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




