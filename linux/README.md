# Linux 版 · WinISO Downloader

## 运行

解压 `WinISO-Downloader-linux-<架构>.tar.gz`，双击 `WinISO-Downloader-<架构>.AppImage`。

- 支持 x86_64 和 aarch64。需要 glibc 2.35 或更新（Ubuntu 22.04+、Debian 12+、Fedora 36+、Arch 等）和图形桌面（X11 或 XWayland）。
- 如果双击没反应，先确认文件有执行权限：文件属性里勾选“允许作为程序执行”，或执行 `chmod +x WinISO-Downloader-*.AppImage`。
- 如果提示缺少 FUSE（例如在 Docker 中），可以这样运行：`./WinISO-Downloader-*.AppImage --appimage-extract-and-run`
- 设置保存在 `~/.config/winiso-downloader/config.json`。

Run: extract the tarball and double-click the `.AppImage` (or `chmod +x` it and run it from a terminal).

## 构建

需要 Python 3.9+ 和 Tk（Debian/Ubuntu：`sudo apt install python3-tk python3-venv`），以及 Docker。

```bash
bash linux/build.sh
```

脚本会：

1. 用 `build-aria2.sh` 在 Alpine 容器里从 aria2 官方源码编译 **完全静态** 的 aria2c（musl + OpenSSL），可以在任何发行版上运行；
2. 用 PyInstaller 打包程序；
3. 用 appimagetool 生成 `linux/dist/WinISO-Downloader-<架构>.AppImage` 和 `.tar.gz`。

如果没有 Docker，也可以先把任意 aria2c 放到 `linux/build/aria2/aria2c`，脚本就会跳过编译这一步。

可以用环境变量 `PYTHON` 指定 Python 路径；设置 `SKIP_PIP=1` 可以跳过 pip 安装。

自检：`./WinISO-Downloader-x86_64.AppImage --selftest result.txt --network`
