
import sys
import io
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice
from pdfminer.layout import *
from pdfminer.converter import PDFPageAggregator
import pdfminer
import binascii
import base64


fp = open('1.pdf','rb')
parser = PDFParser(fp)

# 提供初始密码
password = ''
#创建pdf文档对象，存储文档结构
document = PDFDocument(parser, password)

#创建一个pdf资源管理对象，存储共享资源
rsrcmgr = PDFResourceManager()

laparams = LAParams()

#创建一个device对象
device = PDFPageAggregator(rsrcmgr, laparams=laparams)

#创建一个解释对象
interpreter = PDFPageInterpreter(rsrcmgr, device)

#处理包含在文档中的每一页
for page in PDFPage.create_pages(document):
    interpreter.process_page(page)
    layout = device.get_result()
    for x in layout:
        # 获取文本对象
        print("x:%s"%x);
        if isinstance(x, LTTextBox):
            text=x.get_text();
            print("text:%s"%text);
            a=bytes(text,'raw_unicode_escape')
            print("bytes:%s"%a);
            b=a.decode("gbk")
            print("gbk:%s" % b);