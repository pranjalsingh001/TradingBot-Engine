"""
walk_forward.py — Walk-forward freeze enforcement (Phase F.3).
"""
from datetime import datetime, timezone


class WalkForwardManager:
    """Manages walk-forward evaluation cycles and config freezes."""

    def __init__(self, train_days=60, test_days=20):
        self.train_days = train_days
        self.test_days = test_days
        self.is_frozen = False
        self.freeze_start = None
        self.freeze_end = None

    def start_test_window(self):
        """Begin a frozen test window."""
        self.is_frozen = True
        self.freeze_start = datetime.now(timezone.utc)

    def end_test_window(self):
        """End the frozen test window."""
        self.is_frozen = False
        self.freeze_end = datetime.now(timezone.utc)

    def can_apply_recommendations(self) -> tuple:
        """Check if recommendations can be applied.
        Returns (can_apply: bool, reason: str).
        """
        if self.is_frozen:
            return False, "Walk-forward test window in progress — config frozen"
        return True, ""

    def evaluate_results(self, train_sharpe: float, test_sharpe: float,
                         train_wr: float, test_wr: float) -> dict:
        """Evaluate walk-forward results for overfitting."""
        flags = []
        if train_sharpe > 0 and test_sharpe < 0.5 * train_sharpe:
            flags.append("OVERFITTING: test Sharpe < 50% of train Sharpe")
        if test_wr < train_wr - 0.10:
            flags.append("DEGRADATION: test win rate dropped > 10pp from train")

        return {
            "train_sharpe": train_sharpe,
            "test_sharpe": test_sharpe,
            "train_win_rate": train_wr,
            "test_win_rate": test_wr,
            "flags": flags,
            "passed": len(flags) == 0,
        }
