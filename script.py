import ctypes
import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import keyboard
from pynput.keyboard import Controller, Key

keyboard_controller = Controller()

# Hotkey global dibaca lewat GetAsyncKeyState (status tombol fisik), bukan hook
# library keyboard, agar tetap terbaca saat jendela game yang aktif
VK_F11 = 0x7A  # Start / Stop
VK_F12 = 0x7B  # Stop darurat
START_COUNTDOWN = 3  # Detik untuk pindah ke game setelah klik START

# Variabel global
is_running = False
macro_thread = None
sequence_list = []  # Menyimpan daftar urutan aksi
is_recording = False  # Status mode rekam tombol
editing_item = None  # Item sequence yang sedang diedit (None = mode tambah)
buff_list = []  # [{"key": "f1", "interval": 5.0 (menit), "delay": 1.0 (detik)}]
editing_buff = None  # Buff yang sedang diedit (None = mode tambah)
profiles = {}  # {nama: {"sequence": [...], "pause": "0.5", "buffs": [...]}}

# File profil disimpan di samping script (atau .exe jika di-build PyInstaller)
PROFILE_FILE = os.path.join(
    os.path.dirname(
        sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    ),
    "profiles.json",
)

# Palet warna
BG_COLOR = "#f5f6fa"
FG_TEXT = "#2f3640"
FG_MUTED = "#7f8c8d"
C_PRIMARY = "#1976d2"
C_INFO = "#0288d1"
C_WARN = "#ff9800"
C_DANGER = "#c62828"
C_SUCCESS = "#2e7d32"
C_DISABLED = "#9e9e9e"
C_NEUTRAL = "#607d8b"

# Nama tombol library keyboard yang beda dengan nama pynput Key
KEY_ALIASES = {
    "left shift": "shift_l",
    "right shift": "shift_r",
    "left ctrl": "ctrl_l",
    "right ctrl": "ctrl_r",
    "left alt": "alt_l",
    "right alt": "alt_r",
    "alt gr": "alt_gr",
    "windows": "cmd",
    "left windows": "cmd_l",
    "right windows": "cmd_r",
    "escape": "esc",
    "return": "enter",
}

HINTS = {
    "Tombol": "Contoh: a, 1, space, enter, f1  (atau klik Rekam)",
    "Delay": "Dalam detik, contoh: 0.5",
}


def press_key(val):
  key_to_press = (
      getattr(Key, val.lower())
      if hasattr(Key, val.lower()) and len(val) > 1
      else val
  )
  keyboard_controller.press(key_to_press)
  time.sleep(0.05)
  keyboard_controller.release(key_to_press)


def is_key_down(vk):
  return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def hotkey_watcher():
  # Deteksi tepi (baru ditekan) agar tahan-tombol tidak memicu berulang
  prev = {VK_F11: False, VK_F12: False}
  while True:
    for vk in prev:
      down = is_key_down(vk)
      if down and not prev[vk]:
        if vk == VK_F11:
          root.after(0, toggle_macro)
        else:
          stop_macro()
      prev[vk] = down
    time.sleep(0.03)


def run_macro(loop_pause, buffs, countdown):
  global is_running
  print("=== SCRIPT AUTO HUNT DIMULAI DARI UI ===")
  error_msg = None

  # Beri waktu pindah ke jendela game sebelum tombol pertama dikirim
  for sisa in range(countdown, 0, -1):
    if not is_running:
      break
    root.after(
        0,
        lambda n=sisa: lbl_status.config(
            text=f"● Mulai dalam {n}...  Pindah ke game sekarang!", fg=C_WARN
        ),
    )
    time.sleep(1)
  # Waktu jatuh tempo tiap buff; 0 = langsung dipakai saat START
  buff_due = [0.0] * len(buffs)

  def run_due_buffs():
    for i, buff in enumerate(buffs):
      if is_running and time.monotonic() >= buff_due[i]:
        print(f"[Buff] {buff['key']}")
        press_key(buff["key"])
        time.sleep(buff["delay"])
        buff_due[i] = time.monotonic() + buff["interval"] * 60

  def status_text(n):
    text = f"● BERJALAN — siklus ke-{n}  (F11/F12 untuk stop)"
    if buffs:
      i = min(range(len(buffs)), key=lambda j: buff_due[j])
      sisa = max(0, int(buff_due[i] - time.monotonic()))
      text += f"\nBuff berikutnya: {buffs[i]['key']} dalam {sisa // 60}:{sisa % 60:02d}"
    return text

  try:
    loop_counter = 1
    # F11/F12 ditangani hotkey_watcher dengan mengubah is_running
    while is_running:
      # Salinan list agar aman jika sequence diedit saat berjalan
      for item in list(sequence_list):
        if not is_running:
          break

        # Buff disisipkan di antara aksi agar tidak bentrok dengan sequence
        run_due_buffs()

        tipe = item["type"]
        val = item["val"]

        if tipe == "Tombol":
          press_key(val)
        elif tipe == "Delay":
          time.sleep(float(val))

      root.after(
          0,
          lambda t=status_text(loop_counter): lbl_status.config(
              text=t, fg=C_SUCCESS
          ),
      )
      loop_counter += 1
      time.sleep(loop_pause)

  except Exception as e:
    print(f"Error: {e}")
    error_msg = str(e)

  is_running = False
  root.after(0, lambda: on_macro_stopped(error_msg))


