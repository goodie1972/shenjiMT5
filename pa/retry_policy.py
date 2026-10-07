"""阶段2：分级重试 + 反作弊。

a/b/d → retry_max(3)；c → retry_max_semantic(1)；e → 永不。
NO_RETRY 前缀（实测防模型硬凑价格）：metrics:、trace:§14、s2:order_direction。
反作弊：重试成功后比对不可变字段（direction/cycle_position），豁免=增量声明/程序节点/
反馈明确要求修复的字段；违规 → 立即失败且不再重试。
"""
