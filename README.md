# BTC-AHR999-QUANT-V1: Chiến Lược Định Lượng Bitcoin Dựa Trên Chỉ Số Chu Kỳ AHR999

Hệ thống định lượng giao dịch Bitcoin (`BTCUSDT`) khung ngày (`1d`) dựa trên chỉ số định giá chu kỳ vĩ mô **AHR999** kết hợp bộ lọc xu hướng động lượng (SMA20 / RSI14) để tối ưu hóa tỷ suất sinh lời trên rủi ro, phòng thủ khi thị trường quá nóng và gom mạnh ở vùng đáy.

---

## 1. Cơ sở lý thuyết & Công thức AHR999

Chỉ số AHR999 do thành viên ahr999 đề xuất trên diễn đàn 8btc vào năm 2018, giúp định vị xem giá Bitcoin hiện tại đang rẻ hay đắt so với chi phí đào/tích lũy trung bình và đường định giá tăng trưởng dài hạn.

Chỉ số được tính toán trực tiếp từ dữ liệu giá đóng cửa nến ngày (`1d`):

$$
\text{AHR999} = \left( \frac{\text{Price}}{\text{Cost}_{200d}} \right) \times \left( \frac{\text{Price}}{\text{ExpGrowth}} \right)
$$

Trong đó:

### 1.1. Chi phí trung bình nhân 200 ngày ($\text{Cost}_{200d}$)

Đo lường chi phí vốn trung bình của các nhà đầu tư trong 200 ngày gần nhất (sử dụng Geometric Mean để giảm thiểu độ lệch bởi các đột biến giá). Trong mã nguồn tương ứng cột `cost_200d`:

$$
\text{Cost}_{200d} = \exp\left( \frac{1}{200} \sum_{i=0}^{199} \ln(\text{Close}_{t-i}) \right)
$$

### 1.2. Số ngày từ khối Genesis ($\text{Days Since Genesis}$)

Số ngày tính từ khối khởi nguyên Genesis block của Bitcoin (`2009-01-03`) đến ngày hiện tại của từng dòng dữ liệu:

$$
\text{days} = \text{date} - \text{2009-01-03}
$$

### 1.3. Đường tăng trưởng hàm mũ theo tuổi Bitcoin ($\text{ExpGrowth}$)

Mô hình hồi quy hàm mũ phản ánh giá trị nội tại dài hạn của mạng lưới Bitcoin theo thời gian:

$$
\text{ExpGrowth} = 10^{5.84 \cdot \log_{10}(\text{days}) - 17.01}
$$

*(Các tham số `5.84` và `17.01` có thể cấu hình linh hoạt trong `config.py`, trong mã nguồn tương ứng cột `exp_growth`)*.

### 1.4. Phân loại vùng AHR999 (`ahr_zone`)
- **`opportunity`** ($\text{AHR999} < 0.45$): Vùng đáy định giá siêu rẻ, cơ hội tích lũy mạnh nhất chu kỳ.
- **`dca`** ($0.45 \le \text{AHR999} \le 1.20$): Vùng giá hợp lý, thích hợp duy trì chiến lược tích lũy định kỳ (Dollar-Cost Averaging).
- **`risk`** ($\text{AHR999} > 1.20$): Vùng định giá quá cao / quá nóng, tiềm ẩn rủi ro tạo đỉnh chu kỳ.

---

## 2. Quy tắc Chiến lược Định lượng (Rule-Based Quant Strategy)

Để khắc phục nhược điểm "bắt dao rơi" mù quáng khi thị trường đang rơi tự do ở vùng đáy và "thoát hàng quá sớm" trong một siêu chu kỳ tăng giá, chiến lược kết hợp thêm bộ lọc xu hướng ngắn hạn **SMA(20)** và động lượng **RSI(14)**:

