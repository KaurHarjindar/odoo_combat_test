# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import io

from PyPDF2 import PdfFileWriter, PdfFileReader
from PyPDF2.generic import NameObject, IndirectObject, BooleanObject, NumberObject

from odoo import models
from odoo.tools import format_amount, format_date, format_datetime, pdf

import base64
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from logging import getLogger

_logger = getLogger(__name__)

class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        result = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=res_ids)
        if self._get_report(report_ref).report_name != 'sale_pdf_quote_builder.report_saleorder_quote' and self._get_report(report_ref).report_name != 'sale.report_saleorder':
            return result

        orders = self.env['sale.order'].browse(res_ids)

        for order in orders:
            initial_stream = result[order.id]['stream']
            if initial_stream:
                order_template = order.sale_order_template_id
                header_record = order_template if order_template.sale_header else order.company_id
                footer_record = order_template if order_template.sale_footer else order.company_id
                has_header = bool(header_record.sale_header)
                has_footer = bool(footer_record.sale_footer)

                if (not has_header and not has_footer and not order.room_concept_pdf):
                    continue

                IrBinary = self.env['ir.binary']
                writer = PdfFileWriter()

                # Add header pages to writer object
                if has_header:
                    header_stream = IrBinary._record_to_stream(header_record, 'sale_header').read()
                    self._add_pages_to_writer(writer, header_stream)

                # Add sales report page to writer object
                self._add_pages_to_writer(writer, (initial_stream).getvalue())

                # Add room concept pdf to writer object
                if order.room_concept_pdf:
                    room_concept_stream = IrBinary._record_to_stream(order, 'room_concept_pdf').read()
                    self._add_pages_to_writer(writer, room_concept_stream)
                    
                # Add footer pages to writer object
                if has_footer:
                    footer_stream = IrBinary._record_to_stream(footer_record, 'sale_footer').read()
                    self._add_pages_to_writer(writer, footer_stream)


                # Get form fields mapping
                form_fields = self._get_form_fields_mapping(order)

                # Fill form fileds using writer object and fields mapping
                self._fill_form_fields_pdf(writer, form_fields=form_fields)

                # Update stream in result
                with io.BytesIO() as _buffer:
                    writer.write(_buffer)
                    stream = io.BytesIO(_buffer.getvalue())
                result[order.id].update({'stream': stream})

        return result

    def _add_pages_to_writer(self, writer, document):
        reader = PdfFileReader(io.BytesIO(document), strict=False)
        for page_id in range(0, reader.getNumPages()):
            page = reader.getPage(page_id)
            writer.addPage(page)

    def _get_form_fields_mapping(self, order):
        """ Dictionary mapping specific pdf fields name to Odoo fields data for a sale order.
        Override this method to add new fields to the mapping.

        :param recordset order: sale.order record
        :rtype: dict
        :return: mapping of fields name to Odoo fields data

        Note: order.ensure_one()
        """
        order.ensure_one()
        env = self.with_context(use_babel=True).env
        tz = order.partner_id.tz or self.env.user.tz or 'UTC'
        lang_code = order.partner_id.lang or self.env.user.lang
        form_fields_mapping = {
            'name': order.name,
            'partner_id__name': order.partner_id.name,
            'user_id__name': order.user_id.name,
            'amount_untaxed': format_amount(env, order.amount_untaxed, order.currency_id),
            'amount_total': format_amount(env, order.amount_total, order.currency_id),
            'delivery_date': format_datetime(env, order.commitment_date, tz=tz),
            'validity_date': format_date(env, order.validity_date, lang_code=lang_code),
            'client_order_ref': order.client_order_ref or '',
            'order_date': format_date(env, order.date_order, lang_code=lang_code),
            'partner_id__street': order.partner_id.street or '',
            'partner_id__company': order.partner_id.commercial_partner_id.name or '',
            'partner_id__zip': order.partner_id.zip or '',
            'payment_term': order.payment_term_id.name or '',
            'currency': order.pricelist_id.currency_id.name or '',
            'image': order.product_image or '',
            'signature': order.signature or '',
        }

        return form_fields_mapping

    def _fill_form_fields_pdf(self, writer, form_fields):
        ''' Fill in the form fields of a PDF
        :param writer: a PdfFileWriter object
        :param dict form_fields: a dictionary of form fields to update in the PDF
        :return: a filled PDF datastring
        '''

        # This solves a known problem with PyPDF2, where with some pdf software, forms fields aren't
        # correctly filled until the user click on it, see: https://github.com/py-pdf/pypdf/issues/355
        if hasattr(writer, 'set_need_appearances_writer'):
            writer.set_need_appearances_writer()
            is_upper_version_pypdf2 = True
        else:  # This method was renamed in PyPDF2 2.0
            is_upper_version_pypdf2 = False
            catalog = writer._root_object
            # get the AcroForm tree
            if "/AcroForm" not in catalog:
                writer._root_object.update({
                    NameObject("/AcroForm"): IndirectObject(len(writer._objects), 0, writer)
                })
            writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

        nbr_pages = len(writer.pages) if is_upper_version_pypdf2 else writer.getNumPages()

        # For every binary field insert image and remove field from mapping
        for field in list(form_fields):
            if(isinstance(form_fields[field], bytes)):
                self._fill_form_images_pdf(writer, nbr_pages, field, form_fields[field])
                form_fields.pop(field)

        for page_id in range(0, nbr_pages):
            page = writer.getPage(page_id)

            if is_upper_version_pypdf2:
                writer.update_page_form_field_values(page, form_fields)
            else:
                # This is a known bug on previous version of PyPDF2, fixed in 2.11
                if not page.get('/Annots'):
                    _logger.info("No fields to update in this page")
                else:
                    writer.updatePageFormFieldValues(page, form_fields)

            for raw_annot in page.get('/Annots', []):
                annot = raw_annot.getObject()
                for field in form_fields:
                    # Mark filled fields as readonly to avoid the blue overlay:
                    if annot.get('/T') == field:
                        annot.update({NameObject("/Ff"): NumberObject(1)})

    def _fill_form_images_pdf(self, writer, nbr_pages, field, form_field_value):
        if(not form_field_value):
            return
        for page_id in range(0, nbr_pages):
            page = writer.getPage(page_id)
            if page.get('/Annots'):
                for j in range(0, len(page['/Annots'])):
                    writer_annot = page['/Annots'][j].getObject()
                    if writer_annot.get('/T') == field:
                        # Get coordinates of image field
                        rect = writer_annot.get('/Rect')
                        image_coords = [round(coord) for coord in rect]
                        
                        # Insert image in the field using coordinates
                        packet = io.BytesIO()
                        can = canvas.Canvas(packet)
                        image_reader = ImageReader(io.BytesIO(base64.b64decode(form_field_value)))
                        can.drawImage(image_reader, image_coords[0], image_coords[1], width=image_coords[2]-image_coords[0], height=image_coords[3]-image_coords[1])
                        can.save()                           
                        new_page = PdfFileReader(packet).pages[0]                               
                        page.mergePage(new_page)                               
                        writer_annot.update({NameObject("/Ff"): NumberObject(1)})
