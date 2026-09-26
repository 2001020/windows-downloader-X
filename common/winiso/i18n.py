"""UI strings (Simplified Chinese / English) and system language detection."""

import locale
import os
import subprocess
import sys

STRINGS = {
    "title": {"zh": "Windows ISO 下载器", "en": "Windows ISO Downloader"},
    "subtitle": {"zh": "从 Microsoft 官方服务器获取正版 Windows 镜像，aria2 多线程加速下载",
                 "en": "Genuine Windows images from Microsoft's own servers, accelerated by aria2"},
    "ui_language": {"zh": "界面语言", "en": "Language"},
    "product": {"zh": "产品", "en": "Product"},
    "edition": {"zh": "版本", "en": "Edition"},
    "language": {"zh": "语言", "en": "Language"},
    "arch": {"zh": "架构", "en": "Architecture"},
    "custom_url": {"zh": "自定义链接", "en": "Custom URL"},
    "custom_url_hint": {"zh": "粘贴 ISO 直链（例如从微软官网复制的链接）",
                        "en": "Paste a direct ISO link (e.g. copied from Microsoft's website)"},
    "product_custom": {"zh": "自定义链接（手动粘贴）", "en": "Custom link (paste manually)"},
    "save_to": {"zh": "保存到", "en": "Save to"},
    "browse": {"zh": "浏览…", "en": "Browse…"},
    "advanced": {"zh": "高级", "en": "Advanced"},
    "connections": {"zh": "连接数", "en": "Connections"},
    "proxy": {"zh": "HTTP 代理", "en": "HTTP proxy"},
    "proxy_hint": {"zh": "留空为直连，例如 http://127.0.0.1:7890", "en": "Empty = direct, e.g. http://127.0.0.1:7890"},
    "verify": {"zh": "下载后校验 SHA-256", "en": "Verify SHA-256 after download"},
    "refresh": {"zh": "刷新", "en": "Refresh"},
    "start": {"zh": "开始下载", "en": "Download"},
    "pause": {"zh": "暂停", "en": "Pause"},
    "resume": {"zh": "继续", "en": "Resume"},
    "cancel": {"zh": "取消", "en": "Cancel"},
    "open_folder": {"zh": "打开文件夹", "en": "Open folder"},
    "open_folder_q": {"zh": "现在打开所在文件夹吗？", "en": "Open the containing folder now?"},
    "copy_link": {"zh": "复制链接", "en": "Copy link"},
    "official_page": {"zh": "官网页面", "en": "Official page"},
    "log": {"zh": "日志", "en": "Log"},
    "file": {"zh": "文件", "en": "File"},
    "source": {"zh": "来源", "en": "Source"},
    "source_value": {"zh": "Microsoft 官方 CDN（software.download.prss.microsoft.com，全球加速）",
                     "en": "Microsoft official CDN (software.download.prss.microsoft.com, global)"},
    "loading": {"zh": "正在加载…", "en": "Loading…"},
    "loading_editions": {"zh": "正在读取 {product} 的版本列表…", "en": "Reading editions of {product}…"},
    "loading_languages": {"zh": "正在读取可用语言…", "en": "Reading available languages…"},
    "fallback_editions": {"zh": "无法读取官网页面，使用内置版本列表",
                          "en": "Could not read the product page, using the built-in edition list"},
    "requesting_link": {"zh": "正在向 Microsoft 请求下载链接…", "en": "Requesting a download link from Microsoft…"},
    "link_ok": {"zh": "已获取官方链接（24 小时内有效）：{name}", "en": "Got official link (valid for 24 h): {name}"},
    "starting_aria2": {"zh": "正在启动 aria2…", "en": "Starting aria2…"},
    "downloading": {"zh": "下载中", "en": "Downloading"},
    "paused": {"zh": "已暂停", "en": "Paused"},
    "verifying": {"zh": "正在校验 SHA-256…", "en": "Verifying SHA-256…"},
    "verify_ok": {"zh": "SHA-256 校验通过，与微软官网公布的值一致", "en": "SHA-256 matches the value published by Microsoft"},
    "verify_bad": {"zh": "SHA-256 不一致！文件可能已损坏，建议删除后重新下载。\n期望：{expected}\n实际：{actual}",
                   "en": "SHA-256 mismatch! The file may be corrupt; delete it and download again.\nExpected: {expected}\nActual: {actual}"},
    "no_hash": {"zh": "官网未提供该语言的 SHA-256，已跳过校验", "en": "Microsoft publishes no SHA-256 for this language; skipped"},
    "sha256_actual": {"zh": "SHA-256：{value}", "en": "SHA-256: {value}"},
    "done": {"zh": "下载完成：{path}", "en": "Download finished: {path}"},
    "done_title": {"zh": "下载完成", "en": "Finished"},
    "cancelled": {"zh": "已取消下载", "en": "Download cancelled"},
    "failed": {"zh": "下载失败：{error}", "en": "Download failed: {error}"},
    "error_title": {"zh": "出错了", "en": "Error"},
    "blocked": {"zh": "Microsoft 拒绝了本次请求（错误 715-123130）。\n\n"
                      "微软会拦截来自代理、VPN、数据中心 IP 或过于频繁的请求。\n\n"
                      "解决办法：\n"
                      "1. 关闭代理 / VPN，并清空“高级 → HTTP 代理”后重试；\n"
                      "2. 等几分钟后再试；\n"
                      "3. 点“官网页面”在浏览器中获取链接，再用“自定义链接”下载。\n\n"
                      "详情：{error}",
                "en": "Microsoft rejected the request (error 715-123130).\n\n"
                      "Microsoft blocks requests from proxies, VPNs, data-centre IPs or too many requests.\n\n"
                      "What to do:\n"
                      "1. Turn off your proxy / VPN, clear Advanced → HTTP proxy and retry;\n"
                      "2. Wait a few minutes and retry;\n"
                      "3. Press \"Official page\", get a link in your browser and use \"Custom link\".\n\n"
                      "Details: {error}"},
    "no_arch": {"zh": "微软没有返回 {arch} 架构的链接", "en": "Microsoft returned no link for {arch}"},
    "need_url": {"zh": "请输入以 http:// 或 https:// 开头的下载链接", "en": "Please enter a link starting with http:// or https://"},
    "need_selection": {"zh": "请先选择版本和语言", "en": "Please choose an edition and a language first"},
    "no_aria2": {"zh": "找不到 aria2c，程序文件可能不完整，请重新下载本程序。",
                 "en": "aria2c was not found; the application seems incomplete, please download it again."},
    "file_exists": {"zh": "{path} 已存在。\n\n是否覆盖（删除后重新下载）？",
                    "en": "{path} already exists.\n\nOverwrite it (delete and download again)?"},
    "confirm_cancel": {"zh": "取消下载并删除未完成的文件？\n（选“否”则保留，下次选择同一镜像可断点续传）",
                       "en": "Cancel and delete the unfinished file?\n(Choose \"No\" to keep it and resume later)"},
    "confirm_quit": {"zh": "下载尚未完成，确定退出？\n（未完成的文件会保留，下次可断点续传）",
                     "en": "The download is not finished. Quit anyway?\n(The partial file is kept and can be resumed later)"},
    "resuming_partial": {"zh": "发现未完成的下载，将断点续传", "en": "Found an unfinished download, resuming it"},
    "stat_line": {"zh": "{done} / {total}    速度 {speed}/s    剩余 {eta}    连接 {conns}",
                  "en": "{done} / {total}    {speed}/s    ETA {eta}    {conns} connections"},
    "ready": {"zh": "就绪", "en": "Ready"},
    "copied": {"zh": "链接已复制到剪贴板", "en": "Link copied to the clipboard"},
    "arch_x64": {"zh": "x64（64 位 Intel/AMD）", "en": "x64 (64-bit Intel/AMD)"},
    "arch_x86": {"zh": "x86（32 位）", "en": "x86 (32-bit)"},
    "arch_arm64": {"zh": "Arm64（骁龙等 ARM 设备）", "en": "Arm64 (Snapdragon and other ARM devices)"},
}

