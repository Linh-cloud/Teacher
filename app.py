from flask import Flask, render_template, request, session
import pandas as pd
import os
import pickle
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'Ego'  # Đặt chuỗi bí mật bất kỳ, KHÔNG để trống

def process_tkb_file(filepath):
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    df[0] = df[0].ffill()
    class_labels = []
    for i in range(2, df.shape[1], 2):
        label = df.iloc[0, i]
        if pd.notna(label):
            class_labels.append(label)
    num_classes = len(class_labels)
    tkb_data = []
    for _, row in df.iloc[2:].iterrows():
        time_info = row.iloc[:2].tolist()
        class_data = []
        for i in range(2, 2 + num_classes * 2, 2):
            subject = str(row[i]) if pd.notna(row[i]) else ""
            teacher = str(row[i + 1]) if pd.notna(row[i + 1]) else ""
            class_data.extend([subject, teacher])
        tkb_data.append(time_info + class_data)
    headers = ["Thứ", "Tiết"]
    for label in class_labels:
        headers.extend([f"{label} - Môn", f"{label} - GV"])
    return headers, tkb_data, num_classes

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

@app.route('/', methods=['GET', 'POST'])
def index():
    headers = []
    tkb_data = []
    duplicate_cells = None
    num_classes = 0
    zoom = 1.0

    if request.method == 'POST':
        try:
            zoom = float(request.form.get('zoom', 1))
        except:
            zoom = 1.0
        file = request.files.get('tkb_file')
        action = request.form.get('action')

        # Nút zoom
        if action == "zoom_in":
            zoom = min(zoom + 0.1, 2)
        elif action == "zoom_out":
            zoom = max(zoom - 0.1, 0.5)

        # Nếu upload file mới
        if file and file.filename.endswith('.xlsx'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(filepath)
            headers, tkb_data, num_classes = process_tkb_file(filepath)
            session['headers'] = pickle.dumps(headers)
            session['tkb_data'] = pickle.dumps(tkb_data)
            session['num_classes'] = num_classes
        else:
            headers = pickle.loads(session.get('headers', pickle.dumps([])))
            tkb_data = pickle.loads(session.get('tkb_data', pickle.dumps([])))
            num_classes = session.get('num_classes', 0)

            # Xử lý khi Lưu chỉnh sửa
            if action == 'save_edit':
                new_data = []
                for row_idx, row in enumerate(tkb_data):
                    new_row = []
                    for col_idx, cell in enumerate(row):
                        field_name = f"cell_{row_idx}_{col_idx}"
                        new_value = request.form.get(field_name, cell)
                        new_row.append(new_value)
                    new_data.append(new_row)
                tkb_data = new_data
                session['tkb_data'] = pickle.dumps(tkb_data)

        # Kiểm tra trùng giáo viên
        if action == 'check_duplicates':
            duplicate_cells = check_duplicates(tkb_data, num_classes)

        # Lưu lại zoom vào session
        session['zoom'] = zoom

    else:
        zoom = session.get('zoom', 1)
        if 'headers' in session and 'tkb_data' in session:
            headers = pickle.loads(session['headers'])
            tkb_data = pickle.loads(session['tkb_data'])
            num_classes = session.get('num_classes', 0)
    return render_template(
        'index.html',
        headers=headers,
        tkb_data=tkb_data,
        duplicate_cells=duplicate_cells,
        zip=zip,
        enumerate=enumerate,
        zoom=zoom
    )

if __name__ == '__main__':
    app.run(debug=True)
