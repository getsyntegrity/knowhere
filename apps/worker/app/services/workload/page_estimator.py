"""
Page Estimator Service

Calculates page counts for billing based on:
- PDF: Physical page count from metadata
- PPTX: Slide count
- Text-based (DOCX, TXT, MD, JSON, XLSX): Word-based estimation using count_cn_en

Supported file types:
- .pdf, .docx, .pptx, .xlsx
- .txt, .md, .json, .fragment
- .png, .jpg, .jpeg
"""
import math
import re
from pathlib import Path

from shared.core.logging import logger


# Constants for page estimation
WORDS_PER_PAGE = 500  # Chinese chars + English words + numbers per page
ROWS_PER_PAGE = 50    # For Excel files


def count_cn_en(text: str) -> int:
    """统计中英文单词和数字的数量 (Count Chinese chars, English words, and numbers)"""
    if not text:
        return 0
    text = str(text)
    
    # Chinese characters
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    cn_counts = len(chinese_chars)
    
    # English words
    english_words = re.findall(r'[A-Za-z]+', text)
    en_counts = len(english_words)
    
    # Numbers (including decimals)
    numbers = re.findall(r'\d+(?:\.\d+)?', text)
    number_count = len(numbers)
    
    return cn_counts + en_counts + number_count


class PageEstimator:
    """
    Estimates page count for billing purposes.
    
    Billing Logic:
    - PDF: Physical page count from metadata
    - PPTX: Slide count
    - DOCX/TXT/MD/JSON: Word-based estimation (count_cn_en / 500)
    - XLSX: Row-based estimation (rows / 50)
    - Images: 1 page per image
    """
    
    @classmethod
    def estimate(cls, file_path: str) -> int:
        """
        Estimate page count for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Estimated page count (minimum 1)
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        try:
            if suffix == '.pdf':
                return cls._estimate_pdf(file_path)
            elif suffix == '.pptx':
                return cls._estimate_pptx(file_path)
            elif suffix == '.docx':
                return cls._estimate_docx(file_path)
            elif suffix == '.xlsx':
                return cls._estimate_xlsx(file_path)
            elif suffix in ['.txt', '.md', '.json', '.fragment']:
                return cls._estimate_text(file_path)
            elif suffix in ['.png', '.jpg', '.jpeg']:
                return 1  # Image = 1 page
            else:
                logger.warning(f"Unknown file type for billing: {suffix}, defaulting to 1 page")
                return 1
        except Exception as e:
            logger.error(f"Error estimating pages for {file_path}: {e}")
            return 1  # Fallback to minimum charge
    
    @classmethod
    def _estimate_pdf(cls, file_path: str) -> int:
        """
        Estimate pages for PDF using physical page count from metadata.
        """
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            return max(1, len(reader.pages))
        except ImportError:
            logger.warning("pypdf not installed, defaulting to 1 page")
            return 1
        except Exception as e:
            logger.error(f"PDF estimation error: {e}")
            return 1
    
    @classmethod
    def _estimate_pptx(cls, file_path: str) -> int:
        """
        Estimate pages for PPTX using slide count.
        """
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            return max(1, len(prs.slides))
        except ImportError:
            logger.warning("python-pptx not installed, defaulting to 1 page")
            return 1
        except Exception as e:
            logger.error(f"PPTX estimation error: {e}")
            return 1
    
    @classmethod
    def _estimate_docx(cls, file_path: str) -> int:
        """
        Estimate pages for DOCX using word-based counting.
        """
        try:
            from docx import Document
            
            doc = Document(file_path)
            total_text = ""
            
            # Collect text from paragraphs
            for para in doc.paragraphs:
                total_text += para.text + " "
            
            # Collect text from tables
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        total_text += cell.text + " "
            
            word_count = count_cn_en(total_text)
            return max(1, math.ceil(word_count / WORDS_PER_PAGE))
            
        except ImportError:
            logger.warning("python-docx not installed")
            return 1
        except Exception as e:
            logger.error(f"DOCX estimation error: {e}")
            return 1
    
    @classmethod
    def _estimate_xlsx(cls, file_path: str) -> int:
        """
        Estimate pages for XLSX using row count.
        """
        try:
            import pandas as pd
            
            xlsx = pd.ExcelFile(file_path)
            total_rows = 0
            
            for sheet_name in xlsx.sheet_names:
                df = pd.read_excel(xlsx, sheet_name=sheet_name)
                total_rows += len(df)
            
            return max(1, math.ceil(total_rows / ROWS_PER_PAGE))
            
        except ImportError:
            logger.warning("pandas not installed")
            return 1
        except Exception as e:
            logger.error(f"XLSX estimation error: {e}")
            return 1
    
    @classmethod
    def _estimate_text(cls, file_path: str) -> int:
        """
        Estimate pages for text files using word-based counting.
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            word_count = count_cn_en(content)
            return max(1, math.ceil(word_count / WORDS_PER_PAGE))
            
        except Exception as e:
            logger.error(f"Text estimation error: {e}")
            return 1
