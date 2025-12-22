import { useState, useEffect } from "react";
import { Calendar as CalendarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";
import { format, parse, isValid, differenceInDays } from "date-fns";
import { ptBR } from "date-fns/locale";
import { supabaseDataService } from "@/services/supabaseDataService";

interface DateFilterProps {
  selectedPeriod: 'today' | 'yesterday' | 'custom' | 'range';
  selectedDate?: string;
  selectedEndDate?: string;
  onPeriodChange: (period: 'today' | 'yesterday' | 'custom' | 'range') => void;
  onDateChange?: (date: string) => void;
  onDateRangeChange?: (startDate: string, endDate: string) => void;
}

export function DateFilter({ 
  selectedPeriod, 
  selectedDate,
  selectedEndDate,
  onPeriodChange, 
  onDateChange,
  onDateRangeChange
}: DateFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [customDate, setCustomDate] = useState<Date | undefined>(
    selectedDate ? new Date(selectedDate + 'T12:00:00') : undefined
  );
  const [rangeStartDate, setRangeStartDate] = useState<Date | undefined>(
    selectedDate ? new Date(selectedDate + 'T12:00:00') : undefined
  );
  const [rangeEndDate, setRangeEndDate] = useState<Date | undefined>(
    selectedEndDate ? new Date(selectedEndDate + 'T12:00:00') : undefined
  );
  
  // Estados temporários para a seleção (antes de aplicar)
  const [tempCustomDate, setTempCustomDate] = useState<Date | undefined>(customDate);
  const [tempRangeStartDate, setTempRangeStartDate] = useState<Date | undefined>(rangeStartDate);
  const [tempRangeEndDate, setTempRangeEndDate] = useState<Date | undefined>(rangeEndDate);
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
        const serverDateObj = new Date(currentServerDate + 'T12:00:00'); // Use noon to avoid timezone issues
        const yesterdayObj = new Date(serverDateObj);
        yesterdayObj.setDate(yesterdayObj.getDate() - 1);
        const yesterdayStr = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        }).format(yesterdayObj);
        setServerYesterday(yesterdayStr);
        
        // Initialize customDate with server date if not set
        if (!selectedDate && !customDate) {
          setCustomDate(new Date(currentServerDate + 'T12:00:00'));
        }
        
        console.log('📅 DateFilter initialized with server dates:', {
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
    const typedPeriod = period as 'today' | 'yesterday' | 'custom' | 'range';
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
  };

  const handleRangeChange = (dates: { from?: Date; to?: Date } | undefined) => {
    if (dates?.from) {
      setRangeStartDate(dates.from);
    }
    if (dates?.to) {
      setRangeEndDate(dates.to);
    }
    
    if (onDateRangeChange && dates?.from && dates?.to) {
      // Convert both dates to São Paulo timezone and format as YYYY-MM-DD
      const startDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }).format(dates.from);
      
      const endDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }).format(dates.to);
      
      onDateRangeChange(startDate, endDate);
    }
  };

  // Função para aplicar as mudanças temporárias
  const handleApplyChanges = () => {
    console.log('🔧 DateFilter handleApplyChanges called:', {
      tempRangeStartDate,
      tempRangeEndDate,
      tempCustomDate
    });
    
    if (tempRangeStartDate && tempRangeEndDate) {
      // Aplicar range
      setRangeStartDate(tempRangeStartDate);
      setRangeEndDate(tempRangeEndDate);
      setCustomDate(undefined);
      
      if (onDateRangeChange) {
        const startDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        }).format(tempRangeStartDate);
        
        const endDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        }).format(tempRangeEndDate);
        
        console.log('🔧 DateFilter calling onDateRangeChange:', { startDate, endDate });
        onDateRangeChange(startDate, endDate);
      }
    } else if (tempCustomDate) {
      // Aplicar data única
      setCustomDate(tempCustomDate);
      setRangeStartDate(undefined);
      setRangeEndDate(undefined);
      
      if (onDateChange) {
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        }).format(tempCustomDate);
        onDateChange(saoPauloDate);
      }
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
          <SelectItem value="today">📅 Hoje</SelectItem>
          <SelectItem value="yesterday">📆 Ontem</SelectItem>
          <SelectItem value="custom">🗓️ Data personalizada</SelectItem>
        </SelectContent>
      </Select>

      {(selectedPeriod === 'custom' || selectedPeriod === 'range') && (
        <Popover open={isOpen} onOpenChange={(open) => {
          setIsOpen(open);
          if (open) {
            // Reset temporary states to current values when opening
            setTempCustomDate(customDate);
            setTempRangeStartDate(rangeStartDate);
            setTempRangeEndDate(rangeEndDate);
          }
        }}>
          <PopoverTrigger asChild>
            <Button 
              variant="outline" 
              className={cn(
                isMobile ? "w-full touch-target" : "w-[320px]",
                "justify-start text-left font-normal",
                (!customDate && !rangeStartDate) && "text-muted-foreground"
              )}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {rangeStartDate && rangeEndDate ? (
                <>
                  {format(rangeStartDate, "dd/MM/yyyy", { locale: ptBR })}
                  {" até "}
                  {format(rangeEndDate, "dd/MM/yyyy", { locale: ptBR })}
                  <span className="ml-2 text-xs text-muted-foreground">
                    ({differenceInDays(rangeEndDate, rangeStartDate) + 1} dias)
                  </span>
                </>
              ) : customDate ? (
                format(customDate, "dd/MM/yyyy", { locale: ptBR })
              ) : (
                <span>{selectedPeriod === 'range' ? 'Selecionar período personalizado' : 'Selecionar período'}</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <div className="p-3 border-b">
              <h4 className="font-medium text-sm">Selecionar período</h4>
              <p className="text-xs text-muted-foreground mt-1">
                Clique em uma data para dia específico, ou selecione intervalo
              </p>
              {(tempCustomDate || (tempRangeStartDate && tempRangeEndDate)) && (
                <div className="mt-2 p-2 bg-blue-50 rounded border border-blue-200">
                  <p className="text-xs font-medium text-blue-800">
                    {tempRangeStartDate && tempRangeEndDate ? (
                      <>📊 {format(tempRangeStartDate, "dd/MM/yyyy", { locale: ptBR })} até {format(tempRangeEndDate, "dd/MM/yyyy", { locale: ptBR })}</>
                    ) : tempCustomDate ? (
                      <>📅 {format(tempCustomDate, "dd/MM/yyyy", { locale: ptBR })}</>
                    ) : null}
                  </p>
                  <p className="text-xs text-blue-600 mt-1">Clique em "Aplicar" para confirmar</p>
                </div>
              )}
            </div>
            <Calendar
              mode="range"
              selected={{
                from: tempRangeStartDate || tempCustomDate,
                to: tempRangeEndDate
              }}
              onSelect={(dates) => {
                if (dates?.from && dates?.to) {
                  // Range selecionado (temporário)
                  setTempRangeStartDate(dates.from);
                  setTempRangeEndDate(dates.to);
                  setTempCustomDate(undefined);
                } else if (dates?.from && !dates?.to) {
                  // Data única selecionada (temporário)
                  setTempCustomDate(dates.from);
                  setTempRangeStartDate(undefined);
                  setTempRangeEndDate(undefined);
                }
              }}
              disabled={(date) =>
                date > new Date() || date < new Date("1900-01-01")
              }
              locale={ptBR}
              initialFocus
              numberOfMonths={2}
            />
            <div className="p-3 border-t">
              <div className="flex gap-2 mb-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    if (serverDate) {
                      const today = new Date(serverDate + 'T12:00:00');
                      setTempCustomDate(today);
                      setTempRangeStartDate(undefined);
                      setTempRangeEndDate(undefined);
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
                      const yesterday = new Date(serverYesterday + 'T12:00:00');
                      setTempCustomDate(yesterday);
                      setTempRangeStartDate(undefined);
                      setTempRangeEndDate(undefined);
                    }
                  }}
                  disabled={!serverYesterday}
                >
                  Ontem
                </Button>
              </div>
              <Button 
                size="sm" 
                className="w-full"
                onClick={handleApplyChanges}
                disabled={!tempCustomDate && !tempRangeStartDate}
              >
                Aplicar
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      )}

    </div>
  );
}