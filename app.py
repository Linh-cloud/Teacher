from flask import Flask, render_template, request, session, flash, redirect, url_for
import pandas as pd
import os, pickle, json
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'Ego'
DEFAULT_CLASS_LABELS = ['9A', '9B', '9C', '8A', '8B', '8C', '7A', '7B', '7C', '6A', '6B', '6C', '6D']
DEFAULT_CONSTRAINTS = {
    'min_period': 2,
    'max_period_teacher': 5,
    'no_xe_le': False
}

# ========== XỬ LÝ FILE VÀ TKB ==========

def process_tkb_file(filepath):
    """
    Đọc file TKB an toàn hơn:
    - engine='openpyxl', dtype=str, fillna('') để tránh NaN/mixed dtype
    - Kiểm tra cấu trúc tối thiểu (mỗi lớp 2 cột: Môn, GV)
    - Tránh IndexError khi thiếu cột GV
    - Trả về headers, tkb_data, num_classes, class_labels
    """
    df = pd.read_excel(filepath, sheet_name=0, header=None, engine='openpyxl', dtype=str)
    df = df.fillna('')

    # Cột 0 (Thứ) có thể bị trống ở vài dòng → ffill nếu tồn tại
    if 0 in df.columns:
        df[0] = df[0].ffill()

    # Lấy nhãn lớp ở hàng 0: các cột 2,4,6,... mỗi lớp chiếm 2 cột (Môn, GV)
    class_labels = []
    for i in range(2, df.shape[1], 2):
        label = (df.iloc[0, i] or '').strip()
        if label:
            class_labels.append(label)

    num_classes = len(class_labels)
    if num_classes == 0:
        raise ValueError("Không tìm thấy nhãn lớp ở hàng tiêu đề (hàng 1). "
                         "Hãy đặt tên lớp tại các cột 3,5,7,... (mỗi lớp 2 cột: Môn, GV).")

    # Cần tối thiểu: 2 cột (Thứ, Tiết) + 2*num_classes cột cho các lớp
    min_cols = 2 + num_classes * 2
    if df.shape[1] < min_cols:
        raise ValueError(f"File thiếu cột cho đủ {num_classes} lớp. "
                         f"Cần tối thiểu {min_cols} cột (2 cột Thứ/Tiết + 2 cột mỗi lớp).")

    tkb_data = []
    for _, row in df.iloc[2:].iterrows():  # bỏ 2 hàng đầu: tiêu đề/định dạng
        time_info = row.iloc[:2].tolist() if df.shape[1] >= 2 else ['', '']
        class_data = []
        for i in range(2, 2 + num_classes * 2, 2):
            subject = (row[i] if i < len(row) else '').strip()
            teacher = (row[i + 1] if i + 1 < len(row) else '').strip()
            class_data.extend([subject, teacher])
        tkb_data.append(time_info + class_data)

    headers = ["Thứ", "Tiết"]
    for label in class_labels:
        headers.extend([f"{label} - Môn", f"{label} - GV"])

    return headers, tkb_data, num_classes, class_labels

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

# Thêm tiện ích kiểm tra đuôi file (nếu muốn chặt chẽ hơn endswith)
ALLOWED_EXTENSIONS = {'.xlsx'}
def allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS

# ========== ROUTES ==========

