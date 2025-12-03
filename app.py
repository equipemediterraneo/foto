from flask import Flask, request, render_template, send_file
import requests
import os
from io import BytesIO
from zipfile import ZipFile
import re
from urllib.parse import urlparse

app = Flask(__name__)

# Inserisci la tua API Key nelle environment variables su Render
API_KEY = os.environ.get("UNWATER_API_KEY")
UNWATER_ENDPOINT = "https://api.unwatermark.ai/api/unwatermark/api/v1/auto-unWaterMark"

def fetch_html(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return r.text if r.status_code == 200 else ""

def fetch_image(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return r.content if r.status_code == 200 else None

def process_unwatermark(img_bytes):
    files = {"original_image_file": ("image.jpg", img_bytes)}
    headers = {"ZF-API-KEY": API_KEY}

    r = requests.post(UNWATER_ENDPOINT, files=files, headers=headers)
    if r.status_code == 200:
        data = r.json()
        if "result" in data and "output_image_url" in data["result"]:
            output_url = data["result"]["output_image_url"]
            img_response = requests.get(output_url)
            if img_response.status_code == 200:
                return img_response.content
    return None

def extract_image_urls(html):
    matches = re.findall(
        r'https://cdn\.dealerk\.it/dealer/datafiles/vehicle/images/800x0/[^"\']+\.(?:jpg|jpeg|png)', html, re.I
    )
    return list(set(matches))  # rimuove duplicati

@app.route("/", methods=["GET", "POST"])
def index():
    result_url = None
    error = None

    if request.method == "POST":
        url = request.form.get("url")
        if url:
            html = fetch_html(url)
            image_urls = extract_image_urls(html)[:10]  # Limita a massimo 10 immagini

            if not image_urls:
                error = "Nessuna immagine trovata."
            else:
                zip_buffer = BytesIO()
                with ZipFile(zip_buffer, "w") as zip_file:
                    for img_url in image_urls:
                        img_bytes = fetch_image(img_url)
                        if img_bytes:
                            processed_bytes = process_unwatermark(img_bytes)
                            if processed_bytes:
                                filename = os.path.basename(urlparse(img_url).path)
                                zip_file.writestr(filename, processed_bytes)

                zip_buffer.seek(0)
                tmp_zip_path = "processed_images.zip"
                with open(tmp_zip_path, "wb") as f:
                    f.write(zip_buffer.read())

                result_url = tmp_zip_path

    return render_template("index.html", result_url=result_url, error=error)

@app.route("/<filename>")
def download(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

