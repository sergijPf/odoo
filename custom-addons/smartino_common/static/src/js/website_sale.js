odoo.define('smartino_common.website_sale', function (require) {
    'use strict';

    const publicWidget = require('web.public.widget');
    const websiteSaleUtils = require('website_sale.utils');

    publicWidget.registry.WebsiteSale.include({
        _onClickAdd: function(ev) {
            let $form = $(ev.currentTarget).closest('form');
            if ( $form.is('.oe_product_cart')) {
                let product_id = Number.parseInt($form.find("input[name='product_id']").val());
                let add_qty = Number.parseFloat($form.find("input[name='add_qty']").val() || 1);
                this._rpc({
                    route: "/shop/cart/update_json",
                    params: {
                        product_id: product_id,
                        add_qty: add_qty
                    },
                }).then( (data) => {
                    websiteSaleUtils.updateCartNavBar(data);
                });
                return;
            } else {
                this._super.apply(this, arguments);
            }
        },
    });
});
