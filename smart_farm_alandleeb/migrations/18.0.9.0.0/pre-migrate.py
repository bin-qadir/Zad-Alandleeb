# -*- coding: utf-8 -*-
"""
Pre-migration 18.0.9.0.0 — create missing tables and add missing columns.

This script runs BEFORE Odoo's ORM applies schema updates. It ensures every
table / column introduced since version 18.0.8.0.0 exists in the database
before the ORM tries to use them, preventing "relation does not exist" and
"column does not exist" errors on the hosted Odoo instance.

Changes covered (all code added after the initial 18.0.8.0.0 install):
  NEW TABLES
    farm_boq_work_type          — work-type classification model
    project_cost_analysis_line  — project costing analysis workspace
    farm_field_sale_order_rel   — Many2many junction (farm.field ↔ sale.order)

  NEW COLUMNS on existing tables
    farm_boq_item_template  : work_type_id
    farm_cost_line          : work_type_id
    product_template        : cost_type_id (default cost type for costing lines)
    farm_boq_item           : work_type_id, task_id, sale_order_id,
                              quotation_line_id, execution_status
    farm_field              : partner_id, include_detailed_lines, project_id
    project_project         : analysis_material_total, analysis_labor_total,
                              analysis_overhead_total, analysis_total_cost,
                              analysis_total_profit, analysis_total_sale
"""
import logging

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _table_exists(cr, table):
    cr.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    return bool(cr.fetchone())


def _col_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def _add_col(cr, table, column, col_type, default=None):
    """Add a column to a table if it does not already exist."""
    if _col_exists(cr, table, column):
        _logger.info('column %s.%s already exists — skipping', table, column)
        return
    default_clause = f' DEFAULT {default}' if default is not None else ''
    cr.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}')
    _logger.info('added column %s.%s (%s)', table, column, col_type)


