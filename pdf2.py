import PyPDF2
import pypdf

with open('0.pdf', 'rb') as f:
    pdf_reader = PyPDF2.PdfReader(f, strict=False)
    page = pdf_reader.pages[0]
    content = page.extract_text().encode('latin-1').decode('gbk')
    #print(content)


with open('0.pdf', 'rb') as f:
    pdf_reader = PyPDF2.PdfReader(f, strict=False)
    page = pdf_reader.pages[0]
    page_text = page.extract_text()

    # 修改字体设置
    page_text = page_text.replace('/F1 12 Tf', '/F1 14 Tf')
    page_text = page_text.replace('/F2 12 Tf', '/F2 14 Tf')

    print(page_text)


with open('0.pdf', 'rb') as f:
    pdf_reader = pypdf.PdfReader(f, strict=False)
    pdf_writer = pypdf.PdfWriter()

    # 将第一页的内容替换为中文字符
    page = pdf_reader.pages[0]

    # page属性
    print(page.mediabox.width, page.mediabox.height)

    page_text = '这是中文内容'
    
    contents = page.get_contents();
    data = contents.get_data();

    #contents.set_data(data);
    #page.set_contents(contents);


    obj = page.get_object();
    for i in obj:
        print(i);
        print(type(i))


    pdf_writer.add_page(page)

    with open('output.pdf', 'wb') as f:
        pdf_writer.write(f)