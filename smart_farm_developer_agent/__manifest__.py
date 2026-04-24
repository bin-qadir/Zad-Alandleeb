{
    'name': 'Smart Farm — Developer Agent',
    'version': '18.0.1.0.0',
    'summary': 'Mythos AI Developer Agent: scan code, review Studio views, generate Claude prompts',
    'description': (
        'Developer Agent for the Mythos AI registry.\n\n'
        'Features:\n'
        '  • Scan custom modules (Python, XML, security, manifests)\n'
        '  • Scan Studio customizations (ir.ui.view records)\n'
        '  • mythos.developer.task — reviewable task queue\n'
        '  • Generate structured Claude prompts for each task\n\n'
        'Safety:\n'
        '  • Read-only scans — no auto-write, no auto-modify\n'
        '  • Tasks are produced for human review before any action\n'
        '  • BOQ / Costing / Execution never touched without explicit approval\n'
    ),
    'category': 'Smart Farm',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_mythos_agents',  # mythos.agent registry + menus
        'base',
        'web',
        'project',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mythos_developer_task_views.xml',
        'views/menu.xml',
        'data/developer_agent_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
