#!/usr/bin/python
#-*- coding: utf-8 -*-

from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.layout import *
import re

import logging

#create a logger
logger = logging.getLogger('pdfminer.pdfinterp')
#set logger level
logger.setLevel(logging.DEBUG)

handler = logging.FileHandler('mylog.log')
# create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s {%(pathname)s:%(lineno)d} - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

#打开一个pdf文件
fp = open(u'0.pdf', 'rb')
#创建一个PDF文档解析器对象
parser = PDFParser(fp)
#创建一个PDF文档对象存储文档结构
#提供密码初始化，没有就不用传该参数
#document = PDFDocument(parser, password)
document = PDFDocument(parser)
#检查文件是否允许文本提取
if not document.is_extractable:
    raise PDFTextExtractionNotAllowed
#创建一个PDF资源管理器对象来存储共享资源
#caching = False不缓存
#rsrcmgr = PDFResourceManager(caching = False)
rsrcmgr = PDFResourceManager()
# 创建一个PDF设备对象
laparams = LAParams()
# 创建一个PDF页面聚合对象
device = PDFPageAggregator(rsrcmgr, laparams=laparams)
#创建一个PDF解析器对象
interpreter = PDFPageInterpreter(rsrcmgr, device)
#处理文档当中的每个页面

# doc.get_pages() 获取page列表
#for i, page in enumerate(document.get_pages()):
#PDFPage.create_pages(document) 获取page列表的另一种方式
replace=re.compile(r'\s+');
# 循环遍历列表，每次处理一个page的内容
for page in PDFPage.create_pages(document):
    interpreter.process_page(page)
    # 接受该页面的LTPage对象
    layout=device.get_result()
    # 这里layout是一个LTPage对象 里面存放着 这个page解析出的各种对象
    # 一般包括LTTextBox, LTFigure, LTImage, LTTextBoxHorizontal 等等
    for x in layout:
        #如果x是水平文本对象的话
        if(isinstance(x,LTTextBoxHorizontal)):
            a=x.get_text();
            print('1.type:',type(a))
            print('2:',a);
            #b = bytes(a, 'gb2312')
            #print(b)
            text=re.sub(replace,'',x.get_text())
            if len(text)!=0:
                print('3.len:',type(text))
                print('4:',text.count(text));
                #print(text.encode('utf8'))
                print('5:',text.__len__())
                tlen=text.__len__()
                for i in range(0,tlen):
                    a=text.__getitem__(i)
                    s1=bytes(a,'raw_unicode_escape')
                    #print('%d:%s'%(i,s1));
                print('6:',text.__getitem__(0))
                print('7:%r',x.get_text())
                #print(text)
                b = bytes(text, 'raw_unicode_escape')
                print('7:',b)
                c=b.decode('gb18030')
                print(c)
                d=b.decode("gb2312")
                print(d)
                #d=bytes.fromhex(text)
                #print(d)
        print('-----------------------')