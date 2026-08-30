-- Migration: Drop redundant costs_summary_by_category
-- Safe to run multiple times; handles table, view, or materialized view
BEGIN;

DO $$
BEGIN
  -- Drop as TABLE if it exists
  IF EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name = 'costs_summary_by_category'
  ) THEN
    EXECUTE 'DROP TABLE public.costs_summary_by_category CASCADE';
    RAISE NOTICE 'Dropped TABLE public.costs_summary_by_category';
  -- Drop as VIEW if it exists
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.views 
    WHERE table_schema = 'public' AND table_name = 'costs_summary_by_category'
  ) THEN
    EXECUTE 'DROP VIEW public.costs_summary_by_category CASCADE';
    RAISE NOTICE 'Dropped VIEW public.costs_summary_by_category';
  -- Drop as MATERIALIZED VIEW if it exists
  ELSIF EXISTS (
    SELECT 1 FROM pg_matviews 
    WHERE schemaname = 'public' AND matviewname = 'costs_summary_by_category'
  ) THEN
    EXECUTE 'DROP MATERIALIZED VIEW public.costs_summary_by_category CASCADE';
    RAISE NOTICE 'Dropped MATERIALIZED VIEW public.costs_summary_by_category';
  ELSE
    RAISE NOTICE 'No object named costs_summary_by_category found in public schema';
  END IF;
END$$;

COMMIT;

