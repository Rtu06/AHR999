"""
Module mô phỏng giao dịch định lượng (Backtesting Engine) theo chuỗi thời gian.
Đảm bảo tính trung thực (Không nhìn trước tương lai / No Look-Ahead Bias),
tính phí giao dịch thực tế trên mỗi lượt tái cân bằng tỷ trọng,
và đo lường toàn diện các chỉ số hiệu suất: Total Return, CAGR, Max Drawdown, Sharpe, Sortino, Calmar.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any
import numpy as np
import pandas as pd

from config import INITIAL_CAPITAL, FEE_RATE, RISK_FREE_RATE

logger = logging.getLogger("Backtest")


@dataclass
class BacktestResult:
    """Chứa toàn bộ kết quả mô phỏng backtest và dữ liệu chuỗi thời gian."""
    summary: Dict[str, Any]
    df_equity: pd.DataFrame


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        fee_rate: float = FEE_RATE,
        risk_free_rate: float = RISK_FREE_RATE,
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.risk_free_rate = risk_free_rate

    def run(self, df: pd.DataFrame) -> BacktestResult:
        """
        Thực hiện backtest từng ngày không có look-ahead bias:
        - Tín hiệu sinh tại phiên đóng cửa ngày t (target_weight) sẽ được thực thi
          cho chu kỳ nắm giữ ngày t+1 (actual_weight = target_weight.shift(1)).
        - Phí giao dịch được trừ dựa trên tỷ trọng điều chỉnh (turnover) * fee_rate.
        """
        df = df.copy()

        # Đảm bảo sắp xếp theo thời gian
        df = df.sort_values("date").reset_index(drop=True)

        # 1. Tỷ trọng thực thi cho ngày t là tín hiệu của ngày t-1 (No look-ahead bias)
        # Phiên đầu tiên tỷ trọng = 0 trước khi nhận tín hiệu
        df["actual_weight"] = df["target_weight"].shift(1).fillna(0.0)

        # 2. Khối lượng tái cân bằng (Turnover) tại mỗi phiên
        prev_weight = df["actual_weight"].shift(1).fillna(0.0)
        df["turnover"] = (df["actual_weight"] - prev_weight).abs()

        # 3. Phí giao dịch trên tổng tài sản (%): turnover * fee_rate
        df["fee_pct"] = df["turnover"] * self.fee_rate

        # 4. Tỷ suất sinh lời hàng ngày của Bitcoin
        df["btc_return"] = df["close"].pct_change().fillna(0.0)

        # 5. Tỷ suất sinh lời hàng ngày của Chiến lược (đã trừ phí giao dịch)
        df["strat_return"] = (df["actual_weight"] * df["btc_return"]) - df["fee_pct"]

        # 6. Đường cong vốn Chiến lược (Strategy Equity Curve)
        # Ngày 0: vốn ban đầu
        cum_returns = (1.0 + df["strat_return"]).cumprod()
        df["strat_equity"] = self.initial_capital * cum_returns

        # 7. Điểm đỉnh vốn (Peak) và Mức sụt giảm (Drawdown) của Chiến lược
        df["strat_peak"] = df["strat_equity"].cummax()
        df["strat_drawdown"] = (df["strat_equity"] - df["strat_peak"]) / df["strat_peak"]

        # 8. Benchmark: Mua và Nắm giữ (Buy & Hold BTC)
        # Bắt đầu tại ngày đầu tiên, trừ 1 lần phí vào lệnh ban đầu
        bnh_initial_equity = self.initial_capital * (1.0 - self.fee_rate)
        initial_close = df["close"].iloc[0]
        df["bnh_equity"] = (df["close"] / initial_close) * bnh_initial_equity
        df["bnh_return"] = df["bnh_equity"].pct_change().fillna(0.0)
        df["bnh_peak"] = df["bnh_equity"].cummax()
        df["bnh_drawdown"] = (df["bnh_equity"] - df["bnh_peak"]) / df["bnh_peak"]

        # 9. Tính toán các chỉ số thống kê hiệu suất
        summary = self._compute_performance_metrics(df)

        return BacktestResult(summary=summary, df_equity=df)

    def _compute_performance_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Tính toán các chỉ số định lượng tài chính chuẩn mực."""
        days = (pd.to_datetime(df["date"].iloc[-1]) - pd.to_datetime(df["date"].iloc[0])).days
        years = max(days / 365.25, 0.01)

        # === CHIẾN LƯỢC ===
        strat_final_equity = df["strat_equity"].iloc[-1]
        strat_total_return = (strat_final_equity - self.initial_capital) / self.initial_capital
        strat_cagr = (strat_final_equity / self.initial_capital) ** (1.0 / years) - 1.0

        daily_strat_ret = df["strat_return"]
        strat_vol_ann = daily_strat_ret.std() * np.sqrt(365)

        # Sharpe Ratio
        if strat_vol_ann > 0:
            strat_sharpe = (strat_cagr - self.risk_free_rate) / strat_vol_ann
        else:
            strat_sharpe = 0.0

        # Sortino Ratio (Downside deviation)
        neg_returns = daily_strat_ret[daily_strat_ret < 0]
        downside_std = neg_returns.std() * np.sqrt(365) if len(neg_returns) > 0 else 1e-6
        strat_sortino = (strat_cagr - self.risk_free_rate) / downside_std if downside_std > 0 else 0.0

        # Max Drawdown
        strat_max_dd = df["strat_drawdown"].min()
        strat_calmar = abs(strat_cagr / strat_max_dd) if abs(strat_max_dd) > 0 else 0.0

        # Max Drawdown duration (days)
        is_underwater = df["strat_drawdown"] < 0
        dd_runs = (~is_underwater).cumsum()[is_underwater]
        max_dd_duration_days = dd_runs.value_counts().max() if not dd_runs.empty else 0

        # Số lần tái cân bằng (rebalances)
        rebalance_count = int((df["turnover"] > 0.001).sum())
        total_fees_paid = (df["fee_pct"] * df["strat_equity"].shift(1).fillna(self.initial_capital)).sum()

        # === BENCHMARK: BUY & HOLD ===
        bnh_final_equity = df["bnh_equity"].iloc[-1]
        bnh_total_return = (bnh_final_equity - self.initial_capital) / self.initial_capital
        bnh_cagr = (bnh_final_equity / self.initial_capital) ** (1.0 / years) - 1.0

        daily_bnh_ret = df["bnh_return"]
        bnh_vol_ann = daily_bnh_ret.std() * np.sqrt(365)

        if bnh_vol_ann > 0:
            bnh_sharpe = (bnh_cagr - self.risk_free_rate) / bnh_vol_ann
        else:
            bnh_sharpe = 0.0

        bnh_neg_returns = daily_bnh_ret[daily_bnh_ret < 0]
        bnh_downside_std = bnh_neg_returns.std() * np.sqrt(365) if len(bnh_neg_returns) > 0 else 1e-6
        bnh_sortino = (bnh_cagr - self.risk_free_rate) / bnh_downside_std if bnh_downside_std > 0 else 0.0

        bnh_max_dd = df["bnh_drawdown"].min()
        bnh_calmar = abs(bnh_cagr / bnh_max_dd) if abs(bnh_max_dd) > 0 else 0.0

        bnh_is_underwater = df["bnh_drawdown"] < 0
        bnh_dd_runs = (~bnh_is_underwater).cumsum()[bnh_is_underwater]
        bnh_max_dd_duration = bnh_dd_runs.value_counts().max() if not bnh_dd_runs.empty else 0

        # Tỷ lệ ngày có lời (Daily Win Rate)
        active_days = df[df["actual_weight"] > 0]
        win_days = (active_days["strat_return"] > 0).sum()
        win_rate = (win_days / len(active_days) * 100) if len(active_days) > 0 else 0.0

        return {
            "start_date": df["date"].iloc[0],
            "end_date": df["date"].iloc[-1],
            "total_days": days,
            "years": round(years, 2),
            "initial_capital": self.initial_capital,
            # Strategy Metrics
            "strat_final_equity": strat_final_equity,
            "strat_total_return": strat_total_return * 100,
            "strat_cagr": strat_cagr * 100,
            "strat_volatility": strat_vol_ann * 100,
            "strat_max_dd": strat_max_dd * 100,
            "strat_max_dd_duration_days": int(max_dd_duration_days),
            "strat_sharpe": strat_sharpe,
            "strat_sortino": strat_sortino,
            "strat_calmar": strat_calmar,
            "rebalance_count": rebalance_count,
            "total_fees_paid": total_fees_paid,
            "daily_win_rate": win_rate,
            # Benchmark Metrics
            "bnh_final_equity": bnh_final_equity,
            "bnh_total_return": bnh_total_return * 100,
            "bnh_cagr": bnh_cagr * 100,
            "bnh_volatility": bnh_vol_ann * 100,
            "bnh_max_dd": bnh_max_dd * 100,
            "bnh_max_dd_duration_days": int(bnh_max_dd_duration),
            "bnh_sharpe": bnh_sharpe,
            "bnh_sortino": bnh_sortino,
            "bnh_calmar": bnh_calmar,
        }
