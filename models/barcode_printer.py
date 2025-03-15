# -*- coding: utf-8 -*-
# En un nuevo archivo: models/barcode_printer.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import cups
import logging

_logger = logging.getLogger(__name__)

class BarcodePrinter(models.Model):
    _name = 'barcode.printer'
    _description = 'Impresora de Códigos de Barras'
    _order = 'name'

    name = fields.Char('Nombre', required=True)
    cups_server = fields.Char('Servidor CUPS', default='localhost', 
                            help='Dirección IP o nombre del servidor CUPS (localhost para servidor local)')
    cups_port = fields.Integer('Puerto CUPS', default=631)
    printer_name = fields.Char('Nombre de Impresora en CUPS', required=True,
                              help='Nombre exacto de la impresora en el servidor CUPS')
    printer_type = fields.Selection([
        ('brother_ql810w', 'Brother QL-810W'),
        ('zebra', 'Zebra'),
        ('dymo', 'Dymo LabelWriter'),
        ('generic', 'Impresora Genérica')
    ], string='Tipo de Impresora', default='brother_ql810w', required=True)
    
    paper_width = fields.Selection([
        ('12', '12mm'),
        ('29', '29mm'),
        ('38', '38mm'),
        ('50', '50mm'),
        ('54', '54mm'),
        ('62', '62mm'),
        ('102', '102mm')
    ], string='Ancho de Papel', default='38')
    
    paper_length = fields.Selection([
        ('0', 'Continuo (corte automático)'),
        ('90', '90mm'),
        ('30', '30mm'),
        ('40', '40mm'),
        ('50', '50mm'),
        ('60', '60mm')
    ], string='Largo de Papel', default='0')
    
    active = fields.Boolean('Activo', default=True)
    default = fields.Boolean('Impresora Predeterminada', default=False)
    
    @api.model
    def create(self, vals):
        if vals.get('default'):
            # Desactivar otras impresoras predeterminadas
            self.search([('default', '=', True)]).write({'default': False})
        return super(BarcodePrinter, self).create(vals)
    
    def write(self, vals):
        if vals.get('default'):
            # Desactivar otras impresoras predeterminadas
            self.search([('default', '=', True), ('id', '!=', self.id)]).write({'default': False})
        return super(BarcodePrinter, self).write(vals)
    
    def test_connection(self):
        """Probar la conexión con el servidor CUPS y verificar la impresora"""
        self.ensure_one()
        try:
            # Conectar al servidor CUPS
            conn = cups.Connection(host=self.cups_server, port=self.cups_port)
            
            # Verificar si la impresora existe
            printers = conn.getPrinters()
            if self.printer_name not in printers:
                available_printers = ", ".join(list(printers.keys()))
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Impresora %s no encontrada en el servidor CUPS. Impresoras disponibles: %s') % 
                                  (self.printer_name, available_printers),
                        'type': 'danger',
                        'sticky': False,
                    }
                }
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('Conexión exitosa con el servidor CUPS. Impresora %s está disponible.') % 
                              self.printer_name,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error al conectar con el servidor CUPS: %s') % str(e),
                    'type': 'danger',
                    'sticky': False,
                }
            }
    
    def print_test_label(self):
        """Imprimir una etiqueta de prueba"""
        self.ensure_one()
        
        try:
            # Conectar al servidor CUPS
            conn = cups.Connection(host=self.cups_server, port=self.cups_port)
            
            # Generar datos para la etiqueta de prueba
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
            
            test_content = f"""
ETIQUETA DE PRUEBA
Impresora: {self.name}
Servidor: {self.cups_server}
Fecha: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            temp_file.write(test_content.encode('utf-8'))
            temp_file.close()
            
            # Configurar opciones de impresión
            media_size = f"{self.paper_width}x{self.paper_length if self.paper_length != '0' else '90'}"
            options = {
                "media": media_size,
                "orientation-requested": "3"  # Paisaje
            }
            
            # Imprimir la etiqueta
            conn.printFile(self.printer_name, temp_file.name, 'Test Label', options)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('Etiqueta de prueba enviada a la impresora %s') % self.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error al imprimir etiqueta de prueba: %s') % str(e),
                    'type': 'danger',
                    'sticky': False,
                }
            }
    
    @api.model
    def get_default_printer(self):
        """Obtener la impresora predeterminada"""
        printer = self.search([('default', '=', True), ('active', '=', True)], limit=1)
        if not printer:
            printer = self.search([('active', '=', True)], limit=1)
        return printer