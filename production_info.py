"""Immutable production identification for a single run-in session."""
from __future__ import annotations


def validate_production_info(po, model, operator):
    fields={'PO':str(po).strip(),'Model':str(model).strip(),'Operator':str(operator).strip()}
    if not fields['Model']:
        raise ValueError('Model Name cannot be blank')
    for name,value in fields.items():
        if len(value)>100:
            raise ValueError(f'{name} exceeds 100 characters')
        if any(ord(ch)<32 or ord(ch)==127 for ch in value):
            raise ValueError(f'{name} contains a control character')
    return fields
