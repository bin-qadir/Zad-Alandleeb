# -*- coding: utf-8 -*-
"""
Post-migration for Smart Farm 18.0.11.0.0

Verifies that all new columns exist after ORM upgrade and provides
emergency fallback column creation if anything was missed.
"""
import logging

_logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    ('farm_cost_line', 'is_boq_item'),
    ('farm_cost_line', 'boq_parent_id'),
    ('farm_boq_item', 'count_in_cost_total'),
]


def migrate(cr, version):
    _logger.info("smart_farm 18.0.11.0.0 post-migrate: verifying BOQ hierarchy columns")

    for table, column in REQUIRED_COLUMNS:
        cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, column))
        if cr.fetchone():
            _logger.info("  OK: %s.%s exists", table, column)
        else:
            _logger.warning(
                "  MISSING: %s.%s — applying emergency fallback", table, column
            )
            # Emergency fallback — determine correct type
            if column == 'boq_parent_id':
                cr.execute(f"""
                    ALTER TABLE {table}
                    ADD COLUMN IF NOT EXISTS {column} INTEGER
                        REFERENCES farm_cost_line(id)
                        ON DELETE CASCADE
                """)
            else:
                cr.execute(f"""
                    ALTER TABLE {table}
                    ADD COLUMN IF NOT EXISTS {column} BOOLEAN NOT NULL DEFAULT TRUE
                """)
            _logger.info("  Emergency column added: %s.%s", table, column)

    _logger.info("smart_farm 18.0.11.0.0 post-migrate: done")
