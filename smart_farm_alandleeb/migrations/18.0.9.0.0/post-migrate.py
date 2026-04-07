# -*- coding: utf-8 -*-
"""
Migration 18.0.9.0.0 — add stored analysis total columns to project_project.

The six Float fields added by smart_farm_alandleeb to project.project
(analysis_material_total, analysis_labor_total, analysis_overhead_total,
analysis_total_cost, analysis_total_profit, analysis_total_sale) are
store=True computed fields.  Odoo's ORM creates those columns during a
normal module upgrade, but this explicit migration ensures the columns
exist even when the upgrade is run on an instance where the table was
already created without them.
"""
import logging

_logger = logging.getLogger(__name__)

_COLUMNS = [
    'analysis_material_total',
    'analysis_labor_total',
    'analysis_overhead_total',
    'analysis_total_cost',
    'analysis_total_profit',
    'analysis_total_sale',
]


def migrate(cr, version):
    for col in _COLUMNS:
        cr.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'project_project'
              AND column_name = %s
            """,
            (col,),
        )
        if cr.fetchone():
            _logger.info('project_project.%s already exists — skipping', col)
        else:
            cr.execute(
                f'ALTER TABLE project_project ADD COLUMN {col} DOUBLE PRECISION DEFAULT 0.0'
            )
            _logger.info('project_project.%s created', col)
