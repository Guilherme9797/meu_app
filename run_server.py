# run_server.py
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from server import app

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))

    # suporte opcional a ngrok:  .\meu_app_server.exe --ngrok
    import sys
    use_ngrok = any(a.lower() == "--ngrok" for a in sys.argv)
    if use_ngrok:
        try:
            from pyngrok import ngrok  # pip install pyngrok
            token = os.getenv("NGROK_AUTHTOKEN")
            if token:
                ngrok.set_auth_token(token)
            url = ngrok.connect(addr=port, proto="http").public_url
            print(f"[ngrok] público: {url}")
        except Exception as e:
            print(f"[ngrok] indisponível: {e}")

    app.run(host=host, port=port)
