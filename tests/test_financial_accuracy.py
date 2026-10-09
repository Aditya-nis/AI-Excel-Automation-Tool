import unittest
from decimal import Decimal
import pandas as pd
import numpy as np

from apps.core.utils import to_safe_decimal, safe_divide, calculate_growth_rate
from apps.cleaning.services import apply_single_step
from apps.dashboards.views import clean_numeric_series

class FinancialAccuracyTests(unittest.TestCase):
    """Rigorous tests for financial arithmetic, accounting negatives, and KPI calculations."""

    def test_to_safe_decimal_accounting_negative(self):
        """Parenthesized numbers e.g. (123.45) must be converted to negative Decimal."""
        self.assertEqual(to_safe_decimal('(123.45)'), Decimal('-123.45'))
        self.assertEqual(to_safe_decimal('($1,500.00)'), Decimal('-1500.00'))
        self.assertEqual(to_safe_decimal('-500.25'), Decimal('-500.25'))
        self.assertEqual(to_safe_decimal('$1,234.56'), Decimal('1234.56'))
        self.assertEqual(to_safe_decimal(None), Decimal('0.00'))
        self.assertEqual(to_safe_decimal(''), Decimal('0.00'))

    def test_safe_divide_and_zero_division(self):
        """Division by zero must return None safely without crashing."""
        self.assertIsNone(safe_divide(100, 0))
        self.assertIsNone(safe_divide('100.00', '0.00'))
        self.assertEqual(safe_divide(100, 2), Decimal('50.0000'))
        self.assertEqual(safe_divide(10, 3, precision='0.01'), Decimal('3.33'))

    def test_growth_rate_calculations(self):
        """Growth rate must handle positive, negative, and zero baselines properly."""
        # Standard positive growth: 100 to 150 = +50%
        rate, desc = calculate_growth_rate(150, 100)
        self.assertEqual(rate, Decimal('50.00'))

        # Negative baseline: -100 to 50 = +150%
        rate, desc = calculate_growth_rate(50, -100)
        self.assertEqual(rate, Decimal('150.00'))

        # Zero baseline: division by zero prevented
        rate, desc = calculate_growth_rate(100, 0)
        self.assertIsNone(rate)
        self.assertIn("zero", desc.lower())

    def test_clean_numeric_series_accounting_formats(self):
        """Test clean_numeric_series converts currency and accounting formats accurately."""
        s = pd.Series(['$1,000.50', '(500.25)', '  (₹250.00)  ', '100.00-', '-75.50', 'invalid', None])
        cleaned = clean_numeric_series(s)
        
        self.assertAlmostEqual(cleaned[0], 1000.50)
        self.assertAlmostEqual(cleaned[1], -500.25)
        self.assertAlmostEqual(cleaned[2], -250.00)
        self.assertAlmostEqual(cleaned[3], -100.00)
        self.assertAlmostEqual(cleaned[4], -75.50)
        self.assertTrue(np.isnan(cleaned[5]))
        self.assertTrue(np.isnan(cleaned[6]))

    def test_cleaning_engine_convert_type_negative_preservation(self):
        """Cleaning engine convert_type operation must preserve negative amounts."""
        df = pd.DataFrame({
            'revenue': ['$2,000.00', '(500.00)', '1,500.00', '-200.00']
        })
        step = {
            'operation_type': 'convert_type',
            'column_name': 'revenue',
            'parameters': {'target_type': 'numeric'}
        }
        res_df, affected_rows, desc = apply_single_step(df, step)
        self.assertEqual(affected_rows, 4)
        self.assertEqual(list(res_df['revenue']), [2000.0, -500.0, 1500.0, -200.0])
        # Verify sum equals 2800.00 (not 4200.00)
        self.assertEqual(res_df['revenue'].sum(), 2800.0)
