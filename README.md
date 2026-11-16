# hqpdf_crack

conda create --name pdf -c conda-forge python=3.14

pdfminer.six已经取代pdfminer了

python3 -m pip install pymupdf pytesseract pillow reportlab pdfminer.six reportlab


py/1.py:
python3 py/1.py 0.pdf --decode-gb2312
python3 py/1.py 0.pdf --decode-gb2312 --make-pdf --font-path "/System/Library/Fonts/STHeiti Medium.ttc"