def _create_table_if_missing(cr, table, ddl):
    if _table_exists(cr, table):
        _logger.info('table %s already exists — skipping', table)
        return
    cr.execute(ddl)
    _logger.info('created table %s', table)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def migrate(cr, version):
    _logger.info('smart_farm_alandleeb pre-migrate 18.0.9.0.0 starting')

    # ── 1. farm_boq_work_type ────────────────────────────────────────────────
    _create_table_if_missing(cr, 'farm_boq_work_type', """
        CREATE TABLE farm_boq_work_type (
            id              SERIAL PRIMARY KEY,
            name            VARCHAR NOT NULL,
            code            VARCHAR,
            costing_section VARCHAR NOT NULL DEFAULT 'civil',
            description     TEXT,
            active          BOOLEAN DEFAULT TRUE,
            sequence        INTEGER DEFAULT 10,
            create_uid      INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
            create_date     TIMESTAMP WITHOUT TIME ZONE,
            write_uid       INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
            write_date      TIMESTAMP WITHOUT TIME ZONE
        )
    """)

    # ── 2. New columns on farm_boq_item_template ─────────────────────────────
    _add_col(cr, 'farm_boq_item_template', 'work_type_id', 'INTEGER')

    # ── 2b. New columns on farm_cost_line ────────────────────────────────────
    _add_col(cr, 'farm_cost_line', 'work_type_id',         'INTEGER')
    _add_col(cr, 'farm_cost_line', 'parent_section_id',    'INTEGER')
    _add_col(cr, 'farm_cost_line', 'parent_subsection_id', 'INTEGER')
    _add_col(cr, 'farm_cost_line', 'sequence_no',          'VARCHAR')
    _add_col(cr, 'farm_cost_line', 'source_template_id',   'INTEGER')

    # ── 2c. New column on product_template (default cost type) ───────────────
    _add_col(cr, 'product_template', 'cost_type_id', 'INTEGER')

    # ── 3. New columns on farm_boq_item ─────────────────────────────────────
    _add_col(cr, 'farm_boq_item', 'work_type_id',      'INTEGER')
    _add_col(cr, 'farm_boq_item', 'task_id',           'INTEGER')
    _add_col(cr, 'farm_boq_item', 'sale_order_id',     'INTEGER')
    _add_col(cr, 'farm_boq_item', 'quotation_line_id', 'INTEGER')
    _add_col(cr, 'farm_boq_item', 'execution_status',  "VARCHAR DEFAULT 'draft'")

    # ── 4. New columns on farm_field ─────────────────────────────────────────
    _add_col(cr, 'farm_field', 'partner_id',            'INTEGER')
    _add_col(cr, 'farm_field', 'include_detailed_lines', 'BOOLEAN DEFAULT FALSE')
    _add_col(cr, 'farm_field', 'project_id',            'INTEGER')

    # ── 5. farm_field_sale_order_rel (Many2many junction) ───────────────────
    _create_table_if_missing(cr, 'farm_field_sale_order_rel', """
        CREATE TABLE farm_field_sale_order_rel (
            field_id      INTEGER NOT NULL REFERENCES farm_field(id)  ON DELETE CASCADE,
            sale_order_id INTEGER NOT NULL REFERENCES sale_order(id)  ON DELETE CASCADE,
            PRIMARY KEY (field_id, sale_order_id)
        )
    """)

    # ── 6. project_cost_analysis_line ────────────────────────────────────────
    _create_table_if_missing(cr, 'project_cost_analysis_line', """
        CREATE TABLE project_cost_analysis_line (
            id                      SERIAL PRIMARY KEY,
            project_id              INTEGER NOT NULL
                                        REFERENCES project_project(id) ON DELETE CASCADE,
            parent_id               INTEGER
                                        REFERENCES project_cost_analysis_line(id) ON DELETE CASCADE,
            line_type               VARCHAR NOT NULL DEFAULT 'division',
            sequence                INTEGER DEFAULT 10,
            sequence_no             VARCHAR,
            name                    VARCHAR NOT NULL,
            active                  BOOLEAN DEFAULT TRUE,
            costing_section         VARCHAR,
            work_type_id            INTEGER,
            boq_item_template_id    INTEGER,
            product_id              INTEGER,
            uom_name                VARCHAR,
            quantity                DOUBLE PRECISION DEFAULT 1.0,
            material_total          DOUBLE PRECISION DEFAULT 0.0,
            labor_total             DOUBLE PRECISION DEFAULT 0.0,
            overhead_total          DOUBLE PRECISION DEFAULT 0.0,
            total_cost              DOUBLE PRECISION DEFAULT 0.0,
            suggested_profit_percent DOUBLE PRECISION DEFAULT 0.0,
            profit_amount           DOUBLE PRECISION DEFAULT 0.0,
            sale_total              DOUBLE PRECISION DEFAULT 0.0,
            create_uid              INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
            create_date             TIMESTAMP WITHOUT TIME ZONE,
            write_uid               INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
            write_date              TIMESTAMP WITHOUT TIME ZONE
        )
    """)
    # Indexes that Odoo would create during normal upgrade
    if _table_exists(cr, 'project_cost_analysis_line'):
        cr.execute("""
            CREATE INDEX IF NOT EXISTS project_cost_analysis_line_project_id_idx
                ON project_cost_analysis_line (project_id)
        """)
        cr.execute("""
            CREATE INDEX IF NOT EXISTS project_cost_analysis_line_parent_id_idx
                ON project_cost_analysis_line (parent_id)
        """)

    # ── 7. New columns on project_project ────────────────────────────────────
    for col in (
        'analysis_material_total',
        'analysis_labor_total',
        'analysis_overhead_total',
        'analysis_total_cost',
        'analysis_total_profit',
        'analysis_total_sale',
    ):
        _add_col(cr, 'project_project', col, 'DOUBLE PRECISION', default='0.0')

    _logger.info('smart_farm_alandleeb pre-migrate 18.0.9.0.0 complete')
