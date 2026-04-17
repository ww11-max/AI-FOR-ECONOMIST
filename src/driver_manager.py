"""
跨浏览器驱动管理器
自动检测系统已安装的浏览器（Chrome > Edge > Firefox），
利用 Selenium 4 内置 Selenium Manager 自动下载匹配驱动。
"""

import os
import sys
import random
import time
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By

from config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 平台检测
# ============================================================
_PLATFORM = sys.platform  # "win32", "darwin", "linux"

# ============================================================
# 浏览器自动检测（跨平台）
# ============================================================

def _get_browser_paths() -> dict:
    """根据当前平台返回浏览器默认安装路径"""
    paths = {}

    if _PLATFORM == "win32":
        paths["chrome"] = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        paths["edge"] = [
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
        paths["firefox"] = [
            os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
        ]
    elif _PLATFORM == "darwin":
        paths["chrome"] = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
        paths["edge"] = [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
        paths["firefox"] = [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            os.path.expanduser("~/Applications/Firefox.app/Contents/MacOS/firefox"),
        ]
    else:  # Linux
        paths["chrome"] = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            os.path.expanduser("~/.local/share/applications/chrome-linux/chrome"),
        ]
        paths["edge"] = [
            "/usr/bin/microsoft-edge",
            "/usr/bin/microsoft-edge-stable",
        ]
        paths["firefox"] = [
            "/usr/bin/firefox",
            "/usr/bin/firefox-esr",
        ]

    return paths

_BROWSER_PATHS = _get_browser_paths()

# 各浏览器的 User-Agent 模板（跨平台）
_UA_TEMPLATES = {
    "chrome": {
        "win32": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "darwin": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
    },
    "edge": {
        "win32": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36 Edg/{v}.0.0.0",
        "darwin": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36 Edg/{v}.0.0.0",
        "linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36 Edg/{v}.0.0.0",
    },
    "firefox": {
        "win32": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "darwin": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
        "linux": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    },
}


def detect_installed_browsers() -> list:
    """
    检测系统上已安装的浏览器，按优先级返回。

    Returns:
        已安装浏览器名称列表，如 ['chrome', 'edge']
    """
    installed = []
    for name, paths in _BROWSER_PATHS.items():
        for p in paths:
            if os.path.isfile(p):
                installed.append(name)
                break
    return installed


def auto_detect_browser(preferred: str = None) -> str:
    """
    自动选择浏览器。

    优先级：用户指定 > Chrome > Edge > Firefox

    Args:
        preferred: 用户在.env中指定的浏览器

    Returns:
        浏览器名称 'chrome' / 'edge' / 'firefox'

    Raises:
        RuntimeError: 未找到任何支持的浏览器
    """
    if preferred and preferred.lower() in ("chrome", "edge", "firefox"):
        installed = detect_installed_browsers()
        if preferred.lower() in installed:
            logger.info(f"使用用户指定的浏览器: {preferred}")
            return preferred.lower()
        else:
            logger.warning(f"指定的浏览器 {preferred} 未安装，尝试自动检测")

    installed = detect_installed_browsers()

    # 优先级顺序
    for candidate in ["chrome", "edge", "firefox"]:
        if candidate in installed:
            logger.info(f"自动检测到浏览器: {candidate}")
            return candidate

    raise RuntimeError(
        "未检测到支持的浏览器（Chrome/Edge/Firefox）。"
        "请安装至少一个 Chromium 内核浏览器或 Firefox。"
    )


# ============================================================
# 浏览器驱动管理器
# ============================================================

class BrowserManager:
    """
    跨浏览器驱动管理器。
    自动检测系统浏览器，利用 Selenium 4 Selenium Manager 自动下载驱动。
    """

    def __init__(self, headless: bool = None, download_dir: str = None,
                 browser: str = None, connect_port: int = None):
        self.headless = headless if headless is not None else settings.USE_HEADLESS
        self.download_dir = download_dir or str(settings.OUTPUTS_DIR)
        self.driver = None
        self.connect_port = connect_port  # 连接已有浏览器的调试端口

        # 确定浏览器
        env_browser = os.getenv("BROWSER", "").strip().lower()
        self.browser = browser or env_browser or None  # None 表示自动检测

        # 连接模式不需要检测浏览器
        if connect_port:
            self.browser_name = "edge"  # 默认，实际由连接决定
        else:
            self.browser_name = auto_detect_browser(self.browser)

    def create_driver(self):
        """创建并配置 WebDriver（含反检测）"""
        # 连接模式：复用用户已打开的浏览器
        if self.connect_port:
            self._connect_existing(self.connect_port)
            return self.driver

        creator = {
            "chrome": self._create_chrome,
            "edge": self._create_edge,
            "firefox": self._create_firefox,
        }
        factory = creator.get(self.browser_name)
        if not factory:
            raise ValueError(f"不支持的浏览器: {self.browser_name}")

        driver = factory()
        self._execute_anti_detection(driver)
        logger.info(f"{self.browser_name.capitalize()} WebDriver 创建成功（反检测已注入）")
        self.driver = driver
        return driver

    def _connect_existing(self, port: int):
        """
        连接到用户已打开的浏览器实例（通过远程调试端口）。

        用户需先启动浏览器时加 --remote-debugging-port 参数，例如：
          msedge --remote-debugging-port=9222

        这样 skill 直接复用用户的登录态、cookies、session，
        不会触发验证码等反爬机制。
        """
        debugger_url = f"http://127.0.0.1:{port}"
        debugger_addr = f"127.0.0.1:{port}"  # Selenium debuggerAddress 只接受 host:port

        try:
            # 先探测调试端口是否可用
            import urllib.request
            req = urllib.request.Request(f"{debugger_url}/json/version", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                info = json.loads(resp.read().decode())

            # 识别浏览器类型
            browser_name = info.get("Browser", "").lower()
            user_agent = info.get("User-Agent", "")

            if "edg" in user_agent:
                self.browser_name = "edge"
            elif "chrome" in user_agent:
                self.browser_name = "chrome"
            elif "firefox" in user_agent:
                self.browser_name = "firefox"
            else:
                self.browser_name = "edge"  # 默认

            logger.info(f"检测到已有浏览器: {self.browser_name} ({browser_name})")

            # 用对应浏览器类型连接
            if self.browser_name == "edge":
                options = EdgeOptions()
                options.add_experimental_option("debuggerAddress", debugger_addr)
                self.driver = webdriver.Edge(options=options)
            elif self.browser_name == "chrome":
                options = ChromeOptions()
                options.add_experimental_option("debuggerAddress", debugger_addr)
                self.driver = webdriver.Chrome(options=options)
            elif self.browser_name == "firefox":
                # Firefox 用不同的连接方式
                options = FirefoxOptions()
                # Firefox 暂不支持 debuggerAddress，给出提示
                logger.warning("Firefox 不支持远程调试连接，请使用 Chrome 或 Edge")
                raise RuntimeError("Firefox 不支持 --connect 模式，请使用 Chrome 或 Edge")

            logger.info(f"成功连接到已有 {self.browser_name} 实例 (端口 {port})")
            logger.info("将复用用户的登录态和 cookies，不会触发验证码")

        except urllib.error.URLError:
            raise RuntimeError(
                f"无法连接到调试端口 {port}。"
                f"\n请确保浏览器已用以下命令启动："
                f"\n  Edge:  msedge --remote-debugging-port={port}"
                f"\n  Chrome: chrome --remote-debugging-port={port}"
            )
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"连接浏览器失败: {e}")

    def close(self):
        """关闭驱动"""
        if self.driver:
            try:
                # 连接模式下不关闭用户的浏览器，只断开
                if self.connect_port:
                    self.driver.quit()
                    logger.info(f"已断开与 {self.browser_name} 的连接（浏览器未关闭）")
                else:
                    self.driver.quit()
                    logger.info(f"{self.browser_name.capitalize()} WebDriver 已关闭")
            except Exception as e:
                logger.error(f"关闭WebDriver时出错: {e}")
            finally:
                self.driver = None

    def __enter__(self):
        self.create_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ============================================================
    # Chrome
    # ============================================================
    def _create_chrome(self):
        options = ChromeOptions()
        self._apply_common_options(options)
        self._apply_chromium_prefs(options)
        self._apply_random_ua(options, "chrome")
        # Selenium 4 自动管理驱动，无需指定 Service 路径
        return webdriver.Chrome(options=options)

    # ============================================================
    # Edge
    # ============================================================
    def _create_edge(self):
        options = EdgeOptions()
        self._apply_common_options(options)
        self._apply_chromium_prefs(options)
        self._apply_random_ua(options, "edge")
        return webdriver.Edge(options=options)

    # ============================================================
    # Firefox
    # ============================================================
    def _create_firefox(self):
        options = FirefoxOptions()

        if self.headless:
            options.add_argument("--headless")

        # 反检测
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)

        # UA（根据平台选择对应模板）
        ua_templates = _UA_TEMPLATES.get("firefox", {})
        ua = ua_templates.get(_PLATFORM, ua_templates.get("win32", ""))
        if ua:
            options.set_preference("general.useragent.override", ua)

        # 下载配置
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", self.download_dir)
        options.set_preference("browser.download.manager.showWhenStarting", False)
        options.set_preference("browser.helperApps.neverAsk.saveToDisk",
                               "application/pdf,application/x-pdf,application/octet-stream")
        options.set_preference("pdfjs.disabledCache.enabled", True)

        # 禁用自动化提示
        options.set_preference("dom.webnotifications.enabled", False)

        return webdriver.Firefox(options=options)

    # ============================================================
    # 通用配置（Chromium 内核共用：Chrome + Edge）
    # ============================================================
    def _apply_common_options(self, options):
        """Chromium 通用选项"""
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-software-rasterizer")
            options.add_argument("--disable-images")
            options.add_argument("--disable-extensions")
            options.add_argument("--window-size=1920,1080")

        # 反检测核心
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # SSL 证书：默认不禁用，用户可通过 UNSAFE_SSL=true 启用
        if settings.UNSAFE_SSL:
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--allow-insecure-localhost")

        # 禁止自动化提示弹窗
        options.add_argument("--disable-infobars")

    def _apply_chromium_prefs(self, options):
        """Chromium 下载偏好设置"""
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": False,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        options.add_experimental_option("prefs", prefs)

    def _apply_random_ua(self, options, browser: str):
        """随机 User-Agent（根据当前平台选择对应模板）"""
        templates = _UA_TEMPLATES.get(browser, {})
        ua_template = templates.get(_PLATFORM, templates.get("win32", ""))
        if ua_template:
            version = random.randint(120, 135)
            ua = ua_template.format(v=version)
            options.add_argument(f"user-agent={ua}")

    # ============================================================
    # 反检测脚本注入
    # ============================================================
    def _execute_anti_detection(self, driver):
        """注入反检测 JS 脚本"""
        if self.browser_name == "firefox":
            # Firefox 用 CDP 方式注入
            try:
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                })
            except Exception:
                pass
            return

        # Chromium 内核脚本
        # 动态设置 platform（匹配当前操作系统）
        _platform_str = {"win32": "Win32", "darwin": "MacIntel", "linux": "Linux x86_64"}.get(
            _PLATFORM, "Win32"
        )
        scripts = [
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
            "Object.defineProperty(navigator, 'chrome', {get: () => undefined})",
            "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})",
            "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']})",
            f"Object.defineProperty(navigator, 'platform', {{get: () => '{_platform_str}'}})",
        ]
        for script in scripts:
            try:
                driver.execute_script(script)
            except Exception:
                pass


