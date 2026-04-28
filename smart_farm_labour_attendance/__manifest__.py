{
    'name': 'Lavandula Field Labour Attendance',
    'version': '18.0.1.0.0',
    'summary': 'Daily field labour attendance: presence, GPS, signature, auto labour-entry creation',
    'description': 'Daily Labour Attendance - Track field worker presence per project, division, and BOQ item.',
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_execution',       # farm.job.order, farm.labour.entry, groups
        'smart_farm_work_structure',  # farm.division.work, farm.subdivision.work
        'hr',                         # hr.employee
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/farm_labour_attendance_views.xml',
        'views/farm_labour_attendance_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
