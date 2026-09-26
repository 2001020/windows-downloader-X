# Windows 版

## 运行

双击 `WinISO-Downloader.exe`。这是单文件程序，免安装，aria2 已经内置在里面。

- 系统要求：Windows 10 / 11（x64）。Windows 11 on Arm 也可以运行（系统会自动转译）。
- 如果出现“Windows 已保护你的电脑”（SmartScreen），点 **更多信息 → 仍要运行**。这是因为程序没有代码签名。
- 设置保存在 `%APPDATA%\winiso-downloader\config.json`。

## 构建

需要 [python.org](https://www.python.org/downloads/windows/) 的 64 位 Python 3.9+（安装时勾选 tcl/tk，默认就是勾选的）。

```bat
windows\build.bat
```

或者在 PowerShell 里执行：

```powershell
powershell -ExecutionPolicy Bypass -File windows\build.ps1
```

脚本会：

1. 下载 aria2 官方 Windows 版（aria2-1.37.0-win-64bit），并校验 SHA-256；
2. 安装 PyInstaller（`common/requirements-build.txt`）；
3. 生成 `windows\dist\WinISO-Downloader.exe`。

可以用环境变量 `PYTHON` 指定 Python 路径；设置 `SKIP_PIP=1` 可以跳过 pip 安装。

自检（CI 也在用）：`WinISO-Downloader.exe --selftest result.txt --network`
