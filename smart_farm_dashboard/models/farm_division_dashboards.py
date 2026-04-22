"""
Division Dashboards — Structure, Architectural, Mechanical, Electrical
======================================================================
Each follows the same architecture as farm.civil.dashboard:
  - Abstract mixin  (project_id field, back-nav, JO drill-down, find-or-create)
  - Concrete model  per department with explicit field declarations
  - SQL compute factory  builds _compute_subdiv_kpis per department
  - find-or-create per project_id

Level 2 (Construction Project Dashboard)
    ↓  click department card
Level 3  farm.structure.dashboard / farm.arch.dashboard /
         farm.mech.dashboard      / farm.elec.dashboard
"""
from odoo import api, fields, models, _


# ---------------------------------------------------------------------------
# Subdivision specs  (prefix, ilike-search name, FA icon, accent colour)
# ---------------------------------------------------------------------------

_STRUCT_SPECS = [
    ('fn', 'Foundations',       'fa fa-anchor',       '#1d4ed8'),
    ('ft', 'Footings',          'fa fa-compress',     '#0891b2'),
    ('co', 'Columns',           'fa fa-bars',         '#7c3aed'),
    ('bm', 'Beams',             'fa fa-minus',        '#0f766e'),
    ('sl', 'Slabs',             'fa fa-th',           '#374151'),
    ('st', 'Staircases',        'fa fa-level-up',     '#b45309'),
    ('rw', 'Retaining Walls',   'fa fa-shield',       '#be123c'),
    ('sf', 'Structural Frames', 'fa fa-object-group', '#064e3b'),
]

_ARCH_SPECS = [
    ('bk', 'Block Work',     'fa fa-th-large',    '#374151'),
    ('pl', 'Plaster',        'fa fa-paint-brush', '#0891b2'),
    ('pa', 'Paint',          'fa fa-tint',        '#7c3aed'),
    ('ti', 'Tiling',         'fa fa-th',          '#d97706'),
    ('ce', 'Ceiling',        'fa fa-arrows-v',    '#0f766e'),
    ('dw', 'Doors Windows',  'fa fa-columns',     '#1d4ed8'),
    ('cl', 'Cladding',       'fa fa-square-o',    '#be123c'),
    ('fi', 'Finishes',       'fa fa-star',        '#065f46'),
]

# 6 real BOQ main subdivisions under "Mechanical Works" division
_MECH_SPECS = [
    ('hs', 'HVAC Systems',          'fa fa-sun-o',              '#0891b2'),
    ('ff', 'Fire Fighting Systems', 'fa fa-fire',               '#be123c'),
    ('ws', 'Water Supply System',   'fa fa-tint',               '#1d4ed8'),
    ('ds', 'Drainage System',       'fa fa-arrow-down',         '#374151'),
    ('lg', 'LPG Systems',           'fa fa-fire-extinguisher',  '#b45309'),
    ('ew', 'Equipment Works',       'fa fa-cog',                '#7c3aed'),
]

_ELEC_SPECS = [
    ('pw', 'Power',                'fa fa-bolt',         '#b45309'),
    ('li', 'Lighting',             'fa fa-lightbulb-o',  '#d97706'),
    ('lc', 'Low Current',          'fa fa-signal',       '#0891b2'),
    ('ea', 'Earthing',             'fa fa-shield',       '#374151'),
    ('pn', 'Panels',               'fa fa-th-large',     '#1d4ed8'),
    ('ct', 'Cable Trays',          'fa fa-exchange',     '#7c3aed'),
    ('gn', 'Generators',           'fa fa-battery-full', '#0f766e'),
    ('ee', 'Electrical Equipment', 'fa fa-plug',         '#be123c'),
]


# ---------------------------------------------------------------------------
# Unified compute factory — division_id-based, NO department filter
# ---------------------------------------------------------------------------
# All five construction division dashboards (Civil, Structure, Architectural,
# Mechanical, Electrical) use this single factory.  Subdivision lookup is
# scoped by division_id so same-named subdivisions in other divisions are
# never mixed up.  The total-JO count covers ALL subdivisions under the
# division, not just the ones that appear in subdiv_specs.

