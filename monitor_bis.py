import os
import json
import requests
from pathlib import Path
import PyPDF2

# --------------------------
# Configuração via Secrets
# --------------------------

ANO = int(os.getenv("ANO", "2026"))

PALAVRAS_CHAVE = [
    p.strip().upper()
    for p in os.getenv("PALAVRAS_CHAVE", "").split(",")
    if p.strip()
]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

REQUEST_TIMEOUT = 20

# --------------------------

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "estado_bis.json"

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# --------------------------

def carregar_estado():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))

    return {
        "ULTIMO_BIS": 0,
        "ULTIMO_BIS_ESPECIAL": 0
    }


def salvar_estado(estado):
    STATE_FILE.write_text(
        json.dumps(estado, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

# --------------------------

def enviar_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] TOKEN ou CHAT_ID não configurados.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            data={
                "chat_id": str(TELEGRAM_CHAT_ID),
                "text": msg
            },
            timeout=REQUEST_TIMEOUT
        )
        print(f"[Telegram] status={r.status_code}")
        print(f"[Telegram] resposta={r.text}")
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"[Telegram] erro ao enviar mensagem: {e}")
        return False


def enviar_documento(path):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] TOKEN ou CHAT_ID não configurados.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"

    try:
        with open(path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": str(TELEGRAM_CHAT_ID)},
                files={"document": (path.name, f)},
                timeout=REQUEST_TIMEOUT
            )
        print(f"[Telegram Upload] status={r.status_code}")
        print(f"[Telegram Upload] resposta={r.text}")
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"[Telegram Upload] erro ao enviar documento: {e}")
        return False

# --------------------------

def url_bis(numero):
    return f"https://www2.pc.pe.gov.br/arquivos/BisServ{ANO}/bisServ{numero:03d}_{ANO}.pdf"


def url_bis_especial(numero):
    return f"https://www2.pc.pe.gov.br/arquivos/BisServEspecial{ANO}/bisE{ANO}.{numero:02d}.pdf"

# --------------------------

def existe(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
    except requests.RequestException:
        pass

    try:
        with requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True) as r:
            return r.status_code == 200
    except requests.RequestException as e:
        print(f"[HTTP] erro ao verificar {url}: {e}")
        return False

# --------------------------

def baixar(url, destino):
    try:
        with requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True) as r:
            if r.status_code != 200:
                print(f"[Download] falha {url} HTTP {r.status_code}")
                return False

            with open(destino, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        return True
    except requests.RequestException as e:
        print(f"[Download] erro ao baixar {url}: {e}")
        return False

# --------------------------

def extrair_texto(pdf):
    texto = ""

    try:
        with open(pdf, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for p in reader.pages:
                texto += p.extract_text() or ""
    except Exception as e:
        print(f"[PDF] erro ao extrair texto de {pdf}: {e}")
        return ""

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
            print(f"[BIS] não encontrado: {numero:03d}")
            break

        nome = f"bisServ{numero:03d}_{ANO}.pdf"
        path = DOWNLOAD_DIR / nome

        print("[BIS] Baixando", nome)

        ok = baixar(url, path)
        if not ok:
            print(f"[BIS] falha no download: {nome}")
            break

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
            print(f"[BIS ESPECIAL] não encontrado: {numero:02d}")
            break

        nome = f"bisE{ANO}.{numero:02d}.pdf"
        path = DOWNLOAD_DIR / nome

        print("[BIS ESPECIAL] Baixando", nome)

        ok = baixar(url, path)
        if not ok:
            print(f"[BIS ESPECIAL] falha no download: {nome}")
            break

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
    print("[INFO] Iniciando monitor...")
    print(f"[INFO] ANO={ANO}")
    print(f"[INFO] PALAVRAS_CHAVE={PALAVRAS_CHAVE}")
    print(f"[INFO] TELEGRAM_CHAT_ID={TELEGRAM_CHAT_ID}")

    estado = carregar_estado()
    print(f"[INFO] Estado inicial={estado}")

    # teste opcional
    enviar_telegram("Teste do monitor BIS")

    processar_bis(estado)
    processar_bis_especial(estado)

    salvar_estado(estado)
    print(f"[INFO] Estado final={estado}")


if __name__ == "__main__":
    main()
