# -*- coding: utf-8 -*-

from openerp import api, models, fields
from weboob.core import Weboob
from weboob.capabilities.bank import CapBank
import datetime

class WeboobBankAccount(models.Model):
    _name = 'weboob.bank.account'
    _description = 'External Weboob Bank Account'
    _order = 'weboob_name'
    _rec_name = 'weboob_name'

    weboob_name = fields.Char(string="Weboob Identifier", required=True)
    journal_id = fields.Many2one('account.journal', string="Journal")
    latest_unique_id = fields.Char(string="Last Unique Id",
            required=False, readonly=True)
    state = fields.Selection([
        ('active', 'Active'),
        ('not_found', 'Not found in Weboob'),
        ('inactive', 'Inactive'),
        ], 'Status', readonly=True,
        default=lambda self: 'active')

    @api.multi
    def is_active(self, strict=False):
        """
        Tells whether an account should be considered for import
        according to its recorded state. The account is valid when its
        state is 'active', or when its state is 'not_found' (meaning
        that no corresponding Weboob account was found in a previous
        run).

        The optional 'strict' parameter should be set to True if one
        wants to exclude 'not_found' accounts (defaults to False).
        """
        return all(self.mapped(lambda acc: acc.state == 'active' or
            (not strict and acc.state == 'not_found')))

    @api.multi
    def run_imports(self):
        w = Weboob()
        w.load_backends(CapBank)

        # Build the list of all Weboob-known accounts.
        # The result is a dictionary mapping identifiers of the form
        # weboob_id@weboob_backend to a Weboob account.
        web_accounts = {}
        for account in w.iter_accounts():
            weboob_id = "%s@%s" % (account.id, account.backend)
            web_accounts[weboob_id] = account

        # Iter over the list of Odoo configured accounts for import and
        # build the list of valid accounts for import.
        history = {}
        odoo_accounts = {}
        for account in self:
            try:
                if account.is_active():
                    ident = account.weboob_name
                    history[ident] = w.iter_history(web_accounts[ident])
                    odoo_accounts[ident] = account
                    account.state = 'active'
            except KeyError:
                account.state = 'not_found'

        # Actual import. Fetch all transactions and create bank
        # statements
        statements = []
        bs_model = self.env['account.bank.statement']
        bsl_model = self.env['account.bank.statement.line']
        for ident in history:
            transactions = []
            total_amount = 0.0

            # When we reach the last imported transaction, fetch a few
            # more transactions (until 3 days before the last imported
            # one), in case the bank lately adds new transactions.
            max_date = None

            for web_transaction in history[ident]:
                unique_id = web_transaction.unique_id(account_id=ident)

                # Stop when we reach the unique transaction id seen
                # during the previous import
                if unique_id == odoo_accounts[ident].latest_unique_id:
                    max_date = web_transaction.date - datetime.timedelta(days=4)
                if max_date is not None and web_transaction.date <= max_date:
                    break

                # Add the transaction if it has not yet been imported
                if not bool(bsl_model.sudo().search([('unique_import_id', '=', unique_id)], limit=1)):
                    transactions.append({
                        'name': web_transaction.label,
                        'date': web_transaction.date,
                        'ref': web_transaction.raw,
                        'amount': web_transaction.amount,
                        'unique_import_id': unique_id,
                        })
                    total_amount += float(web_transaction.amount)

            if len(transactions) > 0:
                odoo_accounts[ident].latest_unique_id = transactions[0]['unique_import_id']
                # Create the bank statement
                statements.append(bs_model.create({
                        'name': datetime.date.today().strftime('%Y-%m-%d'),
                        'journal_id': odoo_accounts[ident].journal_id.id,
                        'line_ids': [(0, False, line) for line in reversed(transactions)],
                        'balance_start': float(web_accounts[ident].balance) - total_amount,
                        'balance_end_real': web_accounts[ident].balance,
                        }))

        return statements

    @api.model
    def periodic_all_imports(self):
        """
        Finds all active Weboob bank accounts and run imports.
        This method is intended to be started by an ir.cron job.
        """
        self.search([('state', '=', 'active')]).run_imports()

    @api.one
    def action_activate(self):
        self.state = 'active'

    @api.one
    def action_deactivate(self):
        self.state = 'inactive'
