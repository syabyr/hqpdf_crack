from io import StringIO
from pdfminer.high_level import *

output_string = StringIO()
with open('0.pdf', 'rb') as fin:
	extract_text_to_fp(fin, output_string,codec='gb2312')
	print(output_string.getvalue().strip())
	extract_text_to_fp(fin, output_string, laparams=LAParams(),output_type=None, codec='utf-8')