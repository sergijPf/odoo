/* global odoo,_,$,easyPack */
/* jshint esversion: 6 */
odoo.define('trilab_delivery_inpost.checkout', function (require) {
'use strict';

const publicWidget = require('web.public.widget');
require('website_sale_delivery.checkout');


publicWidget.registry.websiteSaleDelivery.include({
    jsLibs: [
        'https://geowidget.easypack24.net/js/sdk-for-javascript.js'
    ],
    cssLibs: [
        'https://geowidget.easypack24.net/css/easypack.css'
    ],

    init: function () {
        _.extend(this.events, {
            'click #delivery_carrier .o_delivery_carrier_select .inpost_edit_locker': '_onPointSelectClick',
        });
        return this._super.apply(this, arguments);
    },

    start: function () {
        let result = this._super.apply(this, arguments);

        // check if there are inpost carriers with required points and that point is selected
        this._setPaymentButtonState($('#delivery_carrier input[name="delivery_type"]:checked').first());

        return result;
    },

    _setPaymentButtonState: function ($carrier) {
        if (!$carrier) {
            return;
        }

        let $payButton = $('#o_payment_form_pay');
        let disabledReasons = $payButton.data('disabled_reasons') || {};

        disabledReasons.carrier_inpost_locker_selection = !!$carrier.data('inpost-require-point') &&
            !$carrier.data('inpost-selected-point');

        $payButton.data('disabled_reasons', disabledReasons);
        $payButton.prop('disabled', _.contains($payButton.data('disabled_reasons'), true));

        if ($carrier.data('inpost-show-point')) {
            $carrier.siblings('.inpost_edit_locker').show();
        }
    },

    _onCarrierClick: function (ev) {
        let $input = $(ev.currentTarget).find('input[type="radio"]');
        $('#delivery_carrier .inpost_edit_locker').hide();
        this._setPaymentButtonState($input);
        // if ($input.data('inpost-show-point')) {
        //     $input.siblings('.inpost_edit_locker').show();
        // }
        return this._super.apply(this, arguments);
    },

    _handleCarrierUpdateResult: function(result) {
        if (result.status === true) {
            this._setPaymentButtonState($('#delivery_carrier input[name="delivery_type"]:checked').first());
        }
        this._super.apply(this, arguments);
    },

    _onPointSelectClick: function (ev) {
         let self = this;
         let $carrier = $(ev.currentTarget);
         let $carrierInput = $(ev.currentTarget)
             .parent('.o_delivery_carrier_select')
             .find('input[name="delivery_type"]');

         easyPack.init({
             filters: false,
             instance: 'pl',
             mapType: 'osm',
             searchType: 'osm',
             points: {
                 types: ['parcel_locker_only'],
             },
             map: {
                 useGeolocation: false,
                 initialTypes: ['parcel_locker_only']
             }
         });

         // noinspection JSUnresolvedFunction
        let map = easyPack.modalMap(function(point, modal){
             // noinspection JSUnresolvedFunction
             modal.closeModal();
             let desc = '';
             if (!!point.address) {
                 desc = ' (' + _.str.join(', ', ... _.values(point.address)) + ")";
             }
             $carrierInput.data('inpost-selected-point', point.name);
             $carrier.html(point.name + '<span class="text-muted">' + desc + '</span>');
             self._showLoading($carrierInput);
             self._rpc({
                 route: '/shop/update_carrier',
                 params: {
                     'carrier_id': $carrierInput.val(),
                     'inpost_point': point.name
                 },
             }).then(self._handleCarrierUpdateResult.bind(self));
             $.unblockUI();
        }, {'width': 600, 'height': 400});

        $('#widget-modal .widget-modal__close').on('click', function () {
            $.unblockUI();
        });

        let current_ship_address = $('[itemprop="streetAddress"]').text();
        if (!!current_ship_address) {
            // noinspection JSUnresolvedFunction
            map.searchPlace(current_ship_address);
        }

        $.blockUI();
        ev.stopPropagation();
    }

});
});
