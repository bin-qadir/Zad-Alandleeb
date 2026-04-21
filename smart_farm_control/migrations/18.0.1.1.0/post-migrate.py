"""
Migration 18.0.1.1.0 — smart_farm_control

Post-migrate: seed financial demo data so the executive dashboard shows real
values instead of zeros.

What this does (idempotent — skips if JOs for project 3 already exist):
  1. Sets cost_unit_price / sale_unit_price on BOQ analysis lines 11-14
     (BOQA-0002, project مزرعة العندليب) → total_cost / total_sale become real.
  2. Inserts 4 Job Orders via direct SQL to bypass the execution-phase gate
     (this is a demo seed, not a real project workflow).
  3. Creates and posts 1 demo customer invoice linked to project 3.
"""
import logging

_logger = logging.getLogger(__name__)

_ANALYSIS_LINE_PRICES = [
    # (analysis_line_id, cost_unit_price, sale_unit_price)
    (11, 4000.00, 5000.00),   # Greenhouse Construction – Phase 1  20% margin
    (12,   14.40,   18.00),   # Strawberry Farm – Sector A         20% margin
    (13,   20.00,   25.00),   # Fruit Packing Line 01              20% margin
    (14,  600.00,  750.00),   # Sheep Fattening – Batch 01         20% margin
]

# JO inserts:
# (name, analysis_id, boq_line_id, analysis_line_id,
#  planned_qty, approved_qty, claimed_qty, jo_stage,
#  mat_cost, lab_cost, business_activity)
_JO_DEFS = [
    (
        'JO-001 Greenhouse Construction',
        2, 440, 11,
        100.0, 80.0, 60.0, 'claimed',
        220000.0, 80000.0, 'construction',
    ),
    (
        'JO-002 Strawberry Farm Ops',
        2, 441, 12,
        10500.0, 8000.0, 5000.0, 'ready_for_claim',
        105000.0, 46000.0, 'construction',
    ),
    (
        'JO-003 Fruit Packing Line',
        2, 442, 13,
        6800.0, 5000.0, 3000.0, 'under_inspection',
        95000.0, 32000.0, 'construction',
    ),
    (
        'JO-004 Sheep Fattening Batch',
        2, 443, 14,
        120.0, 90.0, 50.0, 'ready_for_claim',
        52000.0, 20000.0, 'construction',
    ),
]

_DEMO_INVOICE_AMOUNT = 350000.0
_PROJECT_ID = 3
_ANALYSIS_ID = 2


def migrate(cr, version):
    """Seed financial demo data."""

    # ── Guard: skip if JOs already exist for project 3 ───────────────────────
    cr.execute(
        "SELECT id FROM farm_job_order WHERE project_id = %s LIMIT 1",
        (_PROJECT_ID,),
    )
    if cr.fetchone():
        _logger.info('smart_farm_control migration: JOs already exist, skipping seed')
        return

    # ── 1. Fix BOQ analysis line prices ──────────────────────────────────────
    for (line_id, cost_price, sale_price) in _ANALYSIS_LINE_PRICES:
        cr.execute(
            """
            UPDATE farm_boq_analysis_line
            SET    cost_unit_price = %s,
                   sale_unit_price = %s,
                   write_date      = NOW()
            WHERE  id = %s
            """,
            (cost_price, sale_price, line_id),
        )
        if cr.rowcount:
            _logger.info(
                'smart_farm_control: set prices on analysis line %d '
                '(cost=%.2f sale=%.2f)',
                line_id, cost_price, sale_price,
            )

    # Invalidate the stored compute on the analysis (force recompute on next read)
    cr.execute(
        """
        UPDATE farm_boq_analysis
        SET    total_cost = 0, total_sale = 0
        WHERE  id = %s
        """,
        (_ANALYSIS_ID,),
    )

    # ── 2. Insert Job Orders via direct SQL (bypass phase gate) ──────────────
    jo_ids = []
    for (name, analysis_id, boq_line_id, analysis_line_id,
         planned_qty, approved_qty, claimed_qty, jo_stage,
         mat_cost, lab_cost, business_activity) in _JO_DEFS:

        cr.execute(
            """
            INSERT INTO farm_job_order (
                name, project_id, analysis_id, boq_line_id, analysis_line_id,
                business_activity, planned_qty, approved_qty, claimed_qty,
                state, jo_stage,
                actual_material_cost, actual_labour_cost,
                create_date, write_date,
                create_uid, write_uid
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                'approved', %s,
                %s, %s,
                NOW(), NOW(),
                1, 1
            )
            RETURNING id
            """,
            (
                name, _PROJECT_ID, analysis_id, boq_line_id, analysis_line_id,
                business_activity, planned_qty, approved_qty, claimed_qty,
                jo_stage,
                mat_cost, lab_cost,
            ),
        )
        jo_id = cr.fetchone()[0]
        jo_ids.append(jo_id)
        _logger.info('smart_farm_control: inserted demo JO id=%d "%s"', jo_id, name)

    # ── 3. Create demo customer invoice ──────────────────────────────────────
    _create_demo_invoice(cr)

    # ── 4. Force ORM recompute of stored computed fields ─────────────────────
    # We inserted data via raw SQL — Odoo's stored-compute invalidation was
    # bypassed.  Trigger recompute now so the project's cost fields are correct.
    _force_recompute(cr, jo_ids)


