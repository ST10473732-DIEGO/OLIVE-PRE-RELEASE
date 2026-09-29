"""Synthetic public-topic PDF for local Chat research acceptance."""
from pathlib import Path
import sys
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def create(destination):
    writer = PdfWriter()
    for text in (
        'Synthetic cybersecurity report. Main finding: a phased rollout reduced pilot incidents from 12 to 4.',
        'Recommendation: adopt cybersecurity controls in phases. Evidence: the pilot covered 30 systems over 90 days.',
        'Implementation cost: 42 synthetic budget units. Limitations: one pilot does not establish industry-wide results.',
    ):
        page = writer.add_blank_page(width=800, height=400)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(('BT /F1 11 Tf 20 300 Td (' + text + ') Tj ET').encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(str(destination))


if __name__ == '__main__':
    create(Path(sys.argv[1]))