@app.route('/')
@app.route('/tkb', methods=['GET', 'POST'])
def tkb():
    headers = []
    tkb_data = []
    num_classes = 0
    zoom = 1.0

    class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)
    vi_pham = []
    dup_cells = set()
    rang_buoc_cfg = session.get('rang_buoc', DEFAULT_CONSTRAINTS.copy())

    if request.method == 'POST':
        zoom = request.form.get('zoom_manual') or request.form.get('zoom')
        try:
            zoom = float(zoom)
        except Exception:
            zoom = 1.0
        zoom = max(0.3, min(zoom, 2))

        file = request.files.get('tkb_file')
        action = request.form.get('action')

        # Nếu người dùng upload file mới
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Chỉ chấp nhận tệp .xlsx. Vui lòng chọn đúng định dạng.", "warning")
                return redirect(url_for('tkb'))

            # Đặt tên an toàn + duy nhất để tránh đè file
            _, ext = os.path.splitext(file.filename)
            safe_stem = os.path.splitext(secure_filename(file.filename))[0] or 'tkb'
            filename = f"{safe_stem}_{uuid.uuid4().hex}{ext.lower()}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Đọc & xử lý: bắt lỗi rõ ràng
            try:
                headers, tkb_data, num_classes, class_labels = process_tkb_file(filepath)
            except ValueError as ve:
                flash(str(ve), "danger")
                return redirect(url_for('tkb'))
            except Exception:
                # Có thể log chi tiết: app.logger.exception("Lỗi đọc/parse Excel")
                flash("Đã xảy ra lỗi khi đọc file TKB. "
                      "Hãy kiểm tra đúng cặp cột (Môn, GV) cho từng lớp và hàng tiêu đề.", "danger")
                return redirect(url_for('tkb'))

            # Lưu vào session (giữ nguyên cách bạn đang dùng pickle)
            session['headers'] = pickle.dumps(headers)
            session['tkb_data'] = pickle.dumps(tkb_data)
            session['num_classes'] = num_classes
            session['class_labels'] = class_labels
            # flash("Tải và xử lý TKB thành công.", "success")

        else:
            # Không upload file mới → thao tác trên dữ liệu sẵn có
            headers = pickle.loads(session.get('headers', pickle.dumps([])))
            tkb_data = pickle.loads(session.get('tkb_data', pickle.dumps([])))
            num_classes = session.get('num_classes', 0)
            class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)

            if not headers or not tkb_data:
                flash("Chưa có dữ liệu TKB. Vui lòng tải tệp .xlsx.", "warning")
                return redirect(url_for('tkb'))

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
                # flash("Lưu chỉnh sửa thành công.", "success")

        # Kiểm tra trùng giáo viên ở mỗi thao tác
        vi_pham, dup_cells = check_gv_trung_tiet_v2(tkb_data, headers, class_labels)
        if vi_pham:
            # Thông báo số lượng trường hợp trùng
            # flash(f"Phát hiện {len(vi_pham)} trường hợp trùng giáo viên trong cùng tiết.", "warning")
            pass

        session['zoom'] = zoom

    else:
        # GET
        zoom = session.get('zoom', 1)
        if 'headers' in session and 'tkb_data' in session:
            try:
                headers = pickle.loads(session['headers'])
                tkb_data = pickle.loads(session['tkb_data'])
                num_classes = session.get('num_classes', 0)
                class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)
                if headers and tkb_data:
                    vi_pham, dup_cells = check_gv_trung_tiet_v2(tkb_data, headers, class_labels)
            except Exception:
                flash("Không thể tải dữ liệu TKB từ session. Vui lòng tải lại tệp.", "warning")

    return render_template(
        'tkb.html',
        headers=headers,
        tkb_data=tkb_data,
        class_labels=class_labels,
        vi_pham=vi_pham,
        dup_cells=dup_cells,
        rang_buoc=rang_buoc_cfg,
        zip=zip,
        enumerate=enumerate,
        zoom=zoom,
        tab='tkb'
    )

@app.route('/khai-bao')
def khai_bao():
    return render_template('khai_bao.html', tab='khai_bao')

@app.route('/rang-buoc', methods=['GET', 'POST'])
def rang_buoc():
    list_to_chuyen_mon = ['Toán', 'Anh', 'Văn']  # Có thể load từ DB
    list_buoi = ['Thứ 2 - Sáng', 'Thứ 2 - Chiều', 'Thứ 3 - Sáng', ...]
    list_tiet = ['Tiết 1', 'Tiết 2', 'Tiết 3', ...]
    current = session.get('rang_buoc', {})
    if request.method == 'POST':
        # Xử lý riêng cho ràng buộc 3 (và các ràng buộc khác)
        rb = {}
        if request.form.get('rb_tiet_hop_to'):
            # Duyệt lấy các dòng đang có
            list_items = []
            count = int(request.form.get('tiet_hop_to_count', 0))
            for i in range(count):
                if request.form.get(f'del_{i}'): continue  # Bỏ dòng đã chọn xóa
                row = {
                    'to_chuyen_mon': request.form.get(f'to_chuyen_mon_{i}'),
                    'buoi': request.form.get(f'buoi_hoc_{i}'),
                    'tiet': request.form.get(f'tiet_{i}'),
                }
                list_items.append(row)
            rb['enabled'] = True
            rb['list'] = list_items
        current['tiet_hop_to'] = rb
        session['rang_buoc'] = current
        saved = True
    else:
        saved = False
    return render_template(
        'rang_buoc.html',
        rang_buoc=current,
        list_to_chuyen_mon=list_to_chuyen_mon,
        list_buoi=list_buoi,
        list_tiet=list_tiet,
        saved=saved,
        tab='rang_buoc'
    )

@app.route('/teacher-off')
def teacher_off():
    tkb_data = pickle.loads(session.get('tkb_data', pickle.dumps([])))
    teacher_off_schedule, weekdays = get_teacher_off_schedule(tkb_data)
    return render_template('teacher_off.html', teacher_off_schedule=teacher_off_schedule, weekdays=weekdays, tab='tkb')

if __name__ == '__main__':
    app.run(debug=True)
