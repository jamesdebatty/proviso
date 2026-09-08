import unittest

from pricing.invoice import invoice_total


class InvoiceTotalTest(unittest.TestCase):
    def test_sums_lines(self):
        self.assertEqual(invoice_total([(3, 2.50, 0.0), (2, 10.00, 0.25)]), 22.50)

    def test_empty_invoice(self):
        self.assertEqual(invoice_total([]), 0)
