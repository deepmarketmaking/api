from pyxll import xl_macro, xl_app, schedule_call
import tkinter as tk
from tkinter import ttk, messagebox
import json
import logging
from subscription_manager import SubscriptionManager
from store.store import store


def configure_data_mapping():
    """
    Open a simplified configuration UI that includes:
      - A single row for Identifier: a dropdown (Identifier Type: Figi, Cusip, Isin)
        and an entry for the Identifier Column.
      - Additional inputs for:
          - Side Column (saved as 'side')
          - Quantity Column (saved as 'quantity')
          - Label Column (saved as 'rfq_label')
          - ATS Column (saved as 'ats')
      - Save button to persist configuration.
    """
    try:
        # Get the active worksheet
        xl = xl_app()
        workbook = xl.ActiveWorkbook
        active_worksheet = workbook.ActiveSheet.Name

        # Get any existing configuration for this worksheet
        existing_config = store.get_worksheet_config_or_default()

        # Create the UI window
        root = tk.Tk()
        root.title(f"Configuration - {active_worksheet}")
        root.geometry("1200x800")

        # Define some styles for better appearance
        style = ttk.Style()
        style.configure("Big.TButton", font=("Arial", 14), padding=10)
        style.configure("Big.TLabel", font=("Arial", 14), padding=10)

        # Create a frame for the configuration inputs
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # -----------------------
        # Row 0: Identifier (dropdown and entry in one row)
        # -----------------------
        ttk.Label(frame, text="Identifier:", style="Big.TLabel").grid(
            row=0, column=0, sticky="w", pady=10)

        # Identifier Type Combobox
        identifier_type_var = tk.StringVar()
        identifier_type_options = ['Figi', 'Cusip', 'Isin']
        existing_identifier = None
        if "input_parameters" in existing_config:
            for key in ['figi', 'cusip', 'isin']:
                if key in existing_config["input_parameters"]:
                    existing_identifier = key.capitalize()
                    break
        identifier_type_var.set(
            existing_identifier if existing_identifier else 'Figi')
        combobox_identifier = ttk.Combobox(frame,
                                           textvariable=identifier_type_var,
                                           values=identifier_type_options,
                                           state='readonly',
                                           width=10,
                                           font=("Arial", 14))
        combobox_identifier.grid(row=0, column=1, pady=10, padx=(5, 5))

        # Identifier Column Entry
        identifier_column_var = tk.StringVar()
        existing_column = ""
        if "input_parameters" in existing_config:
            for key in ['figi', 'cusip', 'isin']:
                if key in existing_config["input_parameters"]:
                    existing_column = existing_config["input_parameters"][key]
                    break
        identifier_column_var.set(existing_column)
        entry_identifier_column = ttk.Entry(frame,
                                            textvariable=identifier_column_var,
                                            width=10,
                                            font=("Arial", 14))
        entry_identifier_column.grid(row=0, column=2, pady=10, padx=(5, 5))

        # Ensure the identifier column entry is always uppercase
        def make_uppercase(*args):
            value = identifier_column_var.get()
            identifier_column_var.set(value.upper())

        identifier_column_var.trace_add("write", make_uppercase)

        # -----------------------
        # Row 1: Side Column
        # -----------------------
        ttk.Label(frame, text="Side Column:", style="Big.TLabel").grid(
            row=1, column=0, sticky="w", pady=10)
        side_column_var = tk.StringVar()
        existing_side = ""
        if "input_parameters" in existing_config and "side" in existing_config["input_parameters"]:
            existing_side = existing_config["input_parameters"]["side"]
        side_column_var.set(existing_side)
        entry_side_column = ttk.Entry(frame, textvariable=side_column_var,
                                      width=10, font=("Arial", 14))
        entry_side_column.grid(row=1, column=1, pady=10, padx=(5, 5))

        # -----------------------
        # Row 2: Quantity Column
        # -----------------------
        ttk.Label(frame, text="Quantity Column:", style="Big.TLabel").grid(
            row=2, column=0, sticky="w", pady=10)
        quantity_column_var = tk.StringVar()
        existing_quantity = ""
        if "input_parameters" in existing_config and "quantity" in existing_config["input_parameters"]:
            existing_quantity = existing_config["input_parameters"]["quantity"]
        quantity_column_var.set(existing_quantity)
        entry_quantity_column = ttk.Entry(frame, textvariable=quantity_column_var,
                                          width=10, font=("Arial", 14))
        entry_quantity_column.grid(row=2, column=1, pady=10, padx=(5, 5))

        # -----------------------
        # Row 3: Label Column (rfq_label)
        # -----------------------
        ttk.Label(frame, text="Label Column:", style="Big.TLabel").grid(
            row=3, column=0, sticky="w", pady=10)
        rfq_label_var = tk.StringVar()
        existing_rfq_label = ""
        if "input_parameters" in existing_config and "rfq_label" in existing_config["input_parameters"]:
            existing_rfq_label = existing_config["input_parameters"]["rfq_label"]
        rfq_label_var.set(existing_rfq_label)
        entry_rfq_label = ttk.Entry(frame, textvariable=rfq_label_var,
                                    width=10, font=("Arial", 14))
        entry_rfq_label.grid(row=3, column=1, pady=10, padx=(5, 5))

        # -----------------------
        # Row 4: ATS Column
        # -----------------------
        ttk.Label(frame, text="ATS Column:", style="Big.TLabel").grid(
            row=4, column=0, sticky="w", pady=10)
        ats_column_var = tk.StringVar()
        existing_ats = ""
        if "input_parameters" in existing_config and "ats" in existing_config["input_parameters"]:
            existing_ats = existing_config["input_parameters"]["ats"]
        ats_column_var.set(existing_ats)
        entry_ats = ttk.Entry(frame, textvariable=ats_column_var,
                              width=10, font=("Arial", 14))
        entry_ats.grid(row=4, column=1, pady=10, padx=(5, 5))

        # Save the configuration when the Save button is pressed
        def save_mapping():
            # Get and validate the Identifier inputs
            identifier_type = identifier_type_var.get().strip().lower()
            identifier_column = identifier_column_var.get().strip().upper()

            if identifier_type not in ['figi', 'cusip', 'isin']:
                messagebox.showerror("Validation Error",
                                     f"Invalid Identifier Type selected: {identifier_type}")
                return
            if not identifier_column:
                messagebox.showerror("Validation Error",
                                     "Identifier Column cannot be empty.")
                return

            # Get the additional configuration values and convert to uppercase
            side_column = side_column_var.get().strip().upper()
            quantity_column = quantity_column_var.get().strip().upper()
            rfq_label = rfq_label_var.get().strip().upper()
            ats = ats_column_var.get().strip().upper()

            # Save all input parameters in one dictionary
            input_data = {
                identifier_type: identifier_column,
                "side": side_column,
                "quantity": quantity_column,
                "rfq_label": rfq_label,
                "ats": ats
            }
            store.worksheet_configurations[active_worksheet] = {
                "input_parameters": input_data
            }

            store.save_configurations_to_docproperty()
            logging.info(f"Configuration for '{active_worksheet}' saved: {
                         json.dumps(input_data, indent=4)}")

            # Trigger any subscription updates
            schedule_call(
                SubscriptionManager.update_active_worksheet_subscriptions)

            messagebox.showinfo("Success", "Configuration saved successfully!")
            root.destroy()

        # Save Button
        ttk.Button(root, text="Save", command=save_mapping,
                   style="Big.TButton").pack(pady=20)

        root.mainloop()

    except Exception as e:
        logging.error(f"Error in configure_data_mapping: {e}")
        messagebox.showerror("Error", f"An error occurred: {e}")


# Load configurations at startup from the custom document property.
schedule_call(store.load_configurations_from_docproperty)
