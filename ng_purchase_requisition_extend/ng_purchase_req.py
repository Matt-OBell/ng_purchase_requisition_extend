# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2012 Mattobell (<http://www.mattobell.com>)
#    Copyright (C) 2010-Today OpenERP SA (<http://www.openerp.com>)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
##############################################################################

from openerp.osv import osv, fields

from tools.translate import _

class purchase_order_line(osv.osv):
    _inherit = "purchase.order.line"

    def on_change_type(self, cr, uid, ids, type, context=None):
        if context is None:
            context = {}
        if not type:
            return {}
        if type == 'budget_code':#internal
            return {'domain': {'product_id': [('type', '=', 'product'), ('budget_type', '=', 'budget_code')]}}
        if type == 'product':
            return {'value': {'budget_code_id': False}, 'domain': {'product_id': [('type', '!=', 'consu'), ('budget_type', '=', 'product')]}}
        return {}

purchase_order_line()

class purchase_requisition(osv.osv):
    _inherit = "purchase.requisition.multiple"
    
    def _check_split_po(self, cr, uid, ids, context=None):
        for mr in self.browse(cr, uid, ids, context):
            if not mr.is_split_po:
                for ir_line in mr.line_ids:
                    if ir_line.supplier_ids:
                        return False
        return True

    _constraints = [
        (_check_split_po, 'You can not select suppliers on requisition lines if Split PO lines box is not checked.', ['is_split_po','line_ids']),
    ]
    
