{
    'name': 'Smart Farm Division Pipeline',
    'version': '18.0.1.0.0',
    'summary': 'Division-level workflow pipeline engine: Pre-Execution → Execution → Control → Financial',
    'description': (
        'Transforms the construction system from a BOQ tracker into a '
        'division-driven workflow engine.\n\n'
        'Each division within a project gets its own pipeline record that '
        'tracks all Job Orders through four workflow stages:\n\n'
        '  Pre-Execution: Planning → Material Request → Procurement → Resources → Ready\n'
        '  Execution:     In Progress → Completed\n'
        '  Control:       Inspection → Approval\n'
        '  Financial:     Claim\n\n'
        'KPI cards show real-time progress percentages and counts aggregated '
        'from the underlying Job Orders, Material Requests, and Purchase Orders.\n\n'
        'Drill-down buttons open filtered Job Order lists for each phase.'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_execution',
        'smart_farm_work_structure',
        'smart_farm_material_request',
        'purchase',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/farm_division_pipeline_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_farm_division_pipeline/static/src/css/division_pipeline.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
