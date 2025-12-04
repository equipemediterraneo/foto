from flask import Flask, request, jsonify, send_file, render_template
import os, uuid, zipfile, shutil, requests
from io import BytesIO

app = Flask(__name__)
API_KEY = os.environ.get("UNWATER_API_KEY")
if not API_KEY:
    raise ValueError("Variabile d'ambiente UNWATER_API_KEY non impostata")

TMP_ROOT = "tmp_jobs"
os.makedirs(TMP_ROOT, exist_ok=True)

jobs = {}  # memorizza lo stato dei job {job_id: {"status": "processing"|"done", "zip_path": path}}

MAX_IMAGES = 10

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return jsonify({"error": "URL mancante"}), 400

        job_id = str(uuid.uuid4())
        job_dir = os.path.join(TMP_ROOT, job_id)
        os.makedirs(job_dir, exist_ok=True)

        jobs[job_id] = {"status": "processing", "zip_path": None}

        # Avvia elaborazione in background (sincrona qui per semplicità)
        process_images(url, job_dir, job_id)

        return jsonify({"job_id": job_id})

    return render_template("index.html")


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job non trovato"}), 404
    return jsonify({"status": job["status"]})


@app.route("/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return "File non pronto", 400
    return send_file(job["zip_path"], as_attachment=True)


def process_images(url, tmp_dir, job_id):
    """
    Funzione per scaricare immagini, inviare a unwatermark e creare ZIP
    """
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except:
        jobs[job_id]["status"] = "error"
        return

    # Estrai immagini DealerK 800x0 con webp/jpg/jpeg/png
    import re
    all_imgs = re.findall(
        r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:webp|jpg|jpeg|png)',
        html, re.IGNORECASE
    )
    all_imgs = list(dict.fromkeys(all_imgs))

    # Priorità webp
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
        local_path = os.path.join(tmp_dir, filename)
        try:
            # Scarica immagine originale
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
            if output_url:
                r2 = requests.get(output_url)
                processed_path = os.path.join(tmp_dir, "processed_" + filename)
                with open(processed_path, "wb") as f:
                    f.write(r2.content)
                processed_files.append(processed_path)
        except Exception as e:
            print(f"Errore processing {src}: {e}")
            continue

    # Crea ZIP finale
    zip_path = os.path.join(tmp_dir, "foto_modificate.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in processed_files:
            zf.write(f, os.path.basename(f))
    jobs[job_id]["zip_path"] = zip_path
    jobs[job_id]["status"] = "done"


if __name__ == "__main__":
    app.run(debug=True)
