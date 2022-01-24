odoo.define('custom_base.settings', function (require) {
"use strict";

var BaseSettingRenderer = require('base.settings').Renderer;

BaseSettingRenderer.include({

    _getAppIconUrl: function (module) {
        if (module == 'odoo_magento2_websites' || module == 'odoo_magento2_storeviews') {
            return "/odoo_magento2/static/description/icon.png";
        }
        else {
            return this._super.apply(this, arguments);
        }
    }
});
});