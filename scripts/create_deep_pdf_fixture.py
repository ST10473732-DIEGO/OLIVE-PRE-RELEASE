"""Synthetic mixed native/scanned PDF; no runtime or model substitution."""
from pathlib import Path
import sys
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def create(destination):
    writer=PdfWriter()
    page=writer.add_blank_page(width=600,height=400)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject()
    stream.set_data(b'BT /F1 22 Tf 40 330 Td (Synthetic report. Native page: apples total 12.) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    image=Image.new('RGB',(1200,800),'white')
    draw=ImageDraw.Draw(image)
    try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',54)
    except OSError:font=ImageFont.load_default(size=54)
    draw.text((70,150),'SCANNED PAGE 2',font=font,fill='black')
    draw.text((70,290),'Pears total: 37',font=font,fill='black')
    output=BytesIO();image.save(output,format='PDF',resolution=144)
    writer.add_page(PdfReader(BytesIO(output.getvalue())).pages[0])
    writer.write(str(destination))


if __name__=='__main__':
    create(Path(sys.argv[1]))
