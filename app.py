from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image, ImageEnhance, ImageOps
import numpy as np
import cv2
import os
import uuid
import time
import threading

app = Flask(__name__)

UPLOAD_FOLDER = 'static/temp'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def cleanup_old_files():
    while True:
        now = time.time()
        try:
            for f in os.listdir(UPLOAD_FOLDER):
                path = os.path.join(UPLOAD_FOLDER, f)
                if os.path.isfile(path) and (now - os.path.getmtime(path)) > 1800:
                    try:
                        os.remove(path)
                    except:
                        pass
        except:
            pass
        time.sleep(300)

threading.Thread(target=cleanup_old_files, daemon=True).start()

def ai_skin_retouch(img_pil):
    img = np.array(img_pil)
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # ধাপ ১: ত্বক মসৃণ (দাগ দূর, এজ ঠিক রাখে)
    smooth = cv2.bilateralFilter(img_bgr, d=15, sigmaColor=100, sigmaSpace=100)
    smooth = cv2.bilateralFilter(smooth, d=15, sigmaColor=70, sigmaSpace=70)

    # ধাপ ২: ডিটেইল এনহ্যান্স (চোখ, চুল, ঠোঁট শার্প)
    detail = cv2.detailEnhance(img_bgr, sigma_s=15, sigma_r=0.18)

    # ধাপ ৩: ব্লেন্ড - ৭০% smooth, ৩০% detail
    blended = cv2.addWeighted(smooth, 0.70, detail, 0.30, 0)

    # ধাপ ৪: হালকা সফট গ্লো (নরম আভা)
    glow = cv2.GaussianBlur(blended, (0, 0), sigmaX=18)
    final = cv2.addWeighted(blended, 0.80, glow, 0.20, 0)

    result_rgb = cv2.cvtColor(final, cv2.COLOR_BGR2RGB)
    result_pil = Image.fromarray(result_rgb)

    # ধাপ ৫: হালকা কালার গ্রেডিং (ছবি পুড়বে না)
    result_pil = ImageEnhance.Brightness(result_pil).enhance(1.05)
    result_pil = ImageEnhance.Color(result_pil).enhance(1.10)
    result_pil = ImageEnhance.Contrast(result_pil).enhance(1.05)
    result_pil = ImageEnhance.Sharpness(result_pil).enhance(1.30)

    return result_pil

def apply_filter(img_pil, filter_name):
    if filter_name == 'none':
        return img_pil

    if filter_name == 'warm':
        r, g, b = img_pil.split()
        r = r.point(lambda i: min(255, int(i * 1.08)))
        b = b.point(lambda i: int(i * 0.94))
        img_pil = Image.merge('RGB', (r, g, b))
        return ImageEnhance.Color(img_pil).enhance(1.10)

    if filter_name == 'bw':
        return ImageOps.grayscale(img_pil).convert('RGB')

    if filter_name == 'hd':
        img_pil = ImageEnhance.Sharpness(img_pil).enhance(2.0)
        img_pil = ImageEnhance.Contrast(img_pil).enhance(1.15)
        img_pil = ImageEnhance.Color(img_pil).enhance(1.10)
        return img_pil

    return img_pil

def adjust_image(img_pil, bright, contrast, color):
    if bright != 100:
        img_pil = ImageEnhance.Brightness(img_pil).enhance(bright / 100.0)
    if contrast != 100:
        img_pil = ImageEnhance.Contrast(img_pil).enhance(contrast / 100.0)
    if color != 100:
        img_pil = ImageEnhance.Color(img_pil).enhance(color / 100.0)
    return img_pil

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/enhance', methods=['POST'])
def enhance():
    try:
        file = request.files.get('image')
        if not file:
            return jsonify({'error': 'কোনো ছবি পাওয়া যায়নি'}), 400

        img = Image.open(file.stream).convert('RGB')

                # ছবি বড় হলে মেমোরি বাঁচানোর জন্য রিসাইজ করা
        img.thumbnail((1024, 1024))

        orig_name = uuid.uuid4().hex + '_orig.jpg'
        orig_path = os.path.join(UPLOAD_FOLDER, orig_name)
        img.save(orig_path, 'JPEG', quality=92, optimize=True)

        enhanced = ai_skin_retouch(img)

        enh_name = uuid.uuid4().hex + '_enh.jpg'
        enh_path = os.path.join(UPLOAD_FOLDER, enh_name)
        enhanced.save(enh_path, 'JPEG', quality=95, optimize=True, subsampling=0)

        return jsonify({
            'original': '/static/temp/' + orig_name,
            'enhanced': '/static/temp/' + enh_name
        })

    except MemoryError:
        return jsonify({'error': 'ছবিটি অনেক বড়'}), 500
    except Exception as e:
        return jsonify({'error': 'সমস্যা: ' + str(e)}), 500

@app.route('/reprocess', methods=['POST'])
def reprocess():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'ডেটা পাওয়া যায়নি'}), 400

        image_name = data.get('image', '')
        filter_name = data.get('filter', 'none')
        rotation = int(data.get('rotation', 0))
        bright = int(data.get('bright', 100))
        contrast = int(data.get('contrast', 100))
        color = int(data.get('color', 100))

        safe_filename = secure_filename(os.path.basename(image_name))
        image_path = os.path.join(UPLOAD_FOLDER, safe_filename)

        if not os.path.exists(image_path):
            return jsonify({'error': 'ছবি খুঁজে পাওয়া যায়নি'}), 404

        img = Image.open(image_path).convert('RGB')
        img = apply_filter(img, filter_name)
        img = adjust_image(img, bright, contrast, color)

        if rotation != 0:
            img = img.rotate(-rotation, expand=True)

        new_name = uuid.uuid4().hex + '_edit.jpg'
        new_path = os.path.join(UPLOAD_FOLDER, new_name)
        img.save(new_path, 'JPEG', quality=95, optimize=True, subsampling=0)

        return jsonify({'enhanced': '/static/temp/' + new_name})

    except MemoryError:
        return jsonify({'error': 'ছবিটি অনেক বড়'}), 500
    except Exception as e:
        return jsonify({'error': 'সমস্যা: ' + str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        safe_name = secure_filename(filename)
        file_path = os.path.join(UPLOAD_FOLDER, safe_name)
        if not os.path.exists(file_path):
            return jsonify({'error': 'ফাইল পাওয়া যায়নি'}), 404

        return send_from_directory(
            os.path.abspath(UPLOAD_FOLDER),
            safe_name,
            as_attachment=True,
            download_name='enhanced_hd.jpg'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
