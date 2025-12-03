from flask import Flask, request, render_template, send_file
import requests
import os
from io import BytesIO
from zipfile import ZipFile

app = Flask(__name__)

# Leggi la chiave API da variabile d'ambiente
API_KEY = os.environ.get("UNWATER_API_KEY")
UNWATER_ENDPOINT = "https://api.unwatermark.ai/v1/image/remove-watermark"

@app.route("/", methods=["GET", "POST"])
def index():
    result_url = None
    if request.method == "POST":
        file = request.files.get("image")
        if file:
            img_bytes = file.read()
            # Chiamata API Unwatermark
            files = {"file": (file.filename, img_bytes)}
            headers = {"Authorization": f"Bearer {API_KEY}"}
            r = requests.post(UNWATER_ENDPOINT, files=files, headers=headers)

            # Controllo se la risposta è un'immagine
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
                # Salva in memoria in un ZIP
                zip_buffer = BytesIO()
                with ZipFile(zip_buffer, "w") as zip_file:
                    zip_file.writestr(file.filename, r.content)
                zip_buffer.seek(0)
                # Salva temporaneamente per invio
                tmp_zip_path = f"processed_{file.filename}.zip"
                with open(tmp_zip_path, "wb") as f:
                    f.write(zip_buffer.read())
                result_url = tmp_zip_path
            else:
                print("Errore API:", r.status_code, r.text)
    return render_template("index.html", result_url=result_url)

@app.route("/<filename>")
def download(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
