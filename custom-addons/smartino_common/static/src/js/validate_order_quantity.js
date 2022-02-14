odoo.define('smartino_common.validate_order_quantity', function (require) {
    'use strict';

    const publicWidget = require('web.public.widget');
    const ajax = require('web.ajax');
    const core = require('web.core');
    const QWeb = core.qweb;


    publicWidget.registry.WebsiteSale.include({
        init: function () {
            this._super.apply(this, arguments);
            this.productQuantityConstraintsData = {};
        },
        willStart: function () {
            const productIds = [...$('*[data-product-id]').get().map(el=>$(el).data('product-id')),
                                ...$('input[name=product_id]').get().map(el=>$(el).val())];

            // fetch quantity validation data from the server and append it to productQuantityConstraintsData
            const productQtyConstrainData = this._updateQuantityValidationData(productIds);

            const xml_load = ajax.loadXML('/smartino_common/static/src/xml/quantity_validation_alert.xml', QWeb);

            return Promise.all([this._super.apply(this), productQtyConstrainData, xml_load]);
        },
        start: function () {
            const $input = this.$("input[name='add_qty'], input.js_quantity");
            if ($input.length) {
                if (this.$('#product_details').length) { // on product page
                    let productId = this.$('#product_details form input[name=product_id]').val();
                    if (this.productQuantityConstraintsData[productId]) {
                        let minProductQty = Number.parseFloat(this.productQuantityConstraintsData[productId].productMinimalQuantity || 1);
                        $input.val( minProductQty ); // default order quantity input value
                    }
                }
                $input.each((_, el) => { 
                    let productId = $(el).data('product-id');
                    let quantity = Number.parseFloat($(el).val());
                    this._validateOrderQuantity(productId, quantity, this.productQuantityConstraintsData[productId]);
                });
            }
            return this._super.apply(this);
        },
        _updateQuantityValidationData: function (productIds) {
            const self = this;

            const productModelData = this._rpc({
                route: '/shop/x_get_products_data_to_validate',
                params: {
                    product_ids: productIds,
                },
            }).then(res => {
                for (let productData of res) {
                    self.productQuantityConstraintsData[productData.id] = {
                        productQuantityMultiplicity: productData.x_quantity_multiplicity,
                        productMinimalQuantity: productData.x_minimal_quantity,
                        productDisplayName: productData.name,
                        productUomName: productData.uom_name
                    };
                }
            });
            return productModelData;
        },
        _onChangeCombination: async function (ev, $parent, combination) {
            this._super.apply(this, arguments);

            let quantity = $parent.find('input[name="add_qty"]').val();

            // remove all validation alerts not related to the product
            this.$('.quantity-validation-alert').not('.quantity-validation-alert-' + combination.product_id).remove();
            if (combination.product_id) {
                // check if product quantity validation data is available
                // otherwise, try to load it from the server
                if ( !(combination.product_id in this.productQuantityConstraintsData) ) {
                    await this._updateQuantityValidationData([combination.product_id]);
                }
                const constrains = this.productQuantityConstraintsData[combination.product_id];
                this._validateOrderQuantity(combination.product_id, quantity, constrains);
            }

            this._quantityValidationUpdateDOM(combination.product_id);
        },
        _changeCartQuantity: function ($input, value) {
            this._super.apply(this, arguments);
            const self = this;

            // wait for the cart page to rerender and only validate the order
            // otherwise the DOM changes are automatically reverted once rerendered
            this.$('#o_cart_summary').one("DOMSubtreeModified", function() {
                const $inputs = self.$("input[name='add_qty'], input.js_quantity");
                $inputs.each((_, el) => {
                    let productId = $(el).data('product-id');
                    let quantity = Number.parseFloat($(el).val());
                    self._validateOrderQuantity(productId, quantity, self.productQuantityConstraintsData[productId]);
                });
            });

            // remove validation alerts if 
            if (value <= 0) {
                let productId = $input.data('product-id');
                this.$('.quantity-validation-alert-' + productId).remove();
            }
        },
        _onClickAddCartJSON: async function (ev) {
            ev.preventDefault();

            const $link = $(ev.currentTarget);
            const $input = $link.closest('.input-group').find("input");

            let minProductQty = 0, productQtyMultiplicity = 1;

            let productId = ($input.data('product-id') || this.$('input[name=product_id]').val());
            let constrains = this.productQuantityConstraintsData[productId];

            // check if valid constrain data exists for productId,
            // otherwise, constrains remain at default value
            if (constrains) {
                minProductQty = constrains.productMinimalQuantity;
                productQtyMultiplicity = constrains.productQuantityMultiplicity;
            }

            const currentQuantity = Number.parseFloat($input.val() || 1);
            const min = Number.parseFloat( Math.max(minProductQty, productQtyMultiplicity) || $input.data("min") || 0);
            const max = Number.parseFloat($input.data("max") || Number.POSITIVE_INFINITY);
            
            const sign = $link.has(".fa-minus").length ? -1 : 1


            let quantity;
            if (currentQuantity%productQtyMultiplicity==0) {
                let amount = Number.parseFloat(productQtyMultiplicity);
                quantity = currentQuantity+amount*sign;
            } else { // make sure that the new quantity after increment, is divisible by the productQtyMultiplicity
                if (sign>0) {
                    let amount = Number.parseFloat(productQtyMultiplicity-(currentQuantity%productQtyMultiplicity));
                    quantity = currentQuantity+amount;
                } else {
                    let amount = Number.parseFloat(-(productQtyMultiplicity-currentQuantity)%productQtyMultiplicity);
                    quantity = currentQuantity-amount;
                }
            }

            // limit quantity between min and max
            quantity = quantity > min ? (quantity < max ? quantity : max) : min;

            if (quantity !== currentQuantity) {
                $input.val(quantity).trigger('change');
            }
            return false;
        },
        _validateOrderQuantity: function (productId, quantity, constrainsData) {
            // remove all validation alerts related to the product
            this.$('.quantity-validation-alert-' + productId).remove();

            if (constrainsData) {
                let minProductQty = Number.parseFloat(constrainsData.productMinimalQuantity || 1);
                let productQtyMultiplicity = Number.parseFloat(constrainsData.productQuantityMultiplicity || 1);
                
                if (quantity < minProductQty && (quantity>0 || !this.$('#cart_products').length)) { // ignore error on quantity 0, when on cart page
                    this._renderQtyValidationAlerts('smartino_common.quantity_validation_minimal_quantity_alert', productId, constrainsData);
                }
                if (quantity % productQtyMultiplicity !== 0) {
                    this._renderQtyValidationAlerts('smartino_common.quantity_validation_quantity_multiplicity_alert', productId, constrainsData);
                }
            }

            this._quantityValidationUpdateDOM(productId);
        },
        _renderQtyValidationAlerts: function (templateId, productId, constrainsData) {
            let $alert = $(QWeb.render(
                templateId,
                {
                    product_id: productId,
                    product_quantity_multiplicity: constrainsData.productQuantityMultiplicity,
                    product_minimal_quantity: constrainsData.productMinimalQuantity,
                    product_name: constrainsData.productDisplayName,
                    uom_name: constrainsData.productUomName
                }
            ));
            $('#cart_products').before($alert); // insert alert on my cart page
            $('#product_details form').after($alert); // insert alert on product page
        },
        _quantityValidationUpdateDOM: function (productId) {
            let $btnDisable = this.$("#add_to_cart, a[href*='/shop/checkout']");

            // check if there are any errors
            if (this.$('.quantity-validation-alert').length) {
                $btnDisable.attr("disabled", true)
                    .addClass('disabled');
            } else {
                $btnDisable.attr("disabled", false)
                    .removeClass('disabled');

                let $inputs = this.$('input.js_quantity')
                               .add('input[name="add_qty"]');
                $inputs.removeClass('is-invalid') // set all quantity inputs to valid
            }

            let $input = this.$(`input.js_quantity[data-product-id='${productId}']`)
                           .add('input[name="add_qty"]');
            if (this.$('.quantity-validation-alert-' + productId).length) {
                $input.addClass('is-invalid')
            } else {
                $input.removeClass('is-invalid')
            }
        }
    });
});
