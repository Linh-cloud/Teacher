import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import json

class TKBApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kiểm tra thời khóa biểu")
        self.entries = []
        self.font_size = 10

        # Tạo các nút bấm cho các chức năng
        self.load_button = tk.Button(root, text="📂 Nhập file TKB", command=self.load_file)
        self.load_button.pack(pady=10)

        # Thêm các nút bấm phóng to và thu nhỏ
        self.zoom_in_btn = tk.Button(root, text="🔍+", command=self.zoom_in)
        self.zoom_in_btn.pack(pady=5)

        self.zoom_out_btn = tk.Button(root, text="🔍−", command=self.zoom_out)
        self.zoom_out_btn.pack(pady=5)


        self.check_button = tk.Button(root, text="🔍 Kiểm tra trùng giáo viên", command=self.check_duplicates, state="disabled")
        self.check_button.pack(pady=5)
        self.export_button = tk.Button(root, text="📊 Thống kê ngày nghỉ GV", command=self.check_teachers_in_schedule, state="normal")
        self.export_button.pack(pady=5)

        # Frame để hiển thị bảng thống kê
        self.frame_stat = tk.Frame(root)

        self.frame = tk.Frame(root)
        self.frame.pack(fill="both", expand=True)

    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not file_path:
            return

        try:
            df = pd.read_excel(file_path, sheet_name=0, header=None)

            # --- BỔ SUNG ĐỂ LẤP ĐẦY NA ở cột "Thứ" ---
            df[0] = df[0].ffill()
            # ------------------------------------------

            # Tìm danh sách lớp
            class_labels = []
            for i in range(2, df.shape[1], 2):
                label = df.iloc[0, i]
                if pd.notna(label):
                    class_labels.append(label)
            self.num_classes = len(class_labels)

            # Tách dữ liệu từ dòng 3 trở đi
            self.tkb_data = []
            for _, row in df.iloc[2:].iterrows():
                time_info = row.iloc[:2].tolist()
                class_data = []
                for i in range(2, 2 + self.num_classes * 2, 2):
                    subject = str(row[i]) if pd.notna(row[i]) else ""
                    teacher = str(row[i + 1]) if pd.notna(row[i + 1]) else ""
                    class_data.extend([subject, teacher])
                self.tkb_data.append(time_info + class_data)

            # Xóa bảng cũ (nếu có)
            for widget in self.frame.winfo_children():
                widget.destroy()

            self.render_table(class_labels)
            self.check_button.config(state="normal")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")

        # Gọi update_idletasks để buộc Tkinter làm mới giao diện
        self.root.update_idletasks()

    def render_table(self, class_labels):
        canvas = tk.Canvas(self.frame)
        scrollbar_y = tk.Scrollbar(self.frame, orient="vertical", command=canvas.yview)
        scrollbar_x = tk.Scrollbar(self.frame, orient="horizontal", command=canvas.xview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        # Tiêu đề "Thứ" và "Tiết"
        tk.Label(scrollable_frame, text="Thứ", bg="#d9edf7", relief="ridge", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="nsew")
        tk.Label(scrollable_frame, text="Tiết", bg="#d9edf7", relief="ridge", font=("Arial", 12, "bold")).grid(row=0, column=1, sticky="nsew")

        # Tiêu đề các ngày trong tuần
        for idx, label in enumerate(class_labels):
            tk.Label(scrollable_frame, text=label, bg="#d9edf7", relief="ridge", font=("Arial", 12, "bold")).grid(row=0, column=2 + idx * 2, columnspan=2, sticky="nsew")

        # Tiêu đề Môn | GV dạy
        tk.Label(scrollable_frame, text="", relief="ridge").grid(row=1, column=0, sticky="nsew")
        tk.Label(scrollable_frame, text="", relief="ridge").grid(row=1, column=1, sticky="nsew")
        for i in range(self.num_classes):
            tk.Label(scrollable_frame, text="Môn", bg="#f7f7f7", relief="ridge", font=("Arial", 10)).grid(row=1, column=2 + i * 2, sticky="nsew")
            tk.Label(scrollable_frame, text="GV dạy", bg="#f7f7f7", relief="ridge", font=("Arial", 10)).grid(row=1, column=3 + i * 2, sticky="nsew")

        # Dữ liệu thời khóa biểu
        self.entries = []
        for row_idx, row_data in enumerate(self.tkb_data):
            row_entries = []
            for col_idx, cell in enumerate(row_data):
                entry = tk.Text(scrollable_frame, width=12, height=1, font=("Arial", self.font_size))
                entry.insert("1.0", cell)
                entry.grid(row=row_idx + 2, column=col_idx, sticky="nsew", padx=1, pady=1)
                row_entries.append(entry)
            self.entries.append(row_entries)

    def check_duplicates(self):
        for row in self.entries:
            teacher_seen = {}
            for i, cell in enumerate(row[2:], start=2):
                if (i - 2) % 2 == 1:
                    cell.config(bg="white")
            for i, cell in enumerate(row[2:], start=2):
                if (i - 2) % 2 == 1:
                    teacher = cell.get("1.0", "end").strip()
                    if teacher:
                        if teacher in teacher_seen:
                            cell.config(bg="salmon")
                            teacher_seen[teacher].config(bg="salmon")
                        else:
                            teacher_seen[teacher] = cell

    def generate_teacher_day_schedule(self):
        teacher_day_schedule = {}

        # Lấy thông tin giáo viên dạy trong từng ngày từ thời khóa biểu
        for row_idx, row_data in enumerate(self.tkb_data):
            weekday = row_data[0]  # Lấy ngày trong tuần (Thứ 2, Thứ 3, ...)

            if weekday not in teacher_day_schedule:
                teacher_day_schedule[weekday] = []

            # Duyệt qua các cột, bắt đầu từ cột 3 để lấy thông tin giáo viên
            for col_idx in range(2, len(row_data), 2):  # Bước 2 để lấy giáo viên
                teacher = row_data[col_idx + 1]  # Giáo viên ở cột sau môn học
                if teacher and teacher not in teacher_day_schedule[weekday]:
                    teacher_day_schedule[weekday].append(teacher)

        # Trả về dictionary chứa giáo viên theo từng ngày, hoặc dictionary trống nếu không có dữ liệu
        return teacher_day_schedule if teacher_day_schedule else {}

    def check_teachers_in_schedule(self):
        # Đọc danh sách giáo viên từ tệp JSON
        try:
            with open("teachers_list.json", "r", encoding="utf-8") as f:
                existing_teachers = json.load(f)["Giáo viên"]
        except FileNotFoundError:
            existing_teachers = ["Bích", "Hải", "T.Huệ", "Linh", "Q.Anh", "Ích", "Phượng", "N.Huệ", "Nhạn", "Sỹ", "Trâm", "Xuân", "Hương", "Ninh", "Nhâm", "Vân", "Lan", "Tuân", "Nghiệp", "Ngoan", "Hường", "Ánh", "Nga", "Yến", "Thụy"]

        # Lấy thông tin giáo viên dạy trong từng ngày từ thời khóa biểu
        teacher_day_schedule = self.generate_teacher_day_schedule()

        # Kiểm tra nếu teacher_day_schedule là None hoặc rỗng
        if not teacher_day_schedule:
            print("Không có dữ liệu giáo viên trong thời khóa biểu.")
            return

        # Tạo dictionary để lưu giáo viên nghỉ (không có trong danh sách dạy)
        teacher_off_schedule = {weekday: [] for weekday in existing_teachers}

        # Duyệt qua tất cả giáo viên đã có và tìm ra giáo viên không dạy trong ngày
        for teacher in existing_teachers:
            for weekday, teachers in teacher_day_schedule.items():
                if teacher not in teachers:
                    teacher_off_schedule[teacher].append(weekday)

        # Tạo cửa sổ mới để hiển thị kết quả
        result_window = tk.Toplevel(self.root)
        result_window.title("Thông tin ngày nghỉ của giáo viên")

        # Cho phép cửa sổ thay đổi kích thước
        result_window.resizable(True, True)  # Cho phép thay đổi kích thước cửa sổ

        # Thêm Scrollbar vào cửa sổ
        canvas = tk.Canvas(result_window)
        scrollbar_y = tk.Scrollbar(result_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar_y.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar_y.pack(side="right", fill="y")
        scrollable_frame.pack(fill="both", expand=True)  # Thêm dòng này, nếu chưa có!

        # Thay đổi chiều cao của Text widget
        result_text = tk.Text(scrollable_frame, font=("Arial", 10), wrap="word")
        result_text.pack(fill="both", expand=True)

        # Kiểm tra và hiển thị thông tin
        for teacher, days_off in teacher_off_schedule.items():
            if days_off:
                days_off_str = ', '.join(str(day) for day in days_off)
                result_text.insert(tk.END, f"{teacher}: {days_off_str}\n")
            else:
                result_text.insert(tk.END, f"{teacher}: Không có ngày nghỉ\n")

        result_text.config(state=tk.DISABLED)  # Không cho phép chỉnh sửa nội dung

        # Trả về danh sách giáo viên nghỉ
        return teacher_off_schedule

    def zoom_in(self):
        self.font_size += 1  # Tăng kích thước font
        self.apply_zoom()

    def zoom_out(self):
        if self.font_size > 6:
            self.font_size -= 1  # Giảm kích thước font
        self.apply_zoom()

    def apply_zoom(self):
        for row in self.entries:
            for cell in row:
                # Cập nhật phông chữ cho từng ô trong bảng
                cell.config(font=("Arial", self.font_size))
        
        # Gọi update_idletasks để buộc Tkinter làm mới giao diện
        self.root.update_idletasks()

if __name__ == "__main__":
    root = tk.Tk()
    app = TKBApp(root)
    root.mainloop()
