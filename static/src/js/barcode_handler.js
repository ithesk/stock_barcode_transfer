odoo.define('stock_barcode_transfer.barcode_handler', function (require) {
    "use strict";

    var core = require('web.core');
    var FieldChar = require('web.basic_fields').FieldChar;
    var registry = require('web.field_registry');
    var _t = core._t;

    var BarcodeHandlerWidget = FieldChar.extend({
        className: 'o_field_barcode_handler',
        events: _.extend({}, FieldChar.prototype.events, {
            'keydown': '_onKeydown',
            'focus': '_onFocus',
            'blur': '_onBlur'
        }),
        
        init: function () {
            this._super.apply(this, arguments);
            this.lastScanned = false;
        },
        
        willStart: function() {
            var self = this;
            return this._super.apply(this, arguments).then(function() {
                // Asegurarse de que los estilos estén cargados
                self._loadCSS();
            });
        },
        
        _loadCSS: function() {
            // Crear CSS dinámicamente si no se carga desde el archivo
            if ($('style.barcode_handler_style').length === 0) {
                var css = `
                    .o_field_barcode_handler {
                        padding: 8px 12px !important;
                        border: 2px solid #7C7BAD !important;
                        border-radius: 4px !important;
                        background-color: #f8f9fa !important;
                        margin-bottom: 10px !important;
                        font-size: 16px !important;
                        width: 100% !important;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
                        transition: all 0.3s ease !important;
                    }
                    
                    .o_field_barcode_handler:focus {
                        border-color: #875A7B !important;
                        box-shadow: 0 0 0 3px rgba(135, 90, 123, 0.25) !important;
                        outline: none !important;
                    }
                    
                    .o_field_barcode_handler::placeholder {
                        color: #adb5bd !important;
                    }
                    
                    .o_barcode_scanner_input {
                        position: relative !important;
                    }
                    
                    .o_barcode_scanner_input:before {
                        content: "\\f02a" !important;
                        font-family: FontAwesome !important;
                        position: absolute !important;
                        left: 10px !important;
                        top: 8px !important;
                        font-size: 18px !important;
                        color: #7C7BAD !important;
                    }
                `;
                $('<style class="barcode_handler_style">' + css + '</style>').appendTo('head');
            }
        },
        
        _onFocus: function() {
            this.lastScanned = false;
        },
        
        _onBlur: function() {
            var self = this;
            if (this.lastScanned) {
                // Si acabamos de escanear, recuperar el foco
                setTimeout(function() {
                    self.$el.focus();
                }, 100);
            }
        },
        
        _onKeydown: function (event) {
            // Si se presiona la tecla Enter, simular un escaneo de código de barras
            if (event.which === 13) {
                event.preventDefault();
                var barcode = this.$el.val();
                if (barcode) {
                    this.$el.val('');
                    this.lastScanned = true;
                    this._processBarcode(barcode);
                }
            }
        },
        
        _processBarcode: function (barcode) {
            var self = this;
            
            // Mostrar un indicador visual de escaneo
            this._showScanEffect();
            
            // Llamar al método on_barcode_scanned del modelo
            this._rpc({
                model: this.model,
                method: 'on_barcode_scanned',
                args: [this.res_id, barcode],
                context: this.record.getContext(),
            }).then(function (result) {
                if (result) {
                    if (result.warning) {
                        self.do_warn(result.warning.title, result.warning.message, false);
                    } else if (result.success) {
                        self.do_notify(_t('Éxito'), result.success, false);
                        self.trigger_up('reload');
                    }
                }
                // Recuperar el foco
                setTimeout(function() {
                    self.$el.focus();
                }, 200);
            }).fail(function (error) {
                var message = '';
                if (error.message && error.message.data) {
                    message = error.message.data.message || '';
                }
                self.do_warn(_t('Error'), message || _t('Ha ocurrido un error al procesar el código de barras'), false);
                // Recuperar el foco
                setTimeout(function() {
                    self.$el.focus();
                }, 200);
            });
        },
        
        _showScanEffect: function() {
            // Efecto visual para indicar escaneo
            var $el = this.$el;
            $el.css('background-color', '#e0f7fa');
            setTimeout(function() {
                $el.css('background-color', '#f8f9fa');
            }, 300);
        },
        
        _renderEdit: function () {
            this._super.apply(this, arguments);
            // Establecer un placeholder útil
            this.$el.attr('placeholder', _t('Escanear o introducir código de barras aquí'));
            
            // Aplicar clase para estilos adicionales
            this.$el.wrap('<div class="o_barcode_scanner_input"></div>');
            
            // Establecer el foco automáticamente si estamos en estado borrador o en progreso
            if (this.recordData && (this.recordData.state === 'draft' || this.recordData.state === 'in_progress')) {
                var self = this;
                setTimeout(function() {
                    self.$el.focus();
                }, 100);
            }
        }
    });

    // Registrar el widget en el registro de campos
    registry.add('barcode_handler', BarcodeHandlerWidget);

    return BarcodeHandlerWidget;
});