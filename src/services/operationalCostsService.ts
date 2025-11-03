import { supabase } from '@/lib/supabase';

export interface OperationalCostCategory {
  id: number;
  name: string;
  created_at?: string;
  updated_at?: string;
}

export interface OperationalCost {
  id: number;
  category_id: number;
  name: string;
  amount: number;
  month: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  category?: OperationalCostCategory;
}

export interface OperationalCostInput {
  category_id: number;
  name: string;
  amount: number;
  month: string;
  is_active: boolean;
}

class OperationalCostsService {
  async getCategories(): Promise<OperationalCostCategory[]> {
    const { data, error } = await supabase
      .from('operational_cost_categories')
      .select('*')
      .order('name');

    if (error) throw error;
    return data || [];
  }

  async createCategory(name: string): Promise<OperationalCostCategory> {
    const { data, error } = await supabase
      .from('operational_cost_categories')
      .insert({ name })
      .select()
      .single();

    if (error) throw error;
    return data;
  }

  async updateCategory(id: number, name: string): Promise<OperationalCostCategory> {
    const { data, error } = await supabase
      .from('operational_cost_categories')
      .update({ name, updated_at: new Date().toISOString() })
      .eq('id', id)
      .select()
      .single();

    if (error) throw error;
    return data;
  }

  async deleteCategory(id: number): Promise<void> {
    const { error } = await supabase
      .from('operational_cost_categories')
      .delete()
      .eq('id', id);

    if (error) throw error;
  }

  async getCostsByMonth(month: string): Promise<OperationalCost[]> {
    const monthFilter = month.length === 7 ? `${month}-01` : month;

    // Extract year and month for exact filtering
    const yearMonth = monthFilter.substring(0, 7); // YYYY-MM

    const { data, error } = await supabase
      .from('operational_costs')
      .select(`
        *,
        category:operational_cost_categories(*)
      `)
      .gte('month', monthFilter)
      .lt('month', this.getNextMonth(monthFilter))
      .order('name');

    if (error) throw error;

    // Filter to exact month to avoid duplicates
    const filteredData = (data || []).filter(cost => {
      const costYearMonth = cost.month.substring(0, 7);
      return costYearMonth === yearMonth;
    });

    return filteredData;
  }

  async getCostsByCategory(month: string): Promise<{ [categoryName: string]: OperationalCost[] }> {
    const costs = await this.getCostsByMonth(month);
    const categories = await this.getCategories();
    
    const grouped: { [categoryName: string]: OperationalCost[] } = {};
    
    categories.forEach(category => {
      grouped[category.name] = costs.filter(cost => cost.category_id === category.id);
    });
    
    return grouped;
  }

  // NEW: Get only ACTIVE costs for calculations
  async getActiveCostsByMonth(month: string): Promise<OperationalCost[]> {
    const monthFilter = month.length === 7 ? `${month}-01` : month;

    // Extract year and month for exact filtering
    const yearMonth = monthFilter.substring(0, 7); // YYYY-MM

    const { data, error } = await supabase
      .from('operational_costs')
      .select(`
        *,
        category:operational_cost_categories(*)
      `)
      .eq('is_active', true)
      .gte('month', monthFilter)
      .lt('month', this.getNextMonth(monthFilter))
      .order('name');

    if (error) throw error;

    // Filter to exact month to avoid duplicates
    const filteredData = (data || []).filter(cost => {
      const costYearMonth = cost.month.substring(0, 7);
      return costYearMonth === yearMonth;
    });

    return filteredData;
  }

  // NEW: Get only ACTIVE costs grouped by category for calculations
  async getActiveCostsByCategory(month: string): Promise<{ [categoryName: string]: OperationalCost[] }> {
    const costs = await this.getActiveCostsByMonth(month);
    const categories = await this.getCategories();
    
    const grouped: { [categoryName: string]: OperationalCost[] } = {};
    
    categories.forEach(category => {
      grouped[category.name] = costs.filter(cost => cost.category_id === category.id);
    });
    
    return grouped;
  }

  async createCost(costData: OperationalCostInput): Promise<OperationalCost> {
    const { data, error } = await supabase
      .from('operational_costs')
      .insert(costData)
      .select(`
        *,
        category:operational_cost_categories(*)
      `)
      .single();

    if (error) throw error;
    return data;
  }

  async updateCost(id: number, updates: Partial<OperationalCostInput>): Promise<OperationalCost> {
    const { data, error } = await supabase
      .from('operational_costs')
      .update({ ...updates, updated_at: new Date().toISOString() })
      .eq('id', id)
      .select(`
        *,
        category:operational_cost_categories(*)
      `)
      .single();

    if (error) throw error;
    return data;
  }

  async deleteCost(id: number): Promise<void> {
    const { error } = await supabase
      .from('operational_costs')
      .delete()
      .eq('id', id);

    if (error) throw error;
  }

