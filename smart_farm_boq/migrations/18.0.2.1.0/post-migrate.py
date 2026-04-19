"""
Migration 18.0.2.1.0 — Separate BOQ project quantity from subitem unit-cost quantity.

Before this version:
  • farm.boq.line.quantity  held the project (BOQ) quantity for subitems.
  • total = quantity × unit_price

After this version:
  • quantity is locked to 1.00 on all subitems (they represent one unit of work).
  • boq_qty  holds the actual project quantity.
  • total = boq_qty × unit_price

This script copies the old quantity value into boq_qty for all existing subitems
(rows where parent_id IS NOT NULL and display_type IS NULL).
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE farm_boq_line
           SET boq_qty   = quantity,
               quantity  = 1.0
         WHERE parent_id IS NOT NULL
           AND display_type IS NULL
    """)
