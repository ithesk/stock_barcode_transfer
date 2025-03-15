from odoo import models, fields, api, _
import logging
import tempfile

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    def generate_barcode(self):
        """Generar códigos de barras para todas las variantes del producto"""
        for product in self.product_variant_ids:
            if not product.barcode:
                barcode = f"P{product.id:08d}"
                product.barcode = barcode
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Códigos Generados'),
                'message': _('Se han generado códigos de barras para las variantes de producto.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def print_product_barcode(self):
        """Imprimir etiqueta de código de barras para la plantilla de producto"""
        self.ensure_one()
        if self.product_variant_count == 1:
            return self.product_variant_ids.print_barcode_label()
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _('Esta plantilla tiene múltiples variantes. Por favor, seleccione una variante específica para imprimir su código de barras.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
    
    @api.model
    def print_product_barcode_static(self, ids):
        """Método estático para imprimir códigos de barras desde enlaces en la interfaz"""
        products = self.browse(ids)
        if len(products) == 1 and products.product_variant_count == 1:
            return products.product_variant_ids.print_barcode_label()
        elif len(products) > 1:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Información'),
                    'message': _('Por favor, seleccione un solo producto para imprimir su código de barras.'),
                    'type': 'info',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _('Este producto tiene múltiples variantes. Por favor, seleccione una variante específica.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    def generate_barcode(self):
        """Generar un código de barras para producto que no tienen"""
        for product in self:
            if not product.barcode:
                # Generar un código único basado en el ID y un prefijo
                barcode = f"P{product.id:08d}"
                product.barcode = barcode
                _logger.info(f'Código de barras generado para el producto {product.name}: {barcode}')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Código Generado'),
                'message': _('Se ha generado un código de barras para el producto.'),
                'type': 'success',
                'sticky': False,
            }
        }
                
    def print_barcode_label(self):
        """Imprimir etiqueta con código de barras para el producto"""
        self.ensure_one()
        
        # Asegurar que el producto tiene un código de barras
        if not self.barcode:
            self.generate_barcode()
            
        # Obtener la impresora de códigos de barras
        try:
            printer = self.env['barcode.printer'].get_default_printer()
        except:
            printer = False
            
        if printer:
            # Usar la impresora configurada
            try:
                transfer_obj = self.env['stock.location.transfer']
                result = transfer_obj._print_product_label(self)
                
                if result:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Éxito'),
                            'message': _('La etiqueta para %s se ha enviado a la impresora.') % self.name,
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Error'),
                            'message': _('Ha ocurrido un error al imprimir la etiqueta. Revise el registro de errores.'),
                            'type': 'warning',
                            'sticky': False,
                        }
                    }
            except Exception as e:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': str(e),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
        else:
            # Usar el informe de etiqueta predefinido si no hay impresora configurada
            return self.env.ref('stock_barcode_transfer.report_product_barcode').report_action(self)
    
    @api.model
    def bulk_generate_barcodes(self):
        """Generar códigos de barras para todos los productos seleccionados sin código"""
        count = 0
        for product in self:
            if not product.barcode:
                barcode = f"P{product.id:08d}"
                product.barcode = barcode
                count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Códigos de Barras Generados'),
                'message': _('Se han generado %s códigos de barras.') % count,
                'type': 'success',
                'sticky': False,
            }
        }