def _make_division_kpi_compute(division_name, subdiv_specs, total_field):
    """Return a _compute_subdiv_kpis method scoped by farm.division.work name.

    Args:
        division_name: Exact name of the farm.division.work record
                       (e.g. 'Civil Works', 'Structural Works', …).
        subdiv_specs:  List of (prefix, name_fragment, icon, colour) tuples.
        total_field:   Name of the Integer field that stores the total JO count.
    """
    name_by_prefix = {s[0]: s[1] for s in subdiv_specs}

    def _compute_subdiv_kpis(self):
        cr      = self.env.cr
        SubDiv  = self.env['farm.subdivision.work']
        DivWork = self.env['farm.division.work']

        # -- resolve division by name once per compute call ------------------
        div    = DivWork.search([('name', '=ilike', division_name)], limit=1)
        div_id = div.id if div else False

        prefix_to_ids      = {}
        id_to_prefix       = {}
        all_ids            = []          # IDs for the spec'd subdivisions
        all_div_subdiv_ids = []          # ALL subdivision IDs under this division

        if div_id:
            all_div_subdiv_ids = SubDiv.search(
                [('division_id', '=', div_id)]).ids

            for pfx, name in name_by_prefix.items():
                ids = SubDiv.search([
                    ('name',       'ilike', name),
                    ('division_id', '=',   div_id),
                ]).ids
                prefix_to_ids[pfx] = ids
                for sid in ids:
                    id_to_prefix[sid] = pfx
                all_ids.extend(ids)

        for rec in self:
            acc = {
                pfx: dict(contract=0.0, inprog=0.0, total_exec=0.0,
                           handover=0.0, inspection=0.0,
                           approved=0.0, claimed=0.0, invoiced=0.0)
                for pfx in name_by_prefix
            }
            pid = rec.project_id.id

            if all_ids:
                # ── Q1: JO metrics — subdivision_id scope only ────────────
                if pid:
                    cr.execute("""
                        SELECT subdivision_id,
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
                        SELECT subdivision_id,
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
                    sid, ctr, inp, tex, hov, ins, apv, clm = row
                    pfx = id_to_prefix.get(sid)
                    if pfx:
                        d = acc[pfx]
                        d['contract']   += ctr
                        d['inprog']     += inp
                        d['total_exec'] += tex
                        d['handover']   += hov
                        d['inspection'] += ins
                        d['approved']   += apv
                        d['claimed']    += clm

                # ── Q2: Invoiced qty via BOQ analysis ─────────────────────
                if pid:
                    cr.execute("""
                        SELECT bl.subdivision_id,
                               COALESCE(SUM(al.lc_invoiced_qty), 0.0)
                        FROM farm_boq_analysis_line al
                        JOIN farm_boq_line     bl ON bl.id = al.boq_line_id
                        JOIN farm_boq_analysis ba ON ba.id = al.analysis_id
                        WHERE (al.display_type IS NULL OR al.display_type = '')
                          AND bl.subdivision_id = ANY(%s)
                          AND ba.project_id     = %s
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

                for sid, inv in cr.fetchall():
                    pfx = id_to_prefix.get(sid)
                    if pfx:
                        acc[pfx]['invoiced'] += inv

            # ── Total JO count — ALL subdivisions under this division ─────
            if all_div_subdiv_ids:
                if pid:
                    cr.execute("""
                        SELECT COUNT(*) FROM farm_job_order
                        WHERE business_activity = 'construction'
                          AND subdivision_id    = ANY(%s)
                          AND project_id        = %s
                    """, (all_div_subdiv_ids, pid))
                else:
                    cr.execute("""
                        SELECT COUNT(*) FROM farm_job_order
                        WHERE business_activity = 'construction'
                          AND subdivision_id    = ANY(%s)
                    """, (all_div_subdiv_ids,))
                setattr(rec, total_field, cr.fetchone()[0] or 0)
            else:
                setattr(rec, total_field, 0)

            for pfx in name_by_prefix:
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

    return _compute_subdiv_kpis


# ---------------------------------------------------------------------------
# Abstract mixin — project_id, navigation, JO drill-down, opener
# ---------------------------------------------------------------------------

class FarmDivisionDashboardMixin(models.AbstractModel):
    _name        = 'farm.division.dashboard.mixin'
    _description = 'Division Dashboard Mixin'

    _DEPT_CODE     = ''   # Kept for backwards compat; no longer used in SQL
    _DEPT_LABEL    = ''   # Override in subclass: 'Structure', 'Architectural', etc.
    _DIVISION_NAME = ''   # Override: exact farm.division.work name, e.g. 'Structural Works'

    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        ondelete='cascade',
        index=True,
        help='When set, all metrics are filtered to this project only.',
    )

    def _dept_jo_action(self, label, subdiv_name=None):
        """Open job orders filtered to this division + optional subdivision + project.

        Uses BOQ-hierarchy (division_id / subdivision_id) — NOT the department
        selection field, which is orthogonal to the BOQ structure.
        """
        self.ensure_one()
        DivWork = self.env['farm.division.work']
        SubDiv  = self.env['farm.subdivision.work']

        div = DivWork.search(
            [('name', '=ilike', self._DIVISION_NAME)], limit=1)
        div_id = div.id if div else False

        if subdiv_name:
            # Specific subdivision: scope search by division_id
            subdiv_ids = SubDiv.search([
                ('name',       'ilike', subdiv_name),
                ('division_id', '=',   div_id),
            ]).ids if div_id else []
            domain = [('business_activity', '=', 'construction')]
            domain += ([('subdivision_id', 'in', subdiv_ids)]
                       if subdiv_ids else [('id', '=', False)])
        else:
            # All JOs for this division: use ALL subdivision IDs
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
            'name':      _(label),
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    domain,
            'context':   ctx,
        }

    def action_back_to_project(self):
        self.ensure_one()
        if self.project_id:
            return (
                self.env['farm.construction.project.dashboard']
                .action_open_for_project(self.project_id.id)
            )
        return (
            self.env['farm.construction.projects.dashboard']
            .action_open_construction_projects_dashboard()
        )

    @api.model
    def action_open_for_project(self, project_id):
        rec = self.search([('project_id', '=', project_id)], limit=1)
        if not rec:
            rec = self.create({'project_id': project_id})
        project_name = self.env['farm.project'].browse(project_id).name
        return {
            'type':      'ir.actions.act_window',
            'name':      _('%s \u2014 %s') % (self._DEPT_LABEL, project_name),
            'res_model': self._name,
            'res_id':    rec.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }


