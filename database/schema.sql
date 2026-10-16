-- Biomedical Equipment Management System: SQLite schema (v1)
-- Dates are stored as TEXT in ISO format: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'.
-- Run PRAGMA foreign_keys = ON on EVERY new connection (SQLite does not remember it).

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------
-- Facilities and departments
-- ---------------------------------------------------------------
CREATE TABLE facilities (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    county      TEXT    NOT NULL,
    level       INTEGER NOT NULL CHECK (level BETWEEN 2 AND 6),  -- Kenya health system levels
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE departments (
    id          INTEGER PRIMARY KEY,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    UNIQUE (facility_id, name),
    UNIQUE (id, facility_id)   -- lets equipment prove its department is in the same facility
);

-- ---------------------------------------------------------------
-- Users and roles
-- ---------------------------------------------------------------
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    full_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN
                  ('system_admin','county_officer','facility_engineer','technician','reporter')),
    facility_id   INTEGER REFERENCES facilities(id),   -- facility-level roles
    county        TEXT,                                -- county officers see their whole county
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        role = 'system_admin'
        OR (role = 'county_officer' AND county IS NOT NULL)
        OR (role IN ('facility_engineer','technician','reporter') AND facility_id IS NOT NULL)
    )
);

-- ---------------------------------------------------------------
-- Equipment types (drive risk, PPM interval, and budgeting)
-- ---------------------------------------------------------------
CREATE TABLE equipment_types (
    id                    INTEGER PRIMARY KEY,
    name                  TEXT    NOT NULL UNIQUE,      -- e.g. 'Infusion pump'
    nomenclature_code     TEXT,                         -- GMDN / UMDNS code if available
    risk_score            INTEGER NOT NULL CHECK (risk_score BETWEEN 1 AND 5),
    ppm_interval_days     INTEGER NOT NULL CHECK (ppm_interval_days > 0),
    expected_life_years   INTEGER NOT NULL CHECK (expected_life_years > 0),
    est_replacement_cost  REAL    NOT NULL CHECK (est_replacement_cost >= 0)
);

-- ---------------------------------------------------------------
-- Equipment
-- ---------------------------------------------------------------
CREATE TABLE equipment (
    id              INTEGER PRIMARY KEY,
    asset_tag       TEXT    NOT NULL UNIQUE,
    facility_id     INTEGER NOT NULL REFERENCES facilities(id),
    department_id   INTEGER NOT NULL,
    type_id         INTEGER NOT NULL REFERENCES equipment_types(id),
    make            TEXT,
    model           TEXT,
    serial_number   TEXT,
    supplier        TEXT,
    purchase_date   TEXT,
    purchase_cost   REAL CHECK (purchase_cost IS NULL OR purchase_cost >= 0),
    warranty_expiry TEXT,
    status          TEXT    NOT NULL DEFAULT 'functional' CHECK (status IN
                    ('functional','partially_functional','non_functional','decommissioned')),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (make, model, serial_number),
    -- department must belong to the SAME facility as the equipment
    FOREIGN KEY (department_id, facility_id) REFERENCES departments(id, facility_id)
);

-- ---------------------------------------------------------------
-- Preventive maintenance schedule (one per device)
-- ---------------------------------------------------------------
CREATE TABLE maintenance_schedules (
    id             INTEGER PRIMARY KEY,
    equipment_id   INTEGER NOT NULL UNIQUE REFERENCES equipment(id) ON DELETE CASCADE,
    interval_days  INTEGER NOT NULL CHECK (interval_days > 0),
    last_done_date TEXT,
    next_due_date  TEXT    NOT NULL
);

-- ---------------------------------------------------------------
-- Work orders (PPM and corrective): source of downtime and cost data
-- ---------------------------------------------------------------
CREATE TABLE work_orders (
    id               INTEGER PRIMARY KEY,
    equipment_id     INTEGER NOT NULL REFERENCES equipment(id),
    wo_type          TEXT    NOT NULL CHECK (wo_type IN ('ppm','corrective')),
    priority         TEXT    NOT NULL DEFAULT 'medium' CHECK (priority IN
                     ('low','medium','high','critical')),
    status           TEXT    NOT NULL DEFAULT 'open' CHECK (status IN
                     ('open','in_progress','completed','cancelled')),
    description      TEXT    NOT NULL,
    reported_by      INTEGER NOT NULL REFERENCES users(id),
    assigned_to      INTEGER REFERENCES users(id),
    opened_at        TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at       TEXT,
    closed_at        TEXT,
    downtime_hours   REAL    NOT NULL DEFAULT 0 CHECK (downtime_hours >= 0),
    cost             REAL    NOT NULL DEFAULT 0 CHECK (cost >= 0),
    resolution_notes TEXT,
    CHECK (closed_at IS NULL OR closed_at >= opened_at)
);

-- ---------------------------------------------------------------
-- Audit trail
-- ---------------------------------------------------------------
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    action      TEXT NOT NULL,          -- 'create', 'update', 'delete', 'login'...
    table_name  TEXT NOT NULL,
    record_id   INTEGER,
    details     TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------
-- Indexes for the queries the app will run most
-- ---------------------------------------------------------------
CREATE INDEX idx_equipment_facility     ON equipment(facility_id);
CREATE INDEX idx_equipment_status       ON equipment(status);
CREATE INDEX idx_equipment_type         ON equipment(type_id);
CREATE INDEX idx_schedules_next_due     ON maintenance_schedules(next_due_date);
CREATE INDEX idx_workorders_equipment   ON work_orders(equipment_id);
CREATE INDEX idx_workorders_status      ON work_orders(status);
CREATE INDEX idx_workorders_opened      ON work_orders(opened_at);
CREATE INDEX idx_users_facility         ON users(facility_id);
CREATE INDEX idx_audit_table_record     ON audit_log(table_name, record_id);
