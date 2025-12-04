from flask import Flask, request, render_template, send_file
import os, uuid, zipfile, shutil, re, requests
from io import BytesIO

app = Flask(__name__)

API_KEY = os.environ.get("UNWATER_API_KEY")
if not API_KEY:
    raise ValueError("Variabile d'ambiente UNWATER_API_KEY non impostata")

MAX_IMAGES = 10
DOWNLOAD_TIMEOUT = 30  # Timeout più alto per download lento

# Headers per simulare browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/118.0.5993.117 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Inserisci un URL valido", 400

        tmp_dir = os.path.join("tmp", str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        # Sessione persistente per più richieste
        session = requests.Session()
        session.headers.update(HEADERS)

        # Scarica HTML con retry
        try:
            resp = session.get(url, timeout=DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except requests.exceptions.RequestException as e:
            return f"Errore durante il download della pagina: {e}", 400

        # Trova immagini DealerK 800x0 (.webp preferite)
        all_imgs = re.findall(
            r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:webp|jpg|jpeg|png)',
            html,
            re.IGNORECASE
        )

        all_imgs = list(dict.fromkeys(all_imgs))  # rimuove duplicati

        # Webp prima
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
                r = session.get(src, timeout=DOWNLOAD_TIMEOUT)
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(r.content)
            except requests.exceptions.RequestException:
                continue  # salta immagine se non scaricabile

            # Invia all'API unwatermark
            try:
                with open(local_path, "rb") as f:
                    files = {"original_image_file": f}
                    headers_api = {"ZF-API-KEY": API_KEY}
                    api_resp = requests.post(
                        "https://api.unwatermark.ai/api/unwatermark/api/v1/auto-unWaterMark",
                        headers=headers_api,
                        files=files,
                        timeout=DOWNLOAD_TIMEOUT
                    )
                data = api_resp.json()
                output_url = data.get("result", {}).get("output_image_url")
            except Exception:
                continue

            # Scarica immagine processata
            if output_url:
                try:
                    r2 = session.get(output_url, timeout=DOWNLOAD_TIMEOUT)
                    r2.raise_for_status()
                    processed_path = os.path.join(tmp_dir, "processed_" + filename)
                    with open(processed_path, "wb") as f:
                        f.write(r2.content)
                    processed_files.append(processed_path)
                except Exception:
                    continue

        # Crea ZIP
        zip_io = BytesIO()
        with zipfile.ZipFile(zip_io, mode="w") as zf:
            for file_path in processed_files:
                zf.write(file_path, os.path.basename(file_path))
        zip_io.seek(0)

        # Pulizia temporanea
        shutil.rmtree(tmp_dir)

        return send_file(
            zip_io,
            mimetype="application/zip",
            download_name="foto_modificate.zip",
            as_attachment=True
        )

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)