def on_macro_stopped(error_msg=None):
  btn_start.config(state=tk.NORMAL, bg=C_SUCCESS)
  btn_stop.config(state=tk.DISABLED, bg=C_DISABLED)
  if error_msg:
    lbl_status.config(text=f"● ERROR: {error_msg}", fg=C_DANGER)
  else:
    lbl_status.config(text="● BERHENTI", fg=C_DANGER)

  root.deiconify()
  root.lift()
  root.attributes("-topmost", True)
  root.after(100, lambda: root.attributes("-topmost", False))


def start_macro(countdown=START_COUNTDOWN):
  global is_running, macro_thread
  # Tunggu thread lama benar-benar selesai agar tidak ada dua makro berjalan
  if is_running or (macro_thread and macro_thread.is_alive()):
    return

  if len(sequence_list) == 0:
    messagebox.showerror(
        "Error", "Sequence masih kosong! Tambahkan minimal 1 aksi/tombol."
    )
    return

  try:
    loop_pause = float(entry_pause.get())
    if loop_pause < 0:
      raise ValueError
  except ValueError:
    messagebox.showerror(
        "Error", "Jeda antar siklus harus angka >= 0 (gunakan titik, mis. 0.5)"
    )
    return

  is_running = True
  btn_start.config(state=tk.DISABLED, bg=C_DISABLED)
  btn_stop.config(state=tk.NORMAL, bg=C_DANGER)
  lbl_status.config(text="● BERJALAN  (F11/F12 untuk stop)", fg=C_SUCCESS)

  macro_thread = threading.Thread(
      # Salinan buff: perubahan daftar buff berlaku saat START berikutnya
      target=run_macro,
      args=(loop_pause, [dict(b) for b in buff_list], countdown),
      daemon=True,
  )
  macro_thread.start()


def stop_macro():
  global is_running
  is_running = False


def toggle_macro():
  # Dari hotkey: jendela game sudah aktif, jadi tanpa hitung mundur
  if is_running:
    stop_macro()
  else:
    start_macro(countdown=0)


# --- PRESET MAKRO OTOMATIS ---
def load_preset_seal_standard():
  global sequence_list
  sequence_list.clear()
  sequence_list.append({"type": "Tombol", "val": "1"})
  sequence_list.append({"type": "Delay", "val": "0.2"})
  for _ in range(5):
    sequence_list.append({"type": "Tombol", "val": "space"})
    sequence_list.append({"type": "Delay", "val": "0.1"})
  update_listbox()
  messagebox.showinfo(
      "Preset Dimuat", "Preset 'Skill 1 + Loot Space' berhasil dimuat!"
  )


def load_preset_seal_with_tab():
  global sequence_list
  sequence_list.clear()
  sequence_list.append({"type": "Tombol", "val": "1"})
  sequence_list.append({"type": "Delay", "val": "0.2"})
  sequence_list.append({"type": "Tombol", "val": "tab"})
  sequence_list.append({"type": "Delay", "val": "0.2"})
  for _ in range(5):
    sequence_list.append({"type": "Tombol", "val": "space"})
    sequence_list.append({"type": "Delay", "val": "0.1"})
  update_listbox()
  messagebox.showinfo(
      "Preset Dimuat", "Preset 'Skill 1 + Tab + Loot' berhasil dimuat!"
  )


# --- PROFIL TERSIMPAN (profiles.json) ---
def read_profiles():
  if not os.path.exists(PROFILE_FILE):
    return {}
  try:
    with open(PROFILE_FILE, encoding="utf-8") as f:
      data = json.load(f)
    if not isinstance(data, dict):
      raise ValueError("format bukan objek JSON")
    return data
  except (OSError, ValueError) as e:
    # Pindahkan file rusak agar tidak tertimpa saat simpan berikutnya
    backup = PROFILE_FILE + ".bak"
    os.replace(PROFILE_FILE, backup)
    messagebox.showwarning(
        "Profil Rusak",
        f"profiles.json tidak bisa dibaca ({e}).\nFile dipindah ke:\n{backup}",
    )
    return {}


