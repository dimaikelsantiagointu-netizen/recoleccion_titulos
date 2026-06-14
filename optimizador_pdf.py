import subprocess
import os
import platform
import shutil

def optimizar_pdf(input_path, output_path):
    """
    Comprime el PDF utilizando Ghostscript.
    Detecta automáticamente si corre en Linux (gs) o Windows (gswin64c).
    Retorna True si optimizó, False si no (pero deja mensaje).
    """
    comando_gs = 'gs'
    mensaje_advertencia = None

    if platform.system() == 'Windows':
        if shutil.which('gswin64c'):
            comando_gs = 'gswin64c'
        elif shutil.which('gswin32c'):
            comando_gs = 'gswin32c'
        else:
            mensaje_advertencia = "Ghostscript no encontrado en Windows. El PDF se guardará sin optimizar."
            print(mensaje_advertencia)
            return False, mensaje_advertencia

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
        subprocess.run(comando, check=True, capture_output=True)
        return True, None
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        mensaje_advertencia = f"Error al optimizar el PDF: {str(e)}"
        print(mensaje_advertencia)
        return False, mensaje_advertencia