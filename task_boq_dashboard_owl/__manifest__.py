{
    'name': 'Task BOQ Owl Dashboard',
    'version': '18.0.1.0.0',
    'summary': 'Owl KPI card dashboard for BOQ executive monitoring',
    'depends': ['web', 'project', 'mail', 'task_boq_dashboard'],
    'data': [
        'security/ir.model.access.csv',
        'views/client_action.xml',
        'views/menu.xml',
        'views/dashboard_mail_views.xml',
        'views/boq_dashboard_export_templates.xml',
        'views/boq_dashboard_export_actions.xml',
        'data/dashboard_mail_template.xml',
        'data/dashboard_mail_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'task_boq_dashboard_owl/static/src/js/boq_kpi_dashboard.js',
            'task_boq_dashboard_owl/static/src/xml/boq_kpi_dashboard.xml',
            'task_boq_dashboard_owl/static/src/scss/boq_kpi_dashboard.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
