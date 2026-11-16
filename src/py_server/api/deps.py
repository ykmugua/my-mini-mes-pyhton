"""依赖注入：repo / policy / use case 的组装点。

当前各组件为无状态模块/纯函数，这里集中 re-export 便于 router 统一引用；
未来若换成带状态的实例，只需改这里。
"""

from .. import services
from ..domain.interlock.policy import InterlockPolicy
from ..domain.trust.policy import ProgramTrustPolicy

get_services = services
trust_policy = ProgramTrustPolicy
interlock_policy = InterlockPolicy