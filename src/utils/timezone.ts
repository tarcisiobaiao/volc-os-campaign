/**
 * Utility functions for handling timezone operations
 * Ensures all timestamps are correctly saved in São Paulo timezone
 */

/**
 * Get current timestamp in São Paulo timezone
 * @returns ISO string with São Paulo timezone
 */
export function getSaoPauloTimestamp(): string {
  const now = new Date();
  
  // Convert to São Paulo timezone
  const saoPauloTime = new Date(now.toLocaleString("en-US", {
    timeZone: "America/Sao_Paulo"
  }));
  
  return saoPauloTime.toISOString();
}

/**
 * Convert any timestamp to São Paulo timezone
 * @param timestamp - ISO string or Date
 * @returns ISO string with São Paulo timezone
 */
export function convertToSaoPauloTimestamp(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  
  // Convert to São Paulo timezone
  const saoPauloTime = new Date(date.toLocaleString("en-US", {
    timeZone: "America/Sao_Paulo"
  }));
  
  return saoPauloTime.toISOString();
}

/**
 * Format timestamp for display in Brazilian format
 * @param timestamp - ISO string or Date (already in São Paulo timezone from Supabase)
 * @returns Formatted string in dd/mm/yyyy, hh:mm:ss format
 */
export function formatSaoPauloTimestamp(timestamp: string | Date): string {
  if (!timestamp) return 'Indisponível';
  
  try {
    let date: Date;
    
    if (typeof timestamp === 'string') {
      // Handle different string formats that might come from the database
      if (timestamp.includes('/') && timestamp.includes(',')) {
        // Format: "10/09/2025, 10:29:04" (already in Brazilian format)
        // Parse it correctly as Brazilian date
        const [datePart, timePart] = timestamp.split(', ');
        const [day, month, year] = datePart.split('/');
        const fullDateString = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${timePart}`;
        date = new Date(fullDateString);
      } else {
        // ISO string or other format
        date = new Date(timestamp);
      }
    } else {
      date = timestamp;
    }
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
      console.warn('Invalid timestamp format:', timestamp);
      return 'Formato inválido';
    }
    
    // Format in Brazilian locale
    return date.toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: 'America/Sao_Paulo' // Ensure consistent timezone
    });
  } catch (error) {
    console.error('Error formatting timestamp:', error, 'Original timestamp:', timestamp);
    return 'Erro na formatação';
  }
}

/**
 * Get São Paulo timezone offset in hours
 * @returns Offset in hours (e.g., -3 for BRT, -2 for BRST)
 */
export function getSaoPauloOffset(): number {
  const now = new Date();
  const utc = new Date(now.getTime() + now.getTimezoneOffset() * 60000);
  const saoPaulo = new Date(utc.toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  
  return Math.round((saoPaulo.getTime() - utc.getTime()) / (1000 * 60 * 60));
}