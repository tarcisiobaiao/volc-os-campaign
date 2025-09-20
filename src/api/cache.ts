// API endpoint para invalidar cache quando n8n inserir dados
export async function POST(request: Request) {
  try {
    const { type, date } = await request.json();

    // Invalidar cache específico baseado no tipo e data
    if (type === 'daily_metrics' && date) {
      // Limpar todos os caches relacionados a essa data
      const cacheKeys = [
        `dashboard_today_${date}`,
        `dashboard_7d_${date}`,
        `dashboard_30d_${date}`,
        `reports_today_${date}`,
        `reports_7d_${date}`,
        `reports_30d_${date}`
      ];

      cacheKeys.forEach(key => {
        localStorage.removeItem(key);
      });

      console.log('🗑️ Cache invalidated for date:', date);
    }

    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Cache invalidation error:', error);
    return new Response(JSON.stringify({ error: 'Failed to invalidate cache' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}