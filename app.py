from flask import Flask, request, render_template, send_file
import os, uuid, zipfile, shutil, re, requests, time
from urllib.parse import urlparse

# Pixelbin SDK
from pixelbin import PixelbinClient, PixelbinConfig

app = Flask(__name__)

# ============================================
# CONFIG PIXELBIN
# ============================================
PIXELBIN_API_TOKEN = os.environ.get("PIXELBIN_API_TOKEN")
if not PIXELBIN_API_TOKEN:
    raise ValueError("Variabile PIXELBIN_API_TOKEN non impostata su Render.")

pixelbin = PixelbinClient(
    PixelbinConfig({
        "domain": "https://api.pixelbin.io",
        "apiSecret": PIXELBIN_API_TOKEN,
    })
)

# Limite a 1 immagine
MAX_IMAGES = 1
BASE_TMP = "/tmp"


# ============================================
# Utility: scarica pagina HTML
# ============================================
def download_page(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return r.text
        except Exception:
            if attempt < 2:
                time.sleep(2)
            else:
                raise


# ============================================
# Utility: processa immagine con Pixelbin
# ============================================
def process_image_with_pixelbin(local_path):
    try:
        with open(local_path, "rb") as f:
            result = pixelbin.predictions.create_and_wait(
                name="wm_remove",
                input={
                    "image": f,
                    "rem_text": True,
                    "rem_logo": True,
                    "box1": "0_0_100_100",
                    "box2": "0_0_0_0",
                    "box3": "0_0_0_0",
                    "box4": "0_0_0_0",
                    "box5": "0_0_0_0"
                }
            )

        print("DEBUG PIXELBIN:", result)

        if result["status"] == "SUCCESS":
            out_url = result["output"][0]
            r = requests.get(out_url, timeout=15)
            r.raise_for_status()
            return r.content
        return None

    except Exception as e:
        print("Errore Pixelbin:", e)
        return None


# ============================================
# Homepage
# ============================================
@app.route("/", methods=["GET", "POST"])
def index():

    if request.method == "POST":
        print("DEBUG FORM:", request.form)

        url = request.form.get("url", "").strip()
        if not url:
            return "Inserisci un URL valido", 400

        # Estrazione nome modello come PHP
        slug = urlparse(url).path.strip("/")
        parts = slug.split("/")
        model_name = parts[-2] if len(parts) >= 2 else "modello_sconosciuto"
        print("MODEL NAME:", model_name)

        # Cartella temporanea
        tmp_dir = os.path.join(BASE_TMP, str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        # Scarica HTML
        try:
            html = download_page(url)
        except Exception as e:
            return f"Errore download pagina: {e}", 400

        # ============================================
        # TROVA IMMAGINI 800x0 + preferenza WEBP
        # ============================================

        # 1) Trova TUTTE le immagini 800x0 (sia webp che jpg/png)
        matches = re.findall(
            r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:webp|jpg|jpeg|png)',
            html,
            re.IGNORECASE
        )

        all_imgs = list(dict.fromkeys(matches))
        print("DEBUG - Immagini trovate:", all_imgs)

        if not all_imgs:
            return "Nessuna immagine trovata (800x0).", 400

        # 2) Ordina con priorità WEBP
        img_urls = sorted(
            all_imgs,
            key=lambda x: 0 if x.lower().endswith(".webp") else 1
        )

        # 3) Limita a 1 immagine MAX
        img_urls = img_urls[:MAX_IMAGES]
        print("DEBUG - Immagine selezionata:", img_urls)

        processed_files = []

        # ============================================
        # DOWNLOAD + PROCESSAMENTO
        # ============================================
        for src in img_urls:
            try:
                filename = os.path.basename(src.split("?")[0])
                local_path = os.path.join(tmp_dir, filename)

                r = requests.get(src, timeout=25)
                r.raise_for_status()

                with open(local_path, "wb") as f:
                    f.write(r.content)

                processed = process_image_with_pixelbin(local_path)
                if processed:
                    processed_path = os.path.join(tmp_dir, "processed_" + filename)
                    with open(processed_path, "wb") as f:
                        f.write(processed)
                    processed_files.append(processed_path)
                else:
                    print("❌ Pixelbin non ha processato.")
            except Exception as e:
                print("Errore immagine:", src, e)

        if not processed_files:
            shutil.rmtree(tmp_dir)
            return "Nessuna immagine processata con successo.", 400

        # ============================================
        # CREA ZIP → nome modello.zip
        # ============================================
        zip_filename = f"{model_name}.zip"
        zip_path = os.path.join(BASE_TMP, zip_filename)

        with zipfile.ZipFile(zip_path, "w") as zf:
            for file_path in processed_files:
                zf.write(file_path, os.path.basename(file_path))

        shutil.rmtree(tmp_dir)

        return render_template("index.html", result_url=f"/download/{zip_filename}")

    return render_template("index.html")


# ============================================
# Download ZIP
# ============================================
@app.route("/download/<zip_filename>")
def download_zip(zip_filename):
    zip_path = os.path.join(BASE_TMP, zip_filename)
    if not os.path.exists(zip_path):
        return "File non trovato", 404

    return send_file(
        zip_path,
        mimetype="application/zip",
        download_name=zip_filename,
        as_attachment=True
    )

# ============================================
# IMPORTANTE: Render usa GUNICORN
# (non usare app.run())
# ============================================
