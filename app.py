from flask import Flask, request, render_template, send_file
import os, uuid, zipfile, shutil, re, requests
from io import BytesIO
from bs4 import BeautifulSoup

app = Flask(__name__)

API_KEY = os.environ.get("UNWATER_API_KEY")
if not API_KEY:
    raise ValueError("Variabile d'ambiente UNWATER_API_KEY non impostata")

MAX_IMAGES = 10

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Inserisci un URL valido", 400

        # Cartella temporanea
        tmp_dir = os.path.join("tmp", str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        # Scarica HTML
        try:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
except requests.exceptions.RequestException as e:
    return f"Errore durante il download della pagina: {e}", 400

        html = resp.text

        # Trova immagini DealerK 800x0 con estensione webp/jpg/jpeg/png
        all_imgs = re.findall(
            r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:webp|jpg|jpeg|png)',
            html,
            re.IGNORECASE
        )

        # Rimuove duplicati
        all_imgs = list(dict.fromkeys(all_imgs))

        # Lista finale: webp in cima
        img_urls = []
        for img in all_imgs:
            if img.lower().endswith(".webp"):
                img_urls.insert(0, img)
            else:
                img_urls.append(img)
        img_urls = img_urls[:MAX_IMAGES]

        # Scarica e processa immagini
        processed_files = []
        for src in img_urls:
            filename = os.path.basename(src.split("?")[0])
            filename = filename.replace("/", "_")
            local_path = os.path.join(tmp_dir, filename)

            # Scarica immagine
            r = requests.get(src)
            with open(local_path, "wb") as f:
                f.write(r.content)

            # Invia all'API unwatermark
            with open(local_path, "rb") as f:
                files = {"original_image_file": f}
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

        # Pulizia cartella temporanea
        shutil.rmtree(tmp_dir)

        return send_file(
            zip_io,
            mimetype="application/zip",
            download_name="foto_modificate.zip",
            as_attachment=True
        )

    return render_template("index.html")