# Microsoft SKU language names -> Chinese display names.
LANGUAGE_ZH = {
    "Arabic": "阿拉伯语",
    "Brazilian Portuguese": "葡萄牙语（巴西）",
    "Bulgarian": "保加利亚语",
    "Chinese (Simplified)": "简体中文",
    "Chinese Simplified": "简体中文",
    "Chinese (Traditional)": "繁體中文",
    "Chinese Traditional": "繁體中文",
    "Croatian": "克罗地亚语",
    "Czech": "捷克语",
    "Danish": "丹麦语",
    "Dutch": "荷兰语",
    "English": "英语（美国）",
    "English International": "英语（国际）",
    "Estonian": "爱沙尼亚语",
    "Finnish": "芬兰语",
    "French": "法语",
    "French Canadian": "法语（加拿大）",
    "German": "德语",
    "Greek": "希腊语",
    "Hebrew": "希伯来语",
    "Hungarian": "匈牙利语",
    "Italian": "意大利语",
    "Japanese": "日语",
    "Korean": "韩语",
    "Latvian": "拉脱维亚语",
    "Lithuanian": "立陶宛语",
    "Norwegian": "挪威语",
    "Polish": "波兰语",
    "Portuguese": "葡萄牙语（葡萄牙）",
    "Romanian": "罗马尼亚语",
    "Russian": "俄语",
    "Serbian Latin": "塞尔维亚语（拉丁）",
    "Slovak": "斯洛伐克语",
    "Slovenian": "斯洛文尼亚语",
    "Spanish": "西班牙语",
    "Spanish (Mexico)": "西班牙语（墨西哥）",
    "Swedish": "瑞典语",
    "Thai": "泰语",
    "Turkish": "土耳其语",
    "Ukrainian": "乌克兰语",
}

