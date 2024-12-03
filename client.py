import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox, filedialog
import psycopg2
import os
import threading
import time

class ChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Application")
        self.root.geometry("700x500")

        # Initialize variables
        self.active_users = ["All"]  # Start with the "All" option for broadcast
        self.username = None
        self.polling = True

        # Login frame
        self.login_frame = tk.Frame(root)
        self.login_frame.pack(fill=tk.BOTH, expand=True)

        self.username_label = tk.Label(self.login_frame, text="Username")
        self.username_label.pack(pady=5)
        self.username_entry = tk.Entry(self.login_frame)
        self.username_entry.pack(pady=5)

        self.password_label = tk.Label(self.login_frame, text="Password")
        self.password_label.pack(pady=5)
        self.password_entry = tk.Entry(self.login_frame, show="*")
        self.password_entry.pack(pady=5)

        self.login_button = tk.Button(self.login_frame, text="Login", command=self.login)
        self.login_button.pack(pady=10)

        # Main chatroom UI (hidden by default)
        self.chat_frame = tk.Frame(root)

        # Sidebar for active users
        self.sidebar = tk.Listbox(self.chat_frame, width=25)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # Chat log
        self.chat_log = scrolledtext.ScrolledText(self.chat_frame, state='disabled', width=60, height=20)
        self.chat_log.pack(pady=10, padx=10)

        # Message entry
        self.message_entry = tk.Entry(self.chat_frame, width=50)
        self.message_entry.pack(pady=5)

        # Buttons
        self.send_button = tk.Button(self.chat_frame, text="Send Message", command=self.send_message)
        self.send_button.pack(pady=5)

        self.send_file_button = tk.Button(self.chat_frame, text="Send File", command=self.send_file)
        self.send_file_button.pack(pady=5)

        # Database connection
        self.db_conn = psycopg2.connect(
            dbname="localchatroom",
            user="postgres",
            password="password",
            host="localhost"
        )
        self.db_cursor = self.db_conn.cursor()

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        # Verify credentials
        self.db_cursor.execute(
            "SELECT password FROM users WHERE username = %s", (username,)
        )
        result = self.db_cursor.fetchone()

        if result and result[0] == password:  # Compare passwords (hashed in real-world apps)
            self.username = username
            self.initialize_chatroom()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")

    def initialize_chatroom(self):
        self.login_frame.pack_forget()
        self.chat_frame.pack(fill=tk.BOTH, expand=True)

        # Load active users
        self.load_active_users()

        # Start polling for new messages
        threading.Thread(target=self.poll_temp_log, daemon=True).start()

    def load_active_users(self):
        self.db_cursor.execute("SELECT username FROM users")
        users = [row[0] for row in self.db_cursor.fetchall()]
        self.active_users = ["All"] + [user for user in users if user != self.username]

        # Update the sidebar
        self.sidebar.delete(0, tk.END)
        for user in self.active_users:
            self.sidebar.insert(tk.END, user)

    def send_message(self):
        message = self.message_entry.get()
        recipient = self.sidebar.get(tk.ACTIVE)

        if not recipient:
            messagebox.showerror("No Recipient", "Please select a recipient.")
            return

        if recipient == "All":
            # Broadcast message
            self.broadcast_message(message)
        else:
            # Private message
            self.private_message(message, recipient)

        self.message_entry.delete(0, tk.END)

    def broadcast_message(self, message):
        log_type = "message"

        # Insert into logs table
        self.db_cursor.execute(
            "INSERT INTO logs (sender, recipient, content, log_type) VALUES (%s, NULL, %s, %s)",
            (self.username, message, log_type)
        )
        self.db_conn.commit()

        # Insert into temp_log for all active users except self
        for user in self.active_users[1:]:
            self.db_cursor.execute(
                "INSERT INTO temp_log (sender, recipient, content, log_type) VALUES (%s, %s, %s, %s)",
                (self.username, user, message, log_type)
            )
        self.db_conn.commit()

        self.log_message(f"Broadcast: {message}")

    def private_message(self, message, recipient):
        log_type = "message"

        # Insert into logs table
        self.db_cursor.execute(
            "INSERT INTO logs (sender, recipient, content, log_type) VALUES (%s, %s, %s, %s)",
            (self.username, recipient, message, log_type)
        )
        self.db_conn.commit()

        # Insert into temp_log
        self.db_cursor.execute(
            "INSERT INTO temp_log (sender, recipient, content, log_type) VALUES (%s, %s, %s, %s)",
            (self.username, recipient, message, log_type)
        )
        self.db_conn.commit()

        self.log_message(f"Private to {recipient}: {message}")

    def send_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            recipient = self.sidebar.get(tk.ACTIVE)

            if not recipient:
                messagebox.showerror("No Recipient", "Please select a recipient.")
                return

            filename = os.path.basename(file_path)

            # Save the file to the recipient's directory
            recipient_dir = os.path.join("files", recipient if recipient != "All" else "broadcast")
            os.makedirs(recipient_dir, exist_ok=True)
            with open(file_path, 'rb') as src, open(os.path.join(recipient_dir, filename), 'wb') as dest:
                dest.write(src.read())

            log_type = "file"
            if recipient == "All":
                # Broadcast file
                self.broadcast_message(f"File sent: {filename}")
            else:
                # Private file
                self.private_message(f"File sent: {filename}", recipient)

    def poll_temp_log(self):
        while self.polling:
            self.db_cursor.execute(
                "SELECT id, sender, content, log_type FROM temp_log WHERE recipient = %s ORDER BY timestamp",
                (self.username,)
            )
            logs = self.db_cursor.fetchall()

            for log in logs:
                log_id, sender, content, log_type = log
                self.log_message(f"{sender}: {content}")

                # Remove from temp_log
                self.db_cursor.execute("DELETE FROM temp_log WHERE id = %s", (log_id,))
                self.db_conn.commit()

            time.sleep(1)

    def log_message(self, message):
        self.chat_log.config(state='normal')
        self.chat_log.insert(tk.END, message + '\n')
        self.chat_log.config(state='disabled')


if __name__ == "__main__":
    root = tk.Tk()
    chat_app = ChatApp(root)
    root.mainloop()
