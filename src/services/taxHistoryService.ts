import { supabase } from '@/lib/supabase';

export interface TaxHistory {
  id?: number;
  month: string; // YYYY-MM-DD format (stored as date)
  percentage: number;
  effective_date: string; // ISO date string
  created_at?: string;
  updated_at?: string;
}

export interface TaxHistoryDisplay {
  month: string; // Display format like "Set/25"
  percentage: number;
}

class TaxHistoryService {
  // Convert YYYY-MM format to YYYY-MM-01 for database storage
  private formatMonthForDB(month: string): string {
    return month.length === 7 ? `${month}-01` : month;
  }

  // Convert YYYY-MM-DD back to YYYY-MM for display logic
  private formatMonthFromDB(monthDate: string): string {
    return monthDate.substring(0, 7);
  }

  // Get current tax rate for a specific month
  async getCurrentTaxRate(month: string): Promise<number> {
    try {
      const monthDate = this.formatMonthForDB(month);
      
      const { data, error } = await supabase
        .from('tax_history')
        .select('percentage')
        .eq('month', monthDate)
        .order('effective_date', { ascending: false })
        .limit(1)
        .single();

      if (error) {
        // If no data found, return default rate
        if (error.code === 'PGRST116') {
          return 8.1; // Default tax rate
        }
        throw error;
      }

      return data?.percentage || 8.1;
    } catch (error) {
      console.error('Error getting current tax rate:', error);
      return 8.1; // Default fallback
    }
  }

  // Update tax rate for current month
  async updateTaxRate(month: string, percentage: number): Promise<TaxHistory> {
    try {
      const effectiveDate = new Date().toISOString();
      const monthDate = this.formatMonthForDB(month);
      
      // Check if there's already a record for this month
      const { data: existingData, error: checkError } = await supabase
        .from('tax_history')
        .select('id')
        .eq('month', monthDate)
        .limit(1);

      if (checkError) throw checkError;

      let result;
      
      if (existingData && existingData.length > 0) {
        // Update existing record
        const { data, error } = await supabase
          .from('tax_history')
          .update({
            percentage: percentage,
            effective_date: effectiveDate,
            updated_at: effectiveDate
          })
          .eq('month', monthDate)
          .select()
          .single();

        if (error) throw error;
        result = data;
      } else {
        // Create new record
        const { data, error } = await supabase
          .from('tax_history')
          .insert({
            month: monthDate,
            percentage: percentage,
            effective_date: effectiveDate,
            created_at: effectiveDate,
            updated_at: effectiveDate
          })
          .select()
          .single();

        if (error) throw error;
        result = data;
      }

      return result;
    } catch (error) {
      console.error('Error updating tax rate:', error);
      throw error;
    }
  }

  // Get tax history for display (last 3 months)
  async getTaxHistoryDisplay(currentMonth: string): Promise<TaxHistoryDisplay[]> {
    try {
      const { data, error } = await supabase
        .from('tax_history')
        .select('month, percentage')
        .order('month', { ascending: false })
        .limit(3);

      if (error) throw error;

      if (!data || data.length === 0) {
        // Return default history if no data
        return this.getDefaultTaxHistory();
      }

      return data.map(item => ({
        month: this.formatMonthForDisplay(this.formatMonthFromDB(item.month)),
        percentage: item.percentage
      }));
    } catch (error) {
      console.error('Error getting tax history:', error);
      return this.getDefaultTaxHistory();
    }
  }

  // Get all tax history records
  async getAllTaxHistory(): Promise<TaxHistory[]> {
    try {
      const { data, error } = await supabase
        .from('tax_history')
        .select('*')
        .order('month', { ascending: false });

      if (error) throw error;
      return data || [];
    } catch (error) {
      console.error('Error getting all tax history:', error);
      return [];
    }
  }

  // Format month for display (YYYY-MM -> Mon/YY)
  private formatMonthForDisplay(monthStr: string): string {
    const [year, month] = monthStr.split('-');
    const monthNames = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    const shortYear = year.slice(-2);
    return `${monthNames[parseInt(month) - 1]}/${shortYear}`;
  }

  // Default tax history for fallback (last 3 months)
  private getDefaultTaxHistory(): TaxHistoryDisplay[] {
    return [
      { month: 'Set/25', percentage: 8.3 },
      { month: 'Ago/25', percentage: 8.1 },
      { month: 'Jul/25', percentage: 7.9 }
    ];
  }

  // Get the most recent tax rate (for current calculations)
  async getLatestTaxRate(): Promise<number> {
    try {
      const { data, error } = await supabase
        .from('tax_history')
        .select('percentage')
        .order('effective_date', { ascending: false })
        .limit(1)
        .single();

      if (error) {
        if (error.code === 'PGRST116') {
          return 8.1; // Default tax rate
        }
        throw error;
      }

      return data?.percentage || 8.1;
    } catch (error) {
      console.error('Error getting latest tax rate:', error);
      return 8.1; // Default fallback
    }
  }

  // Check if today is the first day of a month and auto-create next month tax record
  async checkAndCreateNextMonthTax(): Promise<boolean> {
    try {
      const today = new Date();
      
      // Only run on the 1st day of the month
      if (today.getDate() !== 1) {
        return false;
      }

      const currentMonth = `${today.getFullYear()}-${(today.getMonth() + 1).toString().padStart(2, '0')}`;
      const currentMonthDate = this.formatMonthForDB(currentMonth);
      
      // Check if current month already has a tax record
      const { data: existingRecord, error: checkError } = await supabase
        .from('tax_history')
        .select('id')
        .eq('month', currentMonthDate)
        .limit(1);

      if (checkError) throw checkError;

      // If record already exists, no need to create
      if (existingRecord && existingRecord.length > 0) {
        return false;
      }

      // Get the most recent tax rate to inherit
      const latestRate = await this.getLatestTaxRate();
      
      // Create new record for current month with inherited rate
      const effectiveDate = new Date().toISOString();
      
      const { error: insertError } = await supabase
        .from('tax_history')
        .insert({
          month: currentMonthDate,
          percentage: latestRate,
          effective_date: effectiveDate,
          created_at: effectiveDate,
          updated_at: effectiveDate
        });

      if (insertError) throw insertError;

      return true; // Successfully created
    } catch (error) {
      console.error('Error checking/creating next month tax:', error);
      return false;
    }
  }
}

// Singleton instance
export const taxHistoryService = new TaxHistoryService();