# ============================================================
# 向后兼容别名
# ============================================================
EdgeDriverManager = BrowserManager


# ============================================================
# 工具函数
# ============================================================

def simulate_human_behavior(driver):
    """模拟人类浏览行为，降低被检测风险"""
    try:
        driver.get(settings.CNKI_SEARCH_URL)
        time.sleep(random.uniform(1.0, 2.0))

        search_terms = ["人工智能", "机器学习", "深度学习", "大数据", "经济增长",
                        "FDI", "国际贸易", "金融", "货币政策", "数字经济"]
        term = random.choice(search_terms)
        driver.get(f"{settings.CNKI_SEARCH_URL}?kw={term}")
        time.sleep(random.uniform(1.5, 2.5))

        try:
            elements = driver.find_elements(By.CSS_SELECTOR, ".result-table-list a.fz14")
            if elements:
                random.choice(elements).click()
                time.sleep(random.uniform(2.0, 3.0))
                driver.back()
                time.sleep(random.uniform(1.0, 1.5))
        except Exception:
            pass

        for _ in range(random.randint(2, 5)):
            driver.execute_script(f"window.scrollBy(0, {random.randint(200, 800)});")
            time.sleep(random.uniform(0.5, 1.2))

    except Exception as e:
        logger.warning(f"模拟人类行为时出错: {e}")


def wait_random_time():
    """等待随机时间"""
    time.sleep(random.uniform(settings.WAIT_TIME_MIN, settings.WAIT_TIME_MAX))
