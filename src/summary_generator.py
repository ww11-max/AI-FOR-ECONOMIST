"""
结论摘要生成器
基于PDF文本提取结论段落，结合页面摘要，生成100字以内的研究结论概述
"""

import re
import logging
from typing import Dict, Optional

from .text_extractor import PDFTextExtractor

logger = logging.getLogger(__name__)


class SummaryGenerator:
    """研究结论摘要生成器"""

    def __init__(self, engine: str = "pdfplumber"):
        self.extractor = PDFTextExtractor(engine)

    def generate_summary(self, pdf_path: str,
                         page_abstract: str = "",
                         max_len: int = 100) -> Dict:
        """
        为单篇文献生成研究结论摘要

        Args:
            pdf_path: PDF文件路径
            page_abstract: 从知网页面提取的摘要（可选，作为补充）
            max_len: 摘要最大长度

        Returns:
            {"conclusion": str, "source": str, "char_count": int}
        """
        # 优先从PDF中提取结论
        pdf_conclusion = self.extractor.extract_conclusion(pdf_path)

        if pdf_conclusion:
            return {
                "conclusion": pdf_conclusion,
                "source": "pdf_conclusion",
                "char_count": len(pdf_conclusion),
            }

        # 兜底：使用页面摘要（如果有）
        if page_abstract and len(page_abstract) > 20:
            # 从摘要末尾截取结论性内容
            short_abstract = self._condense_abstract(page_abstract, max_len)
            if short_abstract:
                return {
                    "conclusion": short_abstract,
                    "source": "page_abstract",
                    "char_count": len(short_abstract),
                }

        return {
            "conclusion": "（无法自动提取结论）",
            "source": "none",
            "char_count": 0,
        }

    def _condense_abstract(self, abstract: str, max_len: int) -> str:
        """从摘要中提炼结论性语句"""
        signal_words = ["结果表明", "发现", "证明", "结果显示", "研究显示",
                        "说明", "得出", "揭示", "展示了"]

        sentences = re.split(r"[。！？]", abstract)
        key_sents = [s.strip() for s in sentences
                     if any(w in s for w in signal_words) and len(s.strip()) > 10]

        if not key_sents:
            # 没有信号词，取摘要后半段
            text = abstract.strip()
            if len(text) > max_len:
                # 从中点附近开始截取
                mid = len(text) // 2
                chunk = text[mid:mid + max_len]
                # 对齐到句首
                first_period = chunk.find("。")
                if first_period > 0 and first_period < max_len // 2:
                    chunk = chunk[first_period + 1:]
                return chunk[:max_len - 1].strip() + "…"
            return text

        combined = "。".join(key_sents[:2])
        if len(combined) > max_len:
            combined = combined[:max_len - 1] + "…"
        return combined

    def batch_generate(self, articles: list, download_dir: str) -> list:
        """
        批量生成结论摘要

        Args:
            articles: 文献信息列表 [{"title": ..., "link": ..., ...}]
            download_dir: PDF下载目录

        Returns:
            增强后的文献列表（含conclusion字段）
        """
        results = []
        for article in articles:
            title = article.get("title", "")
            page_abstract = article.get("abstract", "")

            # 尝试匹配PDF文件
            pdf_path = self._find_pdf(title, download_dir)

            if pdf_path:
                summary = self.generate_summary(pdf_path, page_abstract)
                article["conclusion"] = summary["conclusion"]
                article["conclusion_source"] = summary["source"]
                logger.info(f"生成摘要: {title[:30]}... -> {summary['source']}")
            else:
                # 没有PDF，用页面摘要
                if page_abstract:
                    article["conclusion"] = self._condense_abstract(page_abstract, 100)
                    article["conclusion_source"] = "page_abstract"
                else:
                    article["conclusion"] = "（待下载后提取）"
                    article["conclusion_source"] = "none"

            results.append(article)

        return results

    def _find_pdf(self, title: str, download_dir: str) -> Optional[str]:
        """根据标题模糊匹配PDF文件"""
        from pathlib import Path

        download_dir = Path(download_dir)
        if not download_dir.exists():
            return None

        # 清理标题中的非法字符
        clean_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        clean_title = clean_title[:50].strip()  # 截断过长的标题

        # 精确匹配
        for pdf in download_dir.glob("*.pdf"):
            if clean_title in pdf.stem or pdf.stem in clean_title:
                return str(pdf)

        # 模糊匹配：取标题前20个字符
        prefix = clean_title[:20]
        for pdf in download_dir.glob("*.pdf"):
            if prefix in pdf.stem or pdf.stem[:20] in prefix:
                return str(pdf)

        return None
