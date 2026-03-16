import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import requests
import PyPDF2

# --------------------------
# Configuração via Secrets
# --------------------------

ANO = int(os.getenv("ANO", "2026"))

PALAVRAS_CHAVE = [
    p.strip().strip('"').strip("'").upper()
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
        print("[Telegram Upload] TOKEN ou CHAT_ID não configurados.")
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
        r = requests.head(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
        print(f"[HEAD] {url} -> {r.status_code}")
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
    except requests.RequestException as e:
        print(f"[HEAD] erro em {url}: {e}")

    try:
        with requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            stream=True
        ) as r:
            print(f"[GET] {url} -> {r.status_code}")
            return r.status_code == 200
    except requests.RequestException as e:
        print(f"[GET] erro em {url}: {e}")
        return False


# --------------------------

def baixar(url, destino):
    print(f"[DOWNLOAD] tentando baixar: {url}")
    try:
        with requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            stream=True
        ) as r:
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
            for pagina in reader.pages:
                texto += pagina.extract_text() or ""
    except Exception as e:
        print(f"[PDF] erro ao extrair texto de {pdf}: {e}")
        return ""

    return texto.upper()


def procurar_palavras(texto):
    achadas = []

    for palavra in PALAVRAS_CHAVE:
        if palavra in texto:
            achadas.append(palavra)

    return achadas


# --------------------------

def processar_bis(estado, relatorio):
    numero = estado["ULTIMO_BIS"] + 1

    while True:
        url = url_bis(numero)

        if not existe(url):
            print(f"[BIS] não encontrado: {numero:03d}")
            relatorio["proximo_bis_nao_encontrado"] = f"bisServ{numero:03d}_{ANO}.pdf"
            break

        nome = f"bisServ{numero:03d}_{ANO}.pdf"
        path = DOWNLOAD_DIR / nome

        print(f"[BIS] baixando {nome}")

        ok = baixar(url, path)
        if not ok:
            print(f"[BIS] falha no download: {nome}")
            relatorio["bis"].append({
                "nome": nome,
                "tipo": "BIS",
                "status": "ERRO_NO_DOWNLOAD",
                "palavras": [],
                "path": None
            })
            break

        texto = extrair_texto(path)
        palavras = procurar_palavras(texto)

        relatorio["bis"].append({
            "nome": nome,
            "tipo": "BIS",
            "status": "ENCONTRADO",
            "palavras": palavras,
            "path": str(path)
        })

        estado["ULTIMO_BIS"] = numero
        numero += 1


def processar_bis_especial(estado, relatorio):
    numero = estado["ULTIMO_BIS_ESPECIAL"] + 1

    while True:
        url = url_bis_especial(numero)

        if not existe(url):
            print(f"[BIS ESPECIAL] não encontrado: {numero:02d}")
            relatorio["proximo_bis_especial_nao_encontrado"] = f"bisE{ANO}.{numero:02d}.pdf"
            break

        nome = f"bisE{ANO}.{numero:02d}.pdf"
        path = DOWNLOAD_DIR / nome

        print(f"[BIS ESPECIAL] baixando {nome}")

        ok = baixar(url, path)
        if not ok:
            print(f"[BIS ESPECIAL] falha no download: {nome}")
            relatorio["bis_especial"].append({
                "nome": nome,
                "tipo": "BIS ESPECIAL",
                "status": "ERRO_NO_DOWNLOAD",
                "palavras": [],
                "path": None
            })
            break

        texto = extrair_texto(path)
        palavras = procurar_palavras(texto)

        relatorio["bis_especial"].append({
            "nome": nome,
            "tipo": "BIS ESPECIAL",
            "status": "ENCONTRADO",
            "palavras": palavras,
            "path": str(path)
        })

        estado["ULTIMO_BIS_ESPECIAL"] = numero
        numero += 1


# --------------------------

def montar_relatorio(relatorio):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")

    total_bis = len(relatorio["bis"])
    total_bis_especial = len(relatorio["bis_especial"])
    total_atualizacoes = total_bis + total_bis_especial

    linhas = []

    if total_atualizacoes == 0:
        linhas.append("CONSULTA MONITOR BIS")
        linhas.append("")
        linhas.append(f"Consulta realizada em (horário de Brasília): {agora}")
        linhas.append("Nenhuma atualização foi encontrada até o momento.")
        return "\n".join(linhas)

    linhas.append("ATUALIZAÇÃO IDENTIFICADA NO MONITOR BIS")
    linhas.append("")
    linhas.append(f"Consulta realizada em (horário de Brasília): {agora}")
    linhas.append(f"Foram encontradas {total_atualizacoes} atualização(ões) nova(s).")
    linhas.append("")

    if relatorio["bis"]:
        linhas.append("BIS:")
        for item in relatorio["bis"]:
            if item["status"] == "ERRO_NO_DOWNLOAD":
                linhas.append(f"- {item['nome']}: arquivo localizado, mas houve erro no download.")
            elif item["palavras"]:
                linhas.append(
                    f"- {item['nome']}: atualização encontrada e palavra(s)-chave localizada(s): {', '.join(item['palavras'])}."
                )
            else:
                linhas.append(
                    f"- {item['nome']}: atualização encontrada, sem ocorrência das palavras-chave monitoradas."
                )
        linhas.append("")

    if relatorio["bis_especial"]:
        linhas.append("BIS ESPECIAL:")
        for item in relatorio["bis_especial"]:
            if item["status"] == "ERRO_NO_DOWNLOAD":
                linhas.append(f"- {item['nome']}: arquivo localizado, mas houve erro no download.")
            elif item["palavras"]:
                linhas.append(
                    f"- {item['nome']}: atualização encontrada e palavra(s)-chave localizada(s): {', '.join(item['palavras'])}."
                )
            else:
                linhas.append(
                    f"- {item['nome']}: atualização encontrada, sem ocorrência das palavras-chave monitoradas."
                )
        linhas.append("")

    return "\n".join(linhas)


def enviar_documentos_com_palavra_chave(relatorio):
    enviados = 0

    for grupo in (relatorio["bis"], relatorio["bis_especial"]):
        for item in grupo:
            if item["status"] == "ENCONTRADO" and item["palavras"] and item["path"]:
                path = Path(item["path"])
                if path.exists():
                    if enviar_documento(path):
                        enviados += 1

    print(f"[INFO] documentos enviados ao Telegram: {enviados}")


# --------------------------

def main():
    print("[INFO] Iniciando monitor...")
    print(f"[INFO] ANO={ANO}")
    print(f"[INFO] PALAVRAS_CHAVE={PALAVRAS_CHAVE}")
    print(f"[INFO] TELEGRAM_CHAT_ID={TELEGRAM_CHAT_ID}")

    estado = carregar_estado()
    print(f"[INFO] Estado inicial={estado}")

    relatorio = {
        "bis": [],
        "bis_especial": [],
        "proximo_bis_nao_encontrado": "",
        "proximo_bis_especial_nao_encontrado": ""
    }

    processar_bis(estado, relatorio)
    processar_bis_especial(estado, relatorio)

    salvar_estado(estado)

    print(f"[INFO] Estado final={estado}")

    texto_relatorio = montar_relatorio(relatorio)
    enviar_telegram(texto_relatorio)

    enviar_documentos_com_palavra_chave(relatorio)


if __name__ == "__main__":
    main()
