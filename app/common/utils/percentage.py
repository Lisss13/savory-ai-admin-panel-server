def percentage(value: int | float, total: int | float, decimals: int = 2) -> float:
    if total == 0:
        return 0.0
    return round((value / total) * 100, decimals)
