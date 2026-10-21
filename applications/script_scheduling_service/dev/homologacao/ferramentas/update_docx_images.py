import os
import shutil
import zipfile
import struct

DOCX_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'docs', 'homologacao', 'SSS_Manual_Homologacao_UI_Freeze.docx'))
BACKUP_PATH = DOCX_PATH + '.bak'
SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'telas')

def atualizar_docx():
    print('Iniciando atualizacao das figuras no DOCX...')
    
    # Criar backup se nao existir
    if not os.path.exists(BACKUP_PATH):
        shutil.copyfile(DOCX_PATH, BACKUP_PATH)
        print('Backup criado em %s' % BACKUP_PATH)

    temp_docx = DOCX_PATH + '.tmp'
    
    total_substituidas = 0
    total_mantidas = 0

    with zipfile.ZipFile(DOCX_PATH, 'r') as zin, zipfile.ZipFile(temp_docx, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            filename = item.filename
            if filename.startswith('word/media/image') and filename.endswith('.png'):
                # Extrair numero da imagem
                base_name = os.path.basename(filename) # ex: image1.png
                novo_caminho = os.path.join(SCREENSHOTS_DIR, base_name)
                if os.path.exists(novo_caminho):
                    with open(novo_caminho, 'rb') as f:
                        new_data = f.read()
                    zout.writestr(item, new_data)
                    w, h = struct.unpack('>II', new_data[16:24])
                    total_substituidas += 1
                    print('[ATUALIZADA] %s (%dx%d, %d bytes)' % (base_name, w, h, len(new_data)))
                else:
                    data = zin.read(filename)
                    zout.writestr(item, data)
                    total_mantidas += 1
                    print('[MANTIDA] %s' % base_name)
            else:
                data = zin.read(filename)
                zout.writestr(item, data)

    # Substituir arquivo original
    os.replace(temp_docx, DOCX_PATH)
    print('\nConcluido! %d imagens atualizadas, %d mantidas.' % (total_substituidas, total_mantidas))
    print('Tamanho final do DOCX: %d bytes' % os.path.getsize(DOCX_PATH))

if __name__ == '__main__':
    atualizar_docx()