# ===========================================================================
# STRUCTURE DASHBOARD
# ===========================================================================

class FarmStructureDashboard(models.Model):
    _name        = 'farm.structure.dashboard'
    _description = 'Structure Division Dashboard'
    _inherit     = ['farm.division.dashboard.mixin']
    _rec_name    = 'id'

    _DEPT_CODE     = 'structure'
    _DEPT_LABEL    = 'Structure'
    _DIVISION_NAME = 'Structural Works'

    total_structure_jos = fields.Integer(compute='_compute_subdiv_kpis', string='Total Structure JOs')

    # Foundations
    fn_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fn_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Footings
    ft_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ft_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Columns
    co_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    co_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Beams
    bm_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bm_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Slabs
    sl_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sl_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Staircases
    st_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    st_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Retaining Walls
    rw_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    rw_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Structural Frames
    sf_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    sf_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))

    _compute_subdiv_kpis = _make_division_kpi_compute('Structural Works', _STRUCT_SPECS, 'total_structure_jos')

    def action_view_all_structure(self):
        return self._dept_jo_action('All Structure Job Orders')

    def action_view_foundations(self):
        return self._dept_jo_action('Foundations — JOs', 'Foundations')

    def action_view_footings(self):
        return self._dept_jo_action('Footings — JOs', 'Footings')

    def action_view_columns(self):
        return self._dept_jo_action('Columns — JOs', 'Columns')

    def action_view_beams(self):
        return self._dept_jo_action('Beams — JOs', 'Beams')

    def action_view_slabs(self):
        return self._dept_jo_action('Slabs — JOs', 'Slabs')

    def action_view_staircases(self):
        return self._dept_jo_action('Staircases — JOs', 'Staircases')

    def action_view_retaining_walls(self):
        return self._dept_jo_action('Retaining Walls — JOs', 'Retaining Walls')

    def action_view_structural_frames(self):
        return self._dept_jo_action('Structural Frames — JOs', 'Structural Frames')


# ===========================================================================
# ARCHITECTURAL DASHBOARD
# ===========================================================================

class FarmArchDashboard(models.Model):
    _name        = 'farm.arch.dashboard'
    _description = 'Architectural Division Dashboard'
    _inherit     = ['farm.division.dashboard.mixin']
    _rec_name    = 'id'

    _DEPT_CODE     = 'arch'
    _DEPT_LABEL    = 'Architectural'
    _DIVISION_NAME = 'Architectural Works'

    total_arch_jos = fields.Integer(compute='_compute_subdiv_kpis', string='Total Architectural JOs')

    # Block Work
    bk_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    bk_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Plaster
    pl_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pl_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Paint
    pa_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pa_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Tiling
    ti_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ti_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Ceiling
    ce_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ce_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Doors & Windows
    dw_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    dw_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Cladding
    cl_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    cl_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Finishes
    fi_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    fi_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))

    _compute_subdiv_kpis = _make_division_kpi_compute('Architectural Works', _ARCH_SPECS, 'total_arch_jos')

    def action_view_all_arch(self):
        return self._dept_jo_action('All Architectural Job Orders')

    def action_view_block_work(self):
        return self._dept_jo_action('Block Work — JOs', 'Block Work')

    def action_view_plaster(self):
        return self._dept_jo_action('Plaster — JOs', 'Plaster')

    def action_view_paint(self):
        return self._dept_jo_action('Paint — JOs', 'Paint')

    def action_view_tiling(self):
        return self._dept_jo_action('Tiling — JOs', 'Tiling')

    def action_view_ceiling(self):
        return self._dept_jo_action('Ceiling — JOs', 'Ceiling')

    def action_view_doors_windows(self):
        return self._dept_jo_action('Doors & Windows — JOs', 'Doors Windows')

    def action_view_cladding(self):
        return self._dept_jo_action('Cladding — JOs', 'Cladding')

    def action_view_finishes(self):
        return self._dept_jo_action('Finishes — JOs', 'Finishes')


