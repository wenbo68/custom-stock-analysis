# -*- coding: utf-8 -*-
"""
===================================
数据源策略层 - 包初始化
===================================

本包为分层分析应用提供日线 K 线（A 股 / 港股 / 美股），实现：
1. 统一的数据获取接口
2. 自动故障切换
3. 防封禁流控策略

数据源优先级（数字越小越优先，同优先级按初始化顺序排列）：
1. EfinanceFetcher (Priority 0) - 东方财富，A 股
2. TencentFetcher (Priority 0) - 腾讯直连，A 股
3. AkshareFetcher (Priority 1) - akshare 库，A 股 / 港股
4. AlphaVantageFetcher (Priority 3) - 美股补齐源，需配置 ALPHAVANTAGE_API_KEY
5. YfinanceFetcher (Priority 4) - Yahoo Finance，全市场兜底

美股走专用路由（2026-09-23）：Yfinance 为唯一完整历史来源；美股个股在 Yahoo
最新日线落后时，用 AlphaVantage 的免费 100 根窗口补齐缺的最新几根。美股指数只走
Yfinance。Finnhub 的日线接口已转为付费，不再作为价格来源（公司新闻仍用 Finnhub）。
"""

from .base import BaseFetcher, DataFetcherManager
from .efinance_fetcher import EfinanceFetcher
from .tencent_fetcher import TencentFetcher
from .akshare_fetcher import AkshareFetcher, is_hk_stock_code
from .yfinance_fetcher import YfinanceFetcher
from .alphavantage_fetcher import AlphaVantageFetcher
from .us_index_mapping import is_us_index_code, is_us_stock_code, get_us_index_yf_symbol, US_INDEX_MAPPING

__all__ = [
    'BaseFetcher',
    'DataFetcherManager',
    'EfinanceFetcher',
    'TencentFetcher',
    'AkshareFetcher',
    'YfinanceFetcher',
    'AlphaVantageFetcher',
    'is_us_index_code',
    'is_us_stock_code',
    'is_hk_stock_code',
    'get_us_index_yf_symbol',
    'US_INDEX_MAPPING',
]
