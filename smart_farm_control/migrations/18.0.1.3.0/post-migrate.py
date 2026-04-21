"""
Migration 18.0.1.3.0 — smart_farm_control

Fix all stored computed fields on demo data via pure SQL.
Previous migrations left JOs with 0 actual costs and null unit_price.

This migration is self-contained: it reads live BOQ/analysis data and
writes the correct values to all related tables.
"""
import logging

_logger = logging.getLogger(__name__)

_PROJECT_ID  = 3
_ANALYSIS_ID = 2


def migrate(cr, version):
    _fix_analysis_line_totals(cr)
    _fix_analysis_totals(cr)
    _fix_jo_stored_fields(cr)
    _fix_project_fields(cr)
    _log_summary(cr)


def _fix_analysis_line_totals(cr):
    """Recompute cost_total / sale_total on analysis item lines."""
    cr.execute("""
        UPDATE farm_boq_analysis_line
        SET    cost_total = boq_qty * cost_unit_price,
               sale_total = boq_qty * sale_unit_price,
               write_date = NOW()
        WHERE  analysis_id = %s
          AND  (display_type IS NULL OR display_type = '')
          AND  boq_qty > 0
          AND  cost_unit_price > 0
    """, (_ANALYSIS_ID,))
    _logger.info('fixed %d analysis line totals', cr.rowcount)


def _fix_analysis_totals(cr):
    """Recompute total_cost / total_sale on analysis header."""
    cr.execute("""
        UPDATE farm_boq_analysis a
        SET    total_cost = (
                   SELECT COALESCE(SUM(l.cost_total), 0)
                   FROM   farm_boq_analysis_line l
                   WHERE  l.analysis_id = a.id
               ),
               total_sale = (
                   SELECT COALESCE(SUM(l.sale_total), 0)
                   FROM   farm_boq_analysis_line l
                   WHERE  l.analysis_id = a.id
               ),
               write_date = NOW()
        WHERE  a.id = %s
    """, (_ANALYSIS_ID,))
    cr.execute(
        "SELECT total_cost, total_sale FROM farm_boq_analysis WHERE id = %s",
        (_ANALYSIS_ID,),
    )
    row = cr.fetchone()
    _logger.info('analysis %d: total_cost=%.2f total_sale=%.2f', _ANALYSIS_ID, *row)


def _fix_jo_stored_fields(cr):
    """Fix all stored computed fields on demo JOs via SQL joins."""

    # 1. unit_price — stored related from farm_boq_line.unit_price
    cr.execute("""
        UPDATE farm_job_order jo
        SET    unit_price = bl.unit_price,
               write_date = NOW()
        FROM   farm_boq_line bl
        WHERE  bl.id = jo.boq_line_id
          AND  jo.project_id = %s
    """, (_PROJECT_ID,))
    _logger.info('set unit_price on %d JOs', cr.rowcount)

    # 2. planned_cost — from analysis line cost_total
    cr.execute("""
        UPDATE farm_job_order jo
        SET    planned_cost = COALESCE(al.cost_total, 0),
               write_date   = NOW()
        FROM   farm_boq_analysis_line al
        WHERE  al.id = jo.analysis_line_id
          AND  jo.project_id = %s
          AND  jo.analysis_line_id IS NOT NULL
    """, (_PROJECT_ID,))
    _logger.info('set planned_cost on %d JOs', cr.rowcount)

    # 3. actual material and labour costs (hardcoded demo values)
    _ACTUAL_COSTS = {
        'JO-001 Greenhouse Construction': (220000.0, 80000.0),
        'JO-002 Strawberry Farm Ops':     (105000.0, 46000.0),
        'JO-003 Fruit Packing Line':      ( 95000.0, 32000.0),
        'JO-004 Sheep Fattening Batch':   ( 52000.0, 20000.0),
    }
    for jo_name, (mat, lab) in _ACTUAL_COSTS.items():
        cr.execute("""
            UPDATE farm_job_order
            SET    actual_material_cost = %s,
                   actual_labour_cost   = %s,
                   write_date           = NOW()
            WHERE  project_id = %s AND name = %s
        """, (mat, lab, _PROJECT_ID, jo_name))

    # 4. progress_percent
    cr.execute("""
        UPDATE farm_job_order
        SET    progress_percent = CASE
                   WHEN planned_qty > 0
                   THEN ROUND((approved_qty / planned_qty * 100.0)::numeric, 2)
                   ELSE 0
               END,
               write_date = NOW()
        WHERE  project_id = %s
    """, (_PROJECT_ID,))

    # 5. claim / approval amounts
    cr.execute("""
        UPDATE farm_job_order
        SET    approved_amount   = approved_qty * unit_price,
               claimable_amount  = GREATEST(0, approved_qty - claimed_qty) * unit_price,
               claim_amount      = claimed_qty  * unit_price,
               remaining_amount  = GREATEST(0, planned_qty  - approved_qty) * unit_price,
               write_date        = NOW()
        WHERE  project_id = %s
          AND  unit_price > 0
    """, (_PROJECT_ID,))
    _logger.info('set claim/approval amounts on JOs for project %d', _PROJECT_ID)


