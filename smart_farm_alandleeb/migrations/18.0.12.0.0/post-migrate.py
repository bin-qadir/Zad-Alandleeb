# -*- coding: utf-8 -*-
"""
Post-migration for Smart Farm 18.0.12.0.0

Back-fills base_ratio_qty on existing data:
  1. Template lines: set base_ratio_qty = qty_1 where still at default.
  2. Cost-line children: set base_ratio_qty = quantity where still at 0.
  3. BOQ item lines: set base_ratio_qty = qty_1 where still at default.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("smart_farm 18.0.12.0.0 post-migrate: back-filling base_ratio_qty")

    # ── Template lines: base_ratio_qty = qty_1 ───────────────────────────────
    cr.execute("""
        UPDATE farm_boq_item_template_line
        SET    base_ratio_qty = COALESCE(qty_1, 1.0)
        WHERE  base_ratio_qty IS NULL
           OR  base_ratio_qty = 1.0
    """)
    _logger.info("  Back-filled farm_boq_item_template_line.base_ratio_qty (%d rows)",
                 cr.rowcount)

    # ── Cost-line children: base_ratio_qty = quantity ────────────────────────
    cr.execute("""
        UPDATE farm_cost_line
        SET    base_ratio_qty = COALESCE(quantity, 1.0)
        WHERE  boq_parent_id IS NOT NULL
          AND  (base_ratio_qty IS NULL OR base_ratio_qty = 0.0)
    """)
    _logger.info("  Back-filled farm_cost_line.base_ratio_qty (%d rows)", cr.rowcount)

    # ── Cost-line BOQ parents: main_quantity = 1 if not set ──────────────────
    cr.execute("""
        UPDATE farm_cost_line
        SET    main_quantity = 1.0
        WHERE  is_boq_item = TRUE
          AND  (main_quantity IS NULL OR main_quantity = 0.0)
    """)
    _logger.info("  Back-filled farm_cost_line.main_quantity (%d rows)", cr.rowcount)

    # ── BOQ item lines: base_ratio_qty = qty_1 ──────────────────────────────
    cr.execute("""
        UPDATE farm_boq_item_line
        SET    base_ratio_qty = COALESCE(qty_1, 1.0)
        WHERE  base_ratio_qty IS NULL
           OR  base_ratio_qty = 1.0
    """)
    _logger.info("  Back-filled farm_boq_item_line.base_ratio_qty (%d rows)",
                 cr.rowcount)

    _logger.info("smart_farm 18.0.12.0.0 post-migrate: done")
