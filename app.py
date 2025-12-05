from flask import Flask, request, render_template, send_file
import os
import uuid
import zipfile
import shutil
import re
import requests
from urllib.parse import urlparse
from pixelbin import PixelbinClient, PixelbinConfig

app = Flask(__name__)

# Config Pixelbin
PIXELBIN_API_TOKEN = os.environ.get("PIXELBIN_API_TOKEN")
if not PIXELBIN_API_TOKEN:
    raise ValueError("Variabile d'ambiente PIXELBIN_API_TOKEN non impostata")

pixelbin = PixelbinClient(
    PixelbinConfig({
        "domain": "https://api.pixelbin.io",
        "apiSecret": PIXELBIN_API_TOKEN,
    })
)

MAX_IMAGES = 1

# Scarica pagina HTML
def download_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text

# Processa immagine con Pixelbin (sincrono)
def process_image_with_pixelbin(local_path):
    try:
        result = pixelbin.predictions.create_and_wait(
            name="wm_remove",
            input={
                "image": local_path,
                "rem_text": True,
                "rem_logo": True,
                "box1": "0_0_100_100",
                "box2": "0_0_0_0",
                "box3": "0_0_0_0",
                "box4": "0_0_0_0",
                "box5": "0_0_0_0"
            }
        )
        if result["status"] == "SUCCESS":
            output_url = result["output"][0]
            r = requests.get(output_url, timeout=15)
            r.raise_for_status()
            return r.content
        else:
            print("Pixelbin failed:", result.get("error"))
            return None
    except Exception as e:
        print("Errore Pixelbin:", e)
        return None

# Estrai nome modello dall'URL (penultima cartella)
def get_model_name(url):
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2:
        return parts[-2]
    return "modello_sconosciuto"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Inserisci un URL valido", 400

        model_name = get_model_name(url)
        tmp_dir = os.path.join("tmp", str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        try:
            html = download_page(url)
        except Exception as e:
            return f"Errore durante il download della pagina: {e}", 400

        # Trova immagini DealerK 800x0
        all_imgs = re.findall(
            r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:webp|jpg|jpeg|png)',
            html,
            re.IGNORECASE
        )
        all_imgs = list(dict.fromkeys(all_imgs))  # rimuove duplicati

        # Preferenza WebP
        img_urls = []
        for img in all_imgs:
            if img.lower().endswith(".webp"):
                img_urls.insert(0, img)
            else:
                img_urls.append(img)
        img_urls = img_urls[:MAX_IMAGES]

        processed_files = []
        for src in img_urls:
            try:
                filename = os.path.basename(src.split("?")[0])
                local_path = os.path.join(tmp_dir, filename)

                # Scarica immagine
                r = requests.get(src, timeout=20)
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(r.content)

                # Processa con Pixelbin
                processed_bytes = process_image_with_pixelbin(local_path)
                if processed_bytes:
                    processed_path = os.path.join(tmp_dir, filename)
                    with open(processed_path, "wb") as f:
                        f.write(processed_bytes)
                    processed_files.append(processed_path)
                    print("✅ Immagine processata:", src)
                else:
                    print("❌ Fallita Pixelbin:", src)
            except Exception as e:
                print("❌ Errore durante download o processing:", src, e)

        if not processed_files:
            shutil.rmtree(tmp_dir)
            return "Nessuna immagine processata con successo.", 400

        # Crea ZIP finale con nome modello
        zip_filename = f"{model_name}.zip"
        zip_path = os.path.join("tmp", zip_filename)
        with zipfile.ZipFile(zip_path, mode="w") as zf:
            for file_path in processed_files:
                zf.write(file_path, os.path.basename(file_path))

        shutil.rmtree(tmp_dir)
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
        download_name=zip_filename,
        as_attachment=True
    )

if __name__ == "__main__":
    os.makedirs("tmp", exist_ok=True)
    app.run(debug=True)
