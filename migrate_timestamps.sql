-- =====================================================
-- MIGRACION: Convertir timestamps de UTC a hora Ecuador
-- Ejecutar en Supabase SQL Editor
-- =====================================================

-- Location
UPDATE location
  SET timestamp = (timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp;
ALTER TABLE location
  ALTER COLUMN timestamp TYPE timestamp without time zone;

-- Event
UPDATE event
  SET timestamp = (timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp;
ALTER TABLE event
  ALTER COLUMN timestamp TYPE timestamp without time zone;

-- Maintenance
UPDATE maintenance
  SET date = (date AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp;
ALTER TABLE maintenance
  ALTER COLUMN date TYPE timestamp without time zone;

-- AnalyticsRun
UPDATE analytics_run
  SET date_from = (date_from AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp,
      date_to = (date_to AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp,
      generated_at = (generated_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp;
ALTER TABLE analytics_run
  ALTER COLUMN date_from TYPE timestamp without time zone,
  ALTER COLUMN date_to TYPE timestamp without time zone,
  ALTER COLUMN generated_at TYPE timestamp without time zone;

-- VehicleStatisticsSummary
UPDATE vehicle_statistics_summary
  SET date_from = (date_from AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp,
      date_to = (date_to AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp,
      created_at = (created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp;
ALTER TABLE vehicle_statistics_summary
  ALTER COLUMN date_from TYPE timestamp without time zone,
  ALTER COLUMN date_to TYPE timestamp without time zone,
  ALTER COLUMN created_at TYPE timestamp without time zone;

-- SystemSetting
UPDATE system_setting
  SET updated_at = (updated_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')::timestamp;
ALTER TABLE system_setting
  ALTER COLUMN updated_at TYPE timestamp without time zone;

-- Verificar resultado
SELECT 'location' as tabla, COUNT(*) as registros, MIN(timestamp) as earliest, MAX(timestamp) as latest FROM location;
SELECT 'event' as tabla, COUNT(*) as registros, MIN(timestamp) as earliest, MAX(timestamp) as latest FROM event;
SELECT 'maintenance' as tabla, COUNT(*) as registros, MIN(date) as earliest, MAX(date) as latest FROM maintenance;
