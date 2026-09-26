# Potato 门训机器人 NAS 部署

本目录已经包含 Potato 适配层和 GitHub 参考项目的完整业务代码，部署后不依赖 Windows 的 F 盘。

## 1. 上传目录

将整个 `mentorship_bot` 目录上传到 NAS。本机实际部署位置为：

```text
/volume2/docker/potato-menxun-bot
```

不要把 `config.json` 或 `data/` 上传到公开仓库，它们包含 Bot token、身份绑定和管理员信息。

## 2. 检查配置

`config.json` 中科大网站必须统一使用：

```json
{
  "id": "zk",
  "name": "科大",
  "url": "https://mouss.synology.me:1777/",
  "chat_ids": []
}
```

用户私聊操作顺序统一为：

```text
网站
科大
绑定 真实姓名
打卡 灵修
```

姓名必须与网站 `/api/state` 返回的成员名单完全一致。

## 3. 启动

SSH 登录 NAS 后执行：

```sh
cd /volume2/docker/potato-menxun-bot
chmod +x manage.sh
./manage.sh setup
./manage.sh admin-key
./manage.sh start
./manage.sh logs
```

如果 SSH 用户没有 Docker socket 权限，可直接使用 NAS 的 Python 3.12：

```sh
chmod +x manage-native.sh
./manage-native.sh test
./manage-native.sh start
./manage-native.sh status
./manage-native.sh health
```

当前 NAS 使用上面的 Docker Compose 方式，容器设置了 `restart: unless-stopped`，会在 Docker 服务重启后自动恢复。若改用 Python 3.12 原生方式，需在 DSM 的“控制面板 → 任务计划 → 新增 → 触发的任务 → 用户定义的脚本”中选择开机事件，用户选择 `yimaneili`，脚本填写：

```sh
/volume2/docker/potato-menxun-bot/manage-native.sh start
```

## 4. 配置通知群

先把机器人加入 Potato 门训群，并在群里发送一条消息。日志会显示：

```text
收到消息：chat_id=123456 chat_type=2
```

管理员也可以私聊机器人执行：

```text
管理员 绑定群
```

按机器人私聊提示选择已发现的群、确认匹配的 Cedar 小组后即可绑定；发送 `管理员 解绑群` 可解除绑定。该入口只管理 Cedar 小组。旧网站的现有通知群配置可继续保留。

如需手动配置，可把群 ID 写入对应 Cedar 小组的 `config.json` 条目：

```json
"chat_ids": [123456]
```

修改配置后执行：

```sh
./manage.sh restart
```

## 5. 避免重复运行

同一个 Bot token 只能保留一个轮询实例。NAS 启动成功后，应停止 Windows 上的机器人进程，否则两个实例会争抢消息。

## 6. 日常维护

```sh
./manage.sh status
./manage.sh logs
./manage.sh restart
./manage.sh stop
./manage.sh admin-key
```

`docker compose ps` 显示 `healthy` 表示 Potato 轮询和机器人心跳正常。
