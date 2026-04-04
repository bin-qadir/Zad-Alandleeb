# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class SmartFarmDashboardController(models.AbstractModel):
    """
    Server-side data provider for the Smart Farm Financial Performance Dashboard.
    All queries use read_group or mapped aggregations for performance.
    """
    _name = 'smart.farm.dashboard'
    _description = 'Smart Farm Dashboard Data Provider'

    @api.model
    def get_dashboard_data(self, filters=None):
        """
        Main RPC method called by the Owl dashboard component.
        Returns all KPIs, chart data, and filter options in a single call.

        Filters (all optional):
          project_ids : list of project.project ids
          date_from   : 'YYYY-MM-DD' string
          date_to     : 'YYYY-MM-DD' string
          stage_ids   : list of project.task.type ids
        """
        filters = filters or {}
        Task = self.env['project.task']

        # ── Build task domain from filters ────────────────────────────────────
        domain = []
        if filters.get('project_ids'):
            domain.append(('project_id', 'in', filters['project_ids']))
        if filters.get('stage_ids'):
            domain.append(('stage_id', 'in', filters['stage_ids']))
        if filters.get('date_from'):
            domain.append(('create_date', '>=', filters['date_from'] + ' 00:00:00'))
        if filters.get('date_to'):
            domain.append(('create_date', '<=', filters['date_to'] + ' 23:59:59'))

        # ── KPI aggregation via read_group (single DB query) ──────────────────
        cost_groups = Task.read_group(
            domain=domain,
            fields=[
                'material_cost:sum',
                'labor_cost:sum',
                'overhead_cost:sum',
                'total_cost:sum',
                'budget_amount:sum',
                'selling_price:sum',
                '__count',
            ],
            groupby=[],
        )
        agg = cost_groups[0] if cost_groups else {}

        total_material  = agg.get('material_cost',  0.0) or 0.0
        total_labor     = agg.get('labor_cost',     0.0) or 0.0
        total_overhead  = agg.get('overhead_cost',  0.0) or 0.0
        total_cost      = agg.get('total_cost',     0.0) or 0.0
        total_budget    = agg.get('budget_amount',  0.0) or 0.0
        total_selling   = agg.get('selling_price',  0.0) or 0.0
        task_count      = agg.get('__count',        0)   or 0

        # ── Sales: sum confirmed sale.order amounts linked via sale_order_ids ─
        tasks = Task.search(domain)
        so_ids = tasks.mapped('sale_order_ids').filtered(
            lambda so: so.state not in ('cancel',)
        )
        total_sales = sum(so_ids.mapped('amount_untaxed')) if so_ids else 0.0

        # ── Profit metrics ────────────────────────────────────────────────────
        total_profit   = total_sales - total_cost
        profit_margin  = (total_profit / total_sales * 100) if total_sales else 0.0

        # ── Over/Under budget task counts ─────────────────────────────────────
        # Efficient: get tasks with budget set
        budgeted_tasks = tasks.filtered(lambda t: t.budget_amount and t.budget_amount > 0)
        over_budget  = len(budgeted_tasks.filtered(lambda t: t.total_cost > t.budget_amount))
        under_budget = len(budgeted_tasks.filtered(lambda t: t.total_cost <= t.budget_amount))

        # ── Chart 1: Cost vs Sales per Project (bar chart) ────────────────────
        project_groups = Task.read_group(
            domain=domain,
            fields=['project_id', 'total_cost:sum', 'selling_price:sum', 'material_cost:sum', 'labor_cost:sum'],
            groupby=['project_id'],
            orderby='total_cost desc',
            limit=15,
        )
        bar_labels  = []
        bar_cost    = []
        bar_sales   = []
        project_task_map = {}  # project_id -> task ids for SO lookup

        for g in project_groups:
            proj = g.get('project_id')
            label = proj[1] if proj else _('No Project')
            bar_labels.append(label)
            bar_cost.append(round(g.get('total_cost', 0.0) or 0.0, 2))
            # Selling price from tasks (approximation; exact SO sum computed below)
            bar_sales.append(round(g.get('selling_price', 0.0) or 0.0, 2))

        # ── Chart 2: Cost breakdown pie (material/labor/overhead) ─────────────
        pie_data = []
        pie_labels = []
        pie_colors = []
        if total_material:
            pie_labels.append(_('Materials'))
            pie_data.append(round(total_material, 2))
            pie_colors.append('#16a34a')   # green-600
        if total_labor:
            pie_labels.append(_('Labor'))
            pie_data.append(round(total_labor, 2))
            pie_colors.append('#2563eb')   # blue-600
        if total_overhead:
            pie_labels.append(_('Overhead'))
            pie_data.append(round(total_overhead, 2))
            pie_colors.append('#d97706')   # amber-600

        # ── Chart 3: Cost over time (monthly line chart) ──────────────────────
        monthly_groups = Task.read_group(
            domain=domain,
            fields=['total_cost:sum', 'material_cost:sum', 'labor_cost:sum'],
            groupby=['create_date:month'],
            orderby='create_date asc',
        )
        line_labels      = []
        line_total_cost  = []
        line_mat_cost    = []
        line_lab_cost    = []
        for g in monthly_groups:
            line_labels.append(str(g.get('create_date:month', '')))
            line_total_cost.append(round(g.get('total_cost', 0.0) or 0.0, 2))
            line_mat_cost.append(round(g.get('material_cost', 0.0) or 0.0, 2))
            line_lab_cost.append(round(g.get('labor_cost', 0.0) or 0.0, 2))

        # ── Top tasks by cost (table) ─────────────────────────────────────────
        top_tasks_data = []
        top_tasks = tasks.sorted('total_cost', reverse=True)[:10]
        for t in top_tasks:
            top_tasks_data.append({
                'id':          t.id,
                'name':        t.name,
                'project':     t.project_id.name if t.project_id else '—',
                'stage':       t.stage_id.name if t.stage_id else '—',
                'total_cost':  round(t.total_cost, 2),
                'budget':      round(t.budget_amount, 2),
                'selling':     round(t.selling_price, 2),
                'over_budget': t.budget_amount > 0 and t.total_cost > t.budget_amount,
            })

        # ── Currency symbol ───────────────────────────────────────────────────
        company = self.env.company
        currency = company.currency_id
        currency_symbol = currency.symbol or currency.name

        return {
            # KPIs
            'kpi': {
                'total_cost':       round(total_cost, 2),
                'total_sales':      round(total_sales, 2),
                'total_profit':     round(total_profit, 2),
                'profit_margin':    round(profit_margin, 2),
                'task_count':       task_count,
                'over_budget':      over_budget,
                'under_budget':     under_budget,
                'total_material':   round(total_material, 2),
                'total_labor':      round(total_labor, 2),
                'total_overhead':   round(total_overhead, 2),
                'total_budget':     round(total_budget, 2),
            },
            # Charts
            'bar_chart': {
                'labels': bar_labels,
                'cost':   bar_cost,
                'sales':  bar_sales,
            },
            'pie_chart': {
                'labels': pie_labels,
                'data':   pie_data,
                'colors': pie_colors,
            },
            'line_chart': {
                'labels':     line_labels,
                'total_cost': line_total_cost,
                'material':   line_mat_cost,
                'labor':      line_lab_cost,
            },
            # Table
            'top_tasks': top_tasks_data,
            # Meta
            'currency_symbol': currency_symbol,
            'currency_position': currency.position,
        }

    @api.model
    def get_filter_options(self):
        """Return available filter choices for the dashboard dropdowns."""
        projects = self.env['project.project'].search_read(
            [], ['id', 'name'], order='name asc', limit=100
        )
        stages = self.env['project.task.type'].search_read(
            [], ['id', 'name'], order='sequence asc', limit=50
        )
        return {
            'projects': projects,
            'stages':   stages,
        }
