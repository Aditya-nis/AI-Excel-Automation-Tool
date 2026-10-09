import re
import pandas as pd
from apps.understanding.models import UnderstandingAssessment
from apps.datasets.models import DatasetColumn

def assess_column_semantics(version, df):
    """
    Evaluates semantic role for each column with statistical evidence and confidence scores.
    Confidence Thresholds:
      High: >= 0.90
      Medium: 0.70 - 0.89
      Low: < 0.70
    """
    total_rows = len(df)
    columns = DatasetColumn.objects.filter(version=version).select_related('profile')

    for col in columns:
        col_name_lower = col.name.lower()
        profile = getattr(col, 'profile', None)
        inferred_role = 'text'
        confidence = 0.50
        evidence_list = []
        patterns = []

        # 1. Date Check
        if re.search(r'\b(date|dt|time|timestamp|day|dob|joining|created_at|updated_at|period|month|year)\b', col_name_lower):
            evidence_list.append("Header name explicitly matches date/time terminology.")
            confidence += 0.35
        if col.data_type == 'date':
            evidence_list.append("Data values successfully parse as chronological dates.")
            confidence += 0.40
            inferred_role = 'date'
        elif any(term in col_name_lower for term in ['date', 'time', 'day']) and col.data_type in ['integer', 'text']:
            inferred_role = 'date'
            confidence += 0.25

        # 2. Identifier / Key Check
        id_match = re.search(r'\b(id|uuid|key|code|ref|number|no|invoice|sku|customer_id|emp_id)\b', col_name_lower)
        if id_match:
            evidence_list.append(f"Header contains identifier keyword '{id_match.group(0)}'.")
            confidence += 0.30
        if col.is_primary_key or (profile and profile.unique_percentage >= 95.0 and profile.null_count == 0):
            evidence_list.append("Values are 95%+ unique with zero null entries.")
            confidence += 0.40
            inferred_role = 'identifier'

        # 3. Currency / Monetary Measure Check
        currency_match = re.search(r'\b(revenue|sales|price|cost|amount|salary|worth|fee|profit|budget|val|spend|tax|discount_amount)\b', col_name_lower)
        if currency_match:
            evidence_list.append(f"Header indicates financial metric '{currency_match.group(0)}'.")
            confidence += 0.35
        # Check sample symbols
        sample_str = " ".join([str(v) for v in (profile.sample_values if profile else [])])
        if re.search(r'[\$₹€£]|usd|inr|eur', sample_str, re.IGNORECASE):
            evidence_list.append("Values contain monetary currency symbols ($, ₹, €, £).")
            confidence += 0.35
            inferred_role = 'currency'
        elif currency_match and col.data_type in ['decimal', 'integer']:
            inferred_role = 'currency'
            confidence += 0.30

        # 4. Quantity / Count Check
        qty_match = re.search(r'\b(qty|quantity|units|count|items|stock|volume|headcount|pieces)\b', col_name_lower)
        if qty_match and col.data_type in ['integer', 'decimal']:
            evidence_list.append("Header and numeric distribution match item/unit counts.")
            confidence += 0.40
            inferred_role = 'quantity'

        # 5. Percentage / Rate Check
        pct_match = re.search(r'\b(pct|percent|percentage|rate|ratio|margin|share|discount_pct)\b', col_name_lower)
        if pct_match:
            evidence_list.append("Header designates percentage or ratio.")
            confidence += 0.35
            inferred_role = 'percentage'

        # 6. Status / Lifecycle Check
        status_match = re.search(r'\b(status|state|stage|condition|flag|attendance|verdict)\b', col_name_lower)
        if (status_match or col.data_type == 'category') and profile and profile.distinct_count <= 10:
            evidence_list.append(f"Contains low cardinality ({profile.distinct_count} distinct states).")
            confidence += 0.35
            inferred_role = 'status'

        # 7. Dimension (Category) Check
        elif col.data_type == 'category' or (profile and profile.distinct_count <= 50 and profile.unique_percentage < 30):
            evidence_list.append(f"Categorical distribution with {profile.distinct_count if profile else 0} distinct groupings.")
            confidence += 0.25
            inferred_role = 'dimension'

        # 8. General Measure Check
        elif col.data_type in ['integer', 'decimal'] and inferred_role not in ['currency', 'quantity', 'percentage', 'identifier']:
            evidence_list.append("Continuous numeric scale suitable for aggregation.")
            confidence += 0.30
            inferred_role = 'measure'

        # Bound confidence between 0.20 and 0.98 (honest AI: never claim 100% certainty without user confirmation)
        final_conf = min(0.98, max(0.25, round(confidence, 2)))
        
        if final_conf >= 0.90:
            band = 'high'
        elif final_conf >= 0.70:
            band = 'medium'
        else:
            band = 'low'

        evidence_str = " ".join(evidence_list) or "Statistical frequency and character composition analysis."

        # Update DatasetColumn
        col.inferred_role = inferred_role
        col.confidence_score = final_conf
        col.confidence_band = band
        col.evidence = evidence_str
        col.save(update_fields=['inferred_role', 'confidence_score', 'confidence_band', 'evidence'])

        # Create or update UnderstandingAssessment
        assessment, _ = UnderstandingAssessment.objects.update_or_create(
            version=version,
            column_name=col.name,
            defaults={
                'inferred_role': inferred_role,
                'confidence_score': final_conf,
                'confidence_band': band,
                'evidence': evidence_str,
                'sample_patterns': profile.sample_values if profile else []
            }
        )
