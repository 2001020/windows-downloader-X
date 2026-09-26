# macOS 版

## 运行

1. 打开 `WinISO-Downloader-macOS.dmg`，把 **WinISO Downloader** 拖进“应用程序”文件夹；
2. 双击运行。

- 系统要求：macOS 10.13 或更高版本。这是通用程序（Universal），Apple 芯片（M 系列）和 Intel Mac 都原生运行。
- 程序没有 Apple 开发者签名。首次打开如果提示“无法验证开发者”或“已损坏”：
  - 打开 **系统设置 → 隐私与安全性**，在页面底部点 **仍要打开**；
  - 或者在终端执行：`xattr -dr com.apple.quarantine "/Applications/WinISO Downloader.app"`
- 设置保存在 `~/Library/Application Support/winiso-downloader/config.json`。

## 构建

推荐用 [python.org](https://www.python.org/downloads/macos/) 的安装包版 Python（universal2，自带 Tk）。用 Homebrew 或其他 Python 构建出来的 App 只支持构建机本身的架构。另外需要 Xcode 命令行工具（`xcode-select --install`）。

```bash
PYTHON=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 bash macos/build.sh
```

脚本会：

1. 用 `build-aria2.sh` 从 aria2 官方源码分别编译 arm64 和 x86_64 版本，再用 `lipo` 合并成通用二进制。HTTPS 使用系统自带的 AppleTLS，不依赖 Homebrew；
2. 用 PyInstaller 打包成 `WinISO Downloader.app`，并做 ad-hoc 签名；
3. 生成 `macos/dist/WinISO-Downloader-macOS.dmg` 和 `.zip`。

自检：`"WinISO Downloader.app/Contents/MacOS/WinISO Downloader" --selftest result.txt --network`
