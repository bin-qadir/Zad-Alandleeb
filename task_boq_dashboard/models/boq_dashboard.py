from odoo import fields, models, tools


class BoqDashboardReport(models.Model):
    _name = 'boq.dashboard.report'
    _description = 'BOQ Executive Dashboard Report'
    _auto = False
    _order = 'project_id, task_id'

    company_id = fields.Many2one('res.company', readonly=True)
    project_id = fields.Many2one('project.project', readonly=True)
    task_id = fields.Many2one('project.task', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    stage_id = fields.Many2one('project.task.type', readonly=True)
    date_deadline = fields.Date(readonly=True)
    total_cost_planned = fields.Float(readonly=True)
    total_sale_planned = fields.Float(readonly=True)
    total_profit_planned = fields.Float(readonly=True)
    planned_margin_percent = fields.Float(readonly=True)
    total_cost_actual = fields.Float(readonly=True)
    total_profit_actual = fields.Float(readonly=True)
    actual_margin_percent = fields.Float(readonly=True)
    budget_variance = fields.Float(readonly=True)
    budget_variance_percent = fields.Float(readonly=True)
    stock_move_count = fields.Integer(readonly=True)
    purchase_count = fields.Integer(readonly=True)
    timesheet_count = fields.Integer(readonly=True)
    ai_alert_count = fields.Integer(readonly=True)
    is_over_budget = fields.Boolean(readonly=True)
    is_low_margin = fields.Boolean(readonly=True)
    is_delayed = fields.Boolean(readonly=True)
    x_month = fields.Char(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW boq_dashboard_report AS (
                SELECT
                    t.id AS id,
                    t.company_id,
                    t.project_id,
                    p.partner_id,
                    t.id AS task_id,
                    t.stage_id,
                    t.date_deadline,
                    COALESCE(t.total_cost_planned, 0) AS total_cost_planned,
                    COALESCE(t.total_sale_planned, 0) AS total_sale_planned,
                    COALESCE(t.total_profit_planned, 0) AS total_profit_planned,
                    COALESCE(t.planned_margin_percent, 0) AS planned_margin_percent,
                    COALESCE(t.total_cost_actual, 0) AS total_cost_actual,
                    COALESCE(t.total_profit_actual, 0) AS total_profit_actual,
                    COALESCE(t.actual_margin_percent, 0) AS actual_margin_percent,
                    COALESCE(t.budget_variance, 0) AS budget_variance,
                    COALESCE(t.budget_variance_percent, 0) AS budget_variance_percent,
                    COALESCE(t.stock_move_count, 0) AS stock_move_count,
                    COALESCE(t.purchase_count, 0) AS purchase_count,
                    COALESCE(t.timesheet_count, 0) AS timesheet_count,
                    COALESCE(t.ai_alert_count, 0) AS ai_alert_count,
                    CASE WHEN COALESCE(t.budget_variance, 0) > 0 THEN TRUE ELSE FALSE END AS is_over_budget,
                    CASE WHEN COALESCE(t.actual_margin_percent, 0) < 10 THEN TRUE ELSE FALSE END AS is_low_margin,
                    CASE WHEN t.date_deadline IS NOT NULL AND t.date_deadline < CURRENT_DATE THEN TRUE ELSE FALSE END AS is_delayed,
                    TO_CHAR(COALESCE(t.date_deadline, CURRENT_DATE), 'YYYY-MM') AS x_month
                FROM project_task t
                LEFT JOIN project_project p ON p.id = t.project_id
            )
        """)


class BoqDashboardKpi(models.Model):
    _name = 'boq.dashboard.kpi'
    _description = 'BOQ Dashboard KPI'
    _auto = False

    company_id = fields.Many2one('res.company', readonly=True)
    total_tasks = fields.Integer(readonly=True)
    total_projects = fields.Integer(readonly=True)
    total_cost_planned = fields.Float(readonly=True)
    total_cost_actual = fields.Float(readonly=True)
    total_sale_planned = fields.Float(readonly=True)
    total_profit_planned = fields.Float(readonly=True)
    total_profit_actual = fields.Float(readonly=True)
    avg_planned_margin = fields.Float(readonly=True)
    avg_actual_margin = fields.Float(readonly=True)
    over_budget_tasks = fields.Integer(readonly=True)
    delayed_tasks = fields.Integer(readonly=True)
    low_margin_tasks = fields.Integer(readonly=True)
    ai_alerts = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW boq_dashboard_kpi AS (
                SELECT row_number() over(order by t.company_id) as id,
                    t.company_id,
                    COUNT(t.id) as total_tasks,
                    COUNT(DISTINCT t.project_id) as total_projects,
                    COALESCE(SUM(t.total_cost_planned), 0) as total_cost_planned,
                    COALESCE(SUM(t.total_cost_actual), 0) as total_cost_actual,
                    COALESCE(SUM(t.total_sale_planned), 0) as total_sale_planned,
                    COALESCE(SUM(t.total_profit_planned), 0) as total_profit_planned,
                    COALESCE(SUM(t.total_profit_actual), 0) as total_profit_actual,
                    COALESCE(AVG(t.planned_margin_percent), 0) as avg_planned_margin,
                    COALESCE(AVG(t.actual_margin_percent), 0) as avg_actual_margin,
                    SUM(CASE WHEN COALESCE(t.budget_variance, 0) > 0 THEN 1 ELSE 0 END) as over_budget_tasks,
                    SUM(CASE WHEN t.date_deadline IS NOT NULL AND t.date_deadline < CURRENT_DATE THEN 1 ELSE 0 END) as delayed_tasks,
                    SUM(CASE WHEN COALESCE(t.actual_margin_percent, 0) < 10 THEN 1 ELSE 0 END) as low_margin_tasks,
                    COALESCE(SUM(t.ai_alert_count), 0) as ai_alerts
                FROM project_task t GROUP BY t.company_id
            )
        """)
