from rest_framework.exceptions import ValidationError


def teamlead_order_scope(request) -> str:
    """scope=team (default) | merchant — только для role teamlead."""
    scope = (request.query_params.get("scope") or "team").strip().lower()
    if scope not in ("team", "merchant"):
        raise ValidationError({"scope": "Must be 'team' or 'merchant'"})
    return scope
