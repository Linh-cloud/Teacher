from flask import Flask, render_template, request, session, flash, redirect, url_for
import pandas as pd
import os, json, uuid
from werkzeug.utils import secure_filename
from collections import defaultdict

# ================== CONFIG ==================

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8 MB
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'Ego')  # ĐỔI khi deploy!

ALLOWED_EXTENSIONS = {'.xlsx'}
DEFAULT_CLASS_LABELS = ['9A', '9B', '9C', '8A', '8B', '8C', '7A', '7B', '7C', '6A', '6B', '6C', '6D']
DEFAULT_CONSTRAINTS = {
    'min_period': 2,
    'max_period_teacher': 5,
    'no_xe_le': False,
}

# ================== UTILITIES ==================

def allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS

def parse_zoom(raw):
    try:
        z = float(raw)
    except Exception:
        z = 1.0
    return max(0.3, min(z, 2.0))

def normalize_headers(h):
    """Đảm bảo headers là list[str] an toàn."""
    if not isinstance(h, (list, tuple)):
        return []
    out = []
    for x in h:
        try:
            out.append(str(x))
        except Exception:
            out.append("")
    return out

def reset_tkb_session_with_notice():
    """Xóa dữ liệu TKB cũ trong session và báo người dùng."""
    session.pop('headers', None)
    session.pop('tkb_data', None)
    session.pop('num_classes', None)
    session.pop('class_labels', None)
    flash("Dữ liệu phiên cũ không tương thích. Vui lòng tải lại tệp TKB.", "warning")

# ================== XỬ LÝ FILE VÀ TKB ==================

def process_tkb_file(filepath):
    """
    Đọc file TKB an toàn:
    - engine='openpyxl', dtype=str, fillna('') tránh NaN/mixed dtype
    - Kiểm tra cấu trúc tối thiểu (mỗi lớp 2 cột: Môn, GV)
    - Tránh IndexError khi thiếu cột GV
    """
    df = pd.read_excel(filepath, sheet_name=0, header=None, engine='openpyxl', dtype=str)
    df = df.fillna('')

    # Cột 0 (Thứ) đôi khi trống ở vài dòng → ffill nếu tồn tại
    if 0 in df.columns:
        df[0] = df[0].ffill()

    # Lấy nhãn lớp ở hàng 0: các cột 2,4,6,... (mỗi lớp chiếm 2 cột: Môn, GV)
    class_labels = []
    for i in range(2, df.shape[1], 2):
        label = (df.iloc[0, i] or '').strip()
        if label:
            class_labels.append(label)

    num_classes = len(class_labels)
    if num_classes == 0:
        raise ValueError(
            "Không tìm thấy nhãn lớp ở hàng tiêu đề (hàng 1). "
            "Hãy đặt tên lớp tại các cột 3,5,7,... (mỗi lớp 2 cột: Môn, GV)."
        )

    # Cần tối thiểu: 2 cột (Thứ, Tiết) + 2*num_classes cột cho các lớp
    min_cols = 2 + num_classes * 2
    if df.shape[1] < min_cols:
        raise ValueError(
            f"File thiếu cột cho đủ {num_classes} lớp. "
            f"Cần tối thiểu {min_cols} cột (2 cột Thứ/Tiết + 2 cột mỗi lớp)."
        )

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
    """
    Kiểm tra trùng GV cùng tiết theo hàng.
    Phòng thủ kiểu dữ liệu header; chỉ xét header chuỗi kết thúc bằng " - GV".
    """
    headers = normalize_headers(headers)

    vi_pham = []
    dup_cells = set()

    # Chỉ số cột GV: các header kết thúc bằng " - GV"
    gv_cols = [idx for idx, h in enumerate(headers) if isinstance(h, str) and h.endswith(" - GV")]

    for row_idx, row in enumerate(tkb_data or []):
        seen = defaultdict(list)  # gv -> list[col_index]
        for col in gv_cols:
            if col < len(row):
                gv = (row[col] or '').strip()
                if gv:
                    seen[gv].append(col)
        for gv, cols in seen.items():
            if len(cols) > 1:
                dup_cells.update((row_idx, c) for c in cols)
                vi_pham.append({
                    "Giáo viên": gv,
                    "Thứ": row[0] if row else '',
                    "Tiết": row[1] if len(row) > 1 else '',
                    "Số lần trùng": len(cols),
                })
    return vi_pham, dup_cells

def generate_teacher_day_schedule(tkb_data):
    """
    Trả về dict: weekday -> list unique teachers (đã sort).
    """
    schedule = defaultdict(set)
    for row in tkb_data:
        if not row:
            continue
        weekday = row[0]
        # Pattern: [Thứ, Tiết, subj, teacher, subj, teacher, ...]
        for col in range(3, len(row), 2):  # teacher ở cột 3,5,7,...
            teacher = (row[col] or '').strip()
            if teacher:
                schedule[weekday].add(teacher)
    return {k: sorted(v) for k, v in schedule.items()}

