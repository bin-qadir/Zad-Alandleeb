# -*- coding: utf-8 -*-
"""
Pre-migration for Smart Farm 18.0.12.0.0

Adds new columns for master-template quantity propagation:
  - farm_cost_line.main_quantity       FLOAT  (main item quantity on BOQ item headers)
  - farm_cost_line.base_ratio_qty      FLOAT  (component ratio per 1 unit of parent)
  - farm_cost_line.unit_name           VARCHAR (unit label)
  - farm_boq_item_template_line.base_ratio_qty  FLOAT
  - farm_boq_item_line.base_ratio_qty  FLOAT

All operations are fully idempotent (safe to run multiple times).
"""
import logging

_logger = logging.getLogger(__name__)


def _add_column_if_missing(cr, table, column, col_type, default=None):
    """Helper: add a column only if it does not already exist."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    if cr.fetchone():
        _logger.info("  %s.%s already exists, skipping", table, column)
        return
    default_clause = f" DEFAULT {default}" if default is not None else ""
    cr.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}')
    _logger.info("  Added %s.%s (%s)", table, column, col_type)


def migrate(cr, version):
    _logger.info("smart_farm 18.0.12.0.0 pre-migrate: adding quantity propagation columns")

    # ── farm_cost_line ────────────────────────────────────────────────────────
    _add_column_if_missing(cr, 'farm_cost_line', 'main_quantity',
                           'DOUBLE PRECISION', default='0.0')
    _add_column_if_missing(cr, 'farm_cost_line', 'base_ratio_qty',
                           'DOUBLE PRECISION', default='0.0')
    _add_column_if_missing(cr, 'farm_cost_line', 'unit_name', 'VARCHAR')

    # ── farm_boq_item_template_line ──────────────────────────────────────────
    _add_column_if_missing(cr, 'farm_boq_item_template_line', 'base_ratio_qty',
                           'DOUBLE PRECISION', default='1.0')

    # ── farm_boq_item_line ───────────────────────────────────────────────────
    _add_column_if_missing(cr, 'farm_boq_item_line', 'base_ratio_qty',
                           'DOUBLE PRECISION', default='1.0')

    _logger.info("smart_farm 18.0.12.0.0 pre-migrate: done")
