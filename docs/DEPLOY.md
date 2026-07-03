# 部署与文档索引

| 文档 | 读者 | 内容 |
|------|------|------|
| [业务说明](./业务说明.md) | 运营、产品、新同事 | 系统做什么、业务流程、文件夹含义（业务语言） |
| [生产部署](./生产部署.md) | 运维 | systemd 上线、配置、升级、排障 |
| [systemd 执行路径](./systemd执行路径.md) | 运维、开发 | `amazon-spapi-offers` / `catalog` 服务逐步代码路径 |

## systemd 模板

手动部署时可复制（一键脚本会自动生成，一般无需手改）：

```
deploy/install-ubuntu.sh              # Ubuntu 一键部署
deploy/deploy.env.example             # 部署配置示例 → deploy/deploy.env
deploy/systemd/amazon-spapi-offers.service
deploy/systemd/amazon-spapi-catalog.service
deploy/conf.d/celery_spapi.example
```

## 快速命令

```bash
# 安装
uv sync --frozen

# 启动执行端（手动试跑）
export BROKER_URL='redis://:pass@host:6379/2'
uv run celery -A amazon_spapi.worker worker -l info -c 2 -Q SpapiItemOffersUpdate_US

# 提交过期报价任务
uv run schedule-stale-offers -m us -q 20 -t 36 asins.txt
```

详细步骤见 [生产部署](./生产部署.md)。
