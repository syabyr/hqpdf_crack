from PyPDF2 import PdfWriter, PdfReader
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

packet = io.BytesIO()
can = canvas.Canvas(packet, pagesize=letter)
can.setFont("Times-Roman",100)
can.drawString(10, 100, "  ")
can.save()

#move to the beginning of the StringIO buffer
packet.seek(0)

# create a new PDF with Reportlab
new_pdf = PdfReader(packet)
# read your existing PDF
existing_pdf = PdfReader(open("0.pdf", "rb"))
output = PdfWriter()
# add the "watermark" (which is the new pdf) on the existing page
page = existing_pdf.pages[0]
content = page.extract_text().encode('latin-1').decode('gbk');
#page.mergeTextFields(content);
#print(content);

contents = page.get_contents();
data = contents.get_data();

# modify data

contents.set_data(data);

page.


#print(charset.detect(data)['encoding']);
decoded_data = data.decode('gbk');

print(decoded_data);


#contents = contents.decode('gbk');
#print(contents);
page.get_contents().set_data(contents);


page.merge_page(new_pdf.pages[0])
output.add_page(page)
# finally, write "output" to a real file
output_stream = open("destination.pdf", "wb")
output.write(output_stream)
output_stream.close()