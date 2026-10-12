# -*- coding: utf-8 -*-
"""
===================================
API 中间件模块初始化
===================================

职责：
1. 导出全局异常处理器
"""

from api.middlewares.error_handler import add_error_handlers

__all__ = ["add_error_handlers"]
