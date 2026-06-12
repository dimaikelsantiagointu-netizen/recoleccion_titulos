import subprocess
import os
import platform
import shutil

def optimizar_pdf(input_path, output_path):
    """
    Comprime el PDF utilizando Ghostscript. 
    Detecta automáticamente si corre en Linux (gs) o Windows (gswin64c).
    """
    comando_gs = 'gs' # Por defecto para Debian/Linux

    if platform.system() == 'Windows':
        # En Windows buscamos los ejecutables específicos
        if shutil.which('gswin64c'):
            comando_gs = 'gswin64c'
        elif shutil.which('gswin32c'):
            comando_gs = 'gswin32c'
        else:
            print("Aviso: Ghostscript no encontrado en Windows. Se guardará el PDF original sin optimizar.")
            return False

    try:
        comando = [
            comando_gs,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            input_path
        ]
        subprocess.run(comando, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error interno al optimizar el PDF: {e}")
        return False