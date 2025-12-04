from flask import Flask, request, render_template, send_file
import requests, os, zipfile, uuid, shutil
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from io import BytesIO

app = Flask(__name__)

# API KEY da Render
API_KEY = os.environ.get("UNWATER_API_KEY")
if not API_KEY:
    print("⚠️ AVVISO: la variabile UNWATER_API_KEY non è impostata. L'app partirà, ma l'API non funzionerà.")

MAX_IMAGES = 10

def safe_get(url):
    """Download protetto con User-Agent, timeout e gestione degli errori."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    try:
        r = requests.get(url, headers=headers, timeout=12)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"[ERRORE] impossibile scaricare {url}: {e}")
        return None


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Inserisci un URL valido.", 400

        # crea cartella temporanea
        tmp_dir = os.path.join("tmp", str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        # scarica HTML della pagina
        resp = safe_get(url)
        if not resp:
            shutil.rmtree(tmp_dir)
            return "Impossibile scaricare la pagina. Il sito potrebbe bloccare bot o connessioni da server.", 400

        soup = BeautifulSoup(resp.text, "html.parser")

        # trova link immagini
        img_urls = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue

            # converti in URL assoluto
            src = urljoin(url, src)

            if src.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                img_urls.append(src)

        # rimuovi duplicati e taglia a 10 immagini
        img_urls = list(dict.fromkeys(img_urls))[:MAX_IMAGES]

        processed_files = []

        # scarica e processa ogni immagine
        for src in img_urls:
            name = os.path.basename(src.split("?")[0]).replace("/", "_")
            local_path = os.path.join(tmp_dir, name)

            # scarica immagine originale
            img_response = safe_get(src)
            if not img_response:
                continue
            with open(local_path, "wb") as f:
                f.write(img_response.content)

            # invia all'API unwatermark
            try:
                with open(local_path, "rb") as f:
                    api_resp = requests.post(
                        "https://api.unwatermark.ai/api/unwatermark/api/v1/auto-unWaterMark",
                        headers={"ZF-API-KEY": API_KEY},
                        files={"original_image_file": f},
                        timeout=20
                    )
                api_resp.raise_for_status()
                
                data = api_resp.json()
            except Exception as e:
                print("[ERRORE API]:", e)
                continue

            output_url = data.get("result", {}).get("output_image_url")
            if not output_url:
                continue

            # scarica immagine processata
            processed_resp = safe_get(output_url)
            if not processed_resp:
                continue

            processed_path = os.path.join(tmp_dir, "processed_" + name)
            with open(processed_path, "wb") as f:
                f.write(processed_resp.content)

            processed_files.append(processed_path)

        # crea file ZIP
        zip_io = BytesIO()
        with zipfile.ZipFile(zip_io, "w") as zf:
            for p in processed_files:
                zf.write(p, os.path.basename(p))
        zip_io.seek(0)

        # pulizia
        shutil.rmtree(tmp_dir)

        return send_file(
            zip_io,
            mimetype="application/zip",
            download_name="foto_modificate.zip",
            as_attachment=True
        )

    return render_template("index.html")
