# amazon-spapi-workers

Amazon SP-API 后台作业：报价刷新、目录同步、商品下载。

**文档：**

| 文档 | 说明 |
|------|------|
| [docs/业务说明.md](docs/业务说明.md) | 系统做什么、业务流程（业务语言） |
| [docs/生产部署.md](docs/生产部署.md) | 生产环境 systemd 部署与运维 |
| [docs/监控数据.md](docs/监控数据.md) | Worker 监控 ES 索引、`_id` 规则、查询示例 |
| [docs/公开仓库.md](docs/公开仓库.md) | 公开仓库说明、敏感信息约定 |
| [docs/DEPLOY.md](docs/DEPLOY.md) | 文档索引与快速命令 |

**公开仓库：** https://github.com/AriseshineSky/amazon-spapi-workers

**服务器自检：** `./deploy/check-server.sh`（无需跑 Celery 任务）

## Quick start

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd em-workers && uv sync --frozen

mkdir -p ~/.amazon_spapi
# edit ~/.amazon_spapi/config.ini

export BROKER_URL='redis://:password@host:6379/2'
uv run celery -A amazon_spapi.worker worker -l info -c 2 -Q SpapiItemOffersUpdate_US

uv run schedule-stale-offers -m us -q 20 -t 36 asins.txt
```

## SP-API：两条 API 线

| API | SP-API 端点 | 代码 | Celery Job | 队列 |
|-----|------------|------|------------|------|
| **Offers** | `getItemOffersBatch` (Pricing) | `spapi/offers.py` → `amazon/offers/` | `refresh_offers` | `SpapiItemOffersUpdate_{MARKET}` |
| **Catalog** | `searchCatalogItems` (Catalog Items) | `spapi/catalog.py` → `amazon/catalog/` | `refresh_catalog` | `SpapiCatalogItemsUpdate_{MARKET}` |
| **Fetch** | offers + catalog 组合拉取 | `amazon/products/fetch.py` | `fetch_products` | Celery default queue |

**发送端 CLI：**

```bash
# Offers
uv run schedule-stale-offers -m us -q 20 -t 36 asins.txt
uv run python -m amazon_spapi.commands.amazon.enqueue_offers_from_es -m us ...

# Catalog
uv run python -m amazon_spapi.commands.amazon.enqueue_catalog_from_asins -m us asins.txt
uv run python -m amazon_spapi.commands.amazon.enqueue_catalog_from_es -m us ...
```

**Worker 需分别订阅队列：**

```bash
uv run celery -A amazon_spapi.worker worker -Q SpapiItemOffersUpdate_US
uv run celery -A amazon_spapi.worker worker -Q SpapiCatalogItemsUpdate_US
```

## Package layout (`amazon_spapi/`)

业务含义见 [docs/业务说明.md](docs/业务说明.md)。简要对照：

| Directory | Purpose |
|-----------|---------|
| `amazon/` | 业务用例（报价、目录、商品、listing 规则） |
| `spapi/` | SP-API 客户端 |
| `services/` | Elasticsearch |
| `jobs/` | Celery 后台任务 |
| `commands/` | CLI 入队工具 |
| `worker/` | Celery app — **唯一入口：** `celery -A amazon_spapi.worker` |
| `platform/` | 配置、告警、服务 wiring |
| `scheduling/` | 入队、优先级、去重 |

## Background jobs

| Job | Queue |
|-----|-------|
| `refresh_offers` | `SpapiItemOffersUpdate_{MARKET}` |
| `refresh_catalog` | `SpapiCatalogItemsUpdate_{MARKET}` |
| `fetch_products` | Celery default queue |

## Dependencies

Python dependencies are declared in `pyproject.toml` (includes `python-amazon-sp-api`). No private PyPI required.
