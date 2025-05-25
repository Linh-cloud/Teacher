from flask import Flask, render_template, request
import pandas as pd
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

@app.route('/', methods=['GET', 'POST'])
def index():
    table_html = None
    if request.method == 'POST':
        file = request.files.get('tkb_file')
        if file and file.filename.endswith('.xlsx'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(filepath)
            # Đọc file Excel
            df = pd.read_excel(filepath, sheet_name=0, header=None)
            # Đổi NaN thành rỗng cho đẹp
            df = df.fillna('')
            # Chuyển DataFrame sang bảng HTML
            table_html = df.to_html(classes='table table-bordered', index=False, header=False)
    return render_template('index.html', table_html=table_html)

if __name__ == '__main__':
    app.run(debug=True)
