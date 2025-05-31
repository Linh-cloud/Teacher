from flask import Flask, render_template, request, session
import pandas as pd
import os
import pickle
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'Ego'

DEFAULT_CLASS_LABELS = ['9A', '9B', '9C', '8A', '8B', '8C', '7A', '7B', '7C', '6A', '6B', '6C', '6D']

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
    return headers, tkb_data, num_classes, class_labels

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

# Hàm kiểm tra trùng giáo viên, trả về danh sách vi phạm và cell bị trùng
def check_gv_trung_tiet_v2(tkb_data, headers, class_labels):
    vi_pham = []
    dup_cells = set()
    gv_cols = []
    for idx, h in enumerate(headers):
        for label in class_labels:
            if h == f"{label} - GV":
                gv_cols.append((label, idx))
    for row_idx, row in enumerate(tkb_data):
        gvs = {}
        for label, col in gv_cols:
            gv = row[col].strip() if col < len(row) else ""
            if gv:
                gvs.setdefault(gv, []).append(col)
        for gv, cols in gvs.items():
            if len(cols) > 1:
                for col in cols:
                    dup_cells.add((row_idx, col))
                vi_pham.append({
                    "Giáo viên": gv,
                    "Thứ": row[0],
                    "Tiết": row[1],
                    "Số lần trùng": len(cols)
                })
    return vi_pham, dup_cells

# Thống kê ngày nghỉ giáo viên
def generate_teacher_day_schedule(tkb_data):
    teacher_day_schedule = {}
    for row_data in tkb_data:
        weekday = row_data[0]
        if weekday not in teacher_day_schedule:
            teacher_day_schedule[weekday] = []
        for col_idx in range(2, len(row_data), 2):
            if col_idx + 1 < len(row_data):
                teacher = row_data[col_idx + 1]
                if teacher and teacher not in teacher_day_schedule[weekday]:
                    teacher_day_schedule[weekday].append(teacher)
    return teacher_day_schedule

def get_teacher_off_schedule(tkb_data, teachers_list_path="teachers_list.json"):
    try:
        with open(teachers_list_path, "r", encoding="utf-8") as f:
            existing_teachers = json.load(f)["Giáo viên"]
    except Exception:
        existing_teachers = []
    teacher_day_schedule = generate_teacher_day_schedule(tkb_data)
    teacher_off_schedule = {}
    for teacher in existing_teachers:
        days_off = []
        for weekday in teacher_day_schedule.keys():
            if teacher not in teacher_day_schedule[weekday]:
                days_off.append(weekday)
        teacher_off_schedule[teacher] = days_off
    return teacher_off_schedule, list(teacher_day_schedule.keys())

@app.route('/teacher-off')
def teacher_off():
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
    class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)
    vi_pham = []
    dup_cells = set()

    if request.method == 'POST':
        zoom = request.form.get('zoom_manual') or request.form.get('zoom')
        try:
            zoom = float(zoom)
        except:
            zoom = 1.0
        zoom = max(0.3, min(zoom, 2))
        file = request.files.get('tkb_file')
        action = request.form.get('action')

        if file and file.filename.endswith('.xlsx'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(filepath)
            headers, tkb_data, num_classes, class_labels = process_tkb_file(filepath)
            session['headers'] = pickle.dumps(headers)
            session['tkb_data'] = pickle.dumps(tkb_data)
            session['num_classes'] = num_classes
            session['class_labels'] = class_labels
        else:
            headers = pickle.loads(session.get('headers', pickle.dumps([])))
            tkb_data = pickle.loads(session.get('tkb_data', pickle.dumps([])))
            num_classes = session.get('num_classes', 0)
            class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)

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
        vi_pham, dup_cells = check_gv_trung_tiet_v2(tkb_data, headers, class_labels)
        # Kiểm tra trùng ô GV (nếu muốn)
        if action == 'check_duplicates':
            duplicate_cells = check_duplicates(tkb_data, num_classes)

        session['zoom'] = zoom

    else:
        zoom = session.get('zoom', 1)
        if 'headers' in session and 'tkb_data' in session:
            headers = pickle.loads(session['headers'])
            tkb_data = pickle.loads(session['tkb_data'])
            num_classes = session.get('num_classes', 0)
            class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)
        # Kiểm tra trùng giáo viên mỗi lần GET nếu đã có dữ liệu
        if headers and tkb_data:
            vi_pham, dup_cells = check_gv_trung_tiet_v2(tkb_data, headers, class_labels)

    return render_template(
        'index.html',
        headers=headers,
        tkb_data=tkb_data,
        class_labels=class_labels,
        vi_pham=vi_pham,
        dup_cells=dup_cells,
        duplicate_cells=duplicate_cells,
        zip=zip,
        enumerate=enumerate,
        zoom=zoom
    )

if __name__ == '__main__':
    app.run(debug=True)
