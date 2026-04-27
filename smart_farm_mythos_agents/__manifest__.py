{
    'name': 'Lavandula — Mythos AI Agents',
    'version': '18.0.1.0.0',
    'summary': 'Construction Mythos Agent Registry: classify, layer, and log all AI agents',
    'description': (
        'Defines the Construction Mythos Agent Registry:\n\n'
        'Layers:\n'
        '  1. Pre-Contract   — BOQ, Costing, Quotation\n'
        '  2. Contract       — Contract Agent\n'
        '  3. Execution      — Execution, Resources\n'
        '  4. Procurement    — Procurement Agent\n'
        '  5. Quality & Handover — Quality Inspection, Handover\n'
        '  6. Financial Claims   — Claims, Invoicing\n'
        '  7. Risk & Control     — Risk, Compliance\n'
        '  8. Executive Dashboard — Executive Summary\n\n'
        'Models:\n'
        '  - mythos.agent     : agent registry with layer + function classification\n'
        '  - mythos.agent.log : per-run audit log entries\n\n'
        'Safety:\n'
        '  - Default agents created once via noupdate="1" XML data\n'
        '  - Agent names are freely editable and never overwritten on upgrade\n'
        '  - Fully independent from smart_farm_super_agent\n'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_construction',   # construction menu root
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mythos_agent_views.xml',
        'views/mythos_agent_log_views.xml',
        'views/mythos_alert_views.xml',
        'views/menu.xml',
        'data/mythos_agent_data.xml',
        'data/mythos_basic_agents_data.xml',
        'data/mythos_basic_monitor_cron.xml',
        'data/mythos_step2_update_agents.xml',
        'data/mythos_step2_main_agents.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
