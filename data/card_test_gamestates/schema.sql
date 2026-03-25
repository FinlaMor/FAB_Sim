-- FAB Sim card test gamestates database schema
-- Stores pre- and post-play game states for each card, used for
-- regression testing and validation of card effect behaviour.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;


-- ---------------------------------------------------------------------------
-- card_test_gamestates
-- One row per card. Captures the original (pre-play) and post-play game
-- states so that card effects can be validated deterministically.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_test_gamestates (
    card_slug           TEXT    PRIMARY KEY,
    card_name           TEXT    NOT NULL,
    card_types          TEXT    NOT NULL DEFAULT '[]',
    card_category       TEXT    NOT NULL DEFAULT '',
    original_gamestate  TEXT    NOT NULL DEFAULT '{}',
    post_gamestate      TEXT    NOT NULL DEFAULT '{}',
    status              TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'generated', 'validated', 'failed')),
    error_message       TEXT,
    validation_result   TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_card_test_gamestates_status
    ON card_test_gamestates(status);

CREATE INDEX IF NOT EXISTS idx_card_test_gamestates_category
    ON card_test_gamestates(card_category);
