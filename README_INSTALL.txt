Task BOQ Advanced for Odoo 18

Notes:
1) This module is built for Odoo 18 structure and uses <list> views.
2) If your database uses different XML IDs for task/project forms, adjust:
   - project.view_task_form2
   - project.edit_project
3) Record rules assume project.task has user_ids.
   If your database uses user_id instead, update security/security.xml.
4) Copy the folder `task_boq_advanced` into your custom addons path, update Apps List, then install.
