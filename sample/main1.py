# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.
import sys
import io
#sys.stdout = io.TextIOWrapper(sys.stdout.buffer,encoding='gb18030')

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
# 提供初始密码
password = ''


char = '中国小百科全书'
test1=char.encode('utf-8')
test2=char.encode('gbk')

print("test1:%s"%test1)
print("test2:%s"%test2)

print(test2.decode('gbk').encode('utf-8').decode('utf-8'));

print(char.encode('utf-8'))
print(char.encode('gbk'))

#document.initialize()


fp = open('1.pdf','rb')


parser = PDFParser(fp)


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
    print("page: %s"%page);
    print("attr:%s"%page.attrs);
    print("type:%s" %type(page));
    interpreter.process_page(page)
    layout = device.get_result()
    print("layout:%s"%layout)
    for x in layout:
        # 获取文本对象
        print("x:%s"%x);
        if isinstance(x, LTTextBox):
        	text=x.get_text();
        	if(text.strip()):
                    #print("hex:%s"%text.hex())
                    #binascii.unhexlify(text);
                    #base64.b16decode(text);
                    #int_value = int(text,16);
                    #print(hex(int_value))
                    #print(hex(int_value))
                    for i in text:
                        print(i);
                        print(i.encode());
                        #print(binascii.hexlify(i))
                    #print("len:%s"%text.encode('gbk'))
                    with open(r's.txt','a') as f:
                        f.write(text+'\n')

                    print("text1:%s"%text.encode('gbk'));
                    #print("text:%s:"%text.decode('gbk').encode('utf-8').decode('utf-8'));
                    print("text:%s"%text.strip().encode('utf8').hex())
        	for c in x._objs:
        		print("x._objs:%s"%c)
        		if isinstance(x,pdfminer.layout.LTChar):
        			print("fontname %s\r\n"%c.fontname)
        		#print(x.font)
            	#print('text:',x.get_text().strip().encode('gb2312').decode('gbk','ignore').encode('utf-8'))
        # 获取图片对象
        if isinstance(x,LTImage):
            print('这里获取到一张图片')
        # 获取 figure 对象
        if isinstance(x,LTFigure):
            print('这里获取到一个 figure 对象')