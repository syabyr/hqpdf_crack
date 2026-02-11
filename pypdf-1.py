import pypdf

with open("0.pdf", "rb") as pdf_file:
    read_pdf = pypdf.PdfReader(pdf_file)
    number_of_pages = len(read_pdf.pages)
    page = read_pdf.pages[0]
    page_content = page.extract_text()
print(page_content)
print('typeofs:',type(page_content),'s:%s'%page_content)

b = bytes(page_content, 'raw_unicode_escape')
print(b)
#print(b.__len__())
#sss=b[0:556]
sss=b[0:]
c=sss.decode('gb18030')
print(c)
