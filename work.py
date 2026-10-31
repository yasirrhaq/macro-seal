import threading
import time
import tkinter as tk
from tkinter import messagebox
import keyboard
from pynput.keyboard import Controller, Key

keyboard_controller = Controller()

# Variabel status jalannya makro
is_running = False
macro_thread = None


def run_macro(skill_key, loot_count, delay_val, loop_pause):
  global is_running
  print("=== SCRIPT AUTO HUNT DIMULAI DARI UI ===")

  try:
    loop_counter = 1
    while is_running:
      # Cek tombol ESC darurat di keyboard
      if keyboard.is_pressed("esc"):
        print("\n[!] Dihentikan via tombol ESC.")
        break

      # 1. Tekan tombol skill pilihan
      keyboard_controller.press(skill_key)
      time.sleep(0.05)
      keyboard_controller.release(skill_key)
      time.sleep(delay_val)

      # 2. Ambil item (Spasi beruntun sesuai input UI)
      for _ in range(loot_count):
        if not is_running or keyboard.is_pressed("esc"):
          break
        keyboard_controller.press(Key.space)
        time.sleep(0.05)
        keyboard_controller.release(Key.space)
        time.sleep(0.1)

      loop_counter += 1
      time.sleep(loop_pause)
  except Exception as e:
    print(f"Error: {e}")

  is_running = False
  btn_start.config(state=tk.NORMAL, bg="#4CAF50")
  btn_stop.config(state=tk.DISABLED, bg="#cccccc")
  lbl_status.config(text="Status: BERHENTI", fg="red")


def start_macro():
  global is_running, macro_thread
  if is_running:
    return

  # Ambil nilai dari input UI
  skill_key = entry_skill.get().strip()
  if not skill_key:
    messagebox.showerror(
        "Error", "Tombol Skill tidak boleh kosong! (Contoh: 1, 2, f1)"
    )
    return

  try:
    loot_count = int(entry_loot.get())
    delay_val = float(entry_delay.get())
    loop_pause = float(entry_pause.get())
  except ValueError:
    messagebox.showerror(
        "Error",
        "Jumlah loot, delay, dan jeda loop harus berupa angka (Gunakan titik . untuk"
        " desimal)!",
    )
    return

  is_running = True
  btn_start.config(state=tk.DISABLED, bg="#cccccc")
  btn_stop.config(state=tk.NORMAL, bg="#f44336")
  lbl_status.config(text="Status: BERJALAN (Tekan ESC untuk Stop)", fg="green")

  # Jalankan makro di background thread agar UI tidak 'Not Responding'
  macro_thread = threading.Thread(
      target=run_macro,
      args=(skill_key, loot_count, delay_val, loop_pause),
      daemon=True,
  )
  macro_thread.start()


def stop_macro():
  global is_running
  is_running = False


# --- MEMBUAT TAMPILAN WINDOWS (UI) ---
root = tk.Tk()
root.title("Seal Offline - Macro Controller")
root.geometry("340x420")
root.resizable(False, False)

# Judul
lbl_title = tk.Label(
    root, text="Auto Hunt Controller", font=("Arial", 14, "bold")
)
lbl_title.pack(pady=10)

# Frame Form Input
frame_form = tk.Frame(root)
frame_form.pack(pady=5, padx=20, anchor="w")

# 1. Input Tombol Skill
tk.Label(
    frame_form, text="Tombol Skill Utama (misal: 1):", font=("Arial", 10)
).pack(anchor="w")
entry_skill = tk.Entry(frame_form, font=("Arial", 11), width=25)
entry_skill.insert(0, "1")
entry_skill.pack(pady=(0, 10))

# 2. Input Jumlah Spasi (Loot)
tk.Label(
    frame_form, text="Jumlah Tekan Spasi (Multi-Loot):", font=("Arial", 10)
).pack(anchor="w")
entry_loot = tk.Entry(frame_form, font=("Arial", 11), width=25)
entry_loot.insert(0, "5")
entry_loot.pack(pady=(0, 10))

# 3. Input Delay Skill
tk.Label(
    frame_form, text="Delay Antar Aksi (detik):", font=("Arial", 10)
).pack(anchor="w")
entry_delay = tk.Entry(frame_form, font=("Arial", 11), width=25)
entry_delay.insert(0, "0.2")
entry_delay.pack(pady=(0, 10))

# 4. Input Jeda Siklus Besar
tk.Label(
    frame_form, text="Jeda Antar Siklus (detik):", font=("Arial", 10)
).pack(anchor="w")
entry_pause = tk.Entry(frame_form, font=("Arial", 11), width=25)
entry_pause.insert(0, "0.5")
entry_pause.pack(pady=(0, 10))

# Label Status
lbl_status = tk.Label(
    root, text="Status: BERHENTI", font=("Arial", 10, "bold"), fg="red"
)
lbl_status.pack(pady=5)

# Frame Tombol Start / Stop
frame_btn = tk.Frame(root)
frame_btn.pack(pady=10)

btn_start = tk.Button(
    frame_btn,
    text="START",
    font=("Arial", 10, "bold"),
    bg="#4CAF50",
    fg="white",
    width=10,
    command=start_macro,
)
btn_start.pack(side=tk.LEFT, padx=5)

btn_stop = tk.Button(
    frame_btn,
    text="STOP",
    font=("Arial", 10, "bold"),
    bg="#cccccc",
    fg="white",
    width=10,
    state=tk.DISABLED,
    command=stop_macro,
)
btn_stop.pack(side=tk.LEFT, padx=5)

# Menjalankan aplikasi GUI
root.mainloop()