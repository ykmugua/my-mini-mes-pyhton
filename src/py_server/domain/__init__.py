"""领域层：纯 Python，不 import 任何外部框架。"""

from __future__ import annotations


class DomainError(Exception):
    """领域规则违反的基类。

    注意：services.ServiceError 继承此类，使 FastAPI 的异常处理
    （监听 ServiceError）继续有效，同时领域层不依赖任何框架。
    """

    status_code = 400


class InvariantViolation(DomainError):
    """聚合不变量被破坏。"""

    status_code = 400


class ConflictError(DomainError):
    """幂等冲突。"""

    status_code = 409