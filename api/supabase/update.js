import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Credentials', true);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,PATCH,DELETE,POST,PUT');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version'
  );

  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { table, data, filters } = req.body;

    if (!table || !data || !filters) {
      return res.status(400).json({ error: 'Table, data, and filters are required' });
    }

    let query = supabase.from(table).update(data);

    // Apply filters
    if (Array.isArray(filters)) {
      filters.forEach(filter => {
        const { field, operator, value } = filter;
        switch (operator) {
          case 'eq':
            query = query.eq(field, value);
            break;
          default:
            break;
        }
      });
    }

    const { data: result, error } = await query.select();

    if (error) {
      console.error('Error updating data:', error);
      return res.status(500).json({ error: 'Database update failed' });
    }

    res.status(200).json(result);
  } catch (error) {
    console.error('Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
}
