# systemd 单元

生产参数（**队列、并发、worker 名、限速**）在 **`/etc/conf.d/celery_spapi`**，不在 `config.ini`。

| 单元 | 环境变量 |
|------|----------|
| `amazon-spapi-offers.service` | `OFFERS_*` |
| `amazon-spapi-catalog.service` | `CATALOG_*` |

安装：

```bash
sudo cp deploy/conf.d/celery_spapi.example /etc/conf.d/celery_spapi
# 编辑 BROKER_URL、卖场、队列等
sudo ./deploy/install-systemd.sh --user Admin --app-dir ~/src/em-workers
sudo systemctl enable --now amazon-spapi-offers amazon-spapi-catalog
```

改 `/etc/conf.d/celery_spapi` 后：

```bash
sudo systemctl daemon-reload
sudo systemctl restart amazon-spapi-offers amazon-spapi-catalog
```
