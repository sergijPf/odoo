from odoo import models, fields


class ChangeProductStatusWizard(models.TransientModel):
    _name = 'smartino.change.product.status.wizard'
    _description = 'Smartino change Product Status wizard'

    product_ids = fields.Many2many('product.product', default=lambda self: self.env.context.get('active_ids', []),
                                   readonly=True)

    new_status = fields.Selection(
        selection=lambda self: self.env['product.product']._x_get_available_product_status(),
        string='Status',
        help='w przygotowaniu - dla produktów prototypowych, niedostępne w zamówieniach,'
             ' mogą być zlecane szwalni wyszycia próbne, tworzone receptury i wyceny\n'
             'prapremiera - produkt nie wprowadzony na rynek, ale dystrybutorzy mogą zamawiać\n'
             'premiera - produkt zaprezentowany konsumentom, 6 tygodni od publikacji w '
             'B2C (ESKLEP) zmiana statusu na nowość\n'
             'nowość - produkty w pierwszym sezonie sprzedaży\n'
             'kontynuacja - produkt, który jest sprzedawany drugi lub kolejny sezon\n'
             'on hold - nie domawiamy surowców, ale nie robimy głębokich promocji, bo produkt wróci w kolejnym'
             'sezonie (w tym statusie będzie np. asortyment letni jesienią, gdy chcemy go kontynuować kolejnego lata)\n'
             'koniec serii - produkcja i zamówienia do wyczerpania surowców,'
             ' gdy surowce sie skończą automatycznie wchodzi w status wycofane\n'
             'wycofane - produkty, których juz nie planujemy w regularnej sprzedaży, ale w szczególnych warunkach po '
             'zapytaniu ofertowym dystrybutora może być wyprodukowane i zamówione specjalnie surowce, '
             'jeśli dystrybutor wykorzysta całą belkę surowca\n'
    )

    def button_change_status(self):
        self.ensure_one()
        self.product_ids.write({'x_status': self.new_status})