def write_profiles(data):
  # Tulis ke file sementara dulu agar file lama aman jika gagal di tengah
  tmp = PROFILE_FILE + ".tmp"
  with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
  os.replace(tmp, PROFILE_FILE)


def refresh_profile_combo(select=""):
  combo_profile.config(values=sorted(profiles))
  combo_profile.set(select)


def save_profile():
  global profiles
  if not sequence_list:
    messagebox.showerror("Error", "Sequence masih kosong, tidak ada yang disimpan.")
    return

  # Buff yang sudah diketik tapi belum diklik "+" tidak ikut tersimpan
  if entry_buff_key.get().strip() and messagebox.askyesno(
      "Buff Belum Ditambahkan",
      f"Buff '{entry_buff_key.get().strip()}' belum ditambahkan ke daftar.\n"
      "Tambahkan sekarang sebelum menyimpan?",
  ):
    add_buff()

  name = simpledialog.askstring(
      "Simpan Profil",
      "Nama profil:",
      initialvalue=combo_profile.get(),
      parent=root,
  )
  if not name or not name.strip():
    return
  name = name.strip()
  if name in profiles and not messagebox.askyesno(
      "Konfirmasi", f"Profil '{name}' sudah ada. Timpa?"
  ):
    return

  new_profiles = dict(profiles)
  new_profiles[name] = {
      "sequence": [dict(item) for item in sequence_list],
      "pause": entry_pause.get().strip(),
      "buffs": [dict(b) for b in buff_list],
  }
  try:
    write_profiles(new_profiles)
  except OSError as e:
    messagebox.showerror("Error", f"Gagal menyimpan profil:\n{e}")
    return
  profiles = new_profiles
  refresh_profile_combo(select=name)
  messagebox.showinfo("Profil Disimpan", f"Profil '{name}' berhasil disimpan!")


def load_profile():
  name = combo_profile.get()
  if name not in profiles:
    messagebox.showwarning("Peringatan", "Pilih profil terlebih dahulu.")
    return

  data = profiles[name]
  try:
    seq = [
        {"type": item["type"], "val": str(item["val"])}
        for item in data["sequence"]
        if item["type"] in ("Tombol", "Delay")
    ]
    pause = str(data.get("pause", "0.5"))
    # Profil lama tanpa "buffs": daftar buff yang sekarang dibiarkan
    buffs = None if "buffs" not in data else [
        {
            "key": str(b["key"]),
            "interval": float(b["interval"]),
            "delay": float(b["delay"]),
        }
        for b in data["buffs"]
    ]
  except (KeyError, TypeError, ValueError):
    messagebox.showerror("Error", f"Data profil '{name}' rusak.")
    return

  if editing_item is not None:
    cancel_edit()
  sequence_list[:] = seq
  entry_pause.delete(0, tk.END)
  entry_pause.insert(0, pause)
  update_listbox()
  if buffs is not None:
    if editing_buff is not None:
      cancel_buff_edit()
    buff_list[:] = buffs
    update_buff_listbox()


def delete_profile():
  global profiles
  name = combo_profile.get()
  if name not in profiles:
    messagebox.showwarning("Peringatan", "Pilih profil terlebih dahulu.")
    return
  if not messagebox.askyesno("Konfirmasi", f"Hapus profil '{name}'?"):
    return

  new_profiles = {k: v for k, v in profiles.items() if k != name}
  try:
    write_profiles(new_profiles)
  except OSError as e:
    messagebox.showerror("Error", f"Gagal menghapus profil:\n{e}")
    return
  profiles = new_profiles
  refresh_profile_combo()


# --- REKAM & MANIPULASI BARIS ---
def record_key_action(entry=None, btn=None):
  global is_recording
  if is_recording:
    return
  # Default: form aksi utama; form buff mengirim entry & tombolnya sendiri
  entry = entry or entry_val
  btn = btn or btn_record

  is_recording = True
  btn.config(text="Tekan tombol...", bg=C_WARN)
  root.focus_set()
  threading.Thread(target=wait_for_key, args=(entry, btn), daemon=True).start()


def wait_for_key(entry, btn):
  while True:
    event = keyboard.read_event(suppress=False)
    if event.event_type == keyboard.KEY_DOWN:
      break
  key_name = normalize_key(event.name)
  root.after(0, lambda: on_key_recorded(key_name, entry, btn))


def normalize_key(name):
  if len(name) == 1:
    return name
  name = name.lower().strip()
  return KEY_ALIASES.get(name, name.replace(" ", "_"))


def is_valid_key(name):
  return len(name) == 1 or hasattr(Key, name)


