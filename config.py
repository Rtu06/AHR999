"""
Cấu hình hệ thống định lượng giao dịch BTC dựa trên chỉ số AHR999.
File: config.py
"""

from pathlib import Path

# ==============================================================================
# CẤU HÌNH ĐƯỜNG DẪN THƯ MỤC
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"

# Đảm bảo các thư mục tồn tại
DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RAW_DATA_FILE = DATA_RAW_DIR / "btcusdt_1d.csv"
PROCESSED_DATA_FILE = DATA_PROCESSED_DIR / "btcusdt_ahr999_processed.csv"
REPORT_CHART_FILE = OUTPUT_DIR / "backtest_report.png"

# ==============================================================================
# CẤU HÌNH DỮ LIỆU BINANCE
# ==============================================================================
SYMBOL = "BTCUSDT"
INTERVAL = "1d"

# Danh sách API endpoints dự phòng của Binance
BINANCE_ENDPOINTS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

# Ngày bắt đầu lấy dữ liệu Binance (2017-08-17 khi BTCUSDT niêm yết trên Binance)
BINANCE_START_DATE = "2017-08-17"

# ==============================================================================
# CẤU HÌNH CHỈ SỐ AHR999 & GENESIS BLOCK
# ==============================================================================
GENESIS_DATE = "2009-01-03"  # Ngày sinh Genesis Block của Bitcoin

# Tham số đường tăng trưởng hàm mũ (Exponential Growth Line):
# exp_growth = 10 ** (AHR_EXP_A * log10(days_since_genesis) - AHR_EXP_B)
AHR_EXP_A = 5.84
AHR_EXP_B = 17.01

# Chu kỳ trung bình nhân chi phí sản xuất / tích lũy
WINDOW_COST_200D = 200

# Ngưỡng phân loại vùng AHR999
AHR_ZONE_OPPORTUNITY = 0.45  # ahr999 < 0.45: Vùng đáy định giá siêu hời (Bottom / High Value)
AHR_ZONE_DCA = 1.20          # 0.45 <= ahr999 <= 1.20: Vùng tích lũy định kỳ (DCA Zone)
                             # ahr999 > 1.20: Vùng định giá cao / rủi ro quá nóng (Risk Zone)
AHR_ZONE_EXTREME_BUBBLE = 2.0  # Ngưỡng bong bóng hưng phấn cực đại (> 2.0)

# ==============================================================================
# CẤU HÌNH CHIẾN LƯỢC QUANT (RULE-BASED STRATEGY)
# ==============================================================================
# Tham số kỹ thuật lọc xu hướng / động lượng để tránh bắt dao rơi
SMA_TREND_WINDOW = 20        # SMA 20 ngày xác nhận ngắn/trung hạn
RSI_WINDOW = 14              # Chu kỳ RSI 14 ngày
RSI_MOMENTUM_FILTER = 45.0   # Mức RSI phân định động lượng tích cực trong vùng DCA

# Tỷ trọng danh mục mục tiêu (Target Portfolio Weight) theo trạng thái thị trường
WEIGHT_OPPORTUNITY_MOMENTUM = 1.00   # ahr < 0.45 và Close > SMA20 (vùng đáy + có đà hồi phục)
WEIGHT_OPPORTUNITY_KNIFE = 0.80      # ahr < 0.45 và Close <= SMA20 (vùng đáy dao rơi, giữ 20% dự phòng)

WEIGHT_DCA_BULL = 0.75               # 0.45 <= ahr <= 1.20 và Close > SMA20 và RSI > 45 (uptrend lành mạnh)
WEIGHT_DCA_NEUTRAL = 0.50            # 0.45 <= ahr <= 1.20 và Close > SMA20 (đi ngang / đà yếu)
WEIGHT_DCA_DEFENSIVE = 0.35          # 0.45 <= ahr <= 1.20 và Close <= SMA20 (đang điều chỉnh)

WEIGHT_RISK_MOMENTUM = 0.25          # 1.20 < ahr <= 2.00 và Close > SMA20 (vùng nóng nhưng trend chưa gãy)
WEIGHT_RISK_DEFENSIVE = 0.10         # 1.20 < ahr <= 2.00 và Close <= SMA20 (trend suy yếu ở vùng rủi ro)
WEIGHT_RISK_EXTREME = 0.00           # ahr > 2.00: Đỉnh chu kỳ / hưng phấn tột độ -> 100% Tiền mặt (USDT)

# ==============================================================================
# CẤU HÌNH BACKTEST
# ==============================================================================
INITIAL_CAPITAL = 10_000.0   # Vốn ban đầu (USD/USDT)
FEE_RATE = 0.001             # Phí giao dịch Spot (0.1% = 0.001 mỗi lệnh đổi tỷ trọng)
RISK_FREE_RATE = 0.0         # Lãi suất phi rủi ro (dùng tính Sharpe ratio)