# ===========================================================================
# MECHANICAL DASHBOARD
# ===========================================================================

class FarmMechDashboard(models.Model):
    _name        = 'farm.mech.dashboard'
    _description = 'Mechanical Division Dashboard'
    _inherit     = ['farm.division.dashboard.mixin']
    _rec_name    = 'id'

    _DEPT_CODE     = 'mechanical'
    _DEPT_LABEL    = 'Mechanical'
    _DIVISION_NAME = 'Mechanical Works'

    total_mech_jos = fields.Integer(compute='_compute_subdiv_kpis', string='Total Mechanical JOs')

    # HVAC Systems (id=20)
    hs_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    hs_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Fire Fighting Systems (id=24)
    ff_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ff_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Water Supply System (id=56)
    ws_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ws_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Drainage System (id=57)
    ds_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ds_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # LPG Systems (id=25)
    lg_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lg_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Equipment Works — Pumps (id=26)
    ew_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ew_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))

    _compute_subdiv_kpis = _make_division_kpi_compute('Mechanical Works', _MECH_SPECS, 'total_mech_jos')

    def action_view_all_mech(self):
        return self._dept_jo_action('All Mechanical Job Orders')

    def action_view_hvac_systems(self):
        return self._dept_jo_action('HVAC Systems — JOs', 'HVAC Systems')

    def action_view_fire_fighting_systems(self):
        return self._dept_jo_action('Fire Fighting Systems — JOs', 'Fire Fighting Systems')

    def action_view_water_supply(self):
        return self._dept_jo_action('Water Supply System — JOs', 'Water Supply System')

    def action_view_drainage_system(self):
        return self._dept_jo_action('Drainage System — JOs', 'Drainage System')

    def action_view_lpg_systems(self):
        return self._dept_jo_action('LPG Systems — JOs', 'LPG Systems')

    def action_view_equipment_works(self):
        return self._dept_jo_action('Equipment Works (Pumps) — JOs', 'Equipment Works')


# ===========================================================================
# ELECTRICAL DASHBOARD
# ===========================================================================

class FarmElecDashboard(models.Model):
    _name        = 'farm.elec.dashboard'
    _description = 'Electrical Division Dashboard'
    _inherit     = ['farm.division.dashboard.mixin']
    _rec_name    = 'id'

    _DEPT_CODE     = 'electrical'
    _DEPT_LABEL    = 'Electrical'
    _DIVISION_NAME = 'Electrical Works'

    total_elec_jos = fields.Integer(compute='_compute_subdiv_kpis', string='Total Electrical JOs')

    # Power
    pw_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pw_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Lighting
    li_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    li_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Low Current
    lc_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    lc_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Earthing
    ea_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ea_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Panels
    pn_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    pn_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Cable Trays
    ct_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ct_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Generators
    gn_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    gn_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    # Electrical Equipment
    ee_contract   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_executed   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_inprog     = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_notstart   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_handover   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_inspection = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_approved   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_claimed    = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_invoiced   = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_remaining  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))
    ee_variation  = fields.Float(compute='_compute_subdiv_kpis', digits=(16, 2))

    _compute_subdiv_kpis = _make_division_kpi_compute('Electrical Works', _ELEC_SPECS, 'total_elec_jos')

    def action_view_all_elec(self):
        return self._dept_jo_action('All Electrical Job Orders')

    def action_view_power(self):
        return self._dept_jo_action('Power — JOs', 'Power')

    def action_view_lighting(self):
        return self._dept_jo_action('Lighting — JOs', 'Lighting')

    def action_view_low_current(self):
        return self._dept_jo_action('Low Current — JOs', 'Low Current')

    def action_view_earthing(self):
        return self._dept_jo_action('Earthing — JOs', 'Earthing')

    def action_view_panels(self):
        return self._dept_jo_action('Panels — JOs', 'Panels')

    def action_view_cable_trays(self):
        return self._dept_jo_action('Cable Trays — JOs', 'Cable Trays')

    def action_view_generators(self):
        return self._dept_jo_action('Generators — JOs', 'Generators')

    def action_view_electrical_equipment(self):
        return self._dept_jo_action('Electrical Equipment — JOs', 'Electrical Equipment')
