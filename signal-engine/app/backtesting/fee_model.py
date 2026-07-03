"""
fee_model.py — Trading fee computation (Phase G.2).
"""

DEFAULT_TAKER_FEE = 0.0005  # 0.05% Binance taker


def compute_fees(position_size_usd: float, fee_rate: float = DEFAULT_TAKER_FEE) -> tuple:
    """Compute entry + exit fees. Returns (entry_fee, exit_fee, total)."""
    entry_fee = position_size_usd * fee_rate
    exit_fee = position_size_usd * fee_rate
    return round(entry_fee, 4), round(exit_fee, 4), round(entry_fee + exit_fee, 4)


def compute_net_pnl(gross_pnl: float, position_size_usd: float, fee_rate: float = DEFAULT_TAKER_FEE) -> tuple:
    """Returns (net_pnl, total_fees)."""
    _, _, total_fees = compute_fees(position_size_usd, fee_rate)
    return round(gross_pnl - total_fees, 4), total_fees