#   For: Is Split PO Line?
    def make_purchase_order_split(self, cr, uid, ids, line_ids,  partner_id, context=None):
        """
        Create New RFQ for Supplier for Is Split PO Line? ticked.
        """
        if context is None:
            context = {}
        assert partner_id, 'Supplier should be specified'
        purchase_order = self.pool.get('purchase.order')
        purchase_order_line = self.pool.get('purchase.order.line')
        res_partner = self.pool.get('res.partner')
        fiscal_position = self.pool.get('account.fiscal.position')
        supplier = res_partner.browse(cr, uid, partner_id, context=context)
        delivery_address_id = res_partner.address_get(cr, uid, [supplier.id], ['delivery'])['delivery']
        supplier_pricelist = supplier.property_product_pricelist_purchase or False
        res = {}
        for requisition in self.browse(cr, uid, ids, context=context):
            if not requisition.warehouse_id:
                raise osv.except_osv(_('Error'), _('Please specify warehouse.'))
            if supplier.id in filter(lambda x: x, [rfq.state <> 'cancel' and rfq.partner_id.id or None for rfq in requisition.purchase_ids]):
                 raise osv.except_osv(_('Warning'), _('You have already one %s purchase order for this partner, you must cancel this purchase order to create a new quotation.') % rfq.state)
            location_id = requisition.warehouse_id.lot_input_id.id
            
            purchase_id = purchase_order.create(cr, uid, {
                        'origin': requisition.name,
                        'partner_id': supplier.id,
                        'date_order': requisition.date_start,
                        'minimum_planned_date': requisition.date_start,
                        'partner_address_id': delivery_address_id,
                        'pricelist_id': supplier_pricelist.id,
                        'location_id': location_id,
                        'company_id': requisition.company_id.id,
                        'fiscal_position': supplier.property_account_position and supplier.property_account_position.id or False,
                        'mrequisition_id':requisition.id,
                        'ir_number': requisition.ir_id.name, #15 june2015
                        'notes':requisition.description,
                        'warehouse_id':requisition.warehouse_id.id,
                        'site_id': requisition.site_id and requisition.site_id.id or False,#Pass site_id netcom
                        'type': requisition.type,
            })
            res[requisition.id] = purchase_id
            for line in self.pool.get('purchase.requisition.multiple.line').browse(cr, uid, line_ids, context):
                if line.type == 'product':
                    product = line.product_id
                    seller_price, qty, default_uom_po_id, date_planned = self._seller_details(cr, uid, line, supplier, context=context)
                    taxes_ids = product.supplier_taxes_id
                    taxes = fiscal_position.map_tax(cr, uid, supplier.property_account_position, taxes_ids)
                    purchase_order_line.create(cr, uid, {
                        'order_id': purchase_id,
                        'name': product.partner_ref,
                        'product_qty': qty,
                        'product_id': product.id,
                        'product_uom': default_uom_po_id,
                        'price_unit': seller_price,
                        'date_planned': requisition.date_end or date_planned,#date_planned,
                        'notes': product.description_purchase,
                        'mrequisition_id_line':requisition.id,
                        'taxes_id': [(6, 0, taxes)],
                        'type': line.type,
                    }, context=context)
                else:# for budget code                
                    if (line.product_id and line.budget_code_id) or (line.product_id and not line.budget_code_id):
                        product = line.product_id
                        seller_price, qty, default_uom_po_id, date_planned = self._seller_details(cr, uid, line, supplier, context=context)
                        taxes_ids = product.supplier_taxes_id
                        taxes = fiscal_position.map_tax(cr, uid, supplier.property_account_position, taxes_ids)
                        purchase_order_line.create(cr, uid, {
                            'order_id': purchase_id,
                            'name': product.partner_ref,
                            'product_qty': qty,
                            'product_id': product.id,
                            'product_uom': default_uom_po_id,
                            'price_unit': seller_price,
                            'date_planned': requisition.date_end or date_planned,#date_planned,
                            'notes': product.description_purchase,
                            'mrequisition_id_line':requisition.id,
                            'taxes_id': [(6, 0, taxes)],
                            'type': line.type,
                            'budget_code_id': line.budget_code_id and line.budget_code_id.id or False,#pass budget code from MR Line to PO lines.
                        }, context=context)
                    elif not line.product_id and line.budget_code_id:
                        #product = line.product_id
                        #seller_price, qty, default_uom_po_id, date_planned = self._seller_details(cr, uid, line, supplier, context=context)
                        #taxes_ids = product.supplier_taxes_id
                        #taxes = fiscal_position.map_tax(cr, uid, supplier.property_account_position, taxes_ids)
                        purchase_order_line.create(cr, uid, {
                            'order_id': purchase_id,
                            'name':  line.desc,
                            'product_qty': line.product_qty,
                            #'product_id': product.id,
                            'product_uom': line.product_uom_id.id,
                            'price_unit': 0.0,#todo: Fix since we do not have product here so could not use sellers price or pricelist feature.
                            'date_planned': requisition.date_end or requisition.date_start,#date_planned,
                            'notes': line.desc,
                            'mrequisition_id_line':requisition.id,
                            #'taxes_id': [(6, 0, taxes)],
                            'type': line.type,
                            'budget_code_id': line.budget_code_id.id,#pass budget code from MR Line to PO lines.
                        }, context=context)
                    elif not line.product_id and not line.budget_code_id:
                        #product = line.product_id
                        #seller_price, qty, default_uom_po_id, date_planned = self._seller_details(cr, uid, line, supplier, context=context)
                        #taxes_ids = product.supplier_taxes_id
                        #taxes = fiscal_position.map_tax(cr, uid, supplier.property_account_position, taxes_ids)
                        purchase_order_line.create(cr, uid, {
                            'order_id': purchase_id,
                            'name':  line.desc,
                            'product_qty': line.product_qty,
                            #'product_id': product.id,
                            'product_uom': line.product_uom_id.id,
                            'price_unit': 0.0,#todo: Fix since we do not have product here so could not use sellers price or pricelist feature.
                            'date_planned': requisition.date_end or requisition.date_start,#date_planned,
                            'notes': line.desc,
                            'mrequisition_id_line':requisition.id,
                            #'taxes_id': [(6, 0, taxes)],
                            'type': line.type,
                            #'budget_code_id': line.budget_code_id.id,#pass budget code from MR Line to PO lines.
                        }, context=context)
        return res
    
    #Override completely here for "Is Split PO Line?",.
    def tender_done(self, cr, uid, ids, context=None):
        for t in self.browse(cr, uid, ids, context=context):
            if not t.partner_ids and not t.is_split_po:
                raise osv.except_osv(_('Error'), _('At least one supplier must be selected.'))
            if not t.policy_id:
                raise osv.except_osv(_('Error'), _('You can not create RFQ. No requisition policy set'))
            m = t.policy_id.min
            n = t.policy_id.max
            if (len(t.partner_ids) < m or len(t.partner_ids) > n) and not t.is_split_po:
                raise osv.except_osv(_('Error'), _('The state of this requisition cannot be set to Done. Please check your multiple requisition policy. You should have minimum %s suppliers and maximum %s suppliers.')%(m, n))
            
            if t.is_split_po:
                supplier_list = []
                for x in t.line_ids:
                    for sup in x.supplier_ids:
                        if sup.id not in supplier_list:
                            supplier_list.append(sup.id)
                if len(supplier_list) < m or len(supplier_list) > n:
                    raise osv.except_osv(_('Error'), _('The state of this requisition cannot be set to Done. Please check your multiple requisition policy. You should have minimum %s suppliers and maximum %s suppliers while setting suppliers in requisition line.')%(m, n))
            if not t.is_split_po:
                for partner in t.partner_ids:
                    self.make_purchase_order(cr, uid, [t.id], partner.id, context=context)
            else:
                supplier_dict= {}
                for x in t.line_ids:
                    if x.supplier_ids:
                        for sup in x.supplier_ids:
                            if sup.id not in supplier_dict:
                                supplier_dict[sup.id] = [x.id]
                            else:
                                supplier_dict[sup.id].append(x.id)
                if supplier_dict:#supplier_dict = {'s_id': [line ids....], 's_id2':[line_ids....]} - Sample dict
                    for mysupplier in supplier_dict:
                        line_ids = supplier_dict[mysupplier]
                        if line_ids:
                            self.make_purchase_order_split(cr, uid, [t.id], line_ids, mysupplier, context=context)
        self.write(cr, uid, ids, {'state':'done'}, context=context)
#        self.write(cr, uid, ids, {'state':'done', 'date_end':time.strftime('%Y-%m-%d %H:%M:%S')}, context=context)
        return True
    
    _columns = {
        'is_split_po': fields.boolean("Split PO Line?",help="Check this box to issue PO Lines to multiple vendors."),
    }
    
class purchase_requisition_line(osv.osv):
    _inherit = "purchase.requisition.multiple.line"
    
    _columns = {
        'supplier_ids': fields.many2many('res.partner', 'multi_supplier_purchase', 'multiple_id', 'partner_id', 'Suppliers' ),
        'type' :  fields.selection([('product', 'External'),('budget_code', 'Internal')], string='Request Type', required= True),#budget
        'budget_code_id' : fields.many2one('product.budget.code', 'Budget Code'),#budget
        'desc' : fields.char('Description')
    }

    def on_change_type(self, cr, uid, ids, type, context=None):
        if context is None:
            context = {}
        if not type:
            return {}
        if type == 'budget_code':#internal
            return {'domain': {'product_id': [('type', '=', 'product'), ('budget_type', '=', 'budget_code')]}}
        if type == 'product':
            return {'value': {'budget_code_id': False}, 'domain': {'product_id': [('type', '!=', 'consu'), ('budget_type', '=', 'product')]}}
        return {}
   
    def onchange_budget_code_id(self, cr, uid, ids, budget_code_id, context=None):
        if not context:
            context ={}
        if not budget_code_id:
            return {}
        budget_data = self.pool.get('product.budget.code').browse(cr, uid, [budget_code_id], context)[0]
        name = budget_data.name or ''
        code = budget_data.code or ''
        
        desc = code + ' ' + name
        
        return {'value' : {'product_qty' : 1.0,
                           'desc' : desc
                           }}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
