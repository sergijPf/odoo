from odoo import models, _, api
from odoo.exceptions import AccessError, UserError


class IrTranslation(models.Model):
    _inherit = 'ir.translation'

    @api.model
    def x_translate_fields(self, model, id, field=None):
        """ Open a view for translating the field(s) of the record (model, id). """
        main_lang = 'en_US'
        if not self.env['res.lang'].search_count([('code', '!=', main_lang)]):
            raise UserError(_("Translation features are unavailable until you install an extra translation."))

        # determine domain for selecting translations
        record = self.env[model].with_context(lang=main_lang).browse(id)
        domain = ['&', ('res_id', '=', id), ('name', '=like', model + ',%')]

        def make_domain(fld, rec):
            name = "%s,%s" % (fld.model_name, fld.name)
            return ['&', ('res_id', '=', rec.id), ('name', '=', name)]

        # insert missing translations, and extend domain for related fields
        for name, fld in record._fields.items():
            if not fld.translate:
                continue

            rec = record
            if fld.related:
                try:
                    # traverse related fields up to their data source
                    while fld.related:
                        rec, fld = fld.traverse_related(rec)
                    if rec:
                        domain = ['|'] + domain + make_domain(fld, rec)
                except AccessError:
                    continue

            assert fld.translate and rec._name == fld.model_name
            self.insert_missing(fld, rec)

        if field:
            fld = record._fields[field]
            if fld.related:
                rec = record
                try:
                    while fld.related:
                        rec, fld = fld.traverse_related(rec)
                except AccessError:
                    pass
