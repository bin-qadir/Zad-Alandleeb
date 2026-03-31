from odoo import api, fields, models, _


class AiControllerRule(models.Model):
    _name = 'ai.controller.rule'
    _description = 'AI Controller Rule'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    rule_type = fields.Selection([('budget_overrun', 'Budget Overrun'), ('low_margin', 'Low Margin'), ('delayed_task', 'Delayed Task'), ('material_shortage', 'Material Shortage')], required=True)
    threshold_percent = fields.Float()
    threshold_days = fields.Integer()
    alert_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='medium')
    action_type = fields.Selection([('alert_only', 'Alert Only'), ('schedule_activity', 'Schedule Activity'), ('create_rfq', 'Create RFQ')], default='alert_only')
    responsible_user_id = fields.Many2one('res.users')


class AiControllerAlert(models.Model):
    _name = 'ai.controller.alert'
    _description = 'AI Controller Alert'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(required=True)
    task_id = fields.Many2one('project.task', index=True)
    project_id = fields.Many2one(related='task_id.project_id', store=True)
    boq_line_id = fields.Many2one('project.task.boq.line')
    rule_id = fields.Many2one('ai.controller.rule')
    level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='medium', tracking=True)
    status = fields.Selection([('open', 'Open'), ('in_progress', 'In Progress'), ('closed', 'Closed')], default='open', tracking=True)
    summary = fields.Text()
    suggested_action = fields.Text()
    action_executed = fields.Boolean(default=False)


class ProjectTaskAiMixin(models.Model):
    _inherit = 'project.task'

    def ai_run_rules(self):
        rules = self.env['ai.controller.rule'].search([('active', '=', True)])
        Alert = self.env['ai.controller.alert']
        for task in self:
            for rule in rules:
                if rule.rule_type == 'budget_overrun' and task.budget_variance_percent > rule.threshold_percent:
                    Alert.create({'name': _('Budget overrun on %s') % task.display_name, 'task_id': task.id, 'rule_id': rule.id, 'level': rule.alert_level, 'summary': _('Actual cost exceeded planned cost by %.2f%%') % task.budget_variance_percent, 'suggested_action': _('Review material issue, labor consumption, and unplanned overhead.')})
                elif rule.rule_type == 'low_margin' and task.actual_margin_percent < rule.threshold_percent:
                    Alert.create({'name': _('Low margin on %s') % task.display_name, 'task_id': task.id, 'rule_id': rule.id, 'level': rule.alert_level, 'summary': _('Actual margin dropped to %.2f%%') % task.actual_margin_percent, 'suggested_action': _('Review pricing, procurement rates, and labor efficiency.')})
                elif rule.rule_type == 'delayed_task' and task.date_deadline:
                    days = (fields.Date.today() - task.date_deadline).days if fields.Date.today() > task.date_deadline else 0
                    if days > rule.threshold_days:
                        Alert.create({'name': _('Delayed task %s') % task.display_name, 'task_id': task.id, 'rule_id': rule.id, 'level': rule.alert_level, 'summary': _('Task delayed by %s days') % days, 'suggested_action': _('Escalate and re-plan resources.')})
            for line in task.boq_line_ids.filtered(lambda l: l.section_type == 'material'):
                shortage_rules = rules.filtered(lambda r: r.rule_type == 'material_shortage')
                for rule in shortage_rules:
                    if line.qty_to_procure > 0:
                        Alert.create({'name': _('Material shortage on %s') % task.display_name, 'task_id': task.id, 'boq_line_id': line.id, 'rule_id': rule.id, 'level': rule.alert_level, 'summary': _('Line %s still needs %.2f units') % (line.description, line.qty_to_procure), 'suggested_action': _('Create RFQ or reserve stock.')})
        return True


class AiControllerCron(models.AbstractModel):
    _name = 'ai.controller.cron'
    _description = 'AI Controller Scheduler'

    @api.model
    def cron_run_ai_controller(self):
        self.env['project.task'].search([]).ai_run_rules()
        return True
