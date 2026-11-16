#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
高级PDF编码转换工具
支持GB2312 → UTF-8的PDF转换
特性：
- 自动检测文本编码
- 支持多页PDF
- 使用中文字体保持格式
- 可配置的页面布局
"""

from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar, LTFigure
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
import os
import sys
from pathlib import Path

class PDFEncodingConverter:
    """PDF编码转换器"""
    
    def __init__(self, source_encoding='gb2312', target_encoding='utf-8'):
        self.source_encoding = source_encoding
        self.target_encoding = target_encoding
        self.font_path = self._find_font()
        self.font_name = None
        if self.font_path:
            self._register_font()
    
    def _find_font(self):
        """查找系统中的中文字体"""
        possible_paths = [
            'fonts/simsun.ttc',  # 项目本地字体
            '/System/Library/Fonts/SimHei.ttf',  # macOS
            '/System/Library/Fonts/Songti.ttc',  # macOS
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Linux
            'C:\\Windows\\Fonts\\simhei.ttf',  # Windows
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"✓ 找到字体: {path}")
                return path
        
        print("✗ 未找到中文字体，将使用默认字体")
        return None
    
    def _register_font(self):
        """注册字体"""
        try:
            self.font_name = os.path.basename(self.font_path).split('.')[0]
            pdfmetrics.registerFont(TTFont(self.font_name, self.font_path))
            print(f"✓ 字体已注册: {self.font_name}")
        except Exception as e:
            print(f"✗ 字体注册失败: {e}")
            self.font_path = None
            self.font_name = None
    
    def extract_text_from_pdf(self, pdf_path):
        """从PDF提取文本并处理编码"""
        texts = []
        
        try:
            with open(pdf_path, 'rb') as fp:
                parser = PDFParser(fp)
                document = PDFDocument(parser)
                
                if not document.is_extractable:
                    print("✗ PDF文件不允许文本提取")
                    return texts
                
                rsrcmgr = PDFResourceManager()
                laparams = LAParams()
                device = PDFPageAggregator(rsrcmgr, laparams=laparams)
                interpreter = PDFPageInterpreter(rsrcmgr, device)
                
                page_count = 0
                for page_num, page in enumerate(PDFPage.create_pages(document)):
                    page_count += 1
                    interpreter.process_page(page)
                    layout = device.get_result()
                    
                    page_text = []
                    for element in layout:
                        if isinstance(element, LTTextBox):
                            text = element.get_text()
                            # 处理编码
                            text = self._convert_encoding(text)
                            page_text.append(text)
                    
                    texts.append('\n'.join(page_text))
                
                print(f"✓ 成功提取 {page_count} 页文本")
        
        except Exception as e:
            print(f"✗ 提取文本时出错: {e}")
            import traceback
            traceback.print_exc()
        
        return texts
    
    def _convert_encoding(self, text):
        """转换文本编码"""
        try:
            if isinstance(text, bytes):
                # 如果是字节，直接用源编码解码
                return text.decode(self.source_encoding)
            else:
                # 如果已是字符串，尝试通过latin-1中间转换
                try:
                    return text.encode('latin-1').decode(self.source_encoding)
                except:
                    # 如果转换失败，直接返回
                    return text
        except Exception as e:
            print(f"  编码转换警告: {e}")
            return text
    
    def create_utf8_pdf(self, texts, output_path, page_format='A4', 
                       font_size=11, line_spacing=1.2):
        """使用UTF-8编码创建PDF"""
        
        # 设置页面大小
        if page_format.upper() == 'LETTER':
            page_width, page_height = letter
        else:  # 默认 A4
            page_width, page_height = A4
        
        c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
        
        # 设置字体
        current_font = self.font_name if self.font_name else 'Helvetica'
        c.setFont(current_font, font_size)
        
        y_position = page_height - 20  # 从顶部开始
        line_height = font_size * line_spacing
        margin_x = 15
        margin_y = 15
        max_width = page_width - 2 * margin_x
        
        max_chars_per_line = int(max_width / (font_size * 0.5))  # 估算每行字符数
        
        total_lines = 0
        for page_num, text in enumerate(texts, 1):
            print(f"  处理第 {page_num} 页...")
            
            for paragraph in text.split('\n'):
                if not paragraph.strip():
                    # 空行
                    y_position -= line_height
                    total_lines += 1
                    if y_position < margin_y:
                        c.showPage()
                        c.setFont(current_font, font_size)
                        y_position = page_height - margin_y
                    continue
                
                # 处理长行
                for i in range(0, len(paragraph), max_chars_per_line):
                    line = paragraph[i:i+max_chars_per_line]
                    
                    if y_position < margin_y:
                        c.showPage()
                        c.setFont(current_font, font_size)
                        y_position = page_height - margin_y
                    
                    c.drawString(margin_x, y_position, line)
                    y_position -= line_height
                    total_lines += 1
        
        c.save()
        print(f"✓ PDF已保存: {output_path}")
        print(f"  总行数: {total_lines}")
    
    def convert(self, input_pdf, output_pdf):
        """执行完整的转换过程"""
        print(f"\n{'='*50}")
        print(f"PDF 编码转换工具")
        print(f"{'='*50}")
        print(f"输入文件: {input_pdf}")
        print(f"输出文件: {output_pdf}")
        print(f"编码转换: {self.source_encoding} → {self.target_encoding}")
        print(f"{'='*50}\n")
        
        # 检查输入文件
        if not os.path.exists(input_pdf):
            print(f"✗ 输入文件不存在: {input_pdf}")
            return False
        
        # 提取文本
        print("第一步: 提取PDF文本...")
        texts = self.extract_text_from_pdf(input_pdf)
        
        if not texts:
            print("✗ 未能提取任何文本")
            return False
        
        # 创建PDF
        print("\n第二步: 创建UTF-8编码的PDF...")
        self.create_utf8_pdf(texts, output_pdf)
        
        print(f"\n{'='*50}")
        print("✓ 转换完成！")
        print(f"{'='*50}\n")
        
        return True


def main():
    """主程序"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='将GB2312编码的PDF转换为UTF-8编码的PDF'
    )
    parser.add_argument('-i', '--input', default='0.pdf', help='输入PDF文件 (默认: 0.pdf)')
    parser.add_argument('-o', '--output', default='00.pdf', help='输出PDF文件 (默认: 00.pdf)')
    parser.add_argument('-s', '--source-encoding', default='gb2312', help='源编码 (默认: gb2312)')
    parser.add_argument('-t', '--target-encoding', default='utf-8', help='目标编码 (默认: utf-8)')
    parser.add_argument('-f', '--font-size', type=int, default=11, help='字体大小 (默认: 11)')
    parser.add_argument('--page-format', default='A4', choices=['A4', 'LETTER'], 
                       help='页面格式 (默认: A4)')
    
    args = parser.parse_args()
    
    # 创建转换器
    converter = PDFEncodingConverter(args.source_encoding, args.target_encoding)
    
    # 执行转换
    success = converter.convert(args.input, args.output)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
