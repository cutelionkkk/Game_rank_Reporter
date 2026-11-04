#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print "请先按 README.md 安装项目依赖，然后再打开本文件。"
  read "?按回车键关闭窗口…"
  exit 1
fi
print "游戏雷达：http://127.0.0.1:8765"
print "请保留此窗口。关闭窗口会停止网页服务。"
.venv/bin/python run.py --serve --open-browser
if [[ $? -ne 0 ]]; then
  print "如果网页已经打开，可直接使用；其他启动问题请查看上方提示。"
  read "?按回车键关闭窗口…"
fi
