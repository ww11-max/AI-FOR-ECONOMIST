"""
PDF文本提取模块
支持pdfplumber和PyMuPDF双引擎，从PDF中提取全文和研究结论
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import Counter

from config import settings

logger = logging.getLogger(__name__)


class PDFTextExtractor:
    """PDF文本提取器"""

    def __init__(self, engine: str = "pdfplumber"):
        """
        Args:
            engine: "pdfplumber" 或 "pymupdf"
        """
        self.engine = engine

    def extract_text(self, pdf_path: str) -> Tuple[bool, str, Dict]:
        """
        提取PDF全文

        Returns:
            (成功, 文本, 元数据)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return False, "", {"error": f"文件不存在: {pdf_path}"}

        try:
            if self.engine == "pdfplumber":
                text, metadata = self._extract_pdfplumber(pdf_path)
            elif self.engine == "pymupdf":
                text, metadata = self._extract_pymupdf(pdf_path)
            else:
                return False, "", {"error": f"不支持的引擎: {self.engine}"}

            text = self._clean_text(text)
            metadata.update(self._get_basic_info(pdf_path, text))
            return True, text, metadata

        except Exception as e:
            logger.error(f"提取PDF失败 {pdf_path}: {e}")
            return False, "", {"error": str(e)}

    def _extract_pdfplumber(self, pdf_path: Path) -> Tuple[str, Dict]:
        """使用pdfplumber提取"""
        import pdfplumber

        text, metadata = "", {}
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.metadata:
                metadata = {k: str(v) for k, v in (pdf.metadata or {}).items() if v}
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text, metadata

    def _extract_pymupdf(self, pdf_path: Path) -> Tuple[str, Dict]:
        """使用PyMuPDF提取"""
        import fitz

        text, metadata = "", {}
        doc = fitz.open(str(pdf_path))
        if doc.metadata:
            metadata = {k: str(v) for k, v in doc.metadata.items() if v}
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_text = page.get_text()
            if page_text:
                text += page_text + "\n"
        doc.close()
        return text, metadata

    def _clean_text(self, text: str) -> str:
        """清理提取的文本"""
        if not text:
            return ""

        # 合并多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # 移除页码、页眉页脚等噪声
        patterns = [
            r"\d+\s*/\s*\d+",
            r"第\s*\d+\s*页\s*共\s*\d+\s*页",
            r"Copyright\s*©.*?\n",
            r"http[s]?://\S+",
            r"\.{3,}",  # 省略号
            # 期刊页眉格式: "世界经济 * 2026年第4期 ·"
            r"[\u4e00-\u9fff]+\s*[*·]\s*\d{4}年第\d+期\s*[*·]\s*",
            r"^\s*[\u4e00-\u9fff]+\s*\*\s*\d{4}年.*?[·\n]",
            # 通用页眉: 期刊名 + 年份 + 期号
            r"^\s*[\u4e00-\u9fff（)]+\s*\d{4}\s*[年第期\.]*\s*\d*\s*[期卷]*\s*[·*]*",
            # 页脚 DOI / 收稿日期等
            r"DOI[:\s]*10\.\S+",
            r"收稿日期[:\s]*\d{4}[-/]\d{1,2}[-/]\d{1,2}",
            r"基金项目[:：].*?\n",
        ]
        for p in patterns:
            text = re.sub(p, "", text, flags=re.IGNORECASE | re.MULTILINE)

        return text.strip()

    def _get_basic_info(self, pdf_path: Path, text: str) -> Dict:
        """提取基本信息"""
        info = {
            "file_size_kb": round(pdf_path.stat().st_size / 1024, 1),
            "char_count": len(text),
            "word_count": len(text.split()) if text else 0,
        }

        # 尝试找标题
        lines = text.split("\n")[:10]
        candidates = [l.strip() for l in lines if len(l.strip()) > 10]
        if candidates:
            info["possible_title"] = max(candidates, key=len)

        # 高频词
        chinese_words = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
        if chinese_words:
            top_words = Counter(chinese_words).most_common(10)
            # 过滤常见虚词
            stop_words = {"一个", "本文", "我们", "他们", "这个", "那个", "可以", "进行",
                         "研究", "分析", "结果", "影响", "模型", "数据", "方法",
                         "中国", "国家", "企业", "市场", "经济", "社会", "发展"}
            filtered = [(w, c) for w, c in top_words if w not in stop_words]
            if filtered:
                info["keywords"] = ", ".join([w for w, _ in filtered[:5]])

        return info

    def extract_conclusion(self, pdf_path: str) -> str:
        """
        从PDF中提取研究结论段落

        Returns:
            结论文本（100字以内精炼版）
        """
        success, text, _ = self.extract_text(pdf_path)
        if not success or not text:
            return ""

        conclusion = self._find_conclusion_section(text)
        if conclusion:
            return self._summarize_conclusion(conclusion)

        return ""

    def _find_conclusion_section(self, text: str) -> str:
        """定位结论/结语/讨论段落"""
        # 结论标题关键词（从高到低优先级）
        markers = [
            "结论",
            "结语",
            "研究结论",
            "七、结论",
            "八、结论",
            "九、结论",
            "十、结论",
            "六、结论",
            "五、结论",
            "Policy Implications",
            "Conclusions",
            "CONCLUSION",
            "Discussion",
        ]

        # 尝试按标题定位
        for marker in markers:
            # 方法1：按行首标题
            prefix_chars = r"0-9一二三四五六七八九十、.）)"
            pattern = rf"(?:^|\n)\s*[{prefix_chars}]*\s*{re.escape(marker)}\s*[：:]*\s*\n"
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                start = match.end()
                # 截取到下一个标题或文末
                next_section = re.search(
                    r"\n\s*[一二三四五六七八九十\d]+[、.）)]",
                    text[start:]
                )
                end = start + next_section.start() if next_section else len(text)
                conclusion_text = text[start:end].strip()
                if len(conclusion_text) > 50:
                    return conclusion_text

        # 方法2：按"本文"开头段落（结论常用句式）— 向前扩展上下文
        this_paper_patterns = [
            r"本文[^。]{10,200}[。]",
            r"研究表明[^。]{10,200}[。]",
            r"研究发现[^。]{10,200}[。]",
            r"研究结果[^。]{10,200}[。]",
            r"实证结果[^。]{10,200}[。]",
        ]
        all_matches = []
        for p in this_paper_patterns:
            matches = re.findall(p, text)
            all_matches.extend(matches)

        if all_matches:
            # 按位置排序，取后半段（通常结论在末尾）
            # 去重
            unique_matches = list(dict.fromkeys(all_matches))
            # 取最后几段
            key_sentences = unique_matches[-5:]
            return "。".join(key_sentences) + "。"

        return ""

    def _summarize_conclusion(self, conclusion_text: str, max_len: int = 100) -> str:
        """
        将结论段落精炼到指定长度内

        策略：提取核心结论句（包含"表明""发现""证明""支持""显示"等关键词的句子）
        """
        # 先清理页眉页脚噪声
        conclusion_text = self._clean_conclusion_noise(conclusion_text)

        # 结论信号词
        signal_words = ["表明", "发现", "证明", "支持", "显示", "说明", "意味着",
                        "得出", "提出", "建议", "揭示了", "体现了", "强调了"]

        sentences = re.split(r"[。！？]", conclusion_text)
        key_sentences = []

        for sent in sentences:
            sent = sent.strip()
            # 跳过太短或含页眉特征的句子
            if len(sent) < 10:
                continue
            if re.search(r"\d{4}年第\d+期", sent):
                continue
            # 包含信号词的优先
            if any(w in sent for w in signal_words):
                key_sentences.append(sent)

        # 如果信号句不够，补充长句
        if len(key_sentences) < 2:
            for sent in sentences:
                sent = sent.strip()
                if len(sent) > 20 and sent not in key_sentences:
                    if not re.search(r"\d{4}年第\d+期", sent):
                        key_sentences.append(sent)
                if len(key_sentences) >= 3:
                    break

        summary = "。".join(key_sentences[:3])

        # 截断到max_len
        if len(summary) > max_len:
            summary = summary[:max_len - 1] + "…"

        return summary

    def _clean_conclusion_noise(self, text: str) -> str:
        """清理结论文本中的页眉页脚噪声"""
        # 移除期刊页眉行
        text = re.sub(r"[\u4e00-\u9fff]+\s*[*·]\s*\d{4}年第\d+期\s*[*·\n]", "", text)
        text = re.sub(r"^\s*[\u4e00-\u9fff（)]+\s*\d{4}\s*[年第期\.]*\s*\d*\s*[期卷]*\s*[·*]*", "", text, flags=re.MULTILINE)
        # 移除 "页码 · 重复标题" 格式的页眉
        text = re.sub(r"^\d+\s*[·*]\s*.*$", "", text, flags=re.MULTILINE)
        # 移除 DOI、收稿日期等
        text = re.sub(r"DOI[:\s]*10\.\S+", "", text)
        text = re.sub(r"收稿日期[:\s]*\d{4}[-/]\d{1,2}[-/]\d{1,2}", "", text)
        # 移除 "本文" 换行等断裂句
        text = re.sub(r"本文\n", "本文", text)
        text = re.sub(r"\n\s*-\s*\n", "", text)
        # 移除 "以企业 年" 这类断裂文本（年份被误删）
        text = re.sub(r"企业\s*年\s*获授权", "企业获授权", text)
        return text.strip()

    def extract_from_dir(self, pdf_dir: str) -> List[Dict]:
        """批量提取目录下所有PDF"""
        pdf_dir = Path(pdf_dir)
        results = []

        for pdf_file in sorted(pdf_dir.glob("*.pdf")):
            success, text, meta = self.extract_text(str(pdf_file))
            conclusion = self.extract_conclusion(str(pdf_file)) if success else ""

            results.append({
                "filename": pdf_file.name,
                "success": success,
                "text_length": len(text) if success else 0,
                "conclusion": conclusion,
                "metadata": meta,
            })

            if success:
                logger.info(f"提取成功: {pdf_file.name} ({len(text)} 字)")
            else:
                logger.warning(f"提取失败: {pdf_file.name}")

        return results
