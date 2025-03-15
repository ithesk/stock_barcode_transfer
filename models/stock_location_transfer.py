# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import base64
from datetime import datetime
import cups
import tempfile
import os 

_logger = logging.getLogger(__name__)

class StockLocationTransfer(models.Model):
    _name = 'stock.location.transfer'
    _description = 'Transferencia entre Localidades con Código de Barras'
    _inherit = ['barcodes.barcode_events_mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Referencia', required=True, copy=False, readonly=True, 
                      default=lambda self: _('Nuevo'))
    date = fields.Datetime('Fecha', default=fields.Datetime.now, required=True)
    user_id = fields.Many2one('res.users', 'Responsable', default=lambda self: self.env.user)
    origin_location_id = fields.Many2one('stock.location', 'Ubicación Origen', required=True,
                                         domain=[('usage', '=', 'internal')])
    dest_location_id = fields.Many2one('stock.location', 'Ubicación Destino', required=True,
                                       domain=[('usage', '=', 'internal')])
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('in_progress', 'En Progreso'),
        ('done', 'Realizado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft')
    transfer_line_ids = fields.One2many('stock.location.transfer.line', 'transfer_id', 'Líneas de Transferencia')
    note = fields.Text('Notas')
    company_id = fields.Many2one('res.company', 'Compañía', default=lambda self: self.env.user.company_id)
    picking_id = fields.Many2one('stock.picking', 'Albarán Relacionado', readonly=True)
    reception_validated = fields.Boolean('Recepción Validada', default=False)
    scanned_product_code = fields.Char('Escanear Producto', store=False)
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('Nuevo')) == _('Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.location.transfer') or _('Nuevo')
        return super(StockLocationTransfer, self).create(vals)
    
    def action_start(self):
        self.ensure_one()
        if not self.transfer_line_ids:
            raise UserError(_('No puede iniciar una transferencia sin productos.'))
        self.state = 'in_progress'
    
    def action_done(self):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_('Solo puede finalizar transferencias que estén en progreso.'))
        
        # Validar que todos los productos se han recibido correctamente
        for line in self.transfer_line_ids:
            if line.qty_done < line.product_qty:
                raise UserError(_('El producto %s no ha sido completamente recibido.') % line.product_id.name)
        
        # Crear movimiento de stock
        picking_type_id = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('default_location_src_id', '=', self.origin_location_id.id),
            ('default_location_dest_id', '=', self.dest_location_id.id),
        ], limit=1)
        
        if not picking_type_id:
            picking_type_id = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
            ], limit=1)
        
        picking_vals = {
            'picking_type_id': picking_type_id.id,
            'location_id': self.origin_location_id.id,
            'location_dest_id': self.dest_location_id.id,
            'scheduled_date': self.date,
            'origin': self.name,
            'company_id': self.company_id.id,
        }
        
        picking = self.env['stock.picking'].create(picking_vals)
        self.picking_id = picking.id
        
        for line in self.transfer_line_ids:
            self.env['stock.move'].create({
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_done,
                'product_uom': line.product_uom_id.id,
                'picking_id': picking.id,
                'location_id': self.origin_location_id.id,
                'location_dest_id': self.dest_location_id.id,
            })
        
        # Confirmar albarán
        picking.action_confirm()
        picking.action_assign()
        
        # Validar albarán automáticamente
        for move_line in picking.move_line_ids:
            related_line = self.transfer_line_ids.filtered(lambda l: l.product_id.id == move_line.product_id.id)
            if related_line:
                move_line.qty_done = related_line.qty_done
        
        picking.button_validate()
        self.state = 'done'
        
        return True
    
    def action_cancel(self):
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_('No puede cancelar una transferencia finalizada.'))
        self.state = 'cancelled'
    
    def action_print_reception_report(self):
        self.ensure_one()
        return self.env.ref('stock_barcode_transfer.report_reception_transfer').report_action(self)
    
    def _add_product(self, product, qty=1.0):
        """Añadir producto a la transferencia mediante código de barras"""
        if not product:
            return False
        
        line = self.transfer_line_ids.filtered(lambda l: l.product_id.id == product.id)
        if line:
            line.product_qty += qty
        else:
            vals = {
                'transfer_id': self.id,
                'product_id': product.id,
                'product_qty': qty,
                'product_uom_id': product.uom_id.id,
            }
            self.env['stock.location.transfer.line'].create(vals)
        return True
    
    def on_barcode_scanned(self, barcode):
        """Método para manejar el escaneo de códigos de barras"""
        if self.state not in ['draft', 'in_progress']:
            raise UserError(_('Solo puede escanear productos en transferencias en borrador o en progreso.'))
        
        # Intentar encontrar el producto por código de barras
        product = self.env['product.product'].search([
            '|', ('barcode', '=', barcode), ('default_code', '=', barcode)
        ], limit=1)
        
        if not product:
            return {'warning': {
                'title': _('Advertencia'),
                'message': _('Producto no encontrado para el código de barras: %s') % barcode,
            }}
        
        if self.state == 'draft':
            # En estado borrador, añadimos productos a la transferencia
            self._add_product(product)
            return {'success': _('Producto %s añadido a la transferencia.') % product.name}
        
        elif self.state == 'in_progress':
            # En estado en progreso, validamos la recepción
            line = self.transfer_line_ids.filtered(lambda l: l.product_id.id == product.id)
            if not line:
                return {'warning': {
                    'title': _('Advertencia'),
                    'message': _('Este producto no está en la lista de transferencia: %s') % product.name,
                }}
            
            if line.qty_done >= line.product_qty:
                return {'warning': {
                    'title': _('Advertencia'),
                    'message': _('La cantidad recibida del producto %s ya alcanzó lo planificado.') % product.name,
                }}
            
            line.qty_done += 1
            
            # Si el producto no tiene etiqueta, imprimir una
            if not product.barcode:
                self._print_product_label(product)
            
            return {'success': _('Producto %s validado. Recibido: %s/%s') % 
                   (product.name, line.qty_done, line.product_qty)}
    

    def _print_product_label(self, product):
        """Imprimir etiqueta para un producto usando la impresora configurada"""
        try:
            _logger.info(f"Iniciando impresión de etiqueta para producto: {product.name}")
            
            # Obtener la impresora configurada
            printer = self.env['barcode.printer'].get_default_printer()
            if not printer:
                _logger.error("No hay impresora predeterminada configurada")
                raise UserError(_('No hay impresora de códigos de barras configurada como predeterminada.'))
            
            _logger.info(f"Usando impresora: {printer.name} en servidor: {printer.cups_server}")
            
            # Conectar al servidor CUPS configurado
            try:
                conn = cups.Connection(host=printer.cups_server, port=printer.cups_port)
                _logger.info(f"Conexión a CUPS establecida correctamente con servidor {printer.cups_server}")
            except Exception as e:
                _logger.error(f"Error al conectar con CUPS en {printer.cups_server}: {str(e)}")
                raise UserError(_('Error al conectar con el servidor de impresión en %s: %s') % (printer.cups_server, str(e)))
            
            # Verificar que la impresora existe en CUPS
            printers = conn.getPrinters()
            if printer.printer_name not in printers:
                _logger.error(f"Impresora {printer.printer_name} no encontrada en el servidor CUPS")
                available_printers = ", ".join(list(printers.keys()))
                raise UserError(_('Impresora %s no encontrada en el servidor CUPS. Impresoras disponibles: %s') % 
                            (printer.printer_name, available_printers))
            
            # Generar datos para la etiqueta
            _logger.info(f"Generando etiqueta para el producto: {product.name}")
            label_path = self._generate_label_brother(product, printer)
            _logger.info(f"Etiqueta generada en: {label_path}")
            
            # Configurar opciones de impresión según la configuración
            media_size = f"{printer.paper_width}x{printer.paper_length if printer.paper_length != '0' else '90'}"
            options = {
                "media": media_size,
                "orientation-requested": "3"  # Paisaje
            }
            _logger.info(f"Opciones de impresión: {options}")
            
            # Imprimir la etiqueta
            _logger.info(f"Enviando trabajo a la impresora {printer.printer_name}...")
            conn.printFile(printer.printer_name, label_path, 'Product Label - ' + product.name, options)
            _logger.info(f"Trabajo de impresión enviado correctamente")
            
            # Registrar en el historial
            # self.message_post(body=_("Etiqueta impresa para el producto %s en impresora %s") % 
                            # (product.name, printer.name), subject=_("Etiqueta impresa"))
            
            return True
        
        except Exception as e:
            error_msg = str(e)
            _logger.error(f'Error al imprimir etiqueta: {error_msg}', exc_info=True)
            self.message_post(body=_("Error al imprimir etiqueta para %s: %s") % 
                            (product.name, error_msg), subject=_("Error de impresión"))
            
            return False
            
    def _generate_label_brother(self, product, printer):
        """Generar etiqueta para la impresora Brother configurada"""
        try:
            # Intentar usar brother_ql si está disponible
            from brother_ql.conversion import convert
            from brother_ql.raster import BrotherQLRaster
            from PIL import Image, ImageDraw, ImageFont
            import io
            import os
            import tempfile
            
            _logger.info(f"Generando etiqueta para {product.name} con ancho {printer.paper_width}mm")
            
            barcode = product.barcode or product.default_code or f"P{product.id:08d}"
            if not product.barcode:
                # Si el producto no tiene código de barras, asignarle uno
                product.barcode = barcode
            
            # Crear dimensiones de imagen basadas en el tamaño del papel
            width_mm = int(printer.paper_width)
            # Convertir mm a píxeles (aproximado a 96 DPI)
            width_px = int(width_mm * 3.8)  # ~3.8 píxeles por mm a 96 DPI
            height_px = 200  # Altura fija para papel continuo
            
            # Crear la imagen para la etiqueta
            img = Image.new('RGB', (width_px, height_px), color='white')
            draw = ImageDraw.Draw(img)
            
            # Intentar cargar una fuente, usar default si falla
            try:
                font_large = ImageFont.truetype('DejaVuSans.ttf', width_px // 10)
                font_medium = ImageFont.truetype('DejaVuSans.ttf', width_px // 14)
                font_small = ImageFont.truetype('DejaVuSans.ttf', width_px // 18)
            except IOError:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Dibujar el contenido ajustado al ancho
            # Dividir el nombre del producto si es necesario
            product_name = product.name
            y_position = 10
            
            # Calcular caracteres por línea basados en el ancho
            chars_per_line = width_px // 8  # ~8 píxeles por carácter en promedio
            
            if len(product_name) > chars_per_line:
                words = product_name.split()
                current_line = ""
                
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if len(test_line) <= chars_per_line:
                        current_line = test_line
                    else:
                        draw.text((10, y_position), current_line, font=font_large, fill='black')
                        y_position += font_large.size + 2
                        current_line = word
                
                if current_line:
                    draw.text((10, y_position), current_line, font=font_large, fill='black')
                    y_position += font_large.size + 5
            else:
                draw.text((10, y_position), product_name, font=font_large, fill='black')
                y_position += font_large.size + 5
            
            # Añadir línea divisoria
            draw.line([(10, y_position), (width_px - 10, y_position)], fill='black', width=1)
            y_position += 10
            
            # Código de barras (texto)
            draw.text((10, y_position), f"Código: {barcode}", font=font_medium, fill='black')
            y_position += font_medium.size + 5
            
            # Referencia interna si existe
            if product.default_code:
                draw.text((10, y_position), f"Ref: {product.default_code}", font=font_medium, fill='black')
                y_position += font_medium.size + 5
            
            # Fecha de impresión
            from datetime import datetime
            current_date = datetime.now().strftime("%d/%m/%Y")
            draw.text((10, y_position), f"Fecha: {current_date}", font=font_small, fill='black')
            
            # Crear un archivo temporal para la imagen
            temp_img_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            img.save(temp_img_file.name)
            temp_img_file.close()
            
            # Crear un archivo temporal para el archivo binario de la impresora
            temp_bin_file = tempfile.NamedTemporaryFile(delete=False, suffix='.bin')
            temp_bin_file.close()
            
            # Convertir la imagen al formato de la impresora
            # Extraer solo el nombre del modelo "QL-810W" del valor completo "Brother QL-810W"
            model_name = 'QL-810W'
            if 'QL-820' in printer.printer_type:
                model_name = 'QL-820NWB'
                
            _logger.info(f"Usando modelo de impresora: {model_name}")
            
            qlr = BrotherQLRaster(model_name)
            convert(
                qlr, 
                [temp_img_file.name], 
                printer.paper_width,
                threshold=70, 
                cut=True
            )
            
            # Guardar los datos rasterizados en el archivo temporal
            with open(temp_bin_file.name, 'wb') as f:
                f.write(qlr.data)
            
            # Eliminar el archivo temporal de imagen
            try:
                os.unlink(temp_img_file.name)
            except:
                _logger.warning(f"No se pudo eliminar el archivo temporal: {temp_img_file.name}")
            
            return temp_bin_file.name
            
        except Exception as e:
            _logger.error(f'Error al generar etiqueta: {str(e)}', exc_info=True)
            return self._generate_generic_label(product)
                
    def _generate_generic_label(self, product):
        """Generar una etiqueta genérica en formato de texto"""
        barcode = product.barcode or product.default_code or f"P{product.id:08d}"
        if not product.barcode:
            # Si el producto no tiene código de barras, asignarle uno
            product.barcode = barcode
        
        # Crear un archivo temporal para la etiqueta
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        
        # Escribir el contenido de texto para la etiqueta
        label_content = f"""
    Producto: {product.name}
    Código: {barcode}
    Ref: {product.default_code or ''}
    Fecha: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        temp_file.write(label_content.encode('utf-8'))
        temp_file.close()
        
        return temp_file.name

    def _generate_zpl_label(self, product):
        """Generar código ZPL para la impresora de etiquetas"""
        # Aquí generamos el ZPL para la etiqueta
        # Este es un ejemplo básico, ajustar según las necesidades y tipo de impresora
        barcode = product.barcode or product.default_code or str(product.id)
        
        zpl_code = f"""
^XA
^FO50,50^A0N,30,30^FD{product.name}^FS
^FO50,100^BY3^BCN,100,Y,N,N^FD{barcode}^FS
^FO50,220^A0N,20,20^FDRef: {product.default_code or ''}^FS
^XZ
"""
        
        # Guardar el código ZPL en un archivo temporal
        with open('/tmp/product_label.zpl', 'w') as f:
            f.write(zpl_code)
        
        return zpl_code
    
    def validate_all_reception(self):
        """Validar la recepción completa de todos los productos"""
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_('Solo puede validar la recepción en transferencias en progreso.'))
        
        for line in self.transfer_line_ids:
            # Ajustar las cantidades recibidas a las planificadas
            line.qty_done = line.product_qty
        
        self.reception_validated = True
        return True
    
    def action_view_picking(self):
        """Ver el albarán relacionado"""
        self.ensure_one()
        if not self.picking_id:
            return
        
        return {
            'name': _('Albarán'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
            'context': self.env.context,
        }


class StockLocationTransferLine(models.Model):
    _name = 'stock.location.transfer.line'
    _description = 'Línea de Transferencia entre Localidades'

    transfer_id = fields.Many2one('stock.location.transfer', 'Transferencia', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Producto', required=True)
    product_qty = fields.Float('Cantidad Planificada', default=1.0, required=True)
    qty_done = fields.Float('Cantidad Recibida', default=0.0)
    product_uom_id = fields.Many2one('uom.uom', 'Unidad de Medida', required=True)
    state = fields.Selection(related='transfer_id.state', string='Estado', store=True)
    lot_id = fields.Many2one('stock.production.lot', 'Lote/Número de Serie')
    is_damaged = fields.Boolean('Dañado', default=False)
    damage_notes = fields.Text('Notas de Daño')
    
    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id.id
    
    @api.constrains('product_qty')
    def _check_product_qty(self):
        for line in self:
            if line.product_qty <= 0:
                raise ValidationError(_('La cantidad planificada debe ser mayor que cero.'))
    
    def mark_as_damaged(self):
        """Marcar un producto como dañado para saneamiento"""
        self.ensure_one()
        return {
            'name': _('Registrar Daño'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.location.transfer.damage.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_transfer_line_id': self.id}
        }


class StockLocationTransferDamageWizard(models.TransientModel):
    _name = 'stock.location.transfer.damage.wizard'
    _description = 'Asistente para Registro de Daños'

    transfer_line_id = fields.Many2one('stock.location.transfer.line', 'Línea de Transferencia', required=True)
    damage_notes = fields.Text('Descripción del Daño', required=True)
    action = fields.Selection([
        ('repair', 'Enviar a Reparación'),
        ('scrap', 'Desechar'),
        ('return', 'Devolver al Proveedor')
    ], string='Acción a Realizar', required=True, default='repair')
    
    def confirm_damage(self):
        """Confirmar daño y aplicar acción"""
        self.ensure_one()
        
        # Marcar como dañado
        self.transfer_line_id.write({
            'is_damaged': True,
            'damage_notes': self.damage_notes
        })
        
        # Crear acción correspondiente según el tipo de daño
        if self.action == 'scrap':
            # Crear orden de desecho
            scrap_vals = {
                'product_id': self.transfer_line_id.product_id.id,
                'scrap_qty': self.transfer_line_id.qty_done,
                'product_uom_id': self.transfer_line_id.product_uom_id.id,
                'location_id': self.transfer_line_id.transfer_id.dest_location_id.id,
                'origin': self.transfer_line_id.transfer_id.name,
                'company_id': self.transfer_line_id.transfer_id.company_id.id,
            }
            scrap = self.env['stock.scrap'].create(scrap_vals)
            scrap.action_validate()
        
        elif self.action == 'return':
            # Lógica para devolución al proveedor
            # (Aquí se implementaría la creación de una devolución a proveedor)
            pass
        
        elif self.action == 'repair':
            # Lógica para enviar a reparación
            # (Aquí se implementaría la creación de una orden de reparación)
            pass
        
        return {'type': 'ir.actions.act_window_close'}


# Clase para reportes
class ReceptionTransferReport(models.AbstractModel):
    _name = 'report.stock_barcode_transfer.report_reception'
    _description = 'Reporte de Recepción de Transferencia'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.location.transfer'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'stock.location.transfer',
            'docs': docs,
            'data': data,
        }