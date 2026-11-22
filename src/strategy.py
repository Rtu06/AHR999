"""
Module chiến lược định lượng AHR999 Dynamic Quant Strategy.
Kết hợp định giá chu kỳ vĩ mô (AHR999) và bộ lọc xu hướng/động lượng (SMA20, RSI14).
Sinh tín hiệu và tỷ trọng danh mục (target weight) không nhìn trước tương lai (No Look-ahead bias).
"""

import logging
from typing import Tuple
import pandas as pd
import numpy as np

from config import (
    AHR_ZONE_OPPORTUNITY,
    AHR_ZONE_DCA,
    AHR_ZONE_EXTREME_BUBBLE,
    RSI_MOMENTUM_FILTER,
    WEIGHT_OPPORTUNITY_MOMENTUM,
    WEIGHT_OPPORTUNITY_KNIFE,
    WEIGHT_DCA_BULL,
    WEIGHT_DCA_NEUTRAL,
    WEIGHT_DCA_DEFENSIVE,
    WEIGHT_RISK_MOMENTUM,
    WEIGHT_RISK_DEFENSIVE,
    WEIGHT_RISK_EXTREME,
)

logger = logging.getLogger("Strategy")


def evaluate_daily_signal(
    close: float,
    ahr999: float,
    ahr_zone: str,
    sma_20: float,
    rsi_14: float,
) -> Tuple[float, str, str]:
    """
    Quy tắc định lượng phân bổ tỷ trọng cho từng phiên:
    Trả về: (target_weight, signal_code, description)
    
    Tỷ trọng danh mục nằm trong khoảng [0.0, 1.0]:
    - 1.0: 100% vị thế Bitcoin
    - 0.0: 100% Tiền mặt (USDT)
    """
    # 1. VÙNG CƠ HỘI ĐÁY (Opportunity Zone: ahr999 < 0.45)
    if ahr_zone == "opportunity" or ahr999 < AHR_ZONE_OPPORTUNITY:
        if close > sma_20:
            # Vùng định giá rẻ nhất + Đã có tín hiệu xác nhận đảo chiều vượt SMA20
            return (
                WEIGHT_OPPORTUNITY_MOMENTUM,
                "OPPORTUNITY_FULL",
                "Đáy chu kỳ + Xác nhận hồi phục trên SMA20 -> Vị thế tối đa 100%",
            )
        else:
            # Vùng định giá rẻ nhất nhưng đang trong đà giảm mạnh (dao rơi) -> Giữ 20% tiền mặt đề phòng wick sâu hơn
            return (
                WEIGHT_OPPORTUNITY_KNIFE,
                "OPPORTUNITY_KNIFE",
                "Đáy chu kỳ + Dưới SMA20 (tránh dao rơi) -> Tích lũy 80%, giữ 20% tiền mặt",
            )

    # 2. VÙNG TÍCH LŨY ĐỊNH KỲ (DCA Zone: 0.45 <= ahr999 <= 1.20)
    elif ahr_zone == "dca" or (AHR_ZONE_OPPORTUNITY <= ahr999 <= AHR_ZONE_DCA):
        if close > sma_20 and rsi_14 >= RSI_MOMENTUM_FILTER:
            # Thị trường uptrend lành mạnh trong vùng tích lũy
            return (
                WEIGHT_DCA_BULL,
                "DCA_BULL_TREND",
                "Vùng DCA + Uptrend lành mạnh (Trên SMA20 & RSI>=45) -> Tỷ trọng 75%",
            )
        elif close > sma_20:
            # Trên SMA20 nhưng động lượng RSI còn yếu/đi ngang
            return (
                WEIGHT_DCA_NEUTRAL,
                "DCA_NEUTRAL",
                "Vùng DCA + Trên SMA20 nhưng động lượng trung tính -> Tỷ trọng 50%",
            )
        else:
            # Dưới SMA20: Đợt điều chỉnh/pullback trong vùng DCA
            return (
                WEIGHT_DCA_DEFENSIVE,
                "DCA_DEFENSIVE",
                "Vùng DCA + Dưới SMA20 (điều chỉnh ngắn hạn) -> Phòng thủ 35%",
            )

    # 3. VÙNG RỦI RO / ĐỊNH GIÁ QUÁ CAO (Risk Zone: ahr999 > 1.20)
    else:
        if ahr999 >= AHR_ZONE_EXTREME_BUBBLE:
            # Bong bóng hưng phấn tột độ (ahr999 > 2.0) -> Chốt lời toàn bộ, thoát về tiền mặt
            return (
                WEIGHT_RISK_EXTREME,
                "RISK_EXTREME_BUBBLE",
                "Đỉnh hưng phấn cực đại (ahr > 2.0) -> Chốt lời toàn bộ (0% BTC, 100% USDT)",
            )
        elif close > sma_20:
            # Vùng rủi ro cao nhưng đà tăng parabolic vẫn tiếp diễn -> Giữ vị thế runner 25% với trailing
            return (
                WEIGHT_RISK_MOMENTUM,
                "RISK_RUNNER",
                "Vùng rủi ro (1.2 < ahr <= 2.0) + Trên SMA20 -> Giữ 25% runner theo trend",
            )
        else:
            # Vùng rủi ro và bắt đầu gãy SMA20 -> Hạ tỷ trọng khẩn cấp, chỉ giữ 10%
            return (
                WEIGHT_RISK_DEFENSIVE,
                "RISK_SCALE_OUT",
                "Vùng rủi ro + Gãy SMA20 -> Hạ tỷ trọng phòng thủ xuống 10%",
            )


def generate_strategy_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Áp dụng quy tắc chiến lược cho từng phiên dữ liệu.
    Tạo ra các cột:
    - target_weight: Tỷ trọng BTC mong muốn sau khi đóng nến ngày t (0.0 đến 1.0).
    - signal_code: Mã tín hiệu định lượng.
    - signal_desc: Mô tả lý do phân bổ vị thế.
    """
    df = df.copy()

    weights = []
    signals = []
    reasons = []

    for _, row in df.iterrows():
        weight, sig, desc = evaluate_daily_signal(
            close=row["close"],
            ahr999=row["ahr999"],
            ahr_zone=row["ahr_zone"],
            sma_20=row["sma_20"],
            rsi_14=row["rsi_14"],
        )
        weights.append(weight)
        signals.append(sig)
        reasons.append(desc)

    df["target_weight"] = weights
    df["signal_code"] = signals
    df["signal_desc"] = reasons

    # Thống kê phân bổ tỷ trọng
    logger.info("Thống kê tín hiệu chiến lược:")
    for sig, cnt in df["signal_code"].value_counts().items():
        logger.info(" - %-22s: %4d phiên (%5.1f%%)", sig, cnt, (cnt / len(df)) * 100)

    return df
