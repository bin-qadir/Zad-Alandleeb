# -*- coding: utf-8 -*-
"""
Pre-migration for Smart Farm 18.0.11.0.0

Adds three new columns required for the BOQ parent-child cost line hierarchy:
  - farm_cost_line.is_boq_item       BOOLEAN DEFAULT FALSE
  - farm_cost_line.boq_parent_id     INTEGER (FK to farm_cost_line, cascade)
  - farm_boq_item.count_in_cost_total BOOLEAN DEFAULT TRUE

All operations are fully idempotent (safe to run multiple times).
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("smart_farm 18.0.11.0.0 pre-migrate: adding BOQ hierarchy columns")

    # ── farm_cost_line ────────────────────────────────────────────────────────

    # is_boq_item — marks the parent summary line for a BOQ item group
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'farm_cost_line'
          AND column_name = 'is_boq_item'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE farm_cost_line
            ADD COLUMN is_boq_item BOOLEAN NOT NULL DEFAULT FALSE
        """)
        _logger.info("  Added farm_cost_line.is_boq_item")
    else:
        _logger.info("  farm_cost_line.is_boq_item already exists, skipping")

    # boq_parent_id — links component lines to their parent is_boq_item header
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'farm_cost_line'
          AND column_name = 'boq_parent_id'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE farm_cost_line
            ADD COLUMN boq_parent_id INTEGER
                REFERENCES farm_cost_line(id)
                ON DELETE CASCADE
        """)
        cr.execute("""
            CREATE INDEX IF NOT EXISTS farm_cost_line_boq_parent_id_idx
            ON farm_cost_line (boq_parent_id)
        """)
        _logger.info("  Added farm_cost_line.boq_parent_id + index")
    else:
        _logger.info("  farm_cost_line.boq_parent_id already exists, skipping")

    # ── farm_boq_item ─────────────────────────────────────────────────────────

    # count_in_cost_total — when False, exclude this BOQ item from field totals
    # (used when a cost.line parent already carries the cost to avoid double-counting)
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'farm_boq_item'
          AND column_name = 'count_in_cost_total'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE farm_boq_item
            ADD COLUMN count_in_cost_total BOOLEAN NOT NULL DEFAULT TRUE
        """)
        _logger.info("  Added farm_boq_item.count_in_cost_total")
    else:
        _logger.info("  farm_boq_item.count_in_cost_total already exists, skipping")

    _logger.info("smart_farm 18.0.11.0.0 pre-migrate: done")
