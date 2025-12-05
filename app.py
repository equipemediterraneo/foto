import os
import re
import uuid
import shutil
import zipfile
import requests
import nest_asyncio
from flask import Flask, request, render_template, send_file
from pixelbin import PixelbinClient, PixelbinConfig

# Abilita event loop per Pixelbin async (obbligatorio su Render)
nest_asyncio.apply()

app = Flask(__name__)

# ============================
#  CONFIGURAZIONE PIXELBIN
# ============================
PIXELBIN_API_TOKEN = os.getenv("PIXELBIN_API_TOKEN")

# Debug per Render
print("DEBUG Pixelbin Token:", PIXELBIN_API_TOKEN[:6] + "..." if PIXELBIN_API_TOKEN else "NONE")

if not PIXELBIN_API_TOKEN:
    raise ValueError("⚠️ Variabile d'ambiente PIXELBIN_API_TOKEN non impostata")

pixelbin = PixelbinClient(
    PixelbinConfig({
        "domain": "https://api.pixelbin.io",
        "apiSecret": PIXELBIN_API_TOKEN,
    })
)

# Numero massimo immagini da elaborare
MAX_IMAGES = 10

# ============================
#  FUNZIONE DOWNLOAD PAGINA
# ============================
def download_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text

# ============================
#  FUNZIONE PROCESSAMENTO PIXELBIN
# ============================
def process_image(local_path):
    try:
        # Leggi file locale come bytes (Pixelbin non accetta percorsi)
        with open(local_path, "rb") as f:
            img_bytes = f.read()

        # Creazione job
        job = pixelbin.predictions.create(
            name="wm_remove",
            input={
                "image": img_bytes,
                "mask": "",
                "rem_text": "true",
                "rem_logo": "true",
                "box1": "0_0_100_100",
                "box2": "0_0_0_0",
                "box3": "0_0_0_0",
                "box4": "0_0_0_0",
                "box5": "0_0_0_0",
            }
        )

        print("DEBUG Pixelbin Job ID:", job["_id"])

        # Attesa risultato
        result = pixelbin.predictions.wait(job["_id"])
        print("DEBUG Pixelbin Result:", result)

        if result["status"] == "SUCCESS":
            output_url = result["output"][0]
            r = requests.get(output_url, timeout=15)
            r.raise_for_status()
            return r.content

        print("❌ Pixelbin ha restituito errore:", result.get("error"))
        return None

    except Exception as e:
        print("❌ Errore Pixelbin:", e)
        return None

# ============================
#  ENDPOINT PRINCIPALE
# ============================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Inserisci un URL valido", 400

        # Nome modello dal penultimo segmento URL
        slug = url.strip("/").split("/")
        model_name = slug[-2] if len(slug) >= 2 else "modello_sconosciuto"

        tmp_dir = os.path.join("tmp", str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        # Scarica pagina
        try:
            html = download_page(url)
        except Exception as e:
            return f"Errore download pagina: {e}", 400

        # Trova immagini DealerK
        all_imgs = re.findall(
            r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:webp|jpg|jpeg|png)',
            html,
            re.IGNORECASE
        )
        all_imgs = list(dict.fromkeys(all_imgs))  # elimina duplicati

        img_urls = sorted(all_imgs, key=lambda x: 0 if x.lower().endswith(".webp") else 1)[:MAX_IMAGES]
        print("DEBUG - Immagini trovate:", img_urls)

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
                processed_bytes = process_image(local_path)
                if processed_bytes:
                    processed_path = os.path.join(tmp_dir, "processed_" + filename)
                    with open(processed_path, "wb") as f:
                        f.write(processed_bytes)
                    processed_files.append(processed_path)
                    print("✔️ Immagine processata:", src)
                else:
                    print("❌ Fallito Pixelbin:", src)

            except Exception as e:
                print("❌ Errore durante download o processing:", src, e)

        if not processed_files:
            shutil.rmtree(tmp_dir)
            return "❌ Nessuna immagine processata con successo.", 400

        # Crea ZIP
        zip_filename = f"{model_name}.zip"
        zip_path = os.path.join("tmp", zip_filename)
        with zipfile.ZipFile(zip_path, "w") as zf:
            for file_path in processed_files:
                zf.write(file_path, os.path.basename(file_path))

        shutil.rmtree(tmp_dir)
        result_url = f"/download/{zip_filename}"

        return render_template("index.html", result_url=result_url)

    return render_template("index.html")

# ============================
#  ENDPOINT DOWNLOAD ZIP
# ============================
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

# ============================
#  ENDPOINT TEST PIXELBIN
# ============================
@app.route("/test_pixelbin")
def test_pixelbin():
    try:
        job = pixelbin.predictions.create(
            name="wm_remove",
            input={
                "image": "https://cdn.pixelbin.io/v2/dummy-cloudname/original/__playground/playground-default.jpeg",
                "mask": "",
                "rem_text": "false",
                "rem_logo": "false",
                "box1": "0_0_100_100",
                "box2": "0_0_0_0",
                "box3": "0_0_0_0",
                "box4": "0_0_0_0",
                "box5": "0_0_0_0"
            }
        )
        return f"Pixelbin OK — Job creato: {job['_id']}"
    except Exception as e:
        return f"❌ Errore Pixelbin: {e}", 500

# ============================
#  AVVIO SERVER
# ============================
if __name__ == "__main__":
    os.makedirs("tmp", exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5000)
