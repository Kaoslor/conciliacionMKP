-- =====================================================================
-- 001_multimarketplace.sql
-- Migra conciliacion_falabella a un modelo multi-marketplace.
-- Ejecutar UNA vez con un usuario administrador (no con n8n_writer ni
-- metabase_reader), por ejemplo desde DBeaver/pgAdmin sobre la base
-- `conciliacion`. Todo corre en una transacción: si algo falla, no
-- queda nada a medias.
-- =====================================================================
BEGIN;

-- 1) Catálogo de marketplaces ------------------------------------------
--    activo = true  -> ya tiene flujo n8n funcionando
--    activo = false -> aparece en el dashboard como "Próximamente"
CREATE TABLE IF NOT EXISTS marketplace (
    codigo      TEXT PRIMARY KEY,                 -- FALABELLA, PARIS, ...
    nombre      TEXT NOT NULL,                    -- nombre visible
    color       TEXT NOT NULL DEFAULT '#0A2540',  -- color en el dashboard
    activo      BOOLEAN NOT NULL DEFAULT false,
    orden       SMALLINT NOT NULL DEFAULT 100,    -- orden de despliegue
    tolerancia  NUMERIC NOT NULL DEFAULT 2,       -- CLP de redondeo aceptado (referencial)
    creado_en   TIMESTAMP NOT NULL DEFAULT now()
);

INSERT INTO marketplace (codigo, nombre, color, activo, orden) VALUES
    ('FALABELLA',    'Falabella',       '#4C9A2A', true,  10),
    ('PARIS',        'Paris',           '#2563EB', false, 20),
    ('RIPLEY',       'Ripley',          '#7C3AED', false, 30),
    ('MERCADOLIBRE', 'Mercado Libre',   '#D4A106', false, 40),
    ('WALMART',      'Walmart / Lider', '#0EA5E9', false, 50)
ON CONFLICT (codigo) DO NOTHING;

-- 2) Tabla de conciliación genérica ------------------------------------
CREATE TABLE IF NOT EXISTS conciliacion_marketplace (
    id                   BIGSERIAL PRIMARY KEY,
    marketplace          TEXT NOT NULL REFERENCES marketplace(codigo),
    modalidad_logistica  TEXT,                    -- FBS, FBF, Flex, ...
    fecha_transaccion    DATE,
    n_orden              TEXT NOT NULL,
    documento_sap        TEXT,
    tipo_transaccion     TEXT,
    monto_marketplace    NUMERIC,                 -- antes: monto_falabella (con IVA)
    monto_sap            NUMERIC,                 -- con IVA
    diferencia           NUMERIC,                 -- SAP - marketplace
    estado               TEXT,                    -- OK / REVISAR_DIFERENCIA / SIN_DOC_SAP / ...
    ref_pago             TEXT NOT NULL DEFAULT '',-- antes: ref_pago_fpay
    id_liquidacion       TEXT,                    -- settlement / liquidación del marketplace
    fecha_ejecucion      TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_conciliacion_mkp UNIQUE (marketplace, n_orden, ref_pago)
);

CREATE INDEX IF NOT EXISTS ix_conc_mkp_fecha  ON conciliacion_marketplace (marketplace, fecha_transaccion);
CREATE INDEX IF NOT EXISTS ix_conc_mkp_estado ON conciliacion_marketplace (estado);

-- 3) fecha_ejecucion se actualiza también en los UPDATE del upsert ------
--    (el DEFAULT solo aplica al INSERT; sin esto el dashboard mostraría
--    una "última sincronización" desactualizada)
CREATE OR REPLACE FUNCTION fn_touch_fecha_ejecucion() RETURNS trigger AS $$
BEGIN
    NEW.fecha_ejecucion := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conc_mkp_touch ON conciliacion_marketplace;
CREATE TRIGGER trg_conc_mkp_touch
    BEFORE UPDATE ON conciliacion_marketplace
    FOR EACH ROW EXECUTE FUNCTION fn_touch_fecha_ejecucion();

-- 4) Migrar los datos de Falabella y respaldar la tabla antigua ---------
DO $$
BEGIN
    IF to_regclass('public.conciliacion_falabella') IS NOT NULL THEN
        INSERT INTO conciliacion_marketplace
            (marketplace, modalidad_logistica, fecha_transaccion, n_orden,
             documento_sap, tipo_transaccion, monto_marketplace, monto_sap,
             diferencia, estado, ref_pago, fecha_ejecucion)
        SELECT 'FALABELLA', 'FBS', fecha_transaccion, n_orden,
               documento_sap, tipo_transaccion, monto_falabella, monto_sap,
               diferencia, estado, COALESCE(ref_pago_fpay, ''), fecha_ejecucion
        FROM conciliacion_falabella
        ON CONFLICT (marketplace, n_orden, ref_pago) DO NOTHING;

        ALTER TABLE conciliacion_falabella RENAME TO conciliacion_falabella_bkp;
    END IF;
END $$;

-- 5) Permisos -----------------------------------------------------------
GRANT SELECT                 ON marketplace, conciliacion_marketplace TO metabase_reader;
GRANT SELECT, INSERT, UPDATE ON conciliacion_marketplace              TO n8n_writer;
GRANT SELECT                 ON marketplace                           TO n8n_writer;
GRANT USAGE, SELECT          ON SEQUENCE conciliacion_marketplace_id_seq TO n8n_writer;

COMMIT;

-- Verificación (debería dar 37 filas de FALABELLA: 35 OK + 2 REVISAR):
-- SELECT marketplace, estado, COUNT(*) FROM conciliacion_marketplace GROUP BY 1, 2 ORDER BY 1, 2;
--
-- Cuando confirmes que todo funciona, puedes borrar el respaldo:
-- DROP TABLE conciliacion_falabella_bkp;
--
-- Para activar un retail nuevo cuando su flujo n8n esté listo:
-- UPDATE marketplace SET activo = true WHERE codigo = 'PARIS';
