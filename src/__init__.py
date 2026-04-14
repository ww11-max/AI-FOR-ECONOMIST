from .crawler import CNKICrawler
from .driver_manager import BrowserManager, simulate_human_behavior, wait_random_time
from .text_extractor import PDFTextExtractor
from .summary_generator import SummaryGenerator
from .fallback_downloader import FallbackDownloader
from .workflow import EcoAcquireWorkflow

__version__ = "2.2.0"
