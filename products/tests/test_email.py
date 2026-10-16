import os
import unittest
from unittest.mock import MagicMock, patch

from products.email_service import bill_text, bill_html, invoice_pdf, send_sale_email
from products.services import Store
from products.tests.fakedb import FakeDB


def sample_sale(email='customer@example.com'):
    return {
        'id': 'sale_123',
        'bill_number': 'AJ-000001',
        'bill': 'AJ-000001',
        'customer_name': 'Rohit Sharma',
        'customer_mobile': '9876543210',
        'customer_email': email,
        'items': [
            {
                'name': 'Everyday Tee',
                'colour': 'Blue',
                'size': 'M',
                'price': 499.0,
                'qty': 2,
                'line_total': 998.0,
            }
        ],
        'subtotal': 998.0,
        'discount_percent': 10,
        'discount': 99.8,
        'rounding_adjustment': 0.8,
        'total': 899.0,
        'payment_method': 'UPI',
        'created_at': '2026-10-16T12:00:00+00:00',
    }


class EmailServiceTests(unittest.TestCase):
    def test_pdf_generation(self):
        sale = sample_sale()
        pdf_bytes = invoice_pdf(sale)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 500)
        # Check PDF header magic bytes %PDF-
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_bill_text(self):
        sale = sample_sale()
        text = bill_text(sale)
        self.assertIn('Dear Rohit Sharma,', text)
        self.assertIn('Thank you for shopping with us!', text)
        self.assertIn('Bill-AJ-000001.pdf', text)
        self.assertNotIn('Return Policy:', text)
        self.assertIn('The AJ Clothing Store Team', text)
        # Ensure items and calculation lines are not cluttering the email body
        self.assertNotIn('Everyday Tee', text)
        self.assertNotIn('Total Amount:', text)

    def test_bill_html(self):
        sale = sample_sale()
        html = bill_html(sale, logo_cid='store_logo')
        self.assertIn('Dear Rohit Sharma,', html)
        self.assertIn('Thank you for shopping with us!', html)
        self.assertIn('Please find your bill attached as a PDF', html)
        self.assertIn('cid:store_logo', html)
        self.assertNotIn('Return Policy:', html)
        self.assertIn('The AJ Clothing Store Team', html)
        # Ensure items and calculation tables are not cluttering the email body
        self.assertNotIn('Everyday Tee', html)
        self.assertNotIn('Subtotal', html)

    def test_send_sale_email_skipped_without_email(self):
        sale = sample_sale(email='')
        res = send_sale_email(sale)
        self.assertEqual(res['status'], 'skipped')

    @patch.dict(os.environ, {'EMAIL_HOST_USER': '', 'EMAIL_HOST_PASSWORD': ''})
    def test_send_sale_email_missing_credentials(self):
        sale = sample_sale()
        res = send_sale_email(sale)
        self.assertEqual(res['status'], 'failed')
        self.assertIn('not configured', res['error'])

    @patch('smtplib.SMTP')
    @patch.dict(os.environ, {
        'EMAIL_HOST_USER': 'test@example.com',
        'EMAIL_HOST_PASSWORD': 'secretpassword',
    })
    def test_send_sale_email_success(self, mock_smtp_class):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.sendmail.return_value = {}

        sale = sample_sale()
        res = send_sale_email(sale)
        self.assertEqual(res['status'], 'sent')
        self.assertEqual(res['recipient'], 'customer@example.com')
        self.assertTrue(mock_smtp.starttls.called)
        self.assertTrue(mock_smtp.login.called)
        self.assertTrue(mock_smtp.sendmail.called)

    @patch('smtplib.SMTP')
    @patch.dict(os.environ, {
        'EMAIL_HOST_USER': 'test@example.com',
        'EMAIL_HOST_PASSWORD': 'secretpassword',
    })
    def test_send_sale_email_smtp_failure(self, mock_smtp_class):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.sendmail.side_effect = RuntimeError('SMTP connection dropped')

        sale = sample_sale()
        res = send_sale_email(sale)
        self.assertEqual(res['status'], 'failed')
        self.assertIn('SMTP connection dropped', res['error'])


class StoreEmailIntegrationTests(unittest.TestCase):
    def test_update_sale_in_store(self):
        db = FakeDB({'sales': {'sale_1': {'id': 'sale_1', 'bill_number': 'AJ-000001'}}})
        store = Store(db)
        updated = store.update_sale('sale_1', {'email_status': 'sent', 'email_sent_at': '2026-10-16T12:00:00Z'})
        self.assertEqual(updated['email_status'], 'sent')
        self.assertEqual(db.reference('sales/sale_1').get()['email_status'], 'sent')

    def test_store_settings_get_and_update(self):
        db = FakeDB({})
        store = Store(db)
        self.assertEqual(store.get_store_settings(), {})
        updated = store.update_store_settings({
            'name': 'Custom Boutique',
            'phone': '+91 99999 88888',
            'note': 'No exchange after 3 days.',
        })
        self.assertEqual(updated['name'], 'Custom Boutique')
        self.assertEqual(updated['phone'], '+91 99999 88888')
        self.assertEqual(store.get_store_settings()['name'], 'Custom Boutique')

    @patch.dict(os.environ, {
        'STORE_NAME': 'Env Store Name',
        'STORE_PHONE': '+91 11111 22222',
    })
    def test_resolve_store_info_with_env(self):
        from products.email_service import resolve_store_info
        resolved = resolve_store_info()
        self.assertEqual(resolved['name'], 'Env Store Name')
        self.assertEqual(resolved['phone'], '+91 11111 22222')

        # Custom store overrides env
        custom = resolve_store_info({'name': 'Direct Override'})
        self.assertEqual(custom['name'], 'Direct Override')
        self.assertEqual(custom['phone'], '+91 11111 22222')


if __name__ == '__main__':
    unittest.main()
