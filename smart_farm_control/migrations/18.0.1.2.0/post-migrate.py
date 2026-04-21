"""
Migration 18.0.1.2.0 — smart_farm_control

Post-migrate: fix stored computed fields that were bypassed by raw SQL inserts
in migration 18.0.1.1.0.

Steps (all done via SQL to avoid ORM recompute loops):
  1. Recompute farm_boq_analysis_line cost_total / sale_total (from new prices)
  2. Recompute farm_boq_analysis total_cost / total_sale
  3. Set farm_job_order.unit_price (stored related from boq_line)
  4. Set farm_job_order.planned_cost (from analysis line cost_total)
  5. Set farm_job_order approval/claim amounts and progress_percent
  6. Update farm_project cost/revenue fields via ORM engine call
"""
import logging

_logger = logging.getLogger(__name__)

_PROJECT_ID  = 3
_ANALYSIS_ID = 2


def migrate(cr, version):
    _fix_analysis_line_totals(cr)
    _fix_analysis_totals(cr)
    _fix_jo_stored_fields(cr)
    _fix_project_engine(cr)


def _fix_analysis_line_totals(cr):
    """Recompute cost_total and sale_total on analysis item lines."""
    cr.execute("""
        UPDATE farm_boq_analysis_line
        SET    cost_total  = boq_qty * cost_unit_price,
               sale_total  = boq_qty * sale_unit_price,
               write_date  = NOW()
        WHERE  analysis_id = %s
          AND  display_type IS NULL
          AND  boq_qty > 0
    """, (_ANALYSIS_ID,))
    _logger.info(
        'smart_farm_control recompute: updated %d analysis line totals',
        cr.rowcount,
    )


def _fix_analysis_totals(cr):
    """Recompute total_cost and total_sale on the analysis header."""
    cr.execute("""
        UPDATE farm_boq_analysis a
        SET    total_cost  = (
                   SELECT COALESCE(SUM(l.cost_total), 0)
                   FROM   farm_boq_analysis_line l
                   WHERE  l.analysis_id = a.id
                     AND  l.display_type IS NULL
               ),
               total_sale  = (
                   SELECT COALESCE(SUM(l.sale_total), 0)
                   FROM   farm_boq_analysis_line l
                   WHERE  l.analysis_id = a.id
                     AND  l.display_type IS NULL
               ),
               write_date  = NOW()
        WHERE  a.id = %s
    """, (_ANALYSIS_ID,))
    cr.execute(
        "SELECT total_cost, total_sale FROM farm_boq_analysis WHERE id = %s",
        (_ANALYSIS_ID,),
    )
    row = cr.fetchone()
    _logger.info(
        'smart_farm_control recompute: analysis %d total_cost=%.2f total_sale=%.2f',
        _ANALYSIS_ID, row[0], row[1],
    )


def _fix_jo_stored_fields(cr):
    """Set stored related / computed fields on demo JOs via SQL."""

    # unit_price: stored related from farm_boq_line.unit_price
    cr.execute("""
        UPDATE farm_job_order jo
        SET    unit_price = bl.unit_price,
               write_date = NOW()
        FROM   farm_boq_line bl
        WHERE  bl.id = jo.boq_line_id
          AND  jo.project_id = %s
    """, (_PROJECT_ID,))
    _logger.info('smart_farm_control recompute: set unit_price on %d JOs', cr.rowcount)

    # planned_cost: from analysis line cost_total (if analysis_line_id set)
    cr.execute("""
        UPDATE farm_job_order jo
        SET    planned_cost = COALESCE(al.cost_total, 0),
               write_date   = NOW()
        FROM   farm_boq_analysis_line al
        WHERE  al.id = jo.analysis_line_id
          AND  jo.project_id = %s
          AND  jo.analysis_line_id IS NOT NULL
    """, (_PROJECT_ID,))
    _logger.info('smart_farm_control recompute: set planned_cost on %d JOs', cr.rowcount)

    # progress_percent: approved_qty / planned_qty * 100
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

    # approved_amount / claimable_amount / claim_amount / remaining_amount
    cr.execute("""
        UPDATE farm_job_order
        SET    approved_amount    = approved_qty  * unit_price,
               claimable_amount  = GREATEST(0, approved_qty - claimed_qty) * unit_price,
               claim_amount      = claimed_qty    * unit_price,
               remaining_amount  = GREATEST(0, planned_qty - approved_qty) * unit_price,
               write_date        = NOW()
        WHERE  project_id = %s
    """, (_PROJECT_ID,))

    # Log JO financials
    cr.execute("""
        SELECT id, name, unit_price, approved_amount, claim_amount,
               actual_material_cost, actual_labour_cost
        FROM   farm_job_order
        WHERE  project_id = %s
        ORDER  BY id
    """, (_PROJECT_ID,))
    for row in cr.fetchall():
        _logger.info(
            'smart_farm_control recompute: JO %d "%s" '
            'unit_price=%.2f approved=%.2f claim=%.2f mat=%.2f lab=%.2f',
            *row,
        )