| Vùng AHR999 | Điều kiện kỹ thuật | Tỷ trọng mục tiêu (`target_weight`) | Giải thích logic |
| :--- | :--- | :---: | :--- |
| **Opportunity** (< 0.45) | `Close` > `SMA(20)` | **100% BTC** | Đáy định giá + Xác nhận đảo chiều hồi phục vượt SMA20 -> Phân bổ tối đa |
| **Opportunity** (< 0.45) | `Close` ≤ `SMA(20)` | **80% BTC** | Vùng đáy nhưng đang đà rơi tự do -> Gom 80%, giữ 20% tiền mặt dự phòng |
| **DCA** (0.45 – 1.20) | `Close` > `SMA(20)` và `RSI(14)` ≥ 45 | **75% BTC** | Uptrend lành mạnh trong vùng tích lũy -> Tỷ trọng cao đón sóng |
| **DCA** (0.45 – 1.20) | `Close` > `SMA(20)` và `RSI(14)` < 45 | **50% BTC** | Vùng tích lũy, giá trên SMA20 nhưng động lượng đi ngang -> Tỷ trọng 50% |
| **DCA** (0.45 – 1.20) | `Close` ≤ `SMA(20)` | **35% BTC** | Xuất hiện nhịp điều chỉnh ngắn hạn dưới SMA20 -> Hạ tỷ trọng phòng thủ |
| **Risk** (1.20 – 2.00) | `Close` > `SMA(20)` | **25% BTC** | Vùng nóng nhưng trend chưa gãy -> Giữ 25% vị thế trailing runner |
| **Risk** (1.20 – 2.00) | `Close` ≤ `SMA(20)` | **10% BTC** | Vùng nóng và gãy trend SMA20 -> Hạ tỷ trọng khẩn cấp còn 10% |
| **Extreme Bubble** (> 2.00) | Bất kể điều kiện | **0% BTC (100% USDT)** | Bong bóng hưng phấn tột độ -> Chốt lời toàn bộ, bảo toàn vốn |

### Cam kết trung thực trong Backtest (No Look-Ahead Bias)
- Quyết định tỷ trọng (`target_weight`) được tính dựa trên giá đóng cửa phiên ngày $t$.
- Việc thực thi tái cân bằng và nắm giữ vị thế diễn ra ở chu kỳ ngày $t+1$ (`actual_weight[t+1] = target_weight[t]`).
- Phí giao dịch được khấu trừ trực tiếp theo khối lượng điều chỉnh vị thế ($|\Delta \text{weight}| \times \text{Portfolio} \times \text{FeeRate}$, với `fee_rate` cấu hình trong `config.py`).

---

## 3. Cấu trúc Dự án

```text
btc-ahr999-quant-v1/
├── config.py                 # File cấu hình tham số, ngưỡng, đường dẫn và phí
├── requirements.txt          # Danh sách thư viện phụ thuộc
├── run_backtest.py           # Script thực thi toàn bộ pipeline end-to-end
├── README.md                 # Hướng dẫn chi tiết & tài liệu lý thuyết
├── data/
│   ├── raw/                  # Lưu cache dữ liệu thô nến 1d BTCUSDT từ Binance
│   └── processed/            # Lưu dữ liệu sau khi tính chỉ số và tín hiệu chiến lược
├── output/                   # Lưu biểu đồ báo cáo backtest (PNG 300 DPI)
└── src/
    ├── __init__.py           # Đánh dấu gói module
    ├── data_loader.py        # Tải dữ liệu Binance API, phân trang, khử trùng lặp & cache
    ├── indicators.py         # Tính Cost 200d, Exp Growth, AHR999, SMA20, RSI14
    ├── strategy.py           # Sinh tín hiệu định lượng và phân bổ tỷ trọng
    └── backtest.py           # Mô phỏng giao dịch, trừ phí, tính Sharpe, CAGR, Max DD
```

---

## 4. Hướng dẫn Cài đặt & Chạy

### Bước 1: Chuẩn bị môi trường & cài đặt thư viện
Mở Terminal hoặc PowerShell tại thư mục dự án và chạy:

```bash
pip install -r requirements.txt
```

Các thư viện chính bao gồm:
- `pandas`
- `numpy`
- `requests`
- `matplotlib`

### Bước 2: Chạy kiểm định Backtest
Chạy câu lệnh đơn giản:

```bash
python run_backtest.py
```

### Bước 3: Xem kết quả
1. Bảng tóm tắt chỉ số định lượng sẽ in trực tiếp ra màn hình console (Tổng lợi nhuận, CAGR, Max Drawdown, Sharpe, Sortino, Calmar...).
2. Dữ liệu chi tiết từng phiên được lưu tại: `data/processed/btcusdt_ahr999_processed.csv`.
3. Biểu đồ báo cáo trực quan 4 bảng chất lượng cao (300 DPI) được lưu tại: `output/backtest_report.png`.
