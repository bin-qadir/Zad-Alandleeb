{
    'name': 'Smart Farm Contract',
    'version': '18.0.1.0.0',
    'summary': 'Contract layer between BOQ Analysis and Job Order execution',
    'description': (
        'Introduces the Farm Contract model and enforces a contract-approval gate '
        'before Job Orders can be generated.\n\n'
        'Flow:\n'
        '  BOQ Analysis (approved) → Contract (approved/active) → Job Orders\n\n'
        'Also adds a project-lifecycle phase progression:\n'
        '  Pre-Tender → Tender → Contract → Execution\n\n'
        'Models:\n'
        '  farm.contract  — contract header with workflow (draft→review→approved→active→closed)\n'
        'Extensions:\n'
        '  farm.project   — project_phase Selection + contract stat button\n'
        '  farm.job.order — contract_id link\n'
        '  farm.boq.analysis — generate_job_orders() contract gate\n'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_boq_analysis',
        'smart_farm_execution',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/farm_contract_views.xml',
        'views/farm_project_views_inherit.xml',
        'views/farm_job_order_views_inherit.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
