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
    return data || [];
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
    return data || [];
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
}

export const operationalCostsService = new OperationalCostsService();