def on_key_recorded(key_name, entry, btn):
  global is_recording
  entry.delete(0, tk.END)
  entry.insert(0, key_name)
  btn.config(text="⌨ Rekam", bg=C_INFO)
  is_recording = False
  if key_name in ("f11", "f12") and entry is entry_val:
    lbl_hint.config(text=f"⚠ {key_name.upper()} dipakai sebagai hotkey makro!", fg=C_DANGER)
  elif key_name in ("f11", "f12"):
    messagebox.showwarning(
        "Peringatan", f"{key_name.upper()} dipakai sebagai hotkey makro!"
    )
  entry.focus_set()


# --- BUFF OTOMATIS ---
def add_buff(event=None):
  if is_recording:
    return
  key = normalize_key(entry_buff_key.get().strip())
  if not key or not is_valid_key(key):
    messagebox.showerror("Error", f"Tombol buff '{key}' tidak dikenal!")
    return
  try:
    interval = float(entry_buff_interval.get())
    delay = float(entry_buff_delay.get())
    if interval <= 0 or delay < 0:
      raise ValueError
  except ValueError:
    messagebox.showerror(
        "Error", "Interval harus angka > 0 (menit), jeda cast angka >= 0 (detik)."
    )
    return

  new_buff = {"key": key, "interval": interval, "delay": delay}
  # Sama seperti sequence: cari buff yang diedit lewat identitas
  idx = next((i for i, b in enumerate(buff_list) if b is editing_buff), None)
  if idx is not None:
    buff_list[idx] = new_buff
  else:
    buff_list.append(new_buff)
    idx = len(buff_list) - 1
  cancel_buff_edit()
  update_buff_listbox(select=idx)
  entry_buff_key.focus_set()


def edit_buff(event=None):
  global editing_buff
  selected = listbox_buff.curselection()
  if not selected:
    return
  editing_buff = buff_list[selected[0]]
  for entry, field in (
      (entry_buff_key, "key"),
      (entry_buff_interval, "interval"),
      (entry_buff_delay, "delay"),
  ):
    entry.delete(0, tk.END)
    value = editing_buff[field]
    entry.insert(0, value if field == "key" else f"{value:g}")
  frame_buff.config(text=f" 🛡 Edit Buff #{selected[0] + 1} ")
  btn_buff_add.config(text="💾", bg=C_WARN, activebackground=C_WARN)
  btn_buff_cancel.pack(side=tk.RIGHT)
  entry_buff_key.select_range(0, tk.END)
  entry_buff_key.focus_set()


def cancel_buff_edit(event=None):
  global editing_buff
  editing_buff = None
  frame_buff.config(text=" 🛡 Buff Otomatis (tiap N menit) ")
  btn_buff_add.config(text="+", bg=C_PRIMARY, activebackground=C_PRIMARY)
  btn_buff_cancel.pack_forget()
  entry_buff_key.delete(0, tk.END)


def remove_buff(event=None):
  list_remove(buff_list, listbox_buff, update_buff_listbox)


def copy_buff():
  list_copy(buff_list, listbox_buff, update_buff_listbox)


def move_buff(offset):
  list_move(buff_list, listbox_buff, update_buff_listbox, offset)


def update_buff_listbox(select=None):
  listbox_buff.delete(0, tk.END)
  for idx, b in enumerate(buff_list):
    listbox_buff.insert(
        tk.END,
        f"  {idx+1}.  Tekan {b['key']}  tiap {b['interval']:g} menit"
        f"  (jeda cast {b['delay']:g} dtk)",
    )
  apply_selection(listbox_buff, select)


def on_type_changed(event=None):
  tipe = combo_type.get()
  btn_record.config(state=tk.NORMAL if tipe == "Tombol" else tk.DISABLED)
  lbl_hint.config(text=HINTS[tipe], fg=FG_MUTED)
  entry_val.delete(0, tk.END)
  entry_val.focus_set()


def add_action(event=None):
  if is_recording:
    return
  tipe = combo_type.get()
  val = entry_val.get().strip()

  if not val:
    messagebox.showwarning("Peringatan", "Nilai/Tombol tidak boleh kosong!")
    return

  if tipe == "Delay":
    try:
      if float(val) < 0:
        raise ValueError
    except ValueError:
      messagebox.showerror("Error", "Nilai delay harus angka >= 0 (detik)!")
      return
  else:
    val = normalize_key(val)
    if not is_valid_key(val):
      messagebox.showerror(
          "Error",
          f"Tombol '{val}' tidak dikenal!\nGunakan tombol Rekam atau nama"
          " seperti: a, space, enter, shift_r, f1",
      )
      return

  new_item = {"type": tipe, "val": val}
  # Cari posisi item yang diedit lewat identitas, aman walau list sudah digeser
  idx = next(
      (i for i, it in enumerate(sequence_list) if it is editing_item), None
  )
  if idx is not None:
    sequence_list[idx] = new_item
    cancel_edit()
  else:
    if editing_item is not None:
      cancel_edit()  # Item yang diedit sudah dihapus, jadikan aksi baru
    sequence_list.append(new_item)
    idx = len(sequence_list) - 1
  update_listbox(select=idx)
  entry_val.delete(0, tk.END)
  lbl_hint.config(text=HINTS[tipe], fg=FG_MUTED)
  entry_val.focus_set()


