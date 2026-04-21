"""
Smart Farm Control — post-install / post-upgrade hooks.

post_init_hook:
  Activates financial demo data so the executive dashboard shows real values
  out-of-the-box instead of zeros.

  What this does:
  1. Sets cost_unit_price / sale_unit_price on the existing BOQ analysis lines
     (BOQA-0002 lines 11-14) so that total_cost / total_sale become non-zero.

  2. Creates 4 Job Orders linked to the main demo project and approved BOQ
     analysis, with realistic quantities, stages, and actual material costs.

  3. Creates 1 demo customer invoice linked to the main project so that the
     revenue field is populated.

  Idempotent: skips if JOs already exist for project 3.
"""
import logging

_logger = logging.getLogger(__name__)

# ── Demo tuning constants ────────────────────────────────────────────────────
# These match the existing DEMO-2024-001 BOQ lines (IDs 440-443)
# and the analysis lines (IDs 11-14) inside BOQA-0002.
#
# Structure of DEMO-2024-001:
#   Section 437  — Multi-Activity Demo Works
#     Subsection 438 — Demo Operations
#       Sub-sub 439  — Demo Operations Package
#         Line 440   Greenhouse Construction – Phase 1  qty=100  price=5,000
#         Line 441   Strawberry Farm – Sector A         qty=10500 price=18
#         Line 442   Fruit Packing Line 01              qty=6800  price=25
#         Line 443   Sheep Fattening – Batch 01         qty=120   price=750
#
# Analysis BOQA-0002 mirrors these:
#   Line 11 → BOQ line 440  (structural+item)
#   Line 12 → BOQ line 441
#   Line 13 → BOQ line 442
#   Line 14 → BOQ line 443

_ANALYSIS_LINE_PRICES = {
    # analysis_line_id: (cost_unit_price, sale_unit_price)
    11: (4000.00, 5000.00),   # Greenhouse  → cost margin 20%
    12: (   14.40,   18.00),  # Strawberry  → cost margin 20%
    13: (   20.00,   25.00),  # Packing     → cost margin 20%
    14: (  600.00,  750.00),  # Livestock   → cost margin 20%
}

_JO_DEFS = [
    # (name, boq_line_id, analysis_line_id, planned_qty,
    #  approved_qty, claimed_qty, jo_stage, mat_cost, lab_cost)
    (
        'JO-001 Greenhouse Construction',
        440, 11,
        100.0, 80.0, 60.0,
        'claimed',
        220000.0,   # actual material cost
        80000.0,    # actual labour cost
    ),
    (
        'JO-002 Strawberry Farm Ops',
        441, 12,
        10500.0, 8000.0, 5000.0,
        'ready_for_claim',
        105000.0,
        46000.0,
    ),
    (
        'JO-003 Fruit Packing Line',
        442, 13,
        6800.0, 5000.0, 3000.0,
        'under_inspection',
        95000.0,
        32000.0,
    ),
    (
        'JO-004 Sheep Fattening Batch',
        443, 14,
        120.0, 90.0, 50.0,
        'ready_for_claim',
        52000.0,
        20000.0,
    ),
]

# Demo invoice amount (a portion of approved claims already billed)
_DEMO_INVOICE_AMOUNT = 350000.0


def post_init_hook(env):
    """Populate financial demo data after module install/upgrade."""
    _logger.info('smart_farm_control: running post_init_hook')

    # ── 0. Guard: skip if JOs already exist for project 3 ────────────────────
    JO = env['farm.job.order']
    existing = JO.search([('project_id', '=', 3)], limit=1)
    if existing:
        _logger.info('smart_farm_control: JOs already exist, skipping demo seed')
        return

    # ── 1. Fix BOQ analysis line prices ──────────────────────────────────────
    AnalysisLine = env['farm.boq.analysis.line']
    for line_id, (cost_price, sale_price) in _ANALYSIS_LINE_PRICES.items():
        line = AnalysisLine.browse(line_id).exists()
        if line:
            line.write({
                'cost_unit_price': cost_price,
                'sale_unit_price': sale_price,
            })
            _logger.info(
                'smart_farm_control: set prices on analysis line %d (%s)',
                line_id, line.name,
            )

    # ── 2. Create Job Orders ──────────────────────────────────────────────────
    Project  = env['farm.project']
    Analysis = env['farm.boq.analysis']

    project  = Project.browse(3).exists()
    analysis = Analysis.browse(2).exists()

    if not project or not analysis:
        _logger.warning(
            'smart_farm_control: demo project (id=3) or analysis (id=2) '
            'not found — skipping JO creation'
        )
        return

    for (name, boq_line_id, analysis_line_id,
         planned_qty, approved_qty, claimed_qty,
         jo_stage, mat_cost, lab_cost) in _JO_DEFS:

        jo = JO.create({
            'name':              name,
            'project_id':        project.id,
            'analysis_id':       analysis.id,
            'boq_line_id':       boq_line_id,
            'business_activity': project.business_activity or 'construction',
            'planned_qty':       planned_qty,
            'approved_qty':      approved_qty,
            'claimed_qty':       claimed_qty,
            'state':             'approved',
            'jo_stage':          jo_stage,
        })
        # Write actual costs directly (bypass stage guards for demo seeding)
        env.cr.execute(
            """
            UPDATE farm_job_order
            SET    actual_material_cost = %s,
                   actual_labour_cost   = %s
            WHERE  id = %s
            """,
            (mat_cost, lab_cost, jo.id),
        )
        _logger.info('smart_farm_control: created demo JO %d (%s)', jo.id, name)

    # ── 3. Create demo customer invoice ──────────────────────────────────────
    # Check if account.move has farm_project_id (requires smart_farm_sale_contract
    # to be installed with the invoice inherit)
    Move = env['account.move']
    if 'farm_project_id' not in Move._fields:
        _logger.info(
            'smart_farm_control: account.move.farm_project_id not available, '
            'skipping demo invoice creation'
        )
    else:
        # Find a suitable journal (customer invoices journal)
        Journal = env['account.journal']
        journal = Journal.search([
            ('type', '=', 'sale'),
            ('company_id', '=', env.company.id),
        ], limit=1)

        # Find a customer (use the company partner as fallback)
        partner = env['res.partner'].search([
            ('customer_rank', '>', 0),
        ], limit=1) or env.company.partner_id

        if journal:
            try:
                invoice = Move.create({
                    'move_type':       'out_invoice',
                    'farm_project_id': project.id,
                    'partner_id':      partner.id,
                    'journal_id':      journal.id,
                    'invoice_date':    fields_date(),
                    'invoice_line_ids': [(0, 0, {
                        'name':      'Greenhouse Construction – Phase 1 (Claim)',
                        'quantity':  1.0,
                        'price_unit': _DEMO_INVOICE_AMOUNT,
                    })],
                })
                invoice.action_post()
                _logger.info(
                    'smart_farm_control: created & posted demo invoice %s '
                    '(amount_untaxed=%.2f)',
                    invoice.name, invoice.amount_untaxed,
                )
            except Exception as exc:
                _logger.warning(
                    'smart_farm_control: demo invoice creation failed: %s', exc
                )

    # ── 4. Invalidate compute cache so engine re-runs ─────────────────────────
    project.invalidate_recordset()
    _logger.info('smart_farm_control: post_init_hook complete')


def fields_date():
    """Return today's date as a string (avoids importing fields at module level)."""
    from odoo import fields as odoo_fields
    return odoo_fields.Date.today()
