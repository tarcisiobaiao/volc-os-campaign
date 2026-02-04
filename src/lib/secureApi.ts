// Secure API client for making requests to our backend server
// This prevents exposing Supabase credentials in the frontend

// In production (Vercel), VITE_API_URL is '/api' or empty
// In development, it might be 'http://localhost:3001'
const API_BASE_URL = import.meta.env.VITE_API_URL === '/api' ? '' : (import.meta.env.VITE_API_URL || '');

interface QueryFilter {
  field: string;
  operator: 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'like' | 'in';
  value: any;
}

interface QueryOptions {
  table: string;
  select: string;
  filters?: QueryFilter[];
}

interface InsertOptions {
  table: string;
  data: any | any[];
}

interface UpdateOptions {
  table: string;
  data: any;
  filters: QueryFilter[];
}

interface DeleteOptions {
  table: string;
  filters: QueryFilter[];
}

interface RpcOptions {
  functionName: string;
  params?: Record<string, any>;
}

class SecureApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Request failed' }));
        throw new Error(error.error || `HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  }

  // Query data from a table
  async query<T = any>(options: QueryOptions): Promise<T[]> {
    return this.request<T[]>('/api/supabase/query', {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  // Insert data into a table
  async insert<T = any>(options: InsertOptions): Promise<T[]> {
    return this.request<T[]>('/api/supabase/insert', {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  // Update data in a table
  async update<T = any>(options: UpdateOptions): Promise<T[]> {
    return this.request<T[]>('/api/supabase/update', {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  // Delete data from a table
  async delete(options: DeleteOptions): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>('/api/supabase/delete', {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  // Call RPC function
  async rpc<T = any>(options: RpcOptions): Promise<T> {
    return this.request<T>('/api/supabase/rpc', {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  // Specific method for user queries (optimized endpoint)
  async queryUsers(email: string): Promise<any[]> {
    return this.request<any[]>('/api/users/query', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  // Health check
  async healthCheck(): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>('/api/health');
  }
}

// Export singleton instance
export const secureApi = new SecureApiClient();

// Export types for consumers
export type { QueryFilter, QueryOptions, InsertOptions, UpdateOptions, DeleteOptions, RpcOptions };
