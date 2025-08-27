# meu_app/__main__.py
# Permite rodar: python -m meu_app <subcomando>
# Ele tenta usar uma função main()/cli() do main.py na raiz;
# se não houver, executa o main.py como script (__main__).

import os
import sys
import runpy
import importlib

def _run_root_script():
    root = os.path.dirname(os.path.dirname(__file__))  # pasta do projeto
    script = os.path.join(root, "main.py")
    if os.path.exists(script):
        # Executa como se fosse "python main.py ..."
        runpy.run_path(script, run_name="__main__")
    else:
        sys.stderr.write("Erro: main.py não encontrado na raiz do projeto.\n")
        raise SystemExit(1)

def main():
    try:
        # Tenta importar o módulo raiz "main"
        mod = importlib.import_module("main")
        # Se houver uma função pública, chama; senão, executa como script
        if hasattr(mod, "main") and callable(getattr(mod, "main")):
            mod.main()
        elif hasattr(mod, "cli") and callable(getattr(mod, "cli")):
            mod.cli()
        else:
            _run_root_script()
    except ModuleNotFoundError:
        _run_root_script()

if __name__ == "__main__":
    main()
