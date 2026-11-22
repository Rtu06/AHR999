"""
Module tải và tiền xử lý dữ liệu nến 1d BTCUSDT từ Binance REST API.
Hỗ trợ phân trang (pagination), retry endpoint dự phòng, lưu cache và fallback ngoại tuyến.
"""

import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import pandas as pd
import requests

from config import (
    SYMBOL,
    INTERVAL,
    BINANCE_ENDPOINTS,
    BINANCE_START_DATE,
    RAW_DATA_FILE,
)

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataLoader")


def _date_to_ms(date_str: str) -> int:
    """Chuyển đổi chuỗi ngày YYYY-MM-DD sang timestamp millisecond UTC."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_klines_batch(
    symbol: str,
    interval: str,
    start_time: int,
    end_time: Optional[int] = None,
    limit: int = 1000,
) -> Optional[List[list]]:
    """
    Gọi Binance REST API tải một batch nến klines, tự động thử các mirror endpoints nếu lỗi mạng.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time,
        "limit": limit,
    }
    if end_time:
        params["endTime"] = end_time

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityQuant/1.0"
    }

    for endpoint in BINANCE_ENDPOINTS:
        url = f"{endpoint}/api/v3/klines"
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
            else:
                logger.warning("Endpoint %s trả về mã lỗi %s: %s", url, response.status_code, response.text[:100])
        except requests.RequestException as err:
            logger.warning("Không thể kết nối đến %s: %s. Thử endpoint tiếp theo...", url, err)
            continue

    return None


def fetch_all_binance_klines(
    symbol: str = SYMBOL,
    interval: str = INTERVAL,
    start_date: str = BINANCE_START_DATE,
) -> pd.DataFrame:
    """
    Tải toàn bộ lịch sử nến ngày từ Binance API qua nhiều phân trang (pagination).
    """
    start_ms = _date_to_ms(start_date)
    current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    all_rows = []

    logger.info("Bắt đầu tải dữ liệu nến %s %s từ Binance (từ %s)...", symbol, interval, start_date)

    cursor_ms = start_ms
    batch_count = 0

    while cursor_ms < current_ms:
        batch = fetch_klines_batch(symbol, interval, start_time=cursor_ms, limit=1000)
        if not batch or len(batch) == 0:
            logger.info("Không còn dữ liệu mới hoặc API không phản hồi thêm.")
            break

        all_rows.extend(batch)
        batch_count += 1
        last_candle_open_ms = batch[-1][0]
        logger.info(
            "Batch %d: tải %d nến. Nến cuối: %s",
            batch_count,
            len(batch),
            datetime.fromtimestamp(last_candle_open_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
        )

        # 1 ngày = 86,400,000 ms. Di chuyển con trỏ qua nến tiếp theo
        next_ms = last_candle_open_ms + 86400000
        if next_ms <= cursor_ms or len(batch) < 1000:
            # Đã đến nến hiện tại gần nhất
            break
        cursor_ms = next_ms
        time.sleep(0.1)  # Giãn nhẹ để tôn trọng rate-limit Binance

    if not all_rows:
        raise ConnectionError("Không thể tải dữ liệu nến nào từ Binance API.")

    # Format klines của Binance:
    # [0: Open time, 1: Open, 2: High, 3: Low, 4: Close, 5: Volume, 6: Close time, 7: Quote asset volume, ...]
    raw_df = pd.DataFrame(all_rows)
    raw_df = raw_df.iloc[:, [0, 1, 2, 3, 4, 5, 7]]
    raw_df.columns = ["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]

    # Chuẩn hóa kiểu dữ liệu
    raw_df["timestamp"] = raw_df["timestamp"].astype(int)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        raw_df[col] = raw_df[col].astype(float)

    # Thêm cột date dạng YYYY-MM-DD theo chuẩn UTC
    raw_df["date"] = pd.to_datetime(raw_df["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")

    # Loại bỏ bản ghi trùng lặp và sắp xếp theo thời gian tăng dần
    raw_df = raw_df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Đưa cột date lên đầu để dễ đọc
    cols = ["timestamp", "date", "open", "high", "low", "close", "volume", "quote_volume"]
    raw_df = raw_df[cols]

    return raw_df


def load_btc_daily_data(
    symbol: str = SYMBOL,
    interval: str = INTERVAL,
    cache_path: Path = RAW_DATA_FILE,
    force_download: bool = False,
) -> pd.DataFrame:
    """
    Hàm chính tải dữ liệu:
    1. Kiểm tra cache nếu không yêu cầu force_download.
    2. Tải dữ liệu mới nhất từ Binance API.
    3. Hợp nhất và lưu cache.
    4. Nếu lỗi mạng, tự động fallback đọc từ cache offline.
    """
    cache_path = Path(cache_path)

    if not force_download and cache_path.exists():
        try:
            logger.info("Đọc dữ liệu từ cache: %s", cache_path)
            cached_df = pd.read_csv(cache_path)
            if not cached_df.empty and "timestamp" in cached_df.columns:
                # Kiểm tra xem cache có cần cập nhật ngày mới nhất không
                last_cached_date = cached_df["date"].iloc[-1]
                logger.info("Cache hiện có đến ngày %s (%d dòng)", last_cached_date, len(cached_df))
                
                # Cố gắng lấy thêm phần chênh lệch từ Binance
                try:
                    last_ms = int(cached_df["timestamp"].iloc[-1])
                    next_ms = last_ms + 86400000
                    current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    
                    if current_ms - next_ms > 86400000:  # Thiếu ít nhất 1 ngày nến
                        logger.info("Đang kiểm tra nến mới bổ sung từ ngày %s...", last_cached_date)
                        new_batch = fetch_klines_batch(symbol, interval, start_time=next_ms, limit=1000)
                        if new_batch and len(new_batch) > 0:
                            new_df = pd.DataFrame(new_batch).iloc[:, [0, 1, 2, 3, 4, 5, 7]]
                            new_df.columns = ["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]
                            new_df["timestamp"] = new_df["timestamp"].astype(int)
                            for c in ["open", "high", "low", "close", "volume", "quote_volume"]:
                                new_df[c] = new_df[c].astype(float)
                            new_df["date"] = pd.to_datetime(new_df["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
                            
                            cached_df = pd.concat([cached_df, new_df], ignore_index=True)
                            cached_df = cached_df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
                            cached_df.to_csv(cache_path, index=False)
                            logger.info("Đã cập nhật thêm %d nến mới vào cache.", len(new_df))
                except Exception as update_err:
                    logger.warning("Không thể cập nhật nến mới, tiếp tục dùng cache có sẵn: %s", update_err)

                return cached_df
        except Exception as read_err:
            logger.warning("Lỗi đọc cache (%s), chuyển sang tải lại từ đầu...", read_err)

    # Tải mới hoàn toàn từ API
    try:
        df = fetch_all_binance_klines(symbol, interval, start_date=BINANCE_START_DATE)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_path, index=False)
        logger.info("Đã lưu dữ liệu vào cache: %s (%d dòng)", cache_path, len(df))
        return df
    except Exception as api_err:
        logger.error("Không thể kết nối API Binance: %s", api_err)
        if cache_path.exists():
            logger.info("Fallback: Sử dụng dữ liệu cache có sẵn tại %s", cache_path)
            return pd.read_csv(cache_path)
        raise RuntimeError(
            f"Không có dữ liệu: Lỗi kết nối Binance ({api_err}) và chưa có file cache tại {cache_path}"
        ) from api_err
