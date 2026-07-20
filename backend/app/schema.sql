PRAGMA foreign_keys = ON;

-- ============================================
-- USERS
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_soyad      TEXT NOT NULL,
    departman     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================
-- ROOMS
-- ============================================
CREATE TABLE IF NOT EXISTS rooms (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ad        TEXT NOT NULL,
    konum     TEXT NOT NULL,
    kapasite  INTEGER NOT NULL CHECK (kapasite > 0),
    ekipman   TEXT,                          -- JSON string: '["projektor","tv","beyaz tahta"]'
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ============================================
-- RESERVATIONS
-- ============================================
CREATE TABLE IF NOT EXISTS reservations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id          INTEGER NOT NULL REFERENCES rooms(id),
    user_id          INTEGER NOT NULL REFERENCES users(id),
    baslik           TEXT NOT NULL,
    katilimci_sayisi INTEGER NOT NULL CHECK (katilimci_sayisi >= 1),
    start_time       TEXT NOT NULL,           -- ISO 8601, UTC ('2026-07-20T13:00:00Z')
    end_time         TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (end_time > start_time)
);

-- ============================================
-- INDEX — çakışma kontrolü sorgusunu hızlandırır
-- ============================================
CREATE INDEX IF NOT EXISTS idx_reservations_room_time
    ON reservations(room_id, start_time, end_time);