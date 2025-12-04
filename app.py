from flask import Flask, request, render_template, send_file
import os, uuid, zipfile, shutil, re, requests, time
from io import BytesIO
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

app = Flask(__name__)

API_KEY = os.environ.get("UNWATER_API_KEY")
if not API_KEY:
    raise ValueError("Variabile d'ambiente UNWATER_API_KEY non impostata")

MAX_IMAGES = 10

# Funzione per scaricare la pagina con retry e User-Agent
def download_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    }

    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    for attempt in range(3):
        try:
            resp = session.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise e

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Inserisci un URL valido", 400

        # Cartella temporanea
        tmp_dir = os.path.join("tmp", str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        try:
            html = download_page(url)
        except Exception as e:
            return f"Errore durante il download della pagina: {e}", 400

        # Trova immagini DealerK 800x0 con preferenza webp
        all_imgs = re.findall(
            r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:webp|jpg|jpeg|png)',
            html,
            re.IGNORECASE
        )
        all_imgs = list(dict.fromkeys(all_imgs))  # rimuove duplicati

        img_urls = []
        for img in all_imgs:
            if img.lower().endswith(".webp"):
                img_urls.insert(0, img)
            else:
                img_urls.append(img)
        img_urls = img_urls[:MAX_IMAGES]

        processed_files = []
        for src in img_urls:
            filename = os.path.basename(src.split("?")[0])
            filename = filename.replace("/", "_")
            local_path = os.path.join(tmp_dir, filename)

            # Scarica immagine
            try:
                r = requests.get(src, timeout=15)
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(r.content)
            except Exception as e:
                continue

            # Invia all'API Unwatermark
            try:
                with open(local_path, "rb") as f:
                    files = {"original_image_file": f}
                    headers = {"ZF-API-KEY": API_KEY}
                    api_resp = requests.post(
                        "https://api.unwatermark.ai/api/unwatermark/api/v1/auto-unWaterMark",
                        headers=headers,
                        files=files,
                        timeout=30
                    )
                data = api_resp.json()
                output_url = data.get("result", {}).get("output_image_url")
                if output_url:
                    r2 = requests.get(output_url, timeout=15)
                    r2.raise_for_status()
                    processed_path = os.path.join(tmp_dir, "processed_" + filename)
                    with open(processed_path, "wb") as f:
                        f.write(r2.content)
                    processed_files.append(processed_path)
            except Exception as e:
                continue

        if not processed_files:
            shutil.rmtree(tmp_dir)
            return "Nessuna immagine processata con successo.", 400

        # Crea ZIP finale
        zip_filename = f"foto_modificate_{uuid.uuid4().hex}.zip"
        zip_path = os.path.join("tmp", zip_filename)
        with zipfile.ZipFile(zip_path, mode="w") as zf:
            for file_path in processed_files:
                zf.write(file_path, os.path.basename(file_path))

        # Pulizia cartella temporanea
        shutil.rmtree(tmp_dir)

        # URL relativo per il download
        result_url = f"/download/{zip_filename}"
        return render_template("index.html", result_url=result_url)

    return render_template("index.html")

@app.route("/download/<zip_filename>")
def download_zip(zip_filename):
    zip_path = os.path.join("tmp", zip_filename)
    if not os.path.exists(zip_path):
        return "File non trovato", 404
    return send_file(
        zip_path,
        mimetype="application/zip",
        download_name="foto_modificate.zip",
        as_attachment=True
    )

if __name__ == "__main__":
    app.run(debug=True)
