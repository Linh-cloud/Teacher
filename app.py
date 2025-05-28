from flask import Flask, render_template, request, session
import pandas as pd
import os
import pickle
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'Ego'  # Đặt chuỗi bí mật bất kỳ, KHÔNG để trống

def generate_teacher_day_schedule(tkb_data):
    teacher_day_schedule = {}
    for row_data in tkb_data:
        weekday = row_data[0]  # "Thứ"
        if weekday not in teacher_day_schedule:
            teacher_day_schedule[weekday] = []
        # Giáo viên ở cột lẻ (bắt đầu từ cột 4, 6, 8,...)
        for col_idx in range(2, len(row_data), 2):
            if col_idx + 1 < len(row_data):
                teacher = row_data[col_idx + 1]
                if teacher and teacher not in teacher_day_schedule[weekday]:
                    teacher_day_schedule[weekday].append(teacher)
    return teacher_day_schedule

def get_teacher_off_schedule(tkb_data, teachers_list_path="teachers_list.json"):
    # Đọc danh sách giáo viên từ file JSON
    try:
        with open(teachers_list_path, "r", encoding="utf-8") as f:
            existing_teachers = json.load(f)["Giáo viên"]
    except Exception:
        existing_teachers = []
    # Lấy thông tin giáo viên dạy theo từng ngày
    teacher_day_schedule = generate_teacher_day_schedule(tkb_data)
    # Khởi tạo dictionary: giáo viên -> list ngày không dạy
    teacher_off_schedule = {}
    for teacher in existing_teachers:
        days_off = []
        for weekday in teacher_day_schedule.keys():
            if teacher not in teacher_day_schedule[weekday]:
                days_off.append(weekday)
        teacher_off_schedule[teacher] = days_off
    return teacher_off_schedule, list(teacher_day_schedule.keys())

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

@app.route('/teacher-off')
def teacher_off():
    # Lấy tkb_data từ session hoặc nơi bạn lưu
    tkb_data = pickle.loads(session.get('tkb_data', pickle.dumps([])))
    teacher_off_schedule, weekdays = get_teacher_off_schedule(tkb_data)
    return render_template(
        'teacher_off.html',
        teacher_off_schedule=teacher_off_schedule,
        weekdays=weekdays
    )

@app.route('/', methods=['GET', 'POST'])
def index():
    headers = []
    tkb_data = []
    duplicate_cells = None
    num_classes = 0
    zoom = 1.0

    if request.method == 'POST':
        zoom = request.form.get('zoom_manual') or request.form.get('zoom')
        try:
            zoom = float(zoom)
        except:
            zoom = 1.0
        zoom = max(0.3, min(zoom, 2))  # Giới hạn zoom từ 0.3 đến 2.0
        file = request.files.get('tkb_file')
        action = request.form.get('action')

        if action == "zoom_in":
            zoom = min(zoom + 0.05, 2)
        elif action == "zoom_out":
            zoom = max(zoom - 0.05, 0.3)

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
