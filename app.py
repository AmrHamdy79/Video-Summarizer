from flask import Flask, render_template, request, send_file, jsonify
import os
from werkzeug.utils import secure_filename
import threading
from video_processor import VideoProcessor

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'temp'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

os.makedirs('temp', exist_ok=True)
os.makedirs('static', exist_ok=True)

processor = VideoProcessor()
processing_status = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    video_url = request.form.get('video_url')
    
    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    task_id = str(hash(video_url + str(threading.get_ident())))
    processing_status[task_id] = {'status': 'processing', 'progress': 0}
    
    def process():
        try:
            processing_status[task_id]['progress'] = 10
            pdf_path = processor.process_video(video_url, task_id, processing_status)
            processing_status[task_id] = {'status': 'completed', 'progress': 100, 'pdf_path': pdf_path}
        except Exception as e:
            processing_status[task_id] = {'status': 'error', 'progress': 0, 'error': str(e)}
    
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/status/<task_id>')
def get_status(task_id):
    status = processing_status.get(task_id, {'status': 'unknown'})
    return jsonify(status)

@app.route('/download/<task_id>')
def download_pdf(task_id):
    status = processing_status.get(task_id, {})
    if status.get('status') == 'completed':
        pdf_path = status.get('pdf_path')
        return send_file(pdf_path, as_attachment=True, download_name='video_summary.pdf')
    return jsonify({'error': 'PDF not ready'}), 404

if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=5000)