def edit_action(event=None):
  global editing_item
  selected = listbox_seq.curselection()
  if not selected:
    return
  editing_item = sequence_list[selected[0]]
  combo_type.set(editing_item["type"])
  on_type_changed()
  entry_val.insert(0, editing_item["val"])
  entry_val.select_range(0, tk.END)
  frame_builder.config(text=f" 1. Edit Aksi #{selected[0] + 1} ")
  btn_add.config(text="💾 Simpan Perubahan  (Enter)", bg=C_WARN, activebackground=C_WARN)
  btn_cancel.pack(side=tk.RIGHT, padx=(4, 0))


def cancel_edit(event=None):
  global editing_item
  editing_item = None
  frame_builder.config(text=" 1. Tambah Aksi Manual ")
  btn_add.config(
      text="+ Tambahkan ke Sequence  (Enter)", bg=C_PRIMARY, activebackground=C_PRIMARY
  )
  btn_cancel.pack_forget()
  entry_val.delete(0, tk.END)


# Operasi list bersama untuk sequence & buff (mendukung banyak pilihan)
def list_remove(lst, lb, refresh):
  selected = lb.curselection()
  if selected:
    for idx in reversed(selected):
      lst.pop(idx)
    refresh(select=min(selected[0], len(lst) - 1))


def list_copy(lst, lb, refresh):
  # Salinan disisipkan sebagai satu blok setelah item terpilih terakhir
  selected = lb.curselection()
  if selected:
    insert_at = selected[-1] + 1
    lst[insert_at:insert_at] = [lst[i].copy() for i in selected]
    refresh(select=range(insert_at, insert_at + len(selected)))


def list_move(lst, lb, refresh, offset):
  selected = lb.curselection()
  if not selected:
    return
  # Berhenti jika ada item yang sudah di ujung, agar urutan blok tetap utuh
  if selected[0] + offset < 0 or selected[-1] + offset >= len(lst):
    return
  for idx in selected if offset < 0 else reversed(selected):
    lst[idx], lst[idx + offset] = lst[idx + offset], lst[idx]
  refresh(select=[i + offset for i in selected])


def apply_selection(lb, select):
  # select boleh satu index atau kumpulan index
  if select is None:
    return
  indices = [select] if isinstance(select, int) else list(select)
  indices = [i for i in indices if i >= 0]
  for i in indices:
    lb.selection_set(i)
  if indices:
    lb.see(indices[0])


def select_all(lb):
  lb.selection_set(0, tk.END)
  return "break"


def remove_action(event=None):
  list_remove(sequence_list, listbox_seq, update_listbox)


def copy_action():
  list_copy(sequence_list, listbox_seq, update_listbox)


def move_action(offset):
  list_move(sequence_list, listbox_seq, update_listbox, offset)


def clear_actions():
  if sequence_list and messagebox.askyesno(
      "Konfirmasi", "Hapus semua aksi di sequence?"
  ):
    sequence_list.clear()
    update_listbox()


def update_listbox(select=None):
  listbox_seq.delete(0, tk.END)
  for idx, item in enumerate(sequence_list):
    if item["type"] == "Tombol":
      text = f"  {idx+1}.    Tekan  {item['val']}"
    else:
      text = f"  {idx+1}.    Tunggu  {item['val']} detik"
    listbox_seq.insert(tk.END, text)
  apply_selection(listbox_seq, select)
  lbl_count.config(text=f"{len(sequence_list)} aksi")


def make_button(parent, text, bg, command, **kwargs):
  return tk.Button(
      parent,
      text=text,
      bg=bg,
      fg="white",
      activebackground=bg,
      activeforeground="white",
      disabledforeground="#eeeeee",
      font=("Segoe UI", 9, "bold"),
      relief="flat",
      cursor="hand2",
      padx=8,
      pady=3,
      command=command,
      **kwargs,
  )


# --- TAMPILAN UI ---
root = tk.Tk()
root.title("Seal Offline - Modern Macro Builder")
root.minsize(460, 700)
root.config(bg=BG_COLOR)

