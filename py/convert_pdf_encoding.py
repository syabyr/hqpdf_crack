#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
将GB2312编码的PDF转换为UTF-8编码的PDF
从0.pdf读取内容，转换编码，生成00.pdf
"""

from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

def extract_text_from_pdf_with_encoding(pdf_path, source_encoding='gb2312'):
    """
    从PDF中提取文本，处理编码问题
    """
    texts = []
    
    try:
        fp = open(pdf_path, 'rb')
        parser = PDFParser(fp)
        document = PDFDocument(parser)
        
        if not document.is_extractable:
            raise PDFTextExtractionNotAllowed
        
        rsrcmgr = PDFResourceManager()
        laparams = LAParams()
        device = PDFPageAggregator(rsrcmgr, laparams=laparams)
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        
        for page_num, page in enumerate(PDFPage.create_pages(document)):
            interpreter.process_page(page)
            layout = device.get_result()
            
            page_text = []
            for element in layout:
                if isinstance(element, LTTextBox):
                    text = element.get_text()
                    # 尝试处理编码问题
                    try:
                        # 尝试用GB2312解码
                        if isinstance(text, bytes):
                            text = text.decode(source_encoding)
                        else:
                            # 如果已经是字符串，尝试编码再解码
                            try:
                                text = text.encode('latin-1').decode(source_encoding)
                            except:
                                pass
                    except:
                        pass
                    
                    page_text.append(text)
            
            texts.append('\n'.join(page_text))
        
        fp.close()
        
    except Exception as e:
        print(f"提取PDF文本时出错: {e}")
        import traceback
        traceback.print_exc()
    
    return texts


def create_pdf_with_utf8(output_path, texts, page_width=595, page_height=842):
    """
    使用reportlab创建UTF-8编码的PDF
    """
    
    # 查找系统中是否有中文字体
    font_path = None
    possible_font_paths = [
        '/System/Library/Fonts/SimHei.ttf',  # macOS
        '/System/Library/Fonts/Songti.ttc',  # macOS
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',  # Linux
        'C:\\Windows\\Fonts\\simhei.ttf',  # Windows
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/Arial.ttf',  # macOS fallback
    ]
    
    # 检查项目中是否有字体文件
    local_font_path = 'fonts/simsun.ttc'
    if os.path.exists(local_font_path):
        font_path = local_font_path
        print(f"使用本地字体: {font_path}")
    else:
        for path in possible_font_paths:
            if os.path.exists(path):
                font_path = path
                print(f"使用系统字体: {font_path}")
                break
    
    # 创建PDF
    c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
    
    if font_path:
        try:
            # 注册字体
            font_name = os.path.basename(font_path).split('.')[0]
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            current_font = font_name
            current_size = 12
        except Exception as e:
            print(f"注册字体失败: {e}，使用默认字体")
            current_font = 'Helvetica'
            current_size = 12
    else:
        current_font = 'Helvetica'
        current_size = 12
        print("未找到中文字体，使用默认字体")
    
    # 设置字体
    c.setFont(current_font, current_size)
    
    y_position = page_height - 40  # 从顶部开始
    line_height = current_size + 4
    margin = 40
    max_width = page_width - 2 * margin
    
    for text in texts:
        for line in text.split('\n'):
            if y_position < margin:
                # 新建一页
                c.showPage()
                c.setFont(current_font, current_size)
                y_position = page_height - 40
            
            # 处理很长的行（简单的换行处理）
            if len(line) > 60:
                # 简单的分段处理
                for i in range(0, len(line), 60):
                    sub_line = line[i:i+60]
                    c.drawString(margin, y_position, sub_line)
                    y_position -= line_height
            else:
                c.drawString(margin, y_position, line)
                y_position -= line_height
    
    c.save()
    print(f"PDF已保存到: {output_path}")


def convert_pdf_encoding(input_pdf='0.pdf', output_pdf='00.pdf', 
                        source_encoding='gb2312', target_encoding='utf-8'):
    """
    主转换函数
    """
    print(f"开始转换PDF编码...")
    print(f"输入文件: {input_pdf}")
    print(f"输出文件: {output_pdf}")
    print(f"源编码: {source_encoding}")
    print(f"目标编码: {target_encoding}")
    
    # 提取文本
    print("\n第一步: 提取PDF文本...")
    texts = extract_text_from_pdf_with_encoding(input_pdf, source_encoding)
    
    if not texts:
        print("未能提取任何文本！")
        return False
    
    print(f"成功提取 {len(texts)} 页文本")
    
    # 确保文本是UTF-8编码
    print("\n第二步: 转换文本编码...")
    converted_texts = []
    for text in texts:
        if isinstance(text, bytes):
            try:
                text = text.decode(target_encoding)
            except:
                try:
                    text = text.decode(source_encoding).encode(target_encoding).decode(target_encoding)
                except:
                    pass
        converted_texts.append(text)
    
    # 创建新的PDF
    print("\n第三步: 创建新的PDF文件...")
    create_pdf_with_utf8(output_pdf, converted_texts)
    
    print("\n转换完成！")
    return True


if __name__ == '__main__':
    convert_pdf_encoding()
