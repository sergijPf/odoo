odoo.define('smartino_common.Menu', function (require) {
    'use strict';

    const session = require('web.session');
    const Menu = require('web_enterprise.Menu');
    const rpc = require('web.rpc');

    Menu.include({
        /**
         * @override
         */
        start: function (parent, options) {
            return this._super.apply(this, arguments).then(function () {
                rpc.query({
                    model: 'res.company',
                    method: 'search_read',
                    fields: ['logo'],
                    domain: [['id', '=', session.company_id]],
                    kwargs: {limit: 1}
                }).then(function (result) {
                    if (result.length && result[0].logo) {
                        $('#company-logo')
                            .attr('src', session.url('/web/image',
                                {id: session.company_id, model: 'res.company', field: 'logo'}))
                            .parent().show();
                    } else {
                        $('#company-logo').parent().hide();
                    }
                });
            });
        }
    });

});
