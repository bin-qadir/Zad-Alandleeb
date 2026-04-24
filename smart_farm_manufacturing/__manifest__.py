{
    'name': 'Smart Farm — Manufacturing',
    'version': '18.0.2.0.0',
    'summary': 'Manufacturing activity — filtered mirror of Smart Farm engine',
    'description': (
        'Standalone application for the Manufacturing / Packing business activity.\n\n'
        'This module is a FILTERED MIRROR of the Smart Farm engine.\n'
        'NO separate models. NO duplicate logic.\n\n'
        'All records shown here are farm.project / farm.boq / farm.job.order\n'
        'records with business_activity = "manufacturing".\n\n'
        'Menu: Dashboard · Projects · Divisions · Subdivisions · BOQ · '
        'Material · Procurement · Execution · Inspection · Approval · Claims · Invoices'
    ),
    'category': 'Smart Farm/Manufacturing',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_material_request',   # full Smart Farm engine chain
        'smart_farm_work_structure',     # Divisions / Subdivisions reference data
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/actions.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