def _fix_project_fields(cr):
    """Update farm_project stored cost/revenue fields directly via SQL."""

    # Aggregate from JOs
    cr.execute("""
        SELECT
            COALESCE(SUM(actual_material_cost), 0),
            COALESCE(SUM(actual_labour_cost),   0),
            COALESCE(SUM(approved_amount),       0),
            COALESCE(SUM(claim_amount),          0),
            COALESCE(SUM(planned_cost),          0)
        FROM farm_job_order
        WHERE project_id = %s
    """, (_PROJECT_ID,))
    mat, lab, approved, claimed, planned_total = cr.fetchone()
    actual_total = mat + lab

    # Contract value from BOQ total
    cr.execute(
        "SELECT COALESCE(total, 0) FROM farm_boq WHERE project_id = %s LIMIT 1",
        (_PROJECT_ID,),
    )
    contract_val_row = cr.fetchone()
    contract_val = contract_val_row[0] if contract_val_row else 0.0

    # Estimated cost from approved analysis
    cr.execute(
        "SELECT COALESCE(total_cost, 0) FROM farm_boq_analysis WHERE id = %s",
        (_ANALYSIS_ID,),
    )
    est_row = cr.fetchone()
    estimated = est_row[0] if est_row else 0.0

    # Revenue: posted customer invoices
    cr.execute("""
        SELECT COALESCE(SUM(amount_untaxed), 0)
        FROM   account_move
        WHERE  farm_project_id = %s
          AND  move_type = 'out_invoice'
          AND  state = 'posted'
    """, (_PROJECT_ID,))
    revenue = cr.fetchone()[0]
    if not revenue:
        revenue = claimed  # fallback: JO claim amounts

    # Derived
    current_profit   = contract_val - actual_total
    realized_profit  = revenue - actual_total
    estimated_profit = contract_val - estimated
    cost_variance    = actual_total - contract_val

    # Check which columns exist (graceful for partial installs)
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE  table_name = 'farm_project'
          AND  column_name IN (
              'contract_value', 'estimated_cost',
              'actual_material_cost', 'actual_labour_cost',
              'actual_total_cost', 'cost_variance',
              'current_profit', 'estimated_profit',
              'revenue', 'realized_profit'
          )
    """)
    available = {r[0] for r in cr.fetchall()}

    set_parts = []
    params = []

    def _set(col, val):
        if col in available:
            set_parts.append(f'{col} = %s')
            params.append(val)

    _set('contract_value',       contract_val)
    _set('estimated_cost',       estimated)
    _set('actual_material_cost', mat)
    _set('actual_labour_cost',   lab)
    _set('actual_total_cost',    actual_total)
    _set('cost_variance',        cost_variance)
    _set('current_profit',       current_profit)
    _set('estimated_profit',     estimated_profit)
    _set('revenue',              revenue)
    _set('realized_profit',      realized_profit)

    if set_parts:
        params.append(_PROJECT_ID)
        cr.execute(
            f"UPDATE farm_project SET {', '.join(set_parts)}, write_date = NOW() WHERE id = %s",
            params,
        )
        _logger.info(
            'project %d updated: contract=%.2f est=%.2f actual=%.2f '
            'revenue=%.2f realized=%.2f',
            _PROJECT_ID,
            contract_val, estimated, actual_total,
            revenue, realized_profit,
        )


def _log_summary(cr):
    """Log final state for verification."""
    cr.execute("""
        SELECT id, name, jo_stage,
               unit_price, approved_amount, claim_amount,
               actual_material_cost, actual_labour_cost
        FROM   farm_job_order
        WHERE  project_id = %s
        ORDER  BY id
    """, (_PROJECT_ID,))
    for row in cr.fetchall():
        _logger.info(
            'JO %d "%s" stage=%s price=%.2f approved=%.2f claim=%.2f mat=%.2f lab=%.2f',
            *row,
        )

    cr.execute("""
        SELECT contract_value, estimated_cost, actual_total_cost,
               revenue, realized_profit, current_profit
        FROM   farm_project WHERE id = %s
    """, (_PROJECT_ID,))
    row = cr.fetchone()
    _logger.info(
        'PROJECT %d: contract=%.2f est=%.2f actual=%.2f '
        'revenue=%.2f realized=%.2f current_profit=%.2f',
        _PROJECT_ID, *row,
    )
