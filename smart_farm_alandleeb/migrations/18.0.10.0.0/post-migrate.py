# -*- coding: utf-8 -*-
"""
Post-migration 18.0.10.0.0 — safety verification pass.

Runs AFTER the ORM has applied schema changes.  Verifies all critical
columns and tables now exist.  Any remaining gap is reported as a WARNING
so the administrator can investigate without causing a hard failure.
"""
import logging

_logger = logging.getLogger(__name__)

# Tables that MUST exist after upgrade
_REQUIRED_TABLES = [
    'farm_boq_work_type',
    'project_cost_analysis_line',
    'farm_field_sale_order_rel',
]

# (table, column) pairs that MUST exist after upgrade
_REQUIRED_COLUMNS = [
    # project_project analysis totals
    ('project_project', 'analysis_material_total'),
    ('project_project', 'analysis_labor_total'),
    ('project_project', 'analysis_overhead_total'),
    ('project_project', 'analysis_total_cost'),
    ('project_project', 'analysis_total_profit'),
    ('project_project', 'analysis_total_sale'),
    # farm_cost_line hierarchical columns
    ('farm_cost_line', 'work_type_id'),
    ('farm_cost_line', 'parent_section_id'),
    ('farm_cost_line', 'parent_subsection_id'),
    ('farm_cost_line', 'sequence_no'),
    ('farm_cost_line', 'source_template_id'),
    ('farm_cost_line', 'is_manual_item'),
    ('farm_cost_line', 'is_template_based'),
    ('farm_cost_line', 'profit_percent'),
    ('farm_cost_line', 'profit_amount'),
    ('farm_cost_line', 'sale_total'),
    ('farm_cost_line', 'material_amount'),
    ('farm_cost_line', 'labor_amount'),
    ('farm_cost_line', 'overhead_amount'),
    # farm_boq_item linking columns
    ('farm_boq_item', 'work_type_id'),
    ('farm_boq_item', 'task_id'),
    ('farm_boq_item', 'sale_order_id'),
    ('farm_boq_item', 'quotation_line_id'),
    ('farm_boq_item', 'execution_status'),
    # farm_field customer / project columns
    ('farm_field', 'partner_id'),
    ('farm_field', 'include_detailed_lines'),
    ('farm_field', 'project_id'),
    # product_template default cost type
    ('product_template', 'cost_type_id'),
    # farm_boq_item_template work type
    ('farm_boq_item_template', 'work_type_id'),
]


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
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def _add_col_safe(cr, table, column, col_type, default=None):
    """Emergency add — used only when a required column is still missing post-ORM."""
    if not _table_exists(cr, table):
        _logger.error('post-migrate: table %s missing — cannot add column %s', table, column)
        return
    default_clause = f' DEFAULT {default}' if default is not None else ''
    cr.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}')
    _logger.warning('post-migrate: emergency-added column %s.%s', table, column)


def migrate(cr, version):
    _logger.info('smart_farm_alandleeb post-migrate 18.0.10.0.0 starting')

    # ── Verify / emergency-fix critical tables ────────────────────────────────
    for table in _REQUIRED_TABLES:
        if _table_exists(cr, table):
            _logger.info('post-migrate: table %s OK', table)
        else:
            _logger.error('post-migrate: table %s STILL MISSING after ORM upgrade', table)

    # ── Verify / emergency-fix critical columns ───────────────────────────────
    _EMERGENCY_COL_SPECS = {
        # (table, column): (col_type, default)
        ('project_project', 'analysis_material_total'): ('DOUBLE PRECISION', '0.0'),
        ('project_project', 'analysis_labor_total'):    ('DOUBLE PRECISION', '0.0'),
        ('project_project', 'analysis_overhead_total'): ('DOUBLE PRECISION', '0.0'),
        ('project_project', 'analysis_total_cost'):     ('DOUBLE PRECISION', '0.0'),
        ('project_project', 'analysis_total_profit'):   ('DOUBLE PRECISION', '0.0'),
        ('project_project', 'analysis_total_sale'):     ('DOUBLE PRECISION', '0.0'),
        ('farm_cost_line', 'work_type_id'):             ('INTEGER', None),
        ('farm_cost_line', 'parent_section_id'):        ('INTEGER', None),
        ('farm_cost_line', 'parent_subsection_id'):     ('INTEGER', None),
        ('farm_cost_line', 'sequence_no'):              ('VARCHAR', None),
        ('farm_cost_line', 'source_template_id'):       ('INTEGER', None),
        ('farm_cost_line', 'is_manual_item'):           ('BOOLEAN', 'TRUE'),
        ('farm_cost_line', 'is_template_based'):        ('BOOLEAN', 'FALSE'),
        ('farm_cost_line', 'profit_percent'):           ('DOUBLE PRECISION', '0.0'),
        ('farm_cost_line', 'profit_amount'):            ('DOUBLE PRECISION', '0.0'),
        ('farm_cost_line', 'sale_total'):               ('DOUBLE PRECISION', '0.0'),
        ('farm_cost_line', 'material_amount'):          ('DOUBLE PRECISION', '0.0'),
        ('farm_cost_line', 'labor_amount'):             ('DOUBLE PRECISION', '0.0'),
        ('farm_cost_line', 'overhead_amount'):          ('DOUBLE PRECISION', '0.0'),
        ('farm_boq_item', 'work_type_id'):              ('INTEGER', None),
        ('farm_boq_item', 'task_id'):                   ('INTEGER', None),
        ('farm_boq_item', 'sale_order_id'):             ('INTEGER', None),
        ('farm_boq_item', 'quotation_line_id'):         ('INTEGER', None),
        ('farm_boq_item', 'execution_status'):          ("VARCHAR", "'draft'"),
        ('farm_field', 'partner_id'):                   ('INTEGER', None),
        ('farm_field', 'include_detailed_lines'):       ('BOOLEAN', 'FALSE'),
        ('farm_field', 'project_id'):                   ('INTEGER', None),
        ('product_template', 'cost_type_id'):           ('INTEGER', None),
        ('farm_boq_item_template', 'work_type_id'):     ('INTEGER', None),
    }

    for (table, column) in _REQUIRED_COLUMNS:
        if _col_exists(cr, table, column):
            _logger.info('post-migrate: %s.%s OK', table, column)
        else:
            # Try emergency fix
            spec = _EMERGENCY_COL_SPECS.get((table, column))
            if spec:
                col_type, default = spec
                _add_col_safe(cr, table, column, col_type, default)
            else:
                _logger.error('post-migrate: %s.%s MISSING and no spec to fix it', table, column)

    _logger.info('smart_farm_alandleeb post-migrate 18.0.10.0.0 complete')
