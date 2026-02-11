from pypdf import PdfWriter,PdfReader
import pypdf

import logging

logger = logging.getLogger("PyPDF2");

logger.setLevel(logging.DEBUG);

from pypdf._page import PageObject

pdf = PdfReader(open("0.pdf", "rb"))

print('pages:',len(pdf.pages));

print('metadata:',pdf.metadata);

# pypdf._page.PageObject
page = pdf.pages[0];

print('page:');

for i in page:
	print(i)
	print(type(i))

# 'pypdf.generic._data_structures.ContentStream'
contents = page.get_contents();
data = contents.get_data();
print(data);
print('contents:'); # contents内容为空?
for i in contents:
	print(i)
	print(type(i))

#print(contents.operations)

#for operands, operator in contents.operations:
	#if operator == b"Tj":
		#print(type(operands))
		#print(operands)
		#print(type(operands[0]))
		#if(type(operands[0]) == pypdf.generic._base.TextStringObject):
			#newstr = operands[0].get_original_bytes().decode('gbk')
			
		#if(type(operands[0]) == pypdf.generic._base.ByteStringObject):
			#print("debug")
			#print(operands[0].original_bytes.decode('gbk'))

print('data:'); # data里是二进制的opcode?
data = contents.get_data();
print(data);



# 尝试构造写入部分
pdf_writer = PdfWriter();

# 生成空页 # pypdf._page.PageObject
write_page = PageObject.create_blank_page(width=462.5, height=625.9)

# 无法直接操作:ValueError: key must be PdfObject
# write_page['/Contents'] = page['/Contents'];

# write_page.read_from_stream(contents,None)

pdf_writer.add_page(page);
output_stream = open("destination.pdf", "wb")
pdf_writer.write(output_stream)
output_stream.close()

#contents.clear();

#contents.set_data(data);

#page.clear();