#!/usr/local/opt/python@3.9/bin/python3.9


from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.layout import *
from pdfminer.converter import PDFPageAggregator
from pdfminer.high_level import *

fp = open('1.pdf','rb')
parser = PDFParser(fp)
#parser.read_xref();
#xref = parser.find_xref()
#print("xref: %s\r\n"%xref);


# 提供初始密码
password = ''

#创建pdf文档对象，存储文档结构
document = PDFDocument(parser, password)

print("xref: %s\r\n"%document.xrefs);
print("info: %s\r\n"%document.info);
print("decipher: %s\r\n"%document.decipher);
print("catalog: %s\r\n"%document.catalog);
print("caching: %s\r\n"%document.caching);
#创建一个pdf资源管理对象，存储共享资源
rsrcmgr = PDFResourceManager()

print("rsrcmgr.get_font: %s\r\n"%rsrcmgr);


laparams = LAParams()

#创建一个device对象
device = PDFPageAggregator(rsrcmgr, laparams=laparams)

print("device: %s\r\n"%device.get_result());

#创建一个解释对象
interpreter = PDFPageInterpreter(rsrcmgr, device)

#处理包含在文档中的每一页
for page in PDFPage.create_pages(document):
    print("page: %s"%page);
    print("attr:%s"%page.attrs);
    print("type:%s" %type(page));
    interpreter.process_page(page)
    layout = device.get_result()
    print("layout:%s"%layout)
    for x in layout:
        # 获取文本对象
        print("x:%s"%x);
        print("x:%s" % type(x));
        if isinstance(x, LTTextBox):
            for line in x:
                if isinstance(line , LTText):
                    print('line:%s' % line)
                    txt=line.get_text()
                    a = bytes(txt, 'raw_unicode_escape')
                    print("bytes:%s" % a);
                    b = a.decode("gbk")
                    print("gbk:%s" % b);
                for char in line:
                    if isinstance(char ,LTChar):
                        print("fontname:%s,size:%s\r\n" % (char.fontname.decode('gbk') , char.size));
                        break;