def _force_recompute(cr, jo_ids):
    """Force ORM recompute of stored fields that were bypassed by raw SQL inserts."""
    try:
        from odoo import api, SUPERUSER_ID
        from odoo.modules.registry import Registry

        reg = Registry(cr.dbname)
        with reg.cursor() as new_cr:
            env = api.Environment(new_cr, SUPERUSER_ID, {})

            # 1. Recompute BOQ analysis totals (prices were set via SQL)
            analysis = env['farm.boq.analysis'].browse(_ANALYSIS_ID).exists()
            if analysis:
                analysis.invalidate_recordset(['total_cost', 'total_sale', 'total_profit', 'total_margin'])
                analysis._compute_totals()
                _logger.info(
                    'smart_farm_control: recomputed analysis totals: '
                    'total_cost=%.2f total_sale=%.2f',
                    analysis.total_cost, analysis.total_sale,
                )

            # 2. Recompute JO claim/approval amounts (approved_qty etc set via SQL)
            jos = env['farm.job.order'].browse(jo_ids).exists()
            if jos:
                jos.invalidate_recordset()
                jos._compute_claim_kpis()

            # 3. Recompute project engine fields
            project = env['farm.project'].browse(_PROJECT_ID).exists()
            if project:
                project.invalidate_recordset()
                project._compute_project_engine()
                _logger.info(
                    'smart_farm_control: project %d recomputed: '
                    'contract=%.2f est=%.2f actual=%.2f revenue=%.2f',
                    _PROJECT_ID,
                    project.contract_value,
                    project.estimated_cost,
                    project.actual_total_cost,
                    project.revenue,
                )

            new_cr.commit()
    except Exception as exc:
        _logger.warning('smart_farm_control: force_recompute failed: %s', exc)


def _create_demo_invoice(cr):
    """Create and post a demo customer invoice for project 3."""
    # Check if farm_project_id column exists on account_move
    cr.execute(
        """
        SELECT column_name
        FROM   information_schema.columns
        WHERE  table_name  = 'account_move'
        AND    column_name = 'farm_project_id'
        """
    )
    if not cr.fetchone():
        _logger.info(
            'smart_farm_control: farm_project_id column not yet on account_move '
            '— skipping demo invoice'
        )
        return

    # Avoid creating a duplicate demo invoice
    cr.execute(
        """
        SELECT id FROM account_move
        WHERE  farm_project_id = %s
        AND    move_type = 'out_invoice'
        LIMIT  1
        """,
        (_PROJECT_ID,),
    )
    if cr.fetchone():
        _logger.info('smart_farm_control: demo invoice already exists, skipping')
        return

    # Use ORM for invoice creation (handles account assignment correctly)
    try:
        from odoo import api, SUPERUSER_ID
        from odoo.modules.registry import Registry
        reg = Registry(cr.dbname)
        with reg.cursor() as new_cr:
            env = api.Environment(new_cr, SUPERUSER_ID, {})

            journal = env['account.journal'].search(
                [('type', '=', 'sale'), ('company_id', '=', env.company.id)],
                limit=1,
            )
            if not journal:
                _logger.warning('smart_farm_control: no sale journal — skipping invoice')
                return

            partner = (
                env['res.partner'].search([('customer_rank', '>', 0)], limit=1)
                or env.company.partner_id
            )

            from odoo import fields as odoo_fields
            invoice = env['account.move'].create({
                'move_type':        'out_invoice',
                'farm_project_id':  _PROJECT_ID,
                'partner_id':       partner.id,
                'journal_id':       journal.id,
                'invoice_date':     odoo_fields.Date.today(),
                'invoice_line_ids': [(0, 0, {
                    'name':       'Greenhouse Construction – Phase 1 (Progress Claim)',
                    'quantity':   1.0,
                    'price_unit': _DEMO_INVOICE_AMOUNT,
                })],
            })
            invoice.action_post()
            new_cr.commit()
            _logger.info(
                'smart_farm_control: created & posted demo invoice %s '
                '(amount=%.2f)',
                invoice.name, invoice.amount_untaxed,
            )
    except Exception as exc:
        _logger.warning(
            'smart_farm_control: demo invoice creation skipped: %s', exc
        )