tk.Label(
    root,
    text="🎮 Seal Offline Macro Builder",
    font=("Segoe UI", 14, "bold"),
    bg=BG_COLOR,
    fg=FG_TEXT,
).pack(pady=(12, 0))
tk.Label(
    root,
    text="F11 = Start/Stop dari dalam game  •  F12 = Stop darurat",
    font=("Segoe UI", 9),
    bg=BG_COLOR,
    fg=FG_MUTED,
).pack(pady=(0, 6))

# Preset Cepat
frame_preset = tk.LabelFrame(
    root,
    text=" ⚡ Preset & Profil ",
    font=("Segoe UI", 10, "bold"),
    bg=BG_COLOR,
    fg=FG_TEXT,
    padx=10,
    pady=8,
)
frame_preset.pack(pady=3, padx=15, fill="x")

frame_preset_btns = tk.Frame(frame_preset, bg=BG_COLOR)
frame_preset_btns.pack(fill="x")
frame_preset_btns.columnconfigure((0, 1), weight=1)

make_button(
    frame_preset_btns,
    "📌 Preset: Skill 1 + Loot Space",
    "#673ab7",
    load_preset_seal_standard,
).grid(row=0, column=0, sticky="we", padx=(0, 3), pady=2)

make_button(
    frame_preset_btns,
    "📌 Preset: Skill 1 + Tab + Loot",
    "#3f51b5",
    load_preset_seal_with_tab,
).grid(row=0, column=1, sticky="we", padx=(3, 0), pady=2)

# Profil buatan sendiri
frame_profile = tk.Frame(frame_preset, bg=BG_COLOR)
frame_profile.pack(fill="x", pady=(6, 0))

tk.Label(
    frame_profile, text="Profil Saya:", font=("Segoe UI", 9), bg=BG_COLOR
).pack(side=tk.LEFT)
combo_profile = ttk.Combobox(frame_profile, state="readonly", width=16)
combo_profile.pack(side=tk.LEFT, fill="x", expand=True, padx=5)

make_button(frame_profile, "📂 Muat", C_PRIMARY, load_profile).pack(side=tk.LEFT)
make_button(frame_profile, "💾 Simpan", C_SUCCESS, save_profile).pack(
    side=tk.LEFT, padx=3
)
make_button(frame_profile, "🗑", C_DANGER, delete_profile).pack(side=tk.LEFT)

profiles = read_profiles()
refresh_profile_combo()

# Tambah Aksi Manual
frame_builder = tk.LabelFrame(
    root,
    text=" 1. Tambah Aksi Manual ",
    font=("Segoe UI", 10, "bold"),
    bg=BG_COLOR,
    fg=FG_TEXT,
    padx=10,
    pady=8,
)
frame_builder.pack(pady=5, padx=15, fill="x")
frame_builder.columnconfigure(1, weight=1)

tk.Label(
    frame_builder, text="Tipe Aksi:", font=("Segoe UI", 9), bg=BG_COLOR
).grid(row=0, column=0, sticky="w", pady=4)
combo_type = ttk.Combobox(
    frame_builder, values=["Tombol", "Delay"], state="readonly", width=12
)
combo_type.grid(row=0, column=1, sticky="w", pady=4, padx=5)
combo_type.set("Tombol")
combo_type.bind("<<ComboboxSelected>>", on_type_changed)

tk.Label(
    frame_builder, text="Nilai / Tombol:", font=("Segoe UI", 9), bg=BG_COLOR
).grid(row=1, column=0, sticky="w", pady=4)

frame_input_row = tk.Frame(frame_builder, bg=BG_COLOR)
frame_input_row.grid(row=1, column=1, sticky="we", pady=4, padx=5)

entry_val = tk.Entry(frame_input_row, font=("Segoe UI", 10), width=14)
entry_val.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 5), ipady=2)
entry_val.bind("<Return>", add_action)
entry_val.bind("<Escape>", cancel_edit)

btn_record = make_button(frame_input_row, "⌨ Rekam", C_INFO, record_key_action)
btn_record.pack(side=tk.LEFT)

lbl_hint = tk.Label(
    frame_builder,
    text=HINTS["Tombol"],
    font=("Segoe UI", 8),
    bg=BG_COLOR,
    fg=FG_MUTED,
)
lbl_hint.grid(row=2, column=1, sticky="w", padx=5)

frame_add_row = tk.Frame(frame_builder, bg=BG_COLOR)
frame_add_row.grid(row=3, column=0, columnspan=2, pady=(8, 0), sticky="we")

btn_add = make_button(
    frame_add_row, "+ Tambahkan ke Sequence  (Enter)", C_PRIMARY, add_action
)
btn_add.pack(side=tk.LEFT, fill="x", expand=True)

# Hanya tampil saat mode edit
btn_cancel = make_button(frame_add_row, "Batal (Esc)", C_NEUTRAL, cancel_edit)

