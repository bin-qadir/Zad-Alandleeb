# -*- coding: utf-8 -*-
"""
Post-migration 18.0.9.0.0 — safety pass after ORM schema update.

Verifies the project_project analysis columns exist.  If the ORM already
added them this is a no-op; if for any reason they were missed (e.g. the
pre-migrate ran and the ORM skipped them) this adds them now.
"""
import logging

_logger = logging.getLogger(__name__)

_ANALYSIS_COLS = [
    'analysis_material_total',
    'analysis_labor_total',
    'analysis_overhead_total',
    'analysis_total_cost',
    'analysis_total_profit',
    'analysis_total_sale',
]


def migrate(cr, version):
    for col in _ANALYSIS_COLS:
        cr.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'project_project' AND column_name = %s",
            (col,),
        )
        if cr.fetchone():
            _logger.info('project_project.%s OK', col)
        else:
            cr.execute(
                f'ALTER TABLE project_project'
                f' ADD COLUMN {col} DOUBLE PRECISION DEFAULT 0.0'
            )
            _logger.info('post-migrate: created project_project.%s', col)
