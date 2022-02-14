odoo.define('smartino_common.sale_management', function (require) {
    'use strict';

    const publicWidget = require('web.public.widget');

    publicWidget.registry.SalePartnerChoiceButton = publicWidget.Widget.extend({
        selector: '.o_portal_sale_sidebar',
        events: {
            'click a.js_x_partner_choice': '_onClickButton',
        },

        async start() {
            await this._super(...arguments);
            this.orderDetail = this.$el.find('table#sales_order_table').data();
        },

        _onClickButton(ev) {
            ev.preventDefault();
            let self = this,
                $target = $(ev.currentTarget);
            // to avoid double click on link with href.
            $target.css('pointer-events', 'none');

            this._rpc({
                route: "/my/orders/" + $target.data('so-line-id') + "/x_set_partner_choice/" + $target.data('choice'),
                params: {access_token: self.orderDetail.token}
            }).then((data) => {
                if (data) {
                    location.reload();
                }
            });
        },

    });
});