# POSIX locale prefix -> preferred Microsoft SKU language.
LOCALE_TO_SKU = {
    "zh_cn": "Chinese (Simplified)", "zh_sg": "Chinese (Simplified)", "zh_hans": "Chinese (Simplified)",
    "zh_tw": "Chinese (Traditional)", "zh_hk": "Chinese (Traditional)", "zh_mo": "Chinese (Traditional)",
    "zh_hant": "Chinese (Traditional)", "zh": "Chinese (Simplified)",
    "en_us": "English", "en": "English International",
    "ar": "Arabic", "pt_br": "Brazilian Portuguese", "pt": "Portuguese", "bg": "Bulgarian",
    "hr": "Croatian", "cs": "Czech", "da": "Danish", "nl": "Dutch", "et": "Estonian", "fi": "Finnish",
    "fr_ca": "French Canadian", "fr": "French", "de": "German", "el": "Greek", "he": "Hebrew",
    "hu": "Hungarian", "it": "Italian", "ja": "Japanese", "ko": "Korean", "lv": "Latvian",
    "lt": "Lithuanian", "nb": "Norwegian", "no": "Norwegian", "pl": "Polish", "ro": "Romanian",
    "ru": "Russian", "sr": "Serbian Latin", "sk": "Slovak", "sl": "Slovenian", "es_mx": "Spanish (Mexico)",
    "es": "Spanish", "sv": "Swedish", "th": "Thai", "tr": "Turkish", "uk": "Ukrainian",
}


def system_locale():
    """Best guess of the user's locale, e.g. "zh_CN" (works for GUI launches too)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                return buf.value.replace("-", "_")
        except Exception:
            pass
    if sys.platform == "darwin":
        # Apps started from Finder get no LANG, so ask the user defaults.
        for key in ("AppleLanguages", "AppleLocale"):
            try:
                out = subprocess.run(["defaults", "read", "-g", key], capture_output=True, text=True,
                                     timeout=5).stdout
                token = out.replace("(", " ").replace(")", " ").replace('"', " ").replace(",", " ").split()
                if token:
                    return token[0].replace("-", "_")
            except Exception:
                pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX") and not value.startswith("C."):
            return value.split(":")[0].split(".")[0]
    try:
        value = locale.getlocale()[0]
        if value:
            return value
    except Exception:
        pass
    return "en_US"


def default_ui_language():
    return "zh" if system_locale().lower().startswith("zh") else "en"


def preferred_sku_language():
    loc = system_locale().lower().replace("-", "_")
    parts = loc.split("_")
    # zh_Hans_CN style (macOS) -> check script subtag too.
    candidates = [loc, "_".join(parts[:2]), parts[0]]
    if len(parts) >= 3:
        candidates.insert(1, parts[0] + "_" + parts[-1])
    for c in candidates:
        if c in LOCALE_TO_SKU:
            return LOCALE_TO_SKU[c]
    return "English International"


class Translator:
    def __init__(self, lang):
        self.lang = lang

    def __call__(self, key, **kwargs):
        entry = STRINGS.get(key)
        text = (entry.get(self.lang) or entry.get("en")) if entry else key
        return text.format(**kwargs) if kwargs else text

    def language_name(self, sku_language):
        if self.lang == "zh":
            zh = LANGUAGE_ZH.get(sku_language)
            if zh:
                return "%s  ·  %s" % (zh, sku_language)
        return sku_language
