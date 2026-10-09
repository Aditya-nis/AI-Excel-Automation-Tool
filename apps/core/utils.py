import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime
import numpy as np
import pandas as pd

class SafeJSONEncoder(json.JSONEncoder):
    """Encodes NumPy, Pandas, Decimal, and datetime objects safely."""
    def default(self, obj):
        if isinstance(obj, (Decimal,)):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if pd.isna(obj):
            return None
        return super().default(obj)

def to_safe_decimal(val, default=Decimal('0.00'), precision='0.01'):
    """Converts a number or string to Decimal with exact precision handling."""
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return default
    try:
        val_str = str(val).strip().replace(',', '')
        # Handle parenthesized negative numbers e.g. (100.50)
        if val_str.startswith('(') and val_str.endswith(')'):
            val_str = '-' + val_str[1:-1]
        # Remove currency symbols and extraneous symbols
        clean_str = ''.join(c for c in val_str if c in '0123456789.-')
        if not clean_str or clean_str == '-' or clean_str == '.':
            return default
        d = Decimal(clean_str)
        if precision:
            return d.quantize(Decimal(precision), rounding=ROUND_HALF_UP)
        return d
    except (InvalidOperation, ValueError, TypeError):
        return default

def safe_divide(numerator, denominator, precision='0.0001'):
    """Safe division returning None or explicit zero to avoid ZeroDivisionError."""
    num = to_safe_decimal(numerator)
    den = to_safe_decimal(denominator)
    if den == Decimal('0'):
        return None
    try:
        res = num / den
        if precision:
            return res.quantize(Decimal(precision), rounding=ROUND_HALF_UP)
        return res
    except (InvalidOperation, ZeroDivisionError):
        return None

def calculate_growth_rate(current, previous):
    """
    Calculates percentage growth rate.
    Returns (percentage_decimal, explanation_string)
    Honest calculation: when previous is 0 or None, return (None, 'Baseline is zero or unavailable')
    """
    cur = to_safe_decimal(current)
    prev = to_safe_decimal(previous)
    if prev == Decimal('0'):
        return None, "Baseline is zero; percentage growth undefined."
    rate = ((cur - prev) / abs(prev)) * Decimal('100')
    return rate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), "Calculated vs baseline"