# Urutan Makro
frame_list = tk.LabelFrame(
    root,
    text=" 2. Urutan Makro  (Ctrl/Shift + klik = pilih banyak) ",
    font=("Segoe UI", 10, "bold"),
    bg=BG_COLOR,
    fg=FG_TEXT,
    padx=10,
    pady=8,
)
frame_list.pack(pady=5, padx=15, fill="both", expand=True)

frame_listbox = tk.Frame(frame_list, bg=BG_COLOR)
frame_listbox.pack(fill="both", expand=True)

listbox_seq = tk.Listbox(
    frame_listbox,
    font=("Segoe UI", 10),
    height=7,
    bg="white",
    relief="flat",
    highlightthickness=1,
    highlightcolor=C_PRIMARY,
    selectbackground=C_PRIMARY,
    activestyle="none",
    exportselection=False,  # Seleksi tidak hilang saat teks di entry diseleksi
    selectmode=tk.EXTENDED,  # Ctrl/Shift + klik untuk pilih banyak
)
listbox_seq.pack(side=tk.LEFT, fill="both", expand=True)
listbox_seq.bind("<Delete>", remove_action)
listbox_seq.bind("<Control-a>", lambda e: select_all(listbox_seq))
listbox_seq.bind("<Double-Button-1>", edit_action)
listbox_seq.bind("<Return>", edit_action)

scrollbar = ttk.Scrollbar(
    frame_listbox, orient="vertical", command=listbox_seq.yview
)
scrollbar.pack(side=tk.RIGHT, fill="y")
listbox_seq.config(yscrollcommand=scrollbar.set)

# Tombol Kontrol List
frame_list_btn = tk.Frame(frame_list, bg=BG_COLOR)
frame_list_btn.pack(fill="x", pady=(6, 0))

make_button(frame_list_btn, "▲", C_NEUTRAL, lambda: move_action(-1)).pack(
    side=tk.LEFT
)
make_button(frame_list_btn, "▼", C_NEUTRAL, lambda: move_action(1)).pack(
    side=tk.LEFT, padx=3
)
make_button(frame_list_btn, "✏ Edit", C_WARN, edit_action).pack(
    side=tk.LEFT, padx=3
)
make_button(frame_list_btn, "📋 Salin", "#00838f", copy_action).pack(
    side=tk.LEFT, padx=3
)
make_button(frame_list_btn, "Hapus", "#e65100", remove_action).pack(
    side=tk.LEFT, padx=3
)
make_button(frame_list_btn, "Bersihkan", C_DANGER, clear_actions).pack(
    side=tk.LEFT, padx=3
)
lbl_count = tk.Label(
    frame_list_btn, text="0 aksi", font=("Segoe UI", 9), bg=BG_COLOR, fg=FG_MUTED
)
lbl_count.pack(side=tk.RIGHT)

# Buff Otomatis (di luar sequence, dipicu per interval)
frame_buff = tk.LabelFrame(
    root,
    text=" 🛡 Buff Otomatis (tiap N menit) ",
    font=("Segoe UI", 10, "bold"),
    bg=BG_COLOR,
    fg=FG_TEXT,
    padx=10,
    pady=8,
)
frame_buff.pack(pady=5, padx=15, fill="x")

frame_buff_input = tk.Frame(frame_buff, bg=BG_COLOR)
frame_buff_input.pack(fill="x")

tk.Label(frame_buff_input, text="Tombol:", font=("Segoe UI", 9), bg=BG_COLOR).pack(
    side=tk.LEFT
)
entry_buff_key = tk.Entry(frame_buff_input, font=("Segoe UI", 10), width=6)
entry_buff_key.pack(side=tk.LEFT, padx=(3, 3), ipady=2)
entry_buff_key.bind("<Return>", add_buff)
btn_buff_record = make_button(
    frame_buff_input,
    "⌨ Rekam",
    C_INFO,
    lambda: record_key_action(entry_buff_key, btn_buff_record),
)
btn_buff_record.pack(side=tk.LEFT)

tk.Label(frame_buff_input, text="Tiap", font=("Segoe UI", 9), bg=BG_COLOR).pack(
    side=tk.LEFT, padx=(8, 3)
)
entry_buff_interval = tk.Entry(
    frame_buff_input, font=("Segoe UI", 10), width=4, justify="center"
)
entry_buff_interval.insert(0, "5")
entry_buff_interval.pack(side=tk.LEFT, ipady=2)
tk.Label(frame_buff_input, text="mnt, cast", font=("Segoe UI", 9), bg=BG_COLOR).pack(
    side=tk.LEFT, padx=3
)
entry_buff_delay = tk.Entry(
    frame_buff_input, font=("Segoe UI", 10), width=4, justify="center"
)
entry_buff_delay.insert(0, "1")
entry_buff_delay.pack(side=tk.LEFT, ipady=2)
tk.Label(frame_buff_input, text="dtk", font=("Segoe UI", 9), bg=BG_COLOR).pack(
    side=tk.LEFT, padx=3
)
btn_buff_add = make_button(frame_buff_input, "+", C_PRIMARY, add_buff)
btn_buff_add.pack(side=tk.RIGHT)
for entry in (entry_buff_key, entry_buff_interval, entry_buff_delay):
  entry.bind("<Escape>", cancel_buff_edit)
