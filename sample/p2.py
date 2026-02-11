from pdfminer.high_level import extract_text, extract_pages
from pdfminer.layout import LAParams, LTTextContainer
from pdfminer.layout import *

import logging

#create a logger
logger = logging.getLogger('pdfminer.pdfinterp')
#set logger level
logger.setLevel(logging.DEBUG)
#or you can set the following level
#logger.setLevel(logging.DEBUG)

handler = logging.FileHandler('mylog.log')
# create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

#laparams = LAParams()
laparams = {}
s = extract_text('./0.pdf',codec='gbk', laparams=LAParams(**laparams))
print('s:%s'%s)