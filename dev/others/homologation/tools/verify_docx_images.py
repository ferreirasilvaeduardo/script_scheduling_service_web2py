import os
import zipfile
import struct

DOCX_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'docs', 'homologacao', 'SSS_Homologation_Manual_UI_Freeze.docx'))

with zipfile.ZipFile(DOCX_PATH, 'r') as z:
    names = [f for f in z.namelist() if f.startswith('word/media/image') and f.endswith('.png')]
    print('Total de imagens no DOCX: %d' % len(names))
    for n in sorted(names, key=lambda x: int(x.replace('word/media/image', '').replace('.png', ''))):
        data = z.read(n)
        w, h = struct.unpack('>II', data[16:24])
        print('%s: %dx%d (%d bytes)' % (n, w, h, len(data)))
