"""
farm.activity.dashboard  —  Activity-specific Execution Dashboards
===================================================================

One singleton record per business_activity (construction / agriculture /
manufacturing / livestock).  All KPIs are non-stored computed fields that
aggregate live data from farm.job.order on every form read.

Financial driver rule is preserved:
  approved_qty is the ONLY quantity that generates revenue/progress.
"""
from odoo import api, fields, models, _
from datetime import date


class FarmActivityDashboard(models.Model):
    _name        = 'farm.activity.dashboard'
    _description = 'Activity-specific Execution Dashboard'
    _rec_name    = 'activity_label'
    _order       = 'business_activity'

    # ── Identity ──────────────────────────────────────────────────────────────

    business_activity = fields.Selection(
        selection=[
            ('construction',  'Construction'),
            ('agriculture',   'Agriculture'),
            ('manufacturing', 'Manufacturing / Packing'),
            ('livestock',     'Livestock'),
        ],
        string='Business Activity',
        required=True,
        index=True,
    )
    activity_label = fields.Char(compute='_compute_meta', string='Dashboard')
    activity_icon  = fields.Char(compute='_compute_meta')
    activity_theme = fields.Char(compute='_compute_meta')   # CSS suffix

    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency',
        string='Currency',
    )

    # ── Project-level KPIs ────────────────────────────────────────────────────

    project_count    = fields.Integer(compute='_compute_projects', string='Projects')
    project_running  = fields.Integer(compute='_compute_projects', string='Running Projects')
    project_draft    = fields.Integer(compute='_compute_projects', string='Draft Projects')

    # ── Common KPIs (all activities) ──────────────────────────────────────────

    total_jo_count         = fields.Integer(compute='_compute_common', string='Total Job Orders')
    total_planned_amount   = fields.Monetary(compute='_compute_common', currency_field='currency_id', string='Planned Value')
    total_approved_amount  = fields.Monetary(compute='_compute_common', currency_field='currency_id', string='Approved Amount')
    total_claimable_amount = fields.Monetary(compute='_compute_common', currency_field='currency_id', string='Claimable Amount')
    total_claimed_amount   = fields.Monetary(compute='_compute_common', currency_field='currency_id', string='Claimed Amount')
    outstanding_amount     = fields.Monetary(compute='_compute_common', currency_field='currency_id', string='Outstanding (Planned − Claimed)')
    execution_progress_pct = fields.Float(compute='_compute_common', digits=(16, 1), string='Execution Progress %')
    approved_pct           = fields.Float(compute='_compute_common', digits=(16, 1), string='Approved %')
    claim_completion_pct   = fields.Float(compute='_compute_common', digits=(16, 1), string='Claim Completion %')

    # ── Stage distribution ─────────────────────────────────────────────────────

    jo_count_draft            = fields.Integer(compute='_compute_stages', string='Draft')
    jo_count_approved         = fields.Integer(compute='_compute_stages', string='Approved')
    jo_count_in_progress      = fields.Integer(compute='_compute_stages', string='In Progress')
    jo_count_handover         = fields.Integer(compute='_compute_stages', string='Handover Req.')
    jo_count_under_inspection = fields.Integer(compute='_compute_stages', string='Under Inspection')
    jo_count_accepted         = fields.Integer(compute='_compute_stages', string='Accepted')
    jo_count_ready_for_claim  = fields.Integer(compute='_compute_stages', string='Ready for Claim')
    jo_count_claimed          = fields.Integer(compute='_compute_stages', string='Claimed')
    jo_count_closed           = fields.Integer(compute='_compute_stages', string='Closed')
    overdue_count             = fields.Integer(compute='_compute_stages', string='Overdue')

    # ── Construction-specific ─────────────────────────────────────────────────
    # Uses the same approved_qty driver; outstanding = planned − claimed

    con_total_items      = fields.Integer(compute='_compute_construction', string='Total BOQ Items')
    con_dept_civil       = fields.Integer(compute='_compute_construction', string='Civil')
    con_dept_structure   = fields.Integer(compute='_compute_construction', string='Structure')
    con_dept_arch        = fields.Integer(compute='_compute_construction', string='Architectural')
    con_dept_mechanical  = fields.Integer(compute='_compute_construction', string='Mechanical')
    con_dept_electrical  = fields.Integer(compute='_compute_construction', string='Electrical')

    # ── Agriculture-specific ──────────────────────────────────────────────────

    agri_total_harvest_qty     = fields.Float(compute='_compute_agriculture', digits=(16, 2), string='Total Harvest Qty')
    agri_total_net_harvest_qty = fields.Float(compute='_compute_agriculture', digits=(16, 2), string='Net Harvest Qty')
    agri_total_waste_qty       = fields.Float(compute='_compute_agriculture', digits=(16, 2), string='Total Waste Qty')
    agri_waste_pct             = fields.Float(compute='_compute_agriculture', digits=(16, 1), string='Waste %')
    agri_total_input_cost      = fields.Monetary(compute='_compute_agriculture', currency_field='currency_id', string='Total Input Cost')
    agri_harvest_approved_pct  = fields.Float(compute='_compute_agriculture', digits=(16, 1), string='Harvest Approved %')
    agri_count_planting        = fields.Integer(compute='_compute_agriculture', string='Planting JOs')
    agri_count_harvest         = fields.Integer(compute='_compute_agriculture', string='Harvest JOs')
    agri_count_irrigation      = fields.Integer(compute='_compute_agriculture', string='Irrigation JOs')

    # ── Manufacturing-specific ────────────────────────────────────────────────

    mfg_total_packed_qty     = fields.Float(compute='_compute_manufacturing', digits=(16, 2), string='Total Packed Qty')
    mfg_total_executed_qty   = fields.Float(compute='_compute_manufacturing', digits=(16, 2), string='Total Executed Qty')
    mfg_qc_pass_count        = fields.Integer(compute='_compute_manufacturing', string='QC Passed')
    mfg_qc_fail_count        = fields.Integer(compute='_compute_manufacturing', string='QC Failed')
    mfg_qc_conditional_count = fields.Integer(compute='_compute_manufacturing', string='QC Conditional')
    mfg_qc_pending_count     = fields.Integer(compute='_compute_manufacturing', string='QC Pending')
    mfg_qc_pass_pct          = fields.Float(compute='_compute_manufacturing', digits=(16, 1), string='QC Pass %')
    mfg_total_actual_cost    = fields.Monetary(compute='_compute_manufacturing', currency_field='currency_id', string='Total Actual Cost')
    mfg_efficiency_pct       = fields.Float(compute='_compute_manufacturing', digits=(16, 1), string='Efficiency % (Approved/Packed)')

    # ── Livestock-specific ────────────────────────────────────────────────────

    ls_total_animal_count      = fields.Integer(compute='_compute_livestock', string='Total Head Count')
    ls_total_births            = fields.Integer(compute='_compute_livestock', string='Total Births')
    ls_total_deaths            = fields.Integer(compute='_compute_livestock', string='Total Deaths')
    ls_mortality_pct           = fields.Float(compute='_compute_livestock', digits=(16, 1), string='Mortality %')
    ls_avg_live_weight         = fields.Float(compute='_compute_livestock', digits=(16, 2), string='Avg Live Weight (kg)')
    ls_total_approved_sale_qty = fields.Float(compute='_compute_livestock', digits=(16, 2), string='Approved Sale Qty (head)')
    ls_expected_revenue        = fields.Monetary(compute='_compute_livestock', currency_field='currency_id', string='Expected Revenue')
    ls_total_feed_cost         = fields.Monetary(compute='_compute_livestock', currency_field='currency_id', string='Feed Cost')
    ls_total_medical_cost      = fields.Monetary(compute='_compute_livestock', currency_field='currency_id', string='Medical / Vet Cost')
    ls_total_operating_cost    = fields.Monetary(compute='_compute_livestock', currency_field='currency_id', string='Total Operating Cost')
    ls_fattening_pct           = fields.Float(compute='_compute_livestock', digits=(16, 1), string='Fattening Progress % (Avg/Target)')
    ls_ready_for_sale_count    = fields.Integer(compute='_compute_livestock', string='Head Ready for Sale')

    # ────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────────────────────────────────────────

    def _jos(self, include_closed=False):
        """Return job orders for this dashboard's business_activity."""
        domain = [('business_activity', '=', self.business_activity)]
        if not include_closed:
            domain.append(('jo_stage', '!=', 'closed'))
        return self.env['farm.job.order'].search(domain)

    # ────────────────────────────────────────────────────────────────────────
    # Compute methods
    # ────────────────────────────────────────────────────────────────────────

    def _compute_currency(self):
        for rec in self:
            rec.currency_id = rec.env.company.currency_id

    def _compute_projects(self):
        """Count farm.project records for this activity."""
        for rec in self:
            projs = self.env['farm.project'].search(
                [('business_activity', '=', rec.business_activity)]
            )
            rec.project_count   = len(projs)
            rec.project_running = sum(1 for p in projs if p.state == 'running')
            rec.project_draft   = sum(1 for p in projs if p.state == 'draft')

    def _compute_meta(self):
        meta = {
            'construction': ('Construction Dashboard',  'fa-building',  'construction'),
            'agriculture':  ('Agriculture Dashboard',   'fa-leaf',      'agriculture'),
            'manufacturing': ('Manufacturing Dashboard', 'fa-industry',  'manufacturing'),
            'livestock':    ('Livestock Dashboard',     'fa-paw',       'livestock'),
        }
        for rec in self:
            label, icon, theme = meta.get(rec.business_activity, ('Dashboard', 'fa-tachometer', 'construction'))
            rec.activity_label = label
            rec.activity_icon  = icon
            rec.activity_theme = theme

    def _compute_common(self):
        for rec in self:
            jos = rec._jos()
            if not jos:
                rec.total_jo_count         = 0
                rec.total_planned_amount   = 0.0
                rec.total_approved_amount  = 0.0
                rec.total_claimable_amount = 0.0
                rec.total_claimed_amount   = 0.0
                rec.outstanding_amount     = 0.0
                rec.execution_progress_pct = 0.0
                rec.approved_pct           = 0.0
                rec.claim_completion_pct   = 0.0
                continue

            total_planned_qty  = sum(jos.mapped('planned_qty'))
            total_approved_qty = sum(jos.mapped('approved_qty'))
            planned_amt  = sum(j.planned_qty * j.unit_price for j in jos)
            approved_amt = sum(jos.mapped('approved_amount'))
            claimable    = sum(jos.mapped('claimable_amount'))
            claimed      = sum(jos.mapped('claim_amount'))

            rec.total_jo_count         = len(jos)
            rec.total_planned_amount   = planned_amt
            rec.total_approved_amount  = approved_amt
            rec.total_claimable_amount = claimable
            rec.total_claimed_amount   = claimed
            rec.outstanding_amount     = max(0.0, planned_amt - claimed)
            rec.execution_progress_pct = (
                total_approved_qty / total_planned_qty * 100.0
                if total_planned_qty else 0.0
            )
            rec.approved_pct = (
                approved_amt / planned_amt * 100.0
                if planned_amt else 0.0
            )
            rec.claim_completion_pct = (
                claimed / approved_amt * 100.0
                if approved_amt else 0.0
            )

    def _compute_stages(self):
        today = date.today()
        for rec in self:
            all_jos = rec._jos(include_closed=True)
            stage_counts = {}
            overdue = 0
            for jo in all_jos:
                stage_counts[jo.jo_stage] = stage_counts.get(jo.jo_stage, 0) + 1
                if (jo.planned_end_date and jo.planned_end_date < today
                        and jo.jo_stage not in ('claimed', 'closed')):
                    overdue += 1

            rec.jo_count_draft            = stage_counts.get('draft', 0)
            rec.jo_count_approved         = stage_counts.get('approved', 0)
            rec.jo_count_in_progress      = stage_counts.get('in_progress', 0)
            rec.jo_count_handover         = stage_counts.get('handover_requested', 0)
            rec.jo_count_under_inspection = stage_counts.get('under_inspection', 0)
            rec.jo_count_accepted         = stage_counts.get('accepted', 0) + stage_counts.get('partially_accepted', 0)
            rec.jo_count_ready_for_claim  = stage_counts.get('ready_for_claim', 0)
            rec.jo_count_claimed          = stage_counts.get('claimed', 0)
            rec.jo_count_closed           = stage_counts.get('closed', 0)
            rec.overdue_count             = overdue

    def _compute_construction(self):
        for rec in self:
            if rec.business_activity != 'construction':
                rec.con_total_items     = 0
                rec.con_dept_civil      = 0
                rec.con_dept_structure  = 0
                rec.con_dept_arch       = 0
                rec.con_dept_mechanical = 0
                rec.con_dept_electrical = 0
                continue
            jos = rec._jos()
            depts = {}
            for jo in jos:
                dept = jo.department or 'other'
                depts[dept] = depts.get(dept, 0) + 1
            rec.con_total_items     = len(jos)
            rec.con_dept_civil      = depts.get('civil', 0)
            rec.con_dept_structure  = depts.get('structure', 0)
            rec.con_dept_arch       = depts.get('arch', 0)
            rec.con_dept_mechanical = depts.get('mechanical', 0)
            rec.con_dept_electrical = depts.get('electrical', 0)

    def _compute_agriculture(self):
        for rec in self:
            if rec.business_activity != 'agriculture':
                rec.agri_total_harvest_qty     = 0.0
                rec.agri_total_net_harvest_qty = 0.0
                rec.agri_total_waste_qty       = 0.0
                rec.agri_waste_pct             = 0.0
                rec.agri_total_input_cost      = 0.0
                rec.agri_harvest_approved_pct  = 0.0
                rec.agri_count_planting        = 0
                rec.agri_count_harvest         = 0
                rec.agri_count_irrigation      = 0
                continue
            jos = rec._jos()
            harvest     = sum(jos.mapped('harvest_qty'))
            net_harvest = sum(jos.mapped('net_harvest_qty'))
            waste       = sum(jos.mapped('waste_qty'))
            approved_qty = sum(jos.mapped('approved_qty'))
            input_cost  = sum(jo.actual_material_cost + jo.actual_labour_cost for jo in jos)
            op_counts   = {}
            for jo in jos:
                op = jo.operation_type or 'other'
                op_counts[op] = op_counts.get(op, 0) + 1

            rec.agri_total_harvest_qty     = harvest
            rec.agri_total_net_harvest_qty = net_harvest
            rec.agri_total_waste_qty       = waste
            rec.agri_waste_pct             = (waste / harvest * 100.0) if harvest else 0.0
            rec.agri_total_input_cost      = input_cost
            rec.agri_harvest_approved_pct  = (approved_qty / harvest * 100.0) if harvest else 0.0
            rec.agri_count_planting        = op_counts.get('planting', 0)
            rec.agri_count_harvest         = op_counts.get('harvest', 0)
            rec.agri_count_irrigation      = op_counts.get('irrigation', 0)

    def _compute_manufacturing(self):
        for rec in self:
            if rec.business_activity != 'manufacturing':
                rec.mfg_total_packed_qty     = 0.0
                rec.mfg_total_executed_qty   = 0.0
                rec.mfg_qc_pass_count        = 0
                rec.mfg_qc_fail_count        = 0
                rec.mfg_qc_conditional_count = 0
                rec.mfg_qc_pending_count     = 0
                rec.mfg_qc_pass_pct          = 0.0
                rec.mfg_total_actual_cost    = 0.0
                rec.mfg_efficiency_pct       = 0.0
                continue
            jos = rec._jos()
            packed   = sum(jos.mapped('packed_qty'))
            executed = sum(jos.mapped('executed_qty'))
            approved = sum(jos.mapped('approved_qty'))
            cost     = sum(jos.mapped('actual_total_cost'))
            qc = {'passed': 0, 'failed': 0, 'conditional': 0, 'pending': 0}
            for jo in jos:
                r = jo.qc_result or 'pending'
                qc[r] = qc.get(r, 0) + 1

            rec.mfg_total_packed_qty     = packed
            rec.mfg_total_executed_qty   = executed
            rec.mfg_qc_pass_count        = qc['passed']
            rec.mfg_qc_fail_count        = qc['failed']
            rec.mfg_qc_conditional_count = qc['conditional']
            rec.mfg_qc_pending_count     = qc['pending']
            rec.mfg_qc_pass_pct          = (qc['passed'] / len(jos) * 100.0) if jos else 0.0
            rec.mfg_total_actual_cost    = cost
            rec.mfg_efficiency_pct       = (approved / packed * 100.0) if packed else 0.0

    def _compute_livestock(self):
        for rec in self:
            if rec.business_activity != 'livestock':
                rec.ls_total_animal_count      = 0
                rec.ls_total_births            = 0
                rec.ls_total_deaths            = 0
                rec.ls_mortality_pct           = 0.0
                rec.ls_avg_live_weight         = 0.0
                rec.ls_total_approved_sale_qty = 0.0
                rec.ls_expected_revenue        = 0.0
                rec.ls_total_feed_cost         = 0.0
                rec.ls_total_medical_cost      = 0.0
                rec.ls_total_operating_cost    = 0.0
                rec.ls_fattening_pct           = 0.0
                rec.ls_ready_for_sale_count    = 0
                continue
            jos = rec._jos()
            total_animals = sum(jos.mapped('animal_count'))
            births  = sum(jos.mapped('birth_count'))
            deaths  = sum(jos.mapped('death_count'))
            sale_qty = sum(jos.mapped('approved_sale_qty'))
            revenue  = sum(jos.mapped('approved_sale_amount'))
            feed     = sum(jos.mapped('feed_cost'))
            medical  = sum(jos.mapped('medical_cost'))
            caretaking = sum(jos.mapped('caretaking_cost'))

            # Avg live weight — only from JOs that have avg_weight set
            weight_jos = jos.filtered(lambda j: j.avg_weight > 0)
            avg_weight = (
                sum(weight_jos.mapped('avg_weight')) / len(weight_jos)
                if weight_jos else 0.0
            )

            # Fattening % — avg (avg_weight / target_weight) for JOs with target
            fat_jos = jos.filtered(lambda j: j.target_weight > 0)
            fat_pct = (
                sum(j.avg_weight / j.target_weight * 100.0 for j in fat_jos) / len(fat_jos)
                if fat_jos else 0.0
            )

            # Ready for sale = JOs in ready_for_claim or accepted stage
            ready_count = sum(
                j.animal_count for j in jos
                if j.jo_stage in ('ready_for_claim', 'accepted', 'partially_accepted')
            )

            rec.ls_total_animal_count      = total_animals
            rec.ls_total_births            = births
            rec.ls_total_deaths            = deaths
            rec.ls_mortality_pct           = (deaths / (total_animals + births) * 100.0) if (total_animals + births) else 0.0
            rec.ls_avg_live_weight         = avg_weight
            rec.ls_total_approved_sale_qty = sale_qty
            rec.ls_expected_revenue        = revenue
            rec.ls_total_feed_cost         = feed
            rec.ls_total_medical_cost      = medical
            rec.ls_total_operating_cost    = feed + medical + caretaking
            rec.ls_fattening_pct           = fat_pct
            rec.ls_ready_for_sale_count    = ready_count

    # ────────────────────────────────────────────────────────────────────────
    # Singleton opener actions (called from ir.actions.server)
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _open_activity_dashboard(self, activity):
        """Find-or-create singleton for the given activity and return a form action."""
        rec = self.search([('business_activity', '=', activity)], limit=1)
        if not rec:
            rec = self.create({'business_activity': activity})
        return {
            'type':      'ir.actions.act_window',
            'name':      dict(self._fields['business_activity'].selection).get(activity, activity),
            'res_model': 'farm.activity.dashboard',
            'res_id':    rec.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }

    @api.model
    def action_open_construction(self):
        return self._open_activity_dashboard('construction')

    @api.model
    def action_open_agriculture(self):
        return self._open_activity_dashboard('agriculture')

    @api.model
    def action_open_manufacturing(self):
        return self._open_activity_dashboard('manufacturing')

    @api.model
    def action_open_livestock(self):
        return self._open_activity_dashboard('livestock')

    # ── Refresh (re-opens same form, triggering fresh compute) ───────────────

    def action_refresh(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      self.activity_label,
            'res_model': 'farm.activity.dashboard',
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }

    # ── Drill-down actions ───────────────────────────────────────────────────

    def _jo_action(self, name, extra_domain=None):
        """Return a window action for job orders filtered by this activity."""
        self.ensure_one()
        domain = [('business_activity', '=', self.business_activity)]
        if extra_domain:
            domain += extra_domain
        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    domain,
            'context':   {'default_business_activity': self.business_activity},
        }

    def action_view_all_jos(self):
        return self._jo_action('All Job Orders — %s' % self.activity_label)

    def action_view_in_progress(self):
        return self._jo_action('In Progress', [('jo_stage', '=', 'in_progress')])

    def action_view_under_inspection(self):
        return self._jo_action('Under Inspection', [('jo_stage', '=', 'under_inspection')])

    def action_view_ready_for_claim(self):
        return self._jo_action('Ready for Claim', [('jo_stage', '=', 'ready_for_claim')])

    def action_view_claimable(self):
        return self._jo_action('Claimable JOs', [('claimable_qty', '>', 0)])

    def action_view_overdue(self):
        return self._jo_action('Overdue JOs', [
            ('planned_end_date', '<', fields.Date.today()),
            ('jo_stage', 'not in', ('claimed', 'closed')),
        ])

    # ── KPI strip drill-downs ────────────────────────────────────────────────

    def action_view_total_jos(self):
        return self._jo_action('All Job Orders', [('jo_stage', '!=', 'closed')])

    def action_view_planned_jos(self):
        return self._jo_action('Planned Job Orders', [('planned_qty', '>', 0)])

    def action_view_approved_jos(self):
        return self._jo_action('Approved Job Orders', [('approved_qty', '>', 0)])

    def action_view_claimed_jos(self):
        return self._jo_action('Claimed Job Orders', [('jo_stage', '=', 'claimed')])

    # ── Stage tile drill-downs ───────────────────────────────────────────────

    def action_view_stage_draft(self):
        return self._jo_action('Draft', [('jo_stage', '=', 'draft')])

    def action_view_stage_approved_state(self):
        return self._jo_action('Approved', [('jo_stage', '=', 'approved')])

    def action_view_stage_handover(self):
        return self._jo_action('Handover Requested', [('jo_stage', '=', 'handover_requested')])

    def action_view_stage_accepted(self):
        return self._jo_action('Accepted', [('jo_stage', 'in', ('accepted', 'partially_accepted'))])

    def action_view_stage_claimed_s(self):
        return self._jo_action('Claimed', [('jo_stage', '=', 'claimed')])

    def action_view_stage_closed(self):
        return self._jo_action('Closed', [('jo_stage', '=', 'closed')])

    # ── Construction drill-downs ─────────────────────────────────────────────

    def action_view_con_total(self):
        return self._jo_action('All Construction JOs')

    def action_view_dept_civil(self):
        return self._jo_action('Civil Department', [('department', '=', 'civil')])

    def action_view_dept_structure(self):
        return self._jo_action('Structure Department', [('department', '=', 'structure')])

    def action_view_dept_arch(self):
        return self._jo_action('Architectural Department', [('department', '=', 'arch')])

    def action_view_dept_mechanical(self):
        return self._jo_action('Mechanical Department', [('department', '=', 'mechanical')])

    def action_view_dept_electrical(self):
        return self._jo_action('Electrical Department', [('department', '=', 'electrical')])

    # ── Agriculture drill-downs ──────────────────────────────────────────────

    def action_view_agri_harvest_total(self):
        return self._jo_action('Harvest JOs (Total Harvest)', [('harvest_qty', '>', 0)])

    def action_view_agri_net_harvest(self):
        return self._jo_action('Net Harvest JOs', [('net_harvest_qty', '>', 0)])

    def action_view_agri_waste(self):
        return self._jo_action('Waste JOs', [('waste_qty', '>', 0)])

    def action_view_agri_planting(self):
        return self._jo_action('Planting Operations', [('operation_type', '=', 'planting')])

    def action_view_agri_harvest_op(self):
        return self._jo_action('Harvest Operations', [('operation_type', '=', 'harvest')])

    def action_view_agri_irrigation(self):
        return self._jo_action('Irrigation Operations', [('operation_type', '=', 'irrigation')])

    # ── Manufacturing drill-downs ────────────────────────────────────────────

    def action_view_mfg_total_qty(self):
        return self._jo_action('All Manufacturing JOs')

    def action_view_mfg_packed(self):
        return self._jo_action('Packed Qty JOs', [('packed_qty', '>', 0)])

    def action_view_mfg_qc_passed(self):
        return self._jo_action('QC Passed', [('qc_result', '=', 'passed')])

    def action_view_mfg_qc_failed(self):
        return self._jo_action('QC Failed', [('qc_result', '=', 'failed')])

    def action_view_mfg_qc_conditional(self):
        return self._jo_action('QC Conditional', [('qc_result', '=', 'conditional')])

    def action_view_mfg_qc_pending(self):
        return self._jo_action('QC Pending', [('qc_result', 'in', (False, 'pending'))])

    # ── Livestock drill-downs ────────────────────────────────────────────────

    def action_view_ls_herd_total(self):
        return self._jo_action('All Livestock JOs', [('animal_count', '>', 0)])

    def action_view_ls_births(self):
        return self._jo_action('Livestock — Births', [('birth_count', '>', 0)])

    def action_view_ls_deaths(self):
        return self._jo_action('Livestock — Deaths', [('death_count', '>', 0)])

    def action_view_ls_approved_sale(self):
        return self._jo_action('Approved for Sale', [('approved_sale_qty', '>', 0)])

    def action_view_ls_ready_for_sale(self):
        return self._jo_action('Ready for Sale', [
            ('jo_stage', 'in', ('ready_for_claim', 'accepted', 'partially_accepted')),
        ])

    def action_view_ls_costs(self):
        return self._jo_action('Livestock JOs with Costs', [
            '|', '|',
            ('feed_cost', '>', 0),
            ('medical_cost', '>', 0),
            ('caretaking_cost', '>', 0),
        ])

    # ── Project drill-downs ──────────────────────────────────────────────────

    def action_view_projects(self):
        """Open all farm.projects for this activity."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Projects — %s') % self.activity_label,
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain':    [('business_activity', '=', self.business_activity)],
            'context':   {'default_business_activity': self.business_activity},
        }

    def action_view_running_projects(self):
        """Open running farm.projects for this activity."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Running Projects — %s') % self.activity_label,
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain':    [
                ('business_activity', '=', self.business_activity),
                ('state', '=', 'running'),
            ],
            'context':   {'default_business_activity': self.business_activity},
        }
