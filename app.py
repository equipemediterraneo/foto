from flask import Flask, request, render_template, send_file
import requests, os, zipfile, uuid
from bs4 import BeautifulSoup
from io import BytesIO

app = Flask(__name__)

import os

# Legge la API Key dalla variabile d'ambiente
API_KEY = os.environ.get("ZF_API_KEY")

if not API_KEY:
    raise ValueError("Variabile d'ambiente ZF_API_KEY non impostata")

MAX_IMAGES = 10

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Inserisci un URL valido", 400

        # Cartella temporanea per il processo
        tmp_dir = os.path.join("tmp", str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        # Scarica HTML della pagina
        resp = requests.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Trova immagini (JPG, PNG, WebP)
        img_urls = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if src and src.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                img_urls.append(src)

        img_urls = list(dict.fromkeys(img_urls))[:MAX_IMAGES]

        # Scarica immagini e processa con API unwatermark
        processed_files = []
        for src in img_urls:
            filename = os.path.basename(src.split("?")[0])
            filename = filename.replace("/", "_")
            local_path = os.path.join(tmp_dir, filename)

            # Scarica immagine originale
            r = requests.get(src)
            with open(local_path, "wb") as f:
                f.write(r.content)

            # Invia all'API unwatermark
            files = {"original_image_file": open(local_path, "rb")}
            headers = {"ZF-API-KEY": API_KEY}
            api_resp = requests.post(
                "https://api.unwatermark.ai/api/unwatermark/api/v1/auto-unWaterMark",
                headers=headers,
                files=files
            )
            data = api_resp.json()
            output_url = data.get("result", {}).get("output_image_url")

            # Scarica immagine processata
            if output_url:
                r2 = requests.get(output_url)
                processed_path = os.path.join(tmp_dir, "processed_" + filename)
                with open(processed_path, "wb") as f:
                    f.write(r2.content)
                processed_files.append(processed_path)

        # Crea ZIP finale
        zip_io = BytesIO()
        with zipfile.ZipFile(zip_io, mode="w") as zf:
            for file_path in processed_files:
                zf.write(file_path, os.path.basename(file_path))
        zip_io.seek(0)

        # Pulizia cartella temporanea opzionale
        # shutil.rmtree(tmp_dir)

        return send_file(
            zip_io,
            mimetype="application/zip",
            download_name="foto_modificate.zip",
            as_attachment=True
        )

    return render_template("index.html")
