from decimal import Decimal
from django.test import TestCase
from apps.core.utils import to_safe_decimal, safe_divide, calculate_growth_rate

class CoreCalculationsTestCase(TestCase):
    def test_decimal_precision(self):
        d1 = to_safe_decimal('1,234.567', precision='0.01')
        self.assertEqual(d1, Decimal('1234.57'))

        d2 = to_safe_decimal('(500.20)', precision='0.01')
        self.assertEqual(d2, Decimal('-500.20'))

        d3 = to_safe_decimal('₹ 10,000.50', precision='0.01')
        self.assertEqual(d3, Decimal('10000.50'))

    def test_safe_divide_and_zero_denominator(self):
        res = safe_divide(100, 4)
        self.assertEqual(res, Decimal('25.0000'))

        # Non-negotiable honest data rule: zero denominator returns None, never crashes or invents numbers
        zero_res = safe_divide(100, 0)
        self.assertIsNone(zero_res)

    def test_growth_rate_honest_calculation(self):
        # Normal growth
        rate, expl = calculate_growth_rate(150, 100)
        self.assertEqual(rate, Decimal('50.00'))

        # When baseline is zero, percentage growth must not be fabricated
        zero_rate, zero_expl = calculate_growth_rate(150, 0)
        self.assertIsNone(zero_rate)
        self.assertIn("Baseline is zero", zero_expl)
