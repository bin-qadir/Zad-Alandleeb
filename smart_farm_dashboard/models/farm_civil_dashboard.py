"""
farm.civil.dashboard  —  Civil Division Hierarchical Dashboard
==============================================================

Singleton model exposing full 10-metric KPI breakdown per Civil subdivision:

  1.  Contract Qty        = SUM(planned_qty)
  2.  In Progress         = SUM(executed_qty WHERE jo_stage='in_progress')
  3.  Not Started         = contract_qty - SUM(executed_qty)
  4.  Handover Requested  = SUM(executed_qty WHERE jo_stage='handover_requested')
  5.  Under Inspection    = SUM(executed_qty WHERE jo_stage='under_inspection')
  6.  Approved            = SUM(approved_qty)
  7.  Claimed             = SUM(claimed_qty)
  8.  Invoiced            = SUM(lc_invoiced_qty) via farm_boq_analysis_line join
  9.  Remaining           = contract_qty - invoiced_qty
  10. Variation           = approved_qty - contract_qty

Data source: farm.job.order filtered by
  • business_activity = 'construction'
  • department        = 'civil'

All fields are non-stored (compute only); they recompute on every form read.
Performance: 2 raw SQL queries cover all 8 subdivisions × 10 metrics in one pass.
"""
from odoo import api, fields, models, _


# ---------------------------------------------------------------------------
# Subdivision specs: (field_prefix, name_fragment, fa_icon, accent_color)
# ---------------------------------------------------------------------------
_SUBDIV_SPECS = [
    ('sp',  'Site Preparation',  'fa fa-road',      '#0891b2'),
    ('ex',  'Excavation',        'fa fa-arrow-down','#d97706'),
    ('bf',  'Backfilling',       'fa fa-upload',    '#7c3aed'),
    ('cw',  'Concrete Works',    'fa fa-cubes',     '#1d4ed8'),
    ('bw',  'Block Work',        'fa fa-th-large',  '#0f766e'),
    ('wp',  'Waterproofing',     'fa fa-tint',      '#0369a1'),
    ('rw',  'Road Works',        'fa fa-truck',     '#374151'),
    ('en',  'External Networks', 'fa fa-sitemap',   '#be123c'),
]

# Ordered metric suffixes for iteration in compute
_METRIC_KEYS = [
    'contract', 'inprog', 'notstart', 'handover',
    'inspection', 'approved', 'claimed', 'invoiced',
    'remaining', 'variation',
]


