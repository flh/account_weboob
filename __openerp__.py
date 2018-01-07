# -*- coding: utf-8 -*-

{
        'name': 'Weboob bank statements',
        'version' : '1',
        'category': 'Accounting & Finance',
        'description': 'Uses Weboob to import bank statements from online bank website.',
        'depends': ['base', 'account', 'account_bank_statement_import'],
        'data': ['weboob_import_view.xml',
            'security/ir.model.access.csv',
            ],
        'images': [],
        'demo': [],
        'application': False,
}
