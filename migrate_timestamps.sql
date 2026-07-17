-- =====================================================
-- MIGRACION: Convertir columnas a timestamp without time zone
-- Ejecutar en Supabase SQL Editor
--
-- Contexto: El dispositivo envia hora Ecuador local (sin Z).
-- _parse_timestamp() guarda naive Ecuador time.
-- PostgreSQL asume UTC al insertar naive en timezone column,
-- pero el VALOR numerico ya es hora Ecuador.
-- Solo necesitamos QUITAR el timezone label, NO convertir.
-- =====================================================

-- Location
ALTER TABLE location
  ALTER COLUMN timestamp TYPE timestamp without time zone;

-- Event
ALTER TABLE event
  ALTER COLUMN timestamp TYPE timestamp without time zone;

-- Maintenance
ALTER TABLE maintenance
  ALTER COLUMN date TYPE timestamp without time zone;

-- AnalyticsRun
ALTER TABLE analytics_run
  ALTER COLUMN date_from TYPE timestamp without time zone,
  ALTER COLUMN date_to TYPE timestamp without time zone,
  ALTER COLUMN generated_at TYPE timestamp without time zone;

-- VehicleStatisticsSummary
ALTER TABLE vehicle_statistics_summary
  ALTER COLUMN date_from TYPE timestamp without time zone,
  ALTER COLUMN date_to TYPE timestamp without time zone,
  ALTER COLUMN created_at TYPE timestamp without time zone;

-- SystemSetting
ALTER TABLE system_setting
  ALTER COLUMN updated_at TYPE timestamp without time zone;

-- Verificar resultado
SELECT 'location' as tabla, COUNT(*) as registros, MIN(timestamp) as earliest, MAX(timestamp) as latest FROM location;
SELECT 'event' as tabla, COUNT(*) as registros, MIN(timestamp) as earliest, MAX(timestamp) as latest FROM event;
SELECT 'maintenance' as tabla, COUNT(*) as registros, MIN(date) as earliest, MAX(date) as latest FROM maintenance;
