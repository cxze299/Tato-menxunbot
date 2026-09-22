#!/bin/sh
set -eu
cd "$(dirname "$0")"
command="${1:-help}"
case "$command" in
  setup)
    mkdir -p data
    test -f config.json || { cp config.example.json config.json; echo "已生成 config.json，请填写 token、网站地址和 chat_ids。"; }
    docker compose build
    ;;
  start) docker compose up -d --build ;;
  stop) docker compose down ;;
  restart) docker compose down; docker compose up -d --build ;;
  logs) docker compose logs -f --tail 200 bot ;;
  status) docker compose ps ;;
  test) docker compose run --rm --no-deps bot python -m py_compile bot.py reference/menxun_bot.py ;;
  admin-key) docker compose run --rm --no-deps bot python set_admin_key.py ;;
  *) echo "用法：./manage.sh setup|start|stop|restart|logs|status|test|admin-key" ;;
esac
