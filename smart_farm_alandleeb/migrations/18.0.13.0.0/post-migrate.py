# -*- coding: utf-8 -*-
"""
Post-migration for Smart Farm 18.0.13.0.0

Populates parent_path for all existing farm.cost.line records so that
Odoo's _parent_store hierarchy works immediately after upgrade.

parent_path format:
  - Top-level record (id=42):         "42/"
  - Child of record 42 (id=55):       "42/55/"
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("smart_farm 18.0.13.0.0 post-migrate: populating parent_path")

    # Top-level lines (no boq_parent_id)
    cr.execute("""
        UPDATE farm_cost_line
        SET    parent_path = CAST(id AS VARCHAR) || '/'
        WHERE  boq_parent_id IS NULL
          AND  (parent_path IS NULL OR parent_path = '')
    """)
    _logger.info("  Set parent_path for %d top-level lines", cr.rowcount)

    # Child lines (boq_parent_id set) — one level deep only
    cr.execute("""
        UPDATE farm_cost_line child
        SET    parent_path = CAST(child.boq_parent_id AS VARCHAR)
                             || '/' || CAST(child.id AS VARCHAR) || '/'
        WHERE  child.boq_parent_id IS NOT NULL
          AND  (child.parent_path IS NULL OR child.parent_path = '')
    """)
    _logger.info("  Set parent_path for %d child lines", cr.rowcount)

    _logger.info("smart_farm 18.0.13.0.0 post-migrate: done")
