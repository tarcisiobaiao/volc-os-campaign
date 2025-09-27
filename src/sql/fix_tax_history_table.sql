-- Fix tax_history table structure and data format

-- First, check if the table exists and has the old VARCHAR format
-- If it does, we need to migrate it to use DATE format

-- Drop the table if it exists with old structure and recreate
DROP TABLE IF EXISTS tax_history;

-- Create tax_history table with correct DATE format
CREATE TABLE tax_history (
    id SERIAL PRIMARY KEY,
    month DATE NOT NULL, -- Format: YYYY-MM-01 (first day of month)
    percentage DECIMAL(5,2) NOT NULL, -- Tax percentage (e.g., 8.10)
    effective_date TIMESTAMP NOT NULL, -- When this rate became effective
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create index for efficient querying by month
CREATE INDEX idx_tax_history_month ON tax_history(month);

-- Create index for efficient querying by effective_date
CREATE INDEX idx_tax_history_effective_date ON tax_history(effective_date);

-- Insert sample data for testing (using proper DATE format)
INSERT INTO tax_history (month, percentage, effective_date, created_at, updated_at) VALUES
('2025-03-01', 7.1, '2025-03-01 00:00:00', '2025-03-01 00:00:00', '2025-03-01 00:00:00'),
('2025-04-01', 7.3, '2025-04-01 00:00:00', '2025-04-01 00:00:00', '2025-04-01 00:00:00'),
('2025-05-01', 7.5, '2025-05-01 00:00:00', '2025-05-01 00:00:00', '2025-05-01 00:00:00'),
('2025-06-01', 7.7, '2025-06-01 00:00:00', '2025-06-01 00:00:00', '2025-06-01 00:00:00'),
('2025-07-01', 7.9, '2025-07-01 00:00:00', '2025-07-01 00:00:00', '2025-07-01 00:00:00'),
('2025-08-01', 8.1, '2025-08-01 00:00:00', '2025-08-01 00:00:00', '2025-08-01 00:00:00'),
('2025-09-01', 8.3, '2025-09-01 00:00:00', '2025-09-01 00:00:00', '2025-09-01 00:00:00');





