entry_buff_interval.bind("<Return>", add_buff)
entry_buff_delay.bind("<Return>", add_buff)

frame_buff_list = tk.Frame(frame_buff, bg=BG_COLOR)
frame_buff_list.pack(fill="x", pady=(6, 0))

listbox_buff = tk.Listbox(
    frame_buff_list,
    font=("Segoe UI", 9),
    height=3,
    bg="white",
    relief="flat",
    highlightthickness=1,
    highlightcolor=C_PRIMARY,
    selectbackground=C_PRIMARY,
    activestyle="none",
    exportselection=False,
    selectmode=tk.EXTENDED,
)
listbox_buff.pack(fill="x")
listbox_buff.bind("<Delete>", remove_buff)
listbox_buff.bind("<Control-a>", lambda e: select_all(listbox_buff))
listbox_buff.bind("<Double-Button-1>", edit_buff)
listbox_buff.bind("<Return>", edit_buff)

# Tombol kontrol buff, sama seperti list sequence
frame_buff_btn = tk.Frame(frame_buff, bg=BG_COLOR)
frame_buff_btn.pack(fill="x", pady=(6, 0))
make_button(frame_buff_btn, "▲", C_NEUTRAL, lambda: move_buff(-1)).pack(side=tk.LEFT)
make_button(frame_buff_btn, "▼", C_NEUTRAL, lambda: move_buff(1)).pack(
    side=tk.LEFT, padx=3
)
make_button(frame_buff_btn, "✏ Edit", C_WARN, edit_buff).pack(side=tk.LEFT, padx=3)
make_button(frame_buff_btn, "📋 Salin", "#00838f", copy_buff).pack(
    side=tk.LEFT, padx=3
)
make_button(frame_buff_btn, "Hapus", "#e65100", remove_buff).pack(
    side=tk.LEFT, padx=3
)
# Hanya tampil saat mode edit buff
btn_buff_cancel = make_button(frame_buff_btn, "Batal (Esc)", C_NEUTRAL, cancel_buff_edit)

tk.Label(
    frame_buff,
    text="Buff ditekan saat START, lalu diulang tiap interval di sela sequence.",
    font=("Segoe UI", 8),
    bg=BG_COLOR,
    fg=FG_MUTED,
).pack(anchor="w", pady=(4, 0))

# Jalankan
frame_setting = tk.LabelFrame(
    root,
    text=" 3. Jalankan ",
    font=("Segoe UI", 10, "bold"),
    bg=BG_COLOR,
    fg=FG_TEXT,
    padx=10,
    pady=8,
)
frame_setting.pack(pady=5, padx=15, fill="x")

frame_pause = tk.Frame(frame_setting, bg=BG_COLOR)
frame_pause.pack(fill="x")
tk.Label(
    frame_pause,
    text="Jeda antar siklus (detik):",
    font=("Segoe UI", 9),
    bg=BG_COLOR,
).pack(side=tk.LEFT)
entry_pause = tk.Entry(frame_pause, font=("Segoe UI", 10), width=6, justify="center")
entry_pause.insert(0, "0.5")
entry_pause.pack(side=tk.RIGHT, ipady=2)

lbl_status = tk.Label(
    frame_setting,
    text="● BERHENTI",
    font=("Segoe UI", 10, "bold"),
    fg=C_DANGER,
    bg=BG_COLOR,
)
lbl_status.pack(pady=(8, 4))

frame_btn = tk.Frame(frame_setting, bg=BG_COLOR)
frame_btn.pack(fill="x")
frame_btn.columnconfigure((0, 1), weight=1)

btn_start = make_button(frame_btn, "▶ START (F11)", C_SUCCESS, start_macro)
btn_start.config(font=("Segoe UI", 10, "bold"), pady=6)
btn_start.grid(row=0, column=0, sticky="we", padx=(0, 4))

btn_stop = make_button(frame_btn, "⏹ STOP", C_DISABLED, stop_macro, state=tk.DISABLED)
btn_stop.config(font=("Segoe UI", 10, "bold"), pady=6)
btn_stop.grid(row=0, column=1, sticky="we", padx=(4, 0))

entry_val.focus_set()
threading.Thread(target=hotkey_watcher, daemon=True).start()
root.mainloop()