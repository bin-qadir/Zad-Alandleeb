# -*- coding: utf-8 -*-
"""
Pre-migration for Smart Farm 18.0.13.0.0

Adds the parent_path column required by _parent_store on farm.cost.line.
Odoo will populate it automatically during the module upgrade, but we
add the column here to avoid errors if the ORM tries to read it early.

All operations are fully idempotent.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("smart_farm 18.0.13.0.0 pre-migrate: adding parent_path column")

    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'farm_cost_line'
          AND column_name = 'parent_path'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE farm_cost_line
            ADD COLUMN parent_path VARCHAR
        """)
        cr.execute("""
            CREATE INDEX IF NOT EXISTS farm_cost_line_parent_path_idx
            ON farm_cost_line (parent_path)
        """)
        _logger.info("  Added farm_cost_line.parent_path + index")
    else:
        _logger.info("  farm_cost_line.parent_path already exists, skipping")

    _logger.info("smart_farm 18.0.13.0.0 pre-migrate: done")
