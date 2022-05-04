
import logging


_logger = logging.getLogger(__name__)

REMOVE_TABLES = [
    ('common_log_lines_ept', 'common.log.lines.ept'),
    ('common_log_book_ept', 'common.log.book.ept'),
    ('data_queue_mixin_ept', 'data.queue.mixin.ept'),
    ('sale_workflow_process_ept', 'sale.workflow.process.ept'),
    ('vendor_stock_ept', 'vendor.stock.ept')
]

REMOVE_COLUMNS = [
    ('res_config_settings', 'tax_calculation_method'),
    ('res_config_settings', 'is_use_odoo_order_sequence')
]

REMOVE_VIEWS = [
    ('res.config.settings', 'Magento Website Settings'),
    ('res.config.settings', 'Magento Storeview Settings')
]

def migrate(cr, installed_version):
    with cr.savepoint():

        for db_table, table in REMOVE_TABLES:
            # remove table from the db
            cr.execute('SELECT table_name FROM information_schema.tables where table_name = %s', (db_table,))
            if cr.dictfetchall():
                _logger.info(f'removing table {db_table}')
                cr.execute(f'DROP TABLE {db_table}')

            # remove table from the odoo
            if not table:
                continue

            _logger.debug('checking odoo registry')
            cr.execute('SELECT id FROM ir_model WHERE model = %s', (table,))
            model = cr.dictfetchone()

            if not model:
                continue

            _logger.debug(f'removing model {table}({model["id"]}) from odoo registry')
            cr.execute('DELETE FROM ir_model_relation WHERE model = %(id)s', model)
            cr.execute('DELETE FROM ir_model WHERE id = %(id)s', model)

        for table, field in REMOVE_COLUMNS:
            cr.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "{field}"', (table, field))
            cr.execute('DELETE FROM ir_model_fields WHERE model = %s and name = %s', (table.replace('_','.'), field))

        _logger.info('removing views')
        for model, name in REMOVE_VIEWS:
            cr.execute('DELETE FROM ir_ui_view WHERE model = %s and name = %s', (model, name))

    _logger.info('migration finished')
