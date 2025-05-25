from flask import Flask, render_template, request
import pandas as pd
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

def process_tkb_file(filepath):
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    df[0] = df[0].ffill()  # Điền đầy cột "Thứ"
    # Tìm class_labels (tên lớp)
    class_labels = []
    for i in range(2, df.shape[1], 2):
        label = df.iloc[0, i]
        if pd.notna(label):
            class_labels.append(label)
    num_classes = len(class_labels)

    # Tách dữ liệu từ dòng 3 trở đi
    tkb_data = []
    for _, row in df.iloc[2:].iterrows():
        time_info = row.iloc[:2].tolist()
        class_data = []
        for i in range(2, 2 + num_classes * 2, 2):
            subject = str(row[i]) if pd.notna(row[i]) else ""
            teacher = str(row[i + 1]) if pd.notna(row[i + 1]) else ""
            class_data.extend([subject, teacher])
        tkb_data.append(time_info + class_data)
    # Chuẩn bị header cho bảng
    headers = ["Thứ", "Tiết"]
    for label in class_labels:
        headers.extend([f"{label} - Môn", f"{label} - GV"])
    return headers, tkb_data

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
            # Sử dụng hàm xử lý TKB mới
            headers, tkb_data = process_tkb_file(filepath)
            # Hiển thị lên HTML table
            table_html = render_template('table.html', headers=headers, tkb_data=tkb_data)
    return render_template(
        'table.html',
        headers=headers,
        tkb_data=tkb_data,
        duplicate_cells=duplicate_cells,
        zip=zip  # truyền zip vào template!
    )

def check_duplicates(tkb_data, num_classes):
    duplicate_cells = []
    for row in tkb_data:
        seen = {}
        dups = []
        for i in range(2, 2 + num_classes * 2, 2):
            teacher = row[i + 1]
            if teacher and teacher in seen:
                dups.append(i + 1)
                dups.append(seen[teacher])
            else:
                seen[teacher] = i + 1
        duplicate_cells.append(list(set(dups)))
    return duplicate_cells