  async checkAndCopyMonthData(month: string): Promise<boolean> {
    const monthFilter = month.length === 7 ? `${month}-01` : month;
    
    // Check if data already exists for this month
    const { data: existingData, error: checkError } = await supabase
      .from('operational_costs')
      .select('id')
      .gte('month', monthFilter)
      .lt('month', this.getNextMonth(monthFilter))
      .limit(1);

    if (checkError) throw checkError;
    if (existingData && existingData.length > 0) return false;

    // Get previous month data
    const previousMonth = this.getPreviousMonth(monthFilter);
    const { data: previousData, error: previousError } = await supabase
      .from('operational_costs')
      .select('*')
      .gte('month', previousMonth)
      .lt('month', monthFilter);

    if (previousError) throw previousError;
    if (!previousData || previousData.length === 0) return false;

    // Copy data to current month
    const newData = previousData.map(cost => ({
      category_id: cost.category_id,
      name: cost.name,
      amount: cost.amount,
      month: monthFilter,
      is_active: cost.is_active
    }));

    const { error: insertError } = await supabase
      .from('operational_costs')
      .insert(newData);

    if (insertError) throw insertError;
    return true;
  }

  private getNextMonth(date: string): string {
    const d = new Date(date);
    d.setMonth(d.getMonth() + 1);
    return d.toISOString().split('T')[0];
  }

  private getPreviousMonth(date: string): string {
    const d = new Date(date);
    d.setMonth(d.getMonth() - 1);
    return d.toISOString().split('T')[0];
  }

  // NEW: Calculate daily operational costs for current month
  async getDailyActiveCosts(month?: string): Promise<number> {
    const currentMonth = month || new Date().toISOString().slice(0, 7); // YYYY-MM format

    // Get all active costs for the month
    const activeCosts = await this.getActiveCostsByMonth(currentMonth);
    const totalActiveCosts = activeCosts.reduce((sum, cost) => sum + (cost.amount || 0), 0);

    // Calculate days in the month
    const [year, monthNum] = currentMonth.split('-').map(Number);
    const daysInMonth = new Date(year, monthNum, 0).getDate();

    // Return daily cost
    return totalActiveCosts / daysInMonth;
  }

  // NEW: Get operational costs for a date range (multiple months)
  async getCostsForDateRange(startDate: string, endDate: string): Promise<{
    totalCosts: number;
    dailyAverage: number;
    numberOfDays: number;
    monthlyBreakdown: Array<{ month: string; costs: number; days: number }>;
  }> {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const numberOfDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;

    // Get all unique months in the range
    const months = new Set<string>();
    const currentDate = new Date(start);

    while (currentDate <= end) {
      const monthStr = currentDate.toISOString().slice(0, 7);
      months.add(monthStr);
      currentDate.setDate(currentDate.getDate() + 1);
    }

    // Calculate costs for each month
    const monthlyBreakdown: Array<{ month: string; costs: number; days: number }> = [];
    let totalCosts = 0;

    for (const month of Array.from(months)) {
      const activeCosts = await this.getActiveCostsByMonth(month);
      const monthlyCosts = activeCosts.reduce((sum, cost) => sum + (cost.amount || 0), 0);

      // Calculate days in this month that fall within the date range
      const [year, monthNum] = month.split('-').map(Number);
      const monthStart = new Date(year, monthNum - 1, 1);
      const monthEnd = new Date(year, monthNum, 0);

      const rangeStart = start > monthStart ? start : monthStart;
      const rangeEnd = end < monthEnd ? end : monthEnd;

      const daysInRange = Math.ceil((rangeEnd.getTime() - rangeStart.getTime()) / (1000 * 60 * 60 * 24)) + 1;
      const daysInMonth = new Date(year, monthNum, 0).getDate();

      // Proportional costs for days in range
      const dailyCost = monthlyCosts / daysInMonth;
      const proportionalCosts = dailyCost * daysInRange;

      totalCosts += proportionalCosts;
      monthlyBreakdown.push({ month, costs: proportionalCosts, days: daysInRange });
    }

    return {
      totalCosts,
      dailyAverage: totalCosts / numberOfDays,
      numberOfDays,
      monthlyBreakdown
    };
  }

  // NEW: Auto-clone costs from previous month if current month has no data
  async autoClonePreviousMonthCosts(): Promise<{
    success: boolean;
    cloned: boolean;
    message: string;
    currentMonth: string;
  }> {
    try {
      // Get current month in server time (São Paulo)
      const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo'
      }).format(new Date());

      const currentMonth = saoPauloDate.substring(0, 7); // YYYY-MM
      const currentMonthFilter = `${currentMonth}-01`;

      // Check if current month already has data
      const hasData = await this.checkAndCopyMonthData(currentMonthFilter);

      if (hasData) {
        return {
          success: true,
          cloned: true,
          message: `Custos do mês anterior clonados com sucesso para ${currentMonth}`,
          currentMonth
        };
      } else {
        return {
          success: true,
          cloned: false,
          message: `Mês ${currentMonth} já possui custos cadastrados`,
          currentMonth
        };
      }
    } catch (error) {
      console.error('Error in autoClonePreviousMonthCosts:', error);
      return {
        success: false,
        cloned: false,
        message: `Erro ao clonar custos: ${error.message}`,
        currentMonth: ''
      };
    }
  }
}

export const operationalCostsService = new OperationalCostsService();