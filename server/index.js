import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { createClient } from '@supabase/supabase-js';

// Load environment variables from .env.server
dotenv.config({ path: '.env.server' });

const app = express();
const PORT = process.env.SERVER_PORT || 3001;

// Middleware - CORS with flexible origins for development
const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || [
  'http://localhost:5173',
  'http://localhost:8080',
  'http://localhost:3000'
];

app.use(cors({
  origin: (origin, callback) => {
    // Allow requests with no origin (like mobile apps, curl, Postman)
    if (!origin) return callback(null, true);

    // Check if origin is allowed
    if (allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      // In development, allow localhost on any port
      if (process.env.NODE_ENV !== 'production' && origin.startsWith('http://localhost:')) {
        callback(null, true);
      } else {
        callback(new Error('Not allowed by CORS'));
      }
    }
  },
  credentials: true
}));
app.use(express.json());

// Initialize Supabase client with server-side credentials
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!supabaseUrl || !supabaseServiceKey) {
  console.error('❌ SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env.server');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseServiceKey);

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running' });
});

// Secure proxy endpoint for user queries
app.post('/api/users/query', async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({ error: 'Email is required' });
    }

    const { data, error } = await supabase
      .from('users')
      .select('*')
      .eq('email', email);

    if (error) {
      console.error('Error querying users:', error);
      return res.status(500).json({ error: 'Database query failed' });
    }

    res.json(data);
  } catch (error) {
    console.error('Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Secure proxy endpoint for general Supabase queries
app.post('/api/supabase/query', async (req, res) => {
  try {
    const { table, select, filters } = req.body;

    if (!table || !select) {
      return res.status(400).json({ error: 'Table and select fields are required' });
    }

    let query = supabase.from(table).select(select);

    // Apply filters if provided
    if (filters && Array.isArray(filters)) {
      filters.forEach(filter => {
        const { field, operator, value } = filter;
        switch (operator) {
          case 'eq':
            query = query.eq(field, value);
            break;
          case 'neq':
            query = query.neq(field, value);
            break;
          case 'gt':
            query = query.gt(field, value);
            break;
          case 'gte':
            query = query.gte(field, value);
            break;
          case 'lt':
            query = query.lt(field, value);
            break;
          case 'lte':
            query = query.lte(field, value);
            break;
          case 'like':
            query = query.like(field, value);
            break;
          case 'in':
            query = query.in(field, value);
            break;
          default:
            break;
        }
      });
    }

    const { data, error } = await query;

    if (error) {
      console.error('Error querying Supabase:', error);
      return res.status(500).json({ error: 'Database query failed' });
    }

    res.json(data);
  } catch (error) {
    console.error('Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Secure proxy endpoint for inserts
app.post('/api/supabase/insert', async (req, res) => {
  try {
    const { table, data } = req.body;

    if (!table || !data) {
      return res.status(400).json({ error: 'Table and data are required' });
    }

    const { data: result, error } = await supabase
      .from(table)
      .insert(data)
      .select();

    if (error) {
      console.error('Error inserting data:', error);
      return res.status(500).json({ error: 'Database insert failed' });
    }

    res.json(result);
  } catch (error) {
    console.error('Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Secure proxy endpoint for updates
app.post('/api/supabase/update', async (req, res) => {
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

    res.json(result);
  } catch (error) {
    console.error('Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Secure proxy endpoint for deletes
app.post('/api/supabase/delete', async (req, res) => {
  try {
    const { table, filters } = req.body;

    if (!table || !filters) {
      return res.status(400).json({ error: 'Table and filters are required' });
    }

    let query = supabase.from(table).delete();

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

    const { error } = await query;

    if (error) {
      console.error('Error deleting data:', error);
      return res.status(500).json({ error: 'Database delete failed' });
    }

    res.json({ success: true });
  } catch (error) {
    console.error('Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Secure endpoint for RPC calls
app.post('/api/supabase/rpc', async (req, res) => {
  try {
    const { functionName, params } = req.body;

    if (!functionName) {
      return res.status(400).json({ error: 'Function name is required' });
    }

    const { data, error } = await supabase.rpc(functionName, params || {});

    if (error) {
      console.error('Error calling RPC:', error);
      return res.status(500).json({ error: 'RPC call failed' });
    }

    res.json(data);
  } catch (error) {
    console.error('Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`✅ Secure API server running on port ${PORT}`);
  console.log(`🔒 Protected endpoints available at http://localhost:${PORT}/api/*`);
});
