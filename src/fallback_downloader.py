"""
备用PDF下载模块
当CNKI无权限时，自动通过 Sci-Hub / Google Scholar / Unpaywall 获取PDF

策略优先级：
  1. Sci-Hub  — 覆盖最广，但域名经常变动
  2. Unpaywall — 合法OA渠道，基于DOI查询
  3. Google Scholar — 兜底搜索，尝试直接查找开放PDF链接
"""

import re
import time
import logging
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from .driver_manager import BrowserManager, wait_random_time
from config import settings

logger = logging.getLogger(__name__)


# ============================================================
# Sci-Hub 配置（仅从环境变量读取，不硬编码域名）
# 用户需自行设置 SCIHUB_DOMAINS 环境变量，例如：
#   export SCIHUB_DOMAINS=https://sci-hub.se,https://sci-hub.st
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
)

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class FallbackDownloader:
    """
    备用PDF下载器
    支持通过 DOI / 标题+期刊 从开放渠道获取PDF
    """

    def __init__(self, download_dir: str):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._scihub_domain = None  # 缓存可用的Sci-Hub域名
        self._scihub_domains = settings.SCIHUB_DOMAINS  # 从环境变量读取
        self.driver_manager = None
        self.driver = None

    def __enter__(self):
        """启动浏览器（用于Google Scholar兜底搜索）"""
        self.driver_manager = BrowserManager(headless=True, download_dir=str(self.download_dir))
        self.driver = self.driver_manager.create_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver_manager:
            self.driver_manager.close()

    # ============================================================
    # 对外接口：批量下载失败文献
    # ============================================================
    def batch_download(self, articles: List[Dict]) -> Dict[str, List]:
        """
        对CNKI下载失败的文献逐篇尝试备用渠道

        Args:
            articles: 需要重试的文章列表，每个需含 title / doi(可选) / journal(可选)

        Returns:
            {"success": [...], "failed": [...]}
        """
        results = {"success": [], "failed": []}

        # 预探测可用Sci-Hub域名
        self._probe_scihub()

        for i, article in enumerate(articles):
            title = article.get("title", f"article_{i}")
            doi = article.get("doi", "")
            issn = article.get("issn", "") or self._get_issn_from_journal(article.get("journal", ""))

            logger.info(f"[备用下载] ({i+1}/{len(articles)}) {title[:50]}...")

            downloaded = False
            pdf_path = None

            # 策略1: Sci-Hub (优先使用DOI，其次用标题搜索)
            if self._scihub_domain:
                pdf_path = self._try_scihub(title=title, doi=doi, index=i)
                if pdf_path:
                    downloaded = True

            # 策略2: Unpaywall (需要DOI)
            if not downloaded and doi:
                pdf_path = self._try_unpaywall(doi=doi, title=title, index=i)
                if pdf_path:
                    downloaded = True

            # 策略3: Google Scholar 搜索标题查找开放PDF
            if not downloaded:
                pdf_path = self._try_google_scholar(title=title, journal=article.get("journal", ""), index=i)
                if pdf_path:
                    downloaded = True

            if downloaded and pdf_path:
                article["pdf_path"] = str(pdf_path)
                article["download_source"] = "fallback"
                results["success"].append(title)
                logger.info(f"[备用下载] 成功: {title[:50]}...")
            else:
                results["failed"].append(title)
                logger.warning(f"[备用下载] 所有渠道均失败: {title[:50]}...")

            # 礼貌延时
            time.sleep(settings.WAIT_TIME_MIN)

        logger.info(f"[备用下载] 完成: {len(results['success'])} 成功, {len(results['failed'])} 失败")
        return results

    # ============================================================
    # Sci-Hub 下载
    # ============================================================
    def _probe_scihub(self):
        """探测当前可用的Sci-Hub域名（从环境变量读取）"""
        if not self._scihub_domains:
            logger.info("未配置 SCIHUB_DOMAINS 环境变量，将跳过Sci-Hub渠道")
            return
        logger.info("正在探测可用Sci-Hub域名...")
        for domain in self._scihub_domains:
            try:
                resp = requests.get(domain, headers=REQUEST_HEADERS,
                                    timeout=settings.REQUEST_TIMEOUT)
                if resp.status_code == 200 and "sci-hub" in resp.text.lower():
                    self._scihub_domain = domain
                    logger.info(f"Sci-Hub可用: {domain}")
                    return
            except Exception as e:
                logger.debug(f"Sci-Hub域名不可用: {domain} - {e}")
                continue
        logger.warning("所有Sci-Hub域名均不可用，将跳过Sci-Hub渠道")

    def _try_scihub(self, title: str, doi: str, index: int) -> Optional[Path]:
        """尝试通过Sci-Hub下载PDF"""
        if not self._scihub_domain:
            return None

        # 优先用DOI查询，Sci-Hub对DOI支持最好
        query = doi if doi else title
        url = f"{self._scihub_domain}/{query}"

        try:
            logger.debug(f"Sci-Hub请求: {url}")
            resp = requests.get(url, headers=REQUEST_HEADERS,
                                timeout=settings.REQUEST_TIMEOUT)
            resp.raise_for_status()

            html = resp.text

            # 提取PDF嵌入链接：Sci-Hub通常用 <embed> 或 <iframe> 标签
            # 格式1: <embed type="application/pdf" src="...">
            # 格式2: <iframe src="...pdf">
            # 格式3: location.href = '...pdf'
            pdf_url = self._extract_pdf_url_from_html(html)

            if not pdf_url:
                # 兜底：从页面中找任何 .pdf 链接
                pdf_urls = re.findall(r'(https?://[^\s"\'<>]+\.pdf)', html)
                if pdf_urls:
                    pdf_url = pdf_urls[0]

            if not pdf_url:
                logger.debug(f"Sci-Hub未找到PDF链接: {title[:50]}")
                return None

            # 下载PDF文件
            safe_name = self._safe_filename(title, index)
            pdf_path = self.download_dir / f"{safe_name}.pdf"
            return self._download_pdf_file(pdf_url, pdf_path, title)

        except Exception as e:
            logger.debug(f"Sci-Hub下载失败: {title[:50]} - {e}")
            return None

    def _extract_pdf_url_from_html(self, html: str) -> Optional[str]:
        """从Sci-Hub页面HTML中提取PDF链接"""
        patterns = [
            r'<embed[^>]+src=["\']([^"\']+\.pdf)',
            r'<iframe[^>]+src=["\']([^"\']+\.pdf)',
            r'location\.href\s*=\s*["\']([^"\']+\.pdf)',
            r'["\'](/[^"\']*?\.pdf)["\']',  # 相对路径
            r'(https?://[^\s"\'<>]+?/pdf/[^\s"\'<>]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                # 处理相对路径
                if url.startswith("/") and self._scihub_domain:
                    url = f"{self._scihub_domain}{url}"
                return url
        return None

    # ============================================================
    # Unpaywall 下载（合法OA渠道）
    # ============================================================
    def _try_unpaywall(self, doi: str, title: str, index: int) -> Optional[Path]:
        """
        通过Unpaywall API查找OA版本的PDF
        Unpaywall索引了超过4700万篇合法开放获取论文
        """
        unpaywall_email = settings.UNPAYWALL_EMAIL or "eco-acquire@example.com"
        api_url = f"https://api.unpaywall.org/v2/{doi}?email={unpaywall_email}"

        try:
            resp = requests.get(api_url, headers=REQUEST_HEADERS,
                                timeout=settings.REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.debug(f"Unpaywall查询失败 (HTTP {resp.status_code}): {doi}")
                return None

            data = resp.json()

            # 查找最佳OA位置：优先 publisher 版本，其次 repository 版本
            best_oa = data.get("best_oa_location") or {}
            oa_locations = data.get("oa_locations", [])

            pdf_url = None

            # 先检查 best_oa_location
            if best_oa.get("url_for_pdf"):
                pdf_url = best_oa["url_for_pdf"]
            elif best_oa.get("url_for_landing_page"):
                # 尝试从landing page找PDF
                pdf_url = self._find_pdf_on_landing_page(best_oa["url_for_landing_page"])

            # 如果best_oa没有，遍历其他OA位置
            if not pdf_url:
                for loc in oa_locations:
                    if loc.get("url_for_pdf"):
                        pdf_url = loc["url_for_pdf"]
                        break
                    if loc.get("url_for_landing_page"):
                        pdf_url = self._find_pdf_on_landing_page(loc["url_for_landing_page"])
                        if pdf_url:
                            break

            if not pdf_url:
                logger.debug(f"Unpaywall未找到OA PDF: {doi}")
                return None

            safe_name = self._safe_filename(title, index)
            pdf_path = self.download_dir / f"{safe_name}.pdf"
            return self._download_pdf_file(pdf_url, pdf_path, title)

        except Exception as e:
            logger.debug(f"Unpaywall下载失败: {doi} - {e}")
            return None

    def _find_pdf_on_landing_page(self, url: str) -> Optional[str]:
        """访问landing page尝试找到PDF下载链接"""
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS,
                                timeout=settings.REQUEST_TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                return None

            # 查找页面中的PDF链接
            pdf_urls = re.findall(
                r'href=["\']((https?://[^"\']*?\.pdf)[^"\']*)',
                resp.text, re.IGNORECASE
            )
            if pdf_urls:
                # 过滤掉明显不是论文的PDF链接
                for url_match, base_url in pdf_urls:
                    skip_keywords = ["copyright", "license", "terms", "policy", "help", "guide"]
                    if not any(kw in url_match.lower() for kw in skip_keywords):
                        return url_match

            return None
        except Exception:
            return None

    # ============================================================
    # Google Scholar 兜底搜索
    # ============================================================
    def _try_google_scholar(self, title: str, journal: str,
                             index: int) -> Optional[Path]:
        """
        通过Google Scholar搜索文章标题，查找右侧的[PDF]链接
        需要Selenium浏览器（在__enter__中启动）
        """
        if not self.driver:
            logger.warning("浏览器未启动，无法使用Google Scholar渠道")
            return None

        try:
            search_query = title
            if journal:
                search_query = f"{title} {journal}"

            scholar_url = "https://scholar.google.com/scholar?q=" + urllib.parse.quote_plus(search_query)
            logger.debug(f"Google Scholar搜索: {scholar_url}")

            self.driver.get(scholar_url)
            time.sleep(3)

            # Google Scholar结构：搜索结果右侧通常有 [PDF] 链接
            # <a href="...">[PDF]</a> 或 <a href="..."><span>PDF</span></a>
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            # 查找所有含"PDF"的链接
            pdf_links = []
            try:
                all_links = self.driver.find_elements(By.CSS_SELECTOR, "a")
                for link in all_links:
                    link_text = link.text.strip().upper()
                    href = link.get_attribute("href") or ""

                    # 匹配 [PDF] 链接
                    if "PDF" in link_text or ".pdf" in href.lower():
                        # 排除Google Scholar自身的链接
                        if "scholar.google.com" not in href:
                            pdf_links.append(href)
            except Exception as e:
                logger.debug(f"解析Google Scholar结果失败: {e}")

            if not pdf_links:
                logger.debug(f"Google Scholar未找到PDF链接: {title[:50]}")
                return None

            # 尝试第一个PDF链接
            pdf_url = pdf_links[0]
            safe_name = self._safe_filename(title, index)
            pdf_path = self.download_dir / f"{safe_name}.pdf"
            return self._download_pdf_file(pdf_url, pdf_path, title)

        except Exception as e:
            logger.debug(f"Google Scholar下载失败: {title[:50]} - {e}")
            return None

    # ============================================================
    # 工具方法
    # ============================================================
    def _download_pdf_file(self, url: str, save_path: Path,
                            title: str = "") -> Optional[Path]:
        """通用PDF文件下载器"""
        try:
            logger.debug(f"下载PDF: {url[:100]}...")
            resp = requests.get(
                url, headers=REQUEST_HEADERS,
                timeout=max(settings.REQUEST_TIMEOUT, 60),
                stream=True,
            )
            resp.raise_for_status()

            # 验证是否为PDF
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and len(resp.content) < 10000:
                logger.debug(f"响应不是有效PDF (Content-Type: {content_type}, Size: {len(resp.content)})")
                return None

            # 写入文件
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 验证文件
            if save_path.stat().st_size < 10000:
                save_path.unlink()
                logger.debug(f"下载的PDF文件过小，已删除: {save_path.stat().st_size} bytes")
                return None

            logger.info(f"PDF下载成功: {save_path.name} ({save_path.stat().st_size / 1024:.1f}KB)")
            return save_path

        except Exception as e:
            logger.debug(f"PDF下载失败: {title[:50]} - {e}")
            # 清理可能的不完整文件
            if save_path.exists():
                try:
                    save_path.unlink()
                except Exception:
                    pass
            return None

    def _safe_filename(self, title: str, index: int) -> str:
        """生成安全的文件名"""
        # 清理标题中的非法字符
        clean = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', title.strip())
        clean = re.sub(r'_+', '_', clean).strip('_')
        # 截断避免过长
        if len(clean) > 80:
            clean = clean[:80]
        return f"{index+1:03d}_{clean}"

    def _get_issn_from_journal(self, journal_name: str) -> str:
        """根据期刊名从配置中查找ISSN"""
        if not journal_name:
            return ""
        for name, info in settings.TARGET_JOURNALS.items():
            if name in journal_name or journal_name in name:
                return info.get("issn", "")
        return ""
