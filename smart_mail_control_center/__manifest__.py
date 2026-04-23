{
    'name': 'Smart Mail Control Center',
    'version': '18.0.2.0.0',
    'summary': 'Company email control center — classify, track, convert & follow up',
    'description': (
        'Full email management control center for Odoo:\n\n'
        '  • Automatic email classification by importance rules\n'
        '  • Per-user dashboard with workload KPIs\n'
        '  • Email-to-task conversion with follow-up tracking\n'
        '  • Full attachment storage in Odoo (ir.attachment)\n'
        '  • Escalation and state workflow\n'
        '  • Role-based visibility: user / manager / top management\n\n'
        'Syncs from Odoo mail.message (incoming + outgoing emails).\n'
        'Classifies by sender, domain, subject keywords, and attachment presence.\n\n'
        'Hooks into fetchmail.server so emails are captured in real-time after\n'
        'every IMAP/POP3 fetch cycle (every 2 minutes by default).\n\n'
        'Direct routing also supported: configure an incoming mail server to\n'
        'create new mail.tracker.record objects — all emails to that address\n'
        'become tracker records automatically via message_new().'
    ),
    'category': 'Productivity',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'project',
        'hr',
        'base',
        'account',
        'purchase',
        'smart_farm_execution',
        'smart_farm_boq',
        'smart_farm_contract',
        'smart_farm_material_request',
    ],
    'data': [
        'security/mail_tracker_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/mail_importance_rule_data.xml',
        'data/mail_tracker_role_rule_data.xml',
        'views/mail_tracker_record_views.xml',
        'views/mail_importance_rule_views.xml',
        'views/mail_tracker_role_rule_views.xml',
        'views/mail_tracker_dashboard_views.xml',
        'wizard/mail_tracker_convert_task_wizard_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_mail_control_center/static/src/css/mail_tracker.css',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
