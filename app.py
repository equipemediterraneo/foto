from flask import Flask, request, render_template, send_file
import requests
import os
from io import BytesIO
from zipfile import ZipFile

app = Flask(__name__)

# API Key da variabile d'ambiente su Render
API_KEY = os.environ.get("UNWATER_API_KEY")
UNWATER_ENDPOINT = "https://api.unwatermark.ai/api/unwatermark/api/v1/auto-unWaterMark"

@app.route("/", methods=["GET", "POST"])
def index():
    result_url = None

    if request.method == "POST":
        file = request.files.get("image")
        if file:
            img_bytes = file.read()

            # Chiamata all'API Unwatermark
            files = {"original_image_file": (file.filename, img_bytes)}
            headers = {"ZF-API-KEY": API_KEY}

            r = requests.post(UNWATER_ENDPOINT, files=files, headers=headers)
            if r.status_code == 200:
                data = r.json()
                if "result" in data and "output_image_url" in data["result"]:
                    output_url = data["result"]["output_image_url"]

                    # Scarica l'immagine processata
                    img_response = requests.get(output_url)
                    if img_response.status_code == 200:
                        # Crea ZIP in memoria
                        zip_buffer = BytesIO()
                        with ZipFile(zip_buffer, "w") as zip_file:
                            zip_file.writestr(file.filename, img_response.content)
                        zip_buffer.seek(0)

                        # Salva temporaneamente il ZIP
                        tmp_zip_path = f"processed_{file.filename}.zip"
                        with open(tmp_zip_path, "wb") as f:
                            f.write(zip_buffer.read())

                        result_url = tmp_zip_path
                    else:
                        print("Errore download immagine:", img_response.status_code)
                else:
                    print("Errore API, risposta incompleta:", data)
            else:
                print("Errore chiamata API:", r.status_code, r.text)

    return render_template("index.html", result_url=result_url)

@app.route("/<filename>")
def download(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
