# Amazon SP-API 后台作业：报价刷新、目录同步、商品下载。
#
# 单包结构：
#   amazon/      — 报价、目录、商品、listing 规则
#   spapi/       — SP-API 客户端
#   services/    — ES、定价 pipeline
#   jobs/        — Celery 后台任务
#   commands/    — CLI 入队
#   worker/      — Celery app（``celery -A amazon_spapi.worker``）
#   platform/    — 配置、告警、服务 wiring
#   scheduling/  — 入队、优先级、去重