class FarmCivilDashboard(models.Model):
    _name        = 'farm.civil.dashboard'
    _description = 'Civil Division Dashboard'
    _rec_name    = 'id'

    # ── Project scope (None = global, set = project-specific view) ────────
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        ondelete='cascade',
        index=True,
        help='When set, all metrics are filtered to this project only.',
    )

    # ── Header totals ──────────────────────────────────────────────────────
    total_civil_jos = fields.Integer(
        compute='_compute_subdiv_kpis', string='Total Civil JOs')

    # ── Site Preparation ───────────────────────────────────────────────────
    sp_contract   = fields.Float(string='SP Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_executed   = fields.Float(string='SP Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_inprog     = fields.Float(string='SP In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_notstart   = fields.Float(string='SP Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_handover   = fields.Float(string='SP Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_inspection = fields.Float(string='SP Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_approved   = fields.Float(string='SP Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_claimed    = fields.Float(string='SP Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_invoiced   = fields.Float(string='SP Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_remaining  = fields.Float(string='SP Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    sp_variation  = fields.Float(string='SP Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── Excavation ─────────────────────────────────────────────────────────
    ex_contract   = fields.Float(string='EX Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_executed   = fields.Float(string='EX Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_inprog     = fields.Float(string='EX In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_notstart   = fields.Float(string='EX Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_handover   = fields.Float(string='EX Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_inspection = fields.Float(string='EX Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_approved   = fields.Float(string='EX Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_claimed    = fields.Float(string='EX Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_invoiced   = fields.Float(string='EX Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_remaining  = fields.Float(string='EX Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    ex_variation  = fields.Float(string='EX Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── Backfilling ────────────────────────────────────────────────────────
    bf_contract   = fields.Float(string='BF Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_executed   = fields.Float(string='BF Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_inprog     = fields.Float(string='BF In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_notstart   = fields.Float(string='BF Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_handover   = fields.Float(string='BF Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_inspection = fields.Float(string='BF Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_approved   = fields.Float(string='BF Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_claimed    = fields.Float(string='BF Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_invoiced   = fields.Float(string='BF Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_remaining  = fields.Float(string='BF Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    bf_variation  = fields.Float(string='BF Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── Concrete Works ─────────────────────────────────────────────────────
    cw_contract   = fields.Float(string='CW Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_executed   = fields.Float(string='CW Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_inprog     = fields.Float(string='CW In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_notstart   = fields.Float(string='CW Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_handover   = fields.Float(string='CW Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_inspection = fields.Float(string='CW Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_approved   = fields.Float(string='CW Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_claimed    = fields.Float(string='CW Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_invoiced   = fields.Float(string='CW Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_remaining  = fields.Float(string='CW Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    cw_variation  = fields.Float(string='CW Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── Block Work (Masonry) ───────────────────────────────────────────────
    bw_contract   = fields.Float(string='BW Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_executed   = fields.Float(string='BW Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_inprog     = fields.Float(string='BW In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_notstart   = fields.Float(string='BW Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_handover   = fields.Float(string='BW Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_inspection = fields.Float(string='BW Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_approved   = fields.Float(string='BW Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_claimed    = fields.Float(string='BW Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_invoiced   = fields.Float(string='BW Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_remaining  = fields.Float(string='BW Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    bw_variation  = fields.Float(string='BW Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── Waterproofing ──────────────────────────────────────────────────────
    wp_contract   = fields.Float(string='WP Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_executed   = fields.Float(string='WP Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_inprog     = fields.Float(string='WP In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_notstart   = fields.Float(string='WP Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_handover   = fields.Float(string='WP Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_inspection = fields.Float(string='WP Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_approved   = fields.Float(string='WP Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_claimed    = fields.Float(string='WP Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_invoiced   = fields.Float(string='WP Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_remaining  = fields.Float(string='WP Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    wp_variation  = fields.Float(string='WP Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── Road Works ─────────────────────────────────────────────────────────
    rw_contract   = fields.Float(string='RW Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_executed   = fields.Float(string='RW Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_inprog     = fields.Float(string='RW In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_notstart   = fields.Float(string='RW Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_handover   = fields.Float(string='RW Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_inspection = fields.Float(string='RW Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_approved   = fields.Float(string='RW Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_claimed    = fields.Float(string='RW Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_invoiced   = fields.Float(string='RW Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_remaining  = fields.Float(string='RW Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_variation  = fields.Float(string='RW Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── External Networks (Infrastructure) ────────────────────────────────
    en_contract   = fields.Float(string='EN Contract Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    en_executed   = fields.Float(string='EN Executed Qty',         compute='_compute_subdiv_kpis', digits=(16, 2))
    en_inprog     = fields.Float(string='EN In Progress',          compute='_compute_subdiv_kpis', digits=(16, 2))
    en_notstart   = fields.Float(string='EN Not Started',          compute='_compute_subdiv_kpis', digits=(16, 2))
    en_handover   = fields.Float(string='EN Handover Requested',   compute='_compute_subdiv_kpis', digits=(16, 2))
    en_inspection = fields.Float(string='EN Under Inspection',     compute='_compute_subdiv_kpis', digits=(16, 2))
    en_approved   = fields.Float(string='EN Approved',             compute='_compute_subdiv_kpis', digits=(16, 2))
    en_claimed    = fields.Float(string='EN Claimed',              compute='_compute_subdiv_kpis', digits=(16, 2))
    en_invoiced   = fields.Float(string='EN Invoiced',             compute='_compute_subdiv_kpis', digits=(16, 2))
    en_remaining  = fields.Float(string='EN Remaining',            compute='_compute_subdiv_kpis', digits=(16, 2))
    en_variation  = fields.Float(string='EN Variation',            compute='_compute_subdiv_kpis', digits=(16, 2))

    # ── Compute ────────────────────────────────────────────────────────────

    def _compute_subdiv_kpis(self):
        """
        2-query SQL approach, project-aware, division_id-scoped.

        Resolves 'Civil Works' division at runtime — NO department='civil' filter.
        All subdivision lookups are scoped by division_id so same-named
        subdivisions from other divisions are never mixed in.

        When rec.project_id is set:
          • JO query adds  AND project_id = <id>
          • BOQ query adds  JOIN farm_boq_analysis ba ... AND ba.project_id = <id>

        When rec.project_id is False (global view):
          • No project filter — shows all civil data.
        """
        cr      = self.env.cr
        SubDiv  = self.env['farm.subdivision.work']
        DivWork = self.env['farm.division.work']

        # -- Resolve Civil Works division once per compute call --------------
        civil_div    = DivWork.search([('name', '=ilike', 'Civil Works')], limit=1)
        civil_div_id = civil_div.id if civil_div else False

        # ── Build prefix → [subdivision_ids] map (shared across records) ───
        name_by_prefix = {
            'sp': 'Site Preparation',
            'ex': 'Excavation',
            'bf': 'Backfilling',
            'cw': 'Concrete Works',
            'bw': 'Block Work',
            'wp': 'Waterproofing',
            'rw': 'Road Works',
            'en': 'External Networks',
        }
        prefix_to_ids      = {}
        id_to_prefix       = {}
        all_ids            = []     # IDs for the spec'd subdivisions
        all_civil_subdiv_ids = []   # ALL IDs under Civil Works (for total count)

        if civil_div_id:
            all_civil_subdiv_ids = SubDiv.search(
                [('division_id', '=', civil_div_id)]).ids

            for prefix, name in name_by_prefix.items():
                ids = SubDiv.search([
                    ('name',       'ilike', name),
                    ('division_id', '=',   civil_div_id),
                ]).ids
                prefix_to_ids[prefix] = ids
                for sid in ids:
                    id_to_prefix[sid] = prefix
                all_ids.extend(ids)

        for rec in self:
            # ── Zero-initialise per-record accumulators ────────────────────
            acc = {
                pfx: {
                    'contract': 0.0, 'inprog': 0.0, 'total_exec': 0.0,
                    'handover': 0.0, 'inspection': 0.0,
                    'approved': 0.0, 'claimed':   0.0,
                    'invoiced': 0.0,
                }
                for pfx in name_by_prefix
            }

            pid = rec.project_id.id  # None when global view

            if all_ids:
                # ── Query 1: JO metrics (subdivision_id scope, no dept filter) ─
                if pid:
                    cr.execute("""
                        SELECT
                            subdivision_id,
                            COALESCE(SUM(planned_qty),  0),
                            COALESCE(SUM(CASE WHEN jo_stage = 'in_progress'
                                             THEN executed_qty ELSE 0 END), 0),
                            COALESCE(SUM(executed_qty), 0),
                            COALESCE(SUM(CASE WHEN jo_stage = 'handover_requested'
                                             THEN executed_qty ELSE 0 END), 0),
                            COALESCE(SUM(CASE WHEN jo_stage = 'under_inspection'
                                             THEN executed_qty ELSE 0 END), 0),
                            COALESCE(SUM(approved_qty), 0),
                            COALESCE(SUM(claimed_qty),  0)
                        FROM farm_job_order
                        WHERE business_activity = 'construction'
                          AND subdivision_id    = ANY(%s)
                          AND project_id        = %s
                        GROUP BY subdivision_id
                    """, (all_ids, pid))
                else:
                    cr.execute("""
                        SELECT
                            subdivision_id,
                            COALESCE(SUM(planned_qty),  0),
                            COALESCE(SUM(CASE WHEN jo_stage = 'in_progress'
                                             THEN executed_qty ELSE 0 END), 0),
                            COALESCE(SUM(executed_qty), 0),
                            COALESCE(SUM(CASE WHEN jo_stage = 'handover_requested'
                                             THEN executed_qty ELSE 0 END), 0),
                            COALESCE(SUM(CASE WHEN jo_stage = 'under_inspection'
                                             THEN executed_qty ELSE 0 END), 0),
                            COALESCE(SUM(approved_qty), 0),
                            COALESCE(SUM(claimed_qty),  0)
                        FROM farm_job_order
                        WHERE business_activity = 'construction'
                          AND subdivision_id    = ANY(%s)
                        GROUP BY subdivision_id
                    """, (all_ids,))

                for row in cr.fetchall():
                    sid, contract, inprog, total_exec, handover, inspection, approved, claimed = row
                    pfx = id_to_prefix.get(sid)
                    if pfx:
                        d = acc[pfx]
                        d['contract']   += contract
                        d['inprog']     += inprog
                        d['total_exec'] += total_exec
                        d['handover']   += handover
                        d['inspection'] += inspection
                        d['approved']   += approved
                        d['claimed']    += claimed

                # ── Query 2: Invoiced qty (project-filtered via BOQ analysis) ─
                if pid:
                    cr.execute("""
                        SELECT bl.subdivision_id,
                               COALESCE(SUM(al.lc_invoiced_qty), 0.0)
                        FROM farm_boq_analysis_line al
                        JOIN farm_boq_line     bl ON bl.id = al.boq_line_id
                        JOIN farm_boq_analysis ba ON ba.id = al.analysis_id
                        WHERE (al.display_type IS NULL OR al.display_type = '')
                          AND bl.subdivision_id = ANY(%s)
                          AND ba.project_id = %s
                        GROUP BY bl.subdivision_id
                    """, (all_ids, pid))
                else:
                    cr.execute("""
                        SELECT bl.subdivision_id,
                               COALESCE(SUM(al.lc_invoiced_qty), 0.0)
                        FROM farm_boq_analysis_line al
                        JOIN farm_boq_line bl ON bl.id = al.boq_line_id
                        WHERE (al.display_type IS NULL OR al.display_type = '')
                          AND bl.subdivision_id = ANY(%s)
                        GROUP BY bl.subdivision_id
                    """, (all_ids,))

                for sid, invoiced in cr.fetchall():
                    pfx = id_to_prefix.get(sid)
                    if pfx:
                        acc[pfx]['invoiced'] += invoiced

            # ── Total civil JOs — ALL subdivisions under Civil Works ───────
            if all_civil_subdiv_ids:
                if pid:
                    cr.execute("""
                        SELECT COUNT(*) FROM farm_job_order
                        WHERE business_activity = 'construction'
                          AND subdivision_id    = ANY(%s)
                          AND project_id        = %s
                    """, (all_civil_subdiv_ids, pid))
                else:
                    cr.execute("""
                        SELECT COUNT(*) FROM farm_job_order
                        WHERE business_activity = 'construction'
                          AND subdivision_id    = ANY(%s)
                    """, (all_civil_subdiv_ids,))
                total_jos = cr.fetchone()[0] or 0
            else:
                total_jos = 0

            # ── Assign to this record ──────────────────────────────────────
            rec.total_civil_jos = total_jos
            for pfx in ['sp', 'ex', 'bf', 'cw', 'bw', 'wp', 'rw', 'en']:
                d        = acc[pfx]
                contract = d['contract']
                invoiced = d['invoiced']
                approved = d['approved']
                setattr(rec, f'{pfx}_contract',   contract)
                setattr(rec, f'{pfx}_executed',   d['total_exec'])
                setattr(rec, f'{pfx}_inprog',     d['inprog'])
                setattr(rec, f'{pfx}_notstart',   max(0.0, contract - d['total_exec']))
                setattr(rec, f'{pfx}_handover',   d['handover'])
                setattr(rec, f'{pfx}_inspection', d['inspection'])
                setattr(rec, f'{pfx}_approved',   approved)
                setattr(rec, f'{pfx}_claimed',    d['claimed'])
                setattr(rec, f'{pfx}_invoiced',   invoiced)
                setattr(rec, f'{pfx}_remaining',  max(0.0, contract - invoiced))
                setattr(rec, f'{pfx}_variation',  approved - contract)

    # ── Drill-down actions ─────────────────────────────────────────────────

    def _civil_jo_action(self, name, subdiv_name=None):
        """Open civil job orders filtered by BOQ hierarchy (division_id), not department."""
        self.ensure_one()
        DivWork   = self.env['farm.division.work']
        SubDiv    = self.env['farm.subdivision.work']
        civil_div = DivWork.search([('name', '=ilike', 'Civil Works')], limit=1)
        div_id    = civil_div.id if civil_div else False

        if subdiv_name:
            subdiv_ids = SubDiv.search([
                ('name',       'ilike', subdiv_name),
                ('division_id', '=',   div_id),
            ]).ids if div_id else []
            domain = [('business_activity', '=', 'construction')]
            domain += ([('subdivision_id', 'in', subdiv_ids)]
                       if subdiv_ids else [('id', '=', False)])
        else:
            # All civil JOs: scope to all subdivision IDs under Civil Works
            all_ids = SubDiv.search(
                [('division_id', '=', div_id)]).ids if div_id else []
            domain = [('business_activity', '=', 'construction')]
            domain += ([('subdivision_id', 'in', all_ids)]
                       if all_ids else [('id', '=', False)])

        if self.project_id:
            domain += [('project_id', '=', self.project_id.id)]

        ctx = {'default_business_activity': 'construction'}
        if self.project_id:
            ctx['default_project_id'] = self.project_id.id

        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    domain,
            'context':   ctx,
        }

    def action_view_all_civil(self):
        return self._civil_jo_action('All Civil Job Orders')

    def action_view_site_prep(self):
        return self._civil_jo_action('Site Preparation — JOs', 'Site Preparation')

    def action_view_excavation(self):
        return self._civil_jo_action('Excavation — JOs', 'Excavation')

    def action_view_backfilling(self):
        return self._civil_jo_action('Backfilling — JOs', 'Backfilling')

    def action_view_concrete(self):
        return self._civil_jo_action('Concrete Works — JOs', 'Concrete Works')

    def action_view_masonry(self):
        return self._civil_jo_action('Masonry / Block Work — JOs', 'Block Work')

    def action_view_waterproofing(self):
        return self._civil_jo_action('Waterproofing — JOs', 'Waterproofing')

    def action_view_roads(self):
        return self._civil_jo_action('Roads & External Works — JOs', 'Road Works')

    def action_view_infrastructure(self):
        return self._civil_jo_action('Infrastructure Works — JOs', 'External Networks')

    # ── Back-navigation ────────────────────────────────────────────────────

    def action_back_to_project(self):
        """Return to the Level 2 Construction Project Dashboard."""
        self.ensure_one()
        if self.project_id:
            return (
                self.env['farm.construction.project.dashboard']
                .action_open_for_project(self.project_id.id)
            )
        # Fallback to portfolio when there is no project context
        return (
            self.env['farm.construction.projects.dashboard']
            .action_open_construction_projects_dashboard()
        )

    # ── Singleton openers ──────────────────────────────────────────────────

    @api.model
    def action_open_civil_dashboard(self):
        """Global (project-unfiltered) Civil Dashboard singleton."""
        rec = self.search([('project_id', '=', False)], limit=1)
        if not rec:
            rec = self.create({})
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Civil Dashboard'),
            'res_model': 'farm.civil.dashboard',
            'res_id':    rec.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }

    @api.model
    def action_open_for_project(self, project_id):
        """Find-or-create a project-specific Civil Dashboard and open it."""
        rec = self.search([('project_id', '=', project_id)], limit=1)
        if not rec:
            rec = self.create({'project_id': project_id})
        project_name = self.env['farm.project'].browse(project_id).name
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Civil — %s') % project_name,
            'res_model': 'farm.civil.dashboard',
            'res_id':    rec.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }
