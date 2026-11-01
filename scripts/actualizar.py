#!/usr/bin/env python3
"""Todo el proceso: descarga, procesado, calibración, resumen y validación."""
import calibrar
import descargar
import procesar
import resumen
import validar

if __name__ == "__main__":
    descargar.main()
    procesar.main()
    calibrar.main()
    resumen.main()
    validar.main()
