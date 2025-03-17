from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockLocationTransferAddProduct(models.TransientModel):
    _name = 'stock.location.transfer.add.product'
    _description = 'Asistente para Añadir Productos'
    
    transfer_id = fields.Many2one('stock.location.transfer', 'Transferencia', required=True)
    product_id = fields.Many2one('product.product', 'Producto', required=True, 
                                domain=[('type', '!=', 'service')])
    product_qty = fields.Float('Cantidad', default=1.0, required=True)
    product_uom_id = fields.Many2one('uom.uom', 'Unidad de Medida')
    
    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id.id
    
    def add_product(self):
        """Añadir producto a la transferencia"""
        self.ensure_one()
        if self.transfer_id.state != 'draft':
            raise UserError(_('Solo puede añadir productos en transferencias en estado borrador.'))
        
        # Validar cantidad
        if self.product_qty <= 0:
            raise UserError(_('La cantidad debe ser mayor que cero.'))
        
        self.transfer_id._add_product(self.product_id, self.product_qty)
        
        # Mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Producto añadido'),
                'message': _('Se ha añadido %s %s a la transferencia.') % (self.product_qty, self.product_id.name),
                'type': 'success',
                'sticky': False,
            }
        }