# -*- coding: utf-8 -*-
# Copyright (c) 2021, scopen.fr and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
from six import string_types
from erpnext.stock.get_item_details import get_item_details, process_args, sales_doctypes, purchase_doctypes, get_item_tax_info
from frappe.model.mapper import make_mapped_doc
from frappe import _ 


@frappe.whitelist()
def get_item_details_custom(args, doc=None, for_validate=False, overwrite_warehouse=True):

    # standard feature
    out = get_item_details(args, doc, for_validate, overwrite_warehouse)

    # PRocess arges and doc to use it as object
    args = process_args(args)
    if isinstance(doc, string_types):
        doc = json.loads(doc)

    # deal with tax code selling or buying
    transaction_type = None
    type_thirdparty = None
    if doc:
        if doc.get('doctype') in purchase_doctypes:
            transaction_type = 'Achat'
            type_thirdparty = 'Supplier'
        if doc.get('doctype') in sales_doctypes:
            transaction_type = 'Vente'
            type_thirdparty = 'Customer'

        if transaction_type is not None:
            tax_info = get_correct_tax_account(transaction_type, args.item_code)
            if tax_info is not None:
                out.item_tax_template = tax_info.get('name')
                out.item_tax_rate = json.dumps(tax_info.get('detail'))

    # by defaut we don't know what we are working on
    if args.customer is not None:
        thirdparty = args.customer

    if args.supplier is not None:
        thirdparty = args.supplier

    #on Quotation there is no accountancy code
    if doc and doc.get('doctype') == 'Quotation':
        type_thirdparty = None

    if type_thirdparty is not None:
        account = get_correct_default_account(thirdparty, type_thirdparty, args.item_code)
        if type_thirdparty == 'Customer' and account is not None:
            out.income_account = account
        if type_thirdparty == 'Supplier' and account is not None:
            out.expense_account = account

    return out


def get_correct_default_account(thirdparty, type_thirdparty, item_code):

    if thirdparty is not None:
        doc_thirdparty = frappe.get_doc(type_thirdparty, thirdparty)
        categ_compta_thirdparty = doc_thirdparty.categorie_comptable_tiers
        doc_item = frappe.get_doc('Item', item_code)
        account = None

        for thirdparty_setup_categ in frappe.db.get_all(doctype="Categorie comptable Tiers et code comptable Produit",
                                                        as_list=True,
                                                        filters={'parent': 'Special Item Accountancy Code Default'}):
            thirdparty_categ = frappe.get_doc("Categorie comptable Tiers et code comptable Produit",
                                              thirdparty_setup_categ[0])
            if thirdparty_categ.categorie_comptable_tiers == categ_compta_thirdparty:
                if type_thirdparty == 'Customer':
                    account = thirdparty_categ.compte_de_produits
                if type_thirdparty == 'Supplier':
                    account = thirdparty_categ.compte_de_charges
                    break

        for item_group_categ in frappe.db.get_all(doctype="Categorie comptable Tiers et code comptable Produit",
                                                        as_list=True,
                                                        filters={'parent': doc_item.item_group,'parenttype': 'Item Group'}):
            thirdparty_categ = frappe.get_doc("Categorie comptable Tiers et code comptable Produit",
                                              item_group_categ[0])
            if thirdparty_categ.categorie_comptable_tiers == categ_compta_thirdparty:
                if type_thirdparty == 'Customer':
                    account = thirdparty_categ.compte_de_produits
                if type_thirdparty == 'Supplier':
                    account = thirdparty_categ.compte_de_charges
                    break

        if len(doc_item.special_item_accountancy_code_details) != 0:
            for detail in doc_item.special_item_accountancy_code_details:
                if detail.categorie_comptable_tiers == categ_compta_thirdparty:
                    if type_thirdparty == 'Customer':
                        account = detail.compte_de_produits
                    if type_thirdparty == 'Supplier':
                        account = detail.compte_de_charges
                    break

        return account


def get_correct_tax_account(transaction_type, item_code):

    if item_code is not None and transaction_type is not None:
        tax_infos = frappe.get_list("Item Tax",
                                    filters={'parent': item_code, 'transaction_type': transaction_type},
                                    fields=['item_tax_template'])
        if len(tax_infos) != 0:
            tax_info = frappe.get_doc('Item Tax Template', tax_infos[0].item_tax_template)
            if len(tax_info.taxes) != 0:
                tax_info_detail = frappe.get_doc('Item Tax Template Detail', tax_info.taxes[0].name)
                return {'name': tax_info.title, 'detail': {tax_info_detail.tax_type: tax_info_detail.tax_rate}}


@frappe.whitelist()
def make_mapped_doc_custom(method, source_name, selected_children=None, args=None):

    out = make_mapped_doc(method, source_name, selected_children, args)

    if method == 'erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice':
        customer=frappe.get_doc('Customer', out.customer)
        if (customer.categorie_comptable_tiers is None) or (customer.categorie_comptable_tiers == ""):
            frappe.throw(_('Cutomer accountancy category is missing'))
            for itm in out.items:
                itm.income_account = get_correct_default_account(out.customer, 'Customer', itm.item_code)

    if method == 'erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice':
        supplier = frappe.get_doc('Supplier', out.supplier)
        if (supplier.categorie_comptable_tiers is None) or (supplier.categorie_comptable_tiers == ""):
            frappe.throw(_('Cutomer accountancy category is missing'))
        for itm in out.items:
            itm.expense_account = get_correct_default_account(out.supplier, 'Supplier', itm.item_code)

    return out

@frappe.whitelist()
def get_item_tax_info_custom(company, doctype, tax_category, item_codes):

    taxe_infos = get_item_tax_info(company, tax_category, item_codes)

    transaction_type = None

    if doctype in purchase_doctypes:
        transaction_type = 'Achat'
    if doctype in sales_doctypes:
        transaction_type = 'Vente'

    if len(taxe_infos) != 0 and transaction_type is not None:
        for item_code, data in taxe_infos:
            tax_info = get_correct_tax_account(transaction_type, item_code)
            taxe_infos[item_code]["item_tax_rate"] = {'item_tax_template': tax_info.get('name'),
                                                      'item_tax_rate': json.dumps(tax_info.get('detail'))}


    return taxe_infos