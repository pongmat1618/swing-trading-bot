from decimal import ROUND_DOWN, Decimal


def floor_step(value: Decimal, step: Decimal) -> Decimal:
    if not value.is_finite() or not step.is_finite() or step <= 0 or value < 0:
        raise ValueError("invalid quantity or step")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def position_size(
    risk_budget: Decimal, loss_per_unit: Decimal, maximum: Decimal, step: Decimal
) -> Decimal:
    if any(not v.is_finite() or v <= 0 for v in (risk_budget, loss_per_unit, maximum)):
        raise ValueError("risk budget, loss per unit and maximum must be positive")
    return floor_step(min(risk_budget / loss_per_unit, maximum), step)
