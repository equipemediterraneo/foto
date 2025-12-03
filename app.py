from flask import Flask, render_template, request, send_file
import os
import re
import requests
from urllib.parse import urlparse
import zipfile
import io

app = Flask(__name__)

# CONFIG
import os

API_KEY = os.environ.get("UNWATER_API_KEY")
UNWATER_ENDPOINT = "https://api.unwatermark.ai/v1/image/remove-watermark"
USE_UNWATERMARK = True


def fetch_html(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    return r.text


def fetch_image(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    return r.content


def process_unwatermark(img_bytes):
    if not USE_UNWATERMARK:
        return img_bytes

    files = {"file": ("image.jpg", img_bytes)}
    headers = {"Authorization": f"Bearer " + API_KEY}

    r = requests.post(UNWATER_ENDPOINT, files=files, headers=headers)
    if r.status_code == 200:
        return r.content
    return img_bytes


def extract_model_name(url):
    p = urlparse(url).path.strip("/")
    parts = p.split("/")
    return parts[-2] if len(parts) >= 2 else "modello"


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form["url"].strip()
        model = extract_model_name(url)

        html = fetch_html(url)

        pattern = r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:jpg|jpeg|png)'
        urls = list(set(re.findall(pattern, html, re.IGNORECASE)))

        memory_zip = io.BytesIO()
        with zipfile.ZipFile(memory_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            for idx, img_url in enumerate(urls, start=1):
                img_data = fetch_image(img_url)
                clean = process_unwatermark(img_data)
                zipf.writestr(f"{model}_{idx}.jpg", clean)

        memory_zip.seek(0)
        zip_filename = f"{model}.zip"

        return send_file(memory_zip, as_attachment=True, download_name=zip_filename)

    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
