import logging
import tkinter as tk
from tkinter import messagebox
# Ensure this module can handle login/password
from websocket_handler import websocket_client
from subscription_manager import SubscriptionManager
from pyxll import schedule_call

# Obtain a module-specific logger
logger = logging.getLogger(__name__)

# Global WebSocketHandler instance (optional)
ws = None


class LoginDialog:
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Login to Deep MM")
        self.top.grab_set()  # Make the dialog modal

        # Center the dialog
        self.top.geometry("+%d+%d" % (parent.winfo_screenwidth() /
                          2 - 150, parent.winfo_screenheight()/2 - 100))

        # Username Label and Entry
        tk.Label(self.top, text="Username:").grid(
            row=0, column=0, padx=10, pady=10)
        self.username_entry = tk.Entry(self.top)
        self.username_entry.grid(row=0, column=1, padx=10, pady=10)

        # Password Label and Entry
        tk.Label(self.top, text="Password:").grid(
            row=1, column=0, padx=10, pady=10)
        self.password_entry = tk.Entry(self.top, show="*")
        self.password_entry.grid(row=1, column=1, padx=10, pady=10)

        # Submit Button
        submit_button = tk.Button(self.top, text="Login", command=self.submit)
        submit_button.grid(row=2, column=0, columnspan=2, pady=10)

        self.result = None

    def submit(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            messagebox.showwarning(
                "Input Error", "Please enter both username and password.")
            return

        self.result = (username, password)

        self.top.destroy()


def initiate_login():
    """
    Displays the login dialog and starts the WebSocket connection upon successful login.
    """
    # Initialize Tkinter
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    # Prompt for login credentials
    try:
        logger.info('Displaying login dialog.')
        login_dialog = LoginDialog(root)
        root.wait_window(login_dialog.top)

        if login_dialog.result:
            user_login, user_password = login_dialog.result
            logger.info(
                'Login credentials received. Attempting to connect to WebSocket.')

            # Start the WebSocket connection in a separate daemon thread
            # thread = threading.Thread(target=start_event_loop, args=(
            #     user_login, user_password), daemon=True)
            # thread.start()
            websocket_client.configure_auth_token(user_login, user_password)
            schedule_call(SubscriptionManager.init_subscriptions)
        else:
            logger.info('Login canceled by the user.')
    except Exception as e:
        logger.error(f"Error during login process: {e}")
        messagebox.showerror("Error", f"An error occurred during login: {e}")
    finally:
        root.destroy()
