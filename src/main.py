import customtkinter as ctk
from datetime import datetime
from pynput import keyboard
import json
import os
from functools import partial
from tkinter import filedialog
from fpdf import FPDF

CONFIG_FILE = "config/hotkeys.json"
HIGHLIGHT_CONFIG_FILE = "config/highlighting.json"
EVENTS_CONFIG_FILE = "config/events.json"
DROPDOWN_CONFIG_FILE = "config/dropdown_messages.json"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Logging Application")
        self.geometry("800x600")

        # Set up closing protocol
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Load configurations
        self.events_config = self.load_events_config()
        self.dropdown_messages_config = self.load_dropdown_messages_config()
        self.highlight_rules = []

        # Create the textbox
        self.textbox = ctk.CTkTextbox(self, wrap="word")
        self.textbox.pack(expand=True, fill="both", padx=5, pady=5)
        self.textbox.configure(state="disabled")

        # Configure highlighting now that the textbox exists
        self.configure_highlighting()

        # Create the quick-log frame
        self.quick_log_frame = ctk.CTkFrame(self)
        self.quick_log_frame.pack(fill="x", padx=5, pady=(0, 5))

        self.caller_entry = ctk.CTkEntry(self.quick_log_frame, placeholder_text="Caller Text")
        self.caller_entry.pack(side="left", padx=(5,0), pady=5, fill="x", expand=True)

        self.car_report_entry = ctk.CTkEntry(self.quick_log_frame, placeholder_text="Car/Report Number")
        self.car_report_entry.pack(side="left", padx=5, pady=5, fill="x", expand=True)

        dropdown_messages = self.dropdown_messages_config.get("messages", ["No messages configured"])
        self.quick_message_var = ctk.StringVar(value=dropdown_messages[0])
        self.quick_message_menu = ctk.CTkOptionMenu(self.quick_log_frame, values=dropdown_messages, variable=self.quick_message_var)
        self.quick_message_menu.pack(side="left", padx=5, pady=5)

        self.log_quick_message_button = ctk.CTkButton(self.quick_log_frame, text="Log", command=self.log_from_quick_log_bar)
        self.log_quick_message_button.pack(side="left", padx=(0,5), pady=5)

        # Create the main button frame
        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.pack(fill="x", padx=5, pady=5)

        # Create event selection dropdown
        event_names = ["Blank Log"] + [event["name"] for event in self.events_config.get("events", [])]
        self.event_menu_var = ctk.StringVar(value=event_names[0])
        self.event_menu = ctk.CTkOptionMenu(self.button_frame, values=event_names, variable=self.event_menu_var)
        self.event_menu.pack(side="left", padx=5, pady=5)

        # Create the buttons
        self.new_log_button = ctk.CTkButton(self.button_frame, text="New Log", command=self.new_log)
        self.new_log_button.pack(side="left", padx=5, pady=5)

        self.save_button = ctk.CTkButton(self.button_frame, text="Save Log", command=self.save_log)
        self.save_button.pack(side="left", padx=5, pady=5)

        self.export_button = ctk.CTkButton(self.button_frame, text="Export to PDF", command=self.export_to_pdf)
        self.export_button.pack(side="left", padx=5, pady=5)

        self.settings_button = ctk.CTkButton(self.button_frame, text="Settings")
        self.settings_button.pack(side="right", padx=5, pady=5)

        # Setup hotkeys
        self.setup_hotkeys()
        self.log_message("Application started.")

    def log_message(self, message):
        self.textbox.configure(state="normal")
        start_index = self.textbox.index("end-1c")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{timestamp}] {message}\n"
        self.textbox.insert("end", full_message)
        end_index = self.textbox.index("end-1c")
        self.apply_highlighting(start_index, end_index)
        self.textbox.configure(state="disabled")

    def new_log(self):
        selected_event_name = self.event_menu_var.get()

        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

        if selected_event_name == "Blank Log":
            self.log_message("New blank log created.")
            return

        event_data = next((event for event in self.events_config["events"] if event["name"] == selected_event_name), None)
        if not event_data:
            self.log_message(f"Could not find template for {selected_event_name}")
            return

        self.log_message(f"New log created from template: {selected_event_name}")
        for template_line in event_data.get("template", []):
            if "[PROMPT]" in template_line:
                prompt_text = template_line.replace("[PROMPT]", "").strip()
                dialog = ctk.CTkInputDialog(text=prompt_text, title="Template Input")
                user_input = dialog.get_input()
                if user_input is not None and user_input.strip() != "":
                    self.log_message(f"{prompt_text} {user_input}")
            else:
                self.log_message(template_line)

    def log_from_quick_log_bar(self):
        """ Logs a message using the quick log bar controls. """
        caller = self.caller_entry.get().strip()
        car_report = self.car_report_entry.get().strip()
        message = self.quick_message_var.get()

        # Handle the case where the dropdown might be empty or unconfigured
        if message == "No messages configured":
            self.log_message("Cannot log: No messages configured for dropdown.")
            return

        # Construct the string with all separators to match the user's format.
        # The log_message function adds the timestamp, so we prepend " -- ".
        log_string = f"-- {caller} -- {car_report} -- {message}"
        self.log_message(log_string)

        # Clear the entry boxes after logging
        self.caller_entry.delete(0, "end")
        self.car_report_entry.delete(0, "end")

    def save_log(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.textbox.get("1.0", "end-1c"))
            self.log_message(f"Log successfully saved to {filepath}")
        except Exception as e:
            self.log_message(f"Error saving log: {e}")

    def on_closing(self):
        if hasattr(self, 'hotkey_listener'):
            self.hotkey_listener.stop()
        self.destroy()

    def hotkey_action(self, message, type):
        self.after(0, self.process_hotkey_action, message, type)

    def process_hotkey_action(self, message, type):
        if type == "prompt":
            dialog = ctk.CTkInputDialog(text=message, title="User Input Required")
            user_input = dialog.get_input()
            if user_input is not None and user_input.strip() != "":
                self.log_message(f"{message} {user_input}")
        else:
            self.log_message(message)

    def load_config(self, filepath, default_content):
        if not os.path.exists(filepath):
            self.log_message(f"Config file not found. Creating default at {filepath}")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(default_content, f, indent=2)
            return default_content
        with open(filepath, "r") as f:
            return json.load(f)

    def load_hotkeys_config(self):
        return self.load_config(CONFIG_FILE, {"hotkeys": []})

    def load_highlighting_config(self):
        return self.load_config(HIGHLIGHT_CONFIG_FILE, {"rules": []})

    def load_events_config(self):
        return self.load_config(EVENTS_CONFIG_FILE, {"events": []})

    def load_dropdown_messages_config(self):
        return self.load_config(DROPDOWN_CONFIG_FILE, {"messages": []})

    def setup_hotkeys(self):
        config = self.load_hotkeys_config()
        hotkeys = {}
        for item in config.get("hotkeys", []):
            key = item.get("key")
            message = item.get("message")
            type = item.get("type", "static")
            if key and message:
                callback = partial(self.hotkey_action, message=message, type=type)
                hotkeys[key] = callback
        if not hotkeys:
            self.log_message("No valid hotkeys found in configuration.")
            return
        try:
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
        except ValueError as e:
            error_msg = (f"Invalid hotkey syntax for '{e}' in config/hotkeys.json. "
                         "Special keys must be in angle brackets, e.g., '<f1>'.")
            self.log_message(f"Hotkey Error: {error_msg}")
        except Exception as e:
            self.log_message(f"An unexpected error occurred setting up hotkeys: {e}")

    def configure_highlighting(self):
        config = self.load_highlighting_config()
        self.highlight_rules = config.get("rules", [])
        for i, rule in enumerate(self.highlight_rules):
            tag_name = f"highlight_{i}"
            font_parts = ["Helvetica", 10]
            if rule.get("font_style"):
                font_parts.append(rule.get("font_style"))
            self.textbox.tag_config(
                tag_name,
                foreground=rule.get("foreground", "white"),
                font=tuple(font_parts)
            )
            rule["tag_name"] = tag_name

    def apply_highlighting(self, start_index, end_index):
        content = self.textbox.get(start_index, end_index)
        for rule in self.highlight_rules:
            text_to_find = rule.get("text")
            if not text_to_find:
                continue
            start = 0
            while True:
                match_start = content.find(text_to_find, start)
                if match_start == -1:
                    break
                tag_start_index = self.textbox.index(f"{start_index}+{match_start}c")
                tag_end_index = self.textbox.index(f"{tag_start_index}+{len(text_to_find)}c")
                self.textbox.tag_add(rule["tag_name"], tag_start_index, tag_end_index)
                start = match_start + len(text_to_find)

    def export_to_pdf(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf"), ("All Files", "*.*")]
        )
        if not filepath:
            return
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        tag_styles = {rule["tag_name"]: rule for rule in self.highlight_rules}
        content = self.textbox.dump("1.0", "end-1c", tag=True)
        for key, value, index in content:
            if key == "text":
                decoded_text = value.encode('latin-1', 'replace').decode('latin-1')
                pdf.write(5, decoded_text)
            elif key == "tagon":
                style = tag_styles.get(value)
                if style:
                    color_hex = style.get("foreground", "#000000").lstrip('#')
                    r, g, b = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
                    pdf.set_text_color(r, g, b)
                    font_style = style.get("font_style", "").upper()
                    pdf.set_font("Helvetica", style=font_style, size=10)
            elif key == "tagoff":
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", style="", size=10)
        try:
            pdf.output(filepath)
            self.log_message(f"Successfully exported log to {filepath}")
        except Exception as e:
            self.log_message(f"Error exporting to PDF: {e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
