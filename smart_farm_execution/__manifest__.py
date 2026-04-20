{
    'name': 'Smart Farm Execution',
    'version': '18.0.2.0.0',
    'summary': 'Execution layer: Job Orders → Materials + Labour → Progress → Actual Costs',
    'description': (
        'Transforms approved BOQ scope into real field execution:\n'
        'BOQ → BOQ Analysis (Approved) → Job Orders → Material Requests '
        '+ Labour Entries → Progress Logs → Actual Cost vs Planned.\n\n'
        'Models:\n'
        '- farm.job.order: execution record per approved BOQ subitem\n'
        '- farm.material.consumption: materials (planned/requested/issued/consumed)\n'
        '- farm.labour.entry: labour hours logged against job orders\n'
        '- farm.job.progress.log: incremental progress audit trail\n\n'
        'Security: Execution Manager / Execution User / Execution Viewer\n'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_project',
        'smart_farm_boq',
        'smart_farm_boq_analysis',
        'purchase',
        'stock',
        'hr_timesheet',
    ],
    'data': [
        'security/res.groups.xml',
        'security/ir.model.access.csv',
        'views/farm_job_order_views.xml',
        'views/farm_material_consumption_views.xml',
        'views/farm_labour_entry_views.xml',
        'views/farm_job_progress_log_views.xml',
        'views/farm_boq_analysis_execution_inherit.xml',
        'views/farm_project_views_inherit.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_farm_execution/static/src/css/execution_panel.css',
            'smart_farm_execution/static/src/js/execution_panel.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