def get_teacher_off_schedule(tkb_data, teachers_list_path="teachers_list.json"):
    """
    Nếu không có teachers_list.json hoặc rỗng → tự dò danh sách GV từ tkb_data.
    """
    existing_teachers = []
    try:
        with open(teachers_list_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            existing_teachers = list(dict.fromkeys(data.get("Giáo viên", [])))  # unique, giữ thứ tự
    except Exception:
        pass

    if not existing_teachers:
        # Fallback: quét từ tkb_data
        found = set()
        for row in tkb_data:
            for col in range(3, len(row), 2):
                t = (row[col] or '').strip()
                if t:
                    found.add(t)
        existing_teachers = sorted(found)

    teacher_day_schedule = generate_teacher_day_schedule(tkb_data)
    weekdays = list(teacher_day_schedule.keys())

    teacher_off_schedule = {}
    for teacher in existing_teachers:
        days_off = [d for d in weekdays if teacher not in teacher_day_schedule.get(d, [])]
        teacher_off_schedule[teacher] = days_off

    return teacher_off_schedule, weekdays

# ================== ROUTES ==================

@app.route('/')
@app.route('/tkb', methods=['GET', 'POST'])
def tkb():
    # Lấy zoom trước
    zoom = parse_zoom(request.form.get('zoom_manual') or request.form.get('zoom') or session.get('zoom', 1))

    # Lấy cấu hình / ràng buộc
    rang_buoc_cfg = session.get('rang_buoc', DEFAULT_CONSTRAINTS.copy())
    class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)

    headers = []
    tkb_data = []
    num_classes = 0
    vi_pham = []
    dup_cells = set()

    if request.method == 'POST':
        file = request.files.get('tkb_file')
        action = request.form.get('action')

        # Upload file mới
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Chỉ chấp nhận tệp .xlsx. Vui lòng chọn đúng định dạng.", "warning")
                return redirect(url_for('tkb'))

            # Tên file an toàn + duy nhất
            _, ext = os.path.splitext(file.filename)
            safe_stem = os.path.splitext(secure_filename(file.filename))[0] or 'tkb'
            filename = f"{safe_stem}_{uuid.uuid4().hex}{ext.lower()}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                headers, tkb_data, num_classes, class_labels = process_tkb_file(filepath)
            except ValueError as ve:
                flash(str(ve), "danger")
                return redirect(url_for('tkb'))
            except Exception:
                flash("Đã xảy ra lỗi khi đọc file TKB. Hãy kiểm tra đúng cặp cột (Môn, GV) và hàng tiêu đề.", "danger")
                return redirect(url_for('tkb'))

            # Lưu trực tiếp (list/dict) thay vì pickle
            session['headers'] = normalize_headers(headers)
            session['tkb_data'] = tkb_data
            session['num_classes'] = num_classes
            session['class_labels'] = class_labels
            flash("Tải và xử lý TKB thành công.", "success")

        else:
            # Thao tác trên dữ liệu hiện có
            headers = normalize_headers(session.get('headers', []))
            tkb_data = session.get('tkb_data', [])
            num_classes = session.get('num_classes', 0)
            class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)

            # Nếu headers không phải list[str] hợp lệ → reset session
            if (not headers) or any(not isinstance(h, str) for h in headers):
                reset_tkb_session_with_notice()
                return redirect(url_for('tkb'))

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
                session['tkb_data'] = tkb_data
                flash("Lưu chỉnh sửa thành công.", "success")

        # Kiểm tra trùng GV
        vi_pham, dup_cells = check_gv_trung_tiet_v2(tkb_data, headers, class_labels)
        if vi_pham:
            flash(f"Phát hiện {len(vi_pham)} trường hợp trùng giáo viên trong cùng tiết.", "warning")

        session['zoom'] = zoom

    else:
        # GET
        headers = normalize_headers(session.get('headers', []))
        tkb_data = session.get('tkb_data', [])
        num_classes = session.get('num_classes', 0)
        class_labels = session.get('class_labels', DEFAULT_CLASS_LABELS)

        # Nếu headers không phải list[str] hợp lệ → reset session
        if headers and any(not isinstance(h, str) for h in headers):
            reset_tkb_session_with_notice()
            return redirect(url_for('tkb'))

        if headers and tkb_data:
            vi_pham, dup_cells = check_gv_trung_tiet_v2(tkb_data, headers, class_labels)

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
    list_buoi = ['Thứ 2 - Sáng', 'Thứ 2 - Chiều', 'Thứ 3 - Sáng', 'Thứ 3 - Chiều']
    list_tiet = ['Tiết 1', 'Tiết 2', 'Tiết 3', 'Tiết 4', 'Tiết 5']

    current = session.get('rang_buoc', {})
    if request.method == 'POST':
        try:
            rb = {}
            if request.form.get('rb_tiet_hop_to'):
                list_items = []
                count = int(request.form.get('tiet_hop_to_count', 0))
                for i in range(count):
                    if request.form.get(f'del_{i}'):
                        continue
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
            flash("Đã lưu ràng buộc.", "success")
            saved = True
        except Exception:
            flash("Không thể lưu ràng buộc. Vui lòng kiểm tra dữ liệu nhập.", "danger")
            saved = False
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
    tkb_data = session.get('tkb_data', [])
    teacher_off_schedule, weekdays = get_teacher_off_schedule(tkb_data)
    return render_template('teacher_off.html',
                           teacher_off_schedule=teacher_off_schedule,
                           weekdays=weekdays,
                           tab='tkb')

# ================== OPTIONAL ERROR HANDLERS ==================

@app.errorhandler(404)
def page_not_found(e):
    flash("Không tìm thấy trang yêu cầu.", "warning")
    return render_template('error.html', code=404, error=e), 404

@app.errorhandler(413)
def file_too_large(e):
    flash("Tệp tải lên quá lớn. Giới hạn hiện tại là 8 MB.", "danger")
    return redirect(url_for('tkb'))

@app.errorhandler(500)
def internal_error(e):
    flash("Đã xảy ra lỗi hệ thống (500). Vui lòng thử lại sau.", "danger")
    return render_template('error.html', code=500, error=e), 500

# ================== MAIN ==================

if __name__ == '__main__':
    # Debug chỉ nên bật khi dev
    app.run(debug=True)