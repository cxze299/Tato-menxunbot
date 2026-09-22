#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p data logs
pid_file="data/bot.pid"
if test -x /var/packages/python312/target/bin/python3; then
  default_python=/var/packages/python312/target/bin/python3
else
  default_python="$(command -v python3)"
fi
python_bin="${PYTHON_BIN:-$default_python}"

is_running() {
  test -f "$pid_file" || return 1
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  test -n "$pid" && kill -0 "$pid" 2>/dev/null
}

start_bot() {
  if is_running; then echo "机器人已运行，PID=$(cat "$pid_file")"; return; fi
  rm -f "$pid_file"
  nohup "$python_bin" bot.py >>logs/bot.log 2>&1 </dev/null &
  echo "$!" >"$pid_file"
  sleep 3
  if is_running; then echo "机器人已启动，PID=$(cat "$pid_file")"; else echo "启动失败，请查看 logs/bot.log"; exit 1; fi
}

stop_bot() {
  if ! is_running; then rm -f "$pid_file"; echo "机器人未运行"; return; fi
  pid="$(cat "$pid_file")"; kill "$pid"
  count=0
  while kill -0 "$pid" 2>/dev/null && test "$count" -lt 20; do sleep 1; count=$((count+1)); done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"; echo "机器人已停止"
}

case "${1:-status}" in
  start) start_bot ;;
  stop) stop_bot ;;
  restart) stop_bot; start_bot ;;
  status) if is_running; then echo "running PID=$(cat "$pid_file")"; else echo "stopped"; exit 1; fi ;;
  logs) tail -n 200 -f logs/bot.log ;;
  test) "$python_bin" -m py_compile bot.py healthcheck.py reference/menxun_bot.py; echo "检查通过" ;;
  health) "$python_bin" healthcheck.py ;;
  *) echo "用法：./manage-native.sh start|stop|restart|status|logs|test|health" ;;
esac