def _fix_project_engine(cr):
    """Update farm_project financial fields directly via SQL aggregates."""

    # Compute sums from JOs
    cr.execute("""
        SELECT
            COALESCE(SUM(actual_material_cost), 0) AS mat,
            COALESCE(SUM(actual_labour_cost),   0) AS lab,
            COALESCE(SUM(approved_amount),       0) AS approved,
            COALESCE(SUM(claimable_amount),      0) AS claimable,
            COALESCE(SUM(claim_amount),          0) AS claimed,
            COALESCE(SUM(planned_cost),          0) AS planned
        FROM farm_job_order
        WHERE project_id = %s
    """, (_PROJECT_ID,))
    jo_row = cr.fetchone()
    mat, lab, approved, claimable, claimed, planned_cost = jo_row
    actual_total = mat + lab

    # Contract value from BOQ total
    cr.execute("SELECT total FROM farm_boq WHERE project_id = %s LIMIT 1", (_PROJECT_ID,))
    boq_row = cr.fetchone()
    contract_val = boq_row[0] if boq_row else 0.0

    # Estimated cost from approved analysis
    cr.execute(
        "SELECT total_cost FROM farm_boq_analysis WHERE id = %s",
        (_ANALYSIS_ID,),
    )
    est_row = cr.fetchone()
    estimated = est_row[0] if est_row else 0.0

    # Revenue from posted customer invoices
    cr.execute("""
        SELECT COALESCE(SUM(amount_untaxed), 0)
        FROM   account_move
        WHERE  farm_project_id = %s
          AND  move_type = 'out_invoice'
          AND  state = 'posted'
    """, (_PROJECT_ID,))
    revenue = cr.fetchone()[0]

    # Fallback revenue = claim_amount if no invoices
    if not revenue:
        revenue = claimed

    # Derived metrics
    current_profit  = contract_val - actual_total
    realized_profit = revenue - actual_total
    estimated_profit = contract_val - estimated
    forecast = actual_total  # simplified: no remaining planned if all JOs in progress
    cost_variance = actual_total - contract_val

    cr.execute("""
        UPDATE farm_project
        SET    contract_value              = %s,
               estimated_cost             = %s,
               actual_material_cost       = %s,
               actual_labour_cost         = %s,
               actual_total_cost          = %s,
               cost_variance              = %s,
               current_profit             = %s,
               estimated_profit           = %s,
               revenue                    = %s,
               realized_profit            = %s,
               write_date                 = NOW()
        WHERE  id = %s
    """, (
        contract_val, estimated,
        mat, lab, actual_total,
        cost_variance,
        current_profit, estimated_profit,
        revenue, realized_profit,
        _PROJECT_ID,
    ))

    _logger.info(
        'smart_farm_control recompute: project %d — '
        'contract=%.2f est=%.2f actual=%.2f revenue=%.2f realized=%.2f '
        'JO approved=%.2f claim=%.2f',
        _PROJECT_ID,
        contract_val, estimated, actual_total,
        revenue, realized_profit,
        approved, claimed,
    )
