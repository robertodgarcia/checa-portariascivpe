import os
import json
import requests
import re
from pathlib import Path
import PyPDF2

# --------------------------
# Configuração via Secrets
# --------------------------

ANO = int(os.getenv("ANO"))

PALAVRAS_CHAVE = [
    p.strip().upper()
    for p in os.getenv("PALAVRAS_CHAVE", "").split(",")
    if p.strip()
]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --------------------------

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "estado_bis.json"

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# --------------------------

def carregar_estado():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())

    return {
        "ULTIMO_BIS": 0,
        "ULTIMO_BIS_ESPECIAL": 0
    }


def salvar_estado(estado):
    STATE_FILE.write_text(json.dumps(estado, indent=2))


# --------------------------

def enviar_telegram(msg):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    })


def enviar_documento(path):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"

    with open(path, "rb") as f:

        requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID},
            files={"document": f}
        )

# --------------------------

def url_bis(numero):

    return f"https://www2.pc.pe.gov.br/arquivos/BisServ{ANO}/bisServ{numero:03d}_{ANO}.pdf"


def url_bis_especial(numero):

    return f"https://www2.pc.pe.gov.br/arquivos/BisServEspecial{ANO}/bisE{ANO}.{numero:02d}.pdf"

# --------------------------

def existe(url):

    try:
        r = requests.head(url, timeout=20)

        return r.status_code == 200

    except:
        return False

# --------------------------

def baixar(url, destino):

    r = requests.get(url)

    if r.status_code == 200:

        destino.write_bytes(r.content)

        return True

    return False

# --------------------------

def extrair_texto(pdf):

    texto = ""

    reader = PyPDF2.PdfReader(open(pdf, "rb"))

    for p in reader.pages:

        texto += p.extract_text() or ""

    return texto.upper()

# --------------------------

def procurar_palavras(texto):

    achadas = []

    for p in PALAVRAS_CHAVE:

        if p in texto:

            achadas.append(p)

    return achadas

# --------------------------

def processar_bis(estado):

    numero = estado["ULTIMO_BIS"] + 1

    while True:

        url = url_bis(numero)

        if not existe(url):

            break

        nome = f"bisServ{numero:03d}_{ANO}.pdf"

        path = DOWNLOAD_DIR / nome

        print("Baixando", nome)

        baixar(url, path)

        texto = extrair_texto(path)

        palavras = procurar_palavras(texto)

        if palavras:

            enviar_telegram(
                f"ALERTA BIS {nome}\nPalavras: {', '.join(palavras)}"
            )

            enviar_documento(path)

        estado["ULTIMO_BIS"] = numero

        numero += 1


# --------------------------

def processar_bis_especial(estado):

    numero = estado["ULTIMO_BIS_ESPECIAL"] + 1

    while True:

        url = url_bis_especial(numero)

        if not existe(url):

            break

        nome = f"bisE{ANO}.{numero:02d}.pdf"

        path = DOWNLOAD_DIR / nome

        print("Baixando", nome)

        baixar(url, path)

        texto = extrair_texto(path)

        palavras = procurar_palavras(texto)

        if palavras:

            enviar_telegram(
                f"ALERTA BIS ESPECIAL {nome}\nPalavras: {', '.join(palavras)}"
            )

            enviar_documento(path)

        estado["ULTIMO_BIS_ESPECIAL"] = numero

        numero += 1

# --------------------------

def main():

    estado = carregar_estado()

    processar_bis(estado)

    processar_bis_especial(estado)

    salvar_estado(estado)


if __name__ == "__main__":
    main()
