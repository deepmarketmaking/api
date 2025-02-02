# File: main.py

from win32com.client import DispatchWithEvents
import logging
from pyxll import xl_on_open, xl_on_close, xl_macro, xl_app, schedule_call
import ui.login as login  # Import the login module
import ui.configuration_popup as configuration_popup
from subscription_manager import SubscriptionManager
from worksheet_event_handler import WorksheetEventHandler
from store.store import store

_sheet_with_events = None


# Configure logging
logging.basicConfig(
    filename='pyxll_custom.log',  # Ensure this path is correct and writable
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

logging.info('Add-in loaded successfully.')


@xl_macro
def login_macro(data):
    """
    Handler for the Login button. Delegates the login process to the login module.
    """
    login.initiate_login()


@xl_on_open
def on_excel_open(data):
    logging.info('Excel add-in opened.')
    # Removed automatic WebSocket connection to keep main.py simple


@xl_on_close
def on_excel_close():
    logging.info('Excel is closing. Performing cleanup...')
    # Delegate the cleanup to login.py
    try:
        login.close_websocket()
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")


@xl_macro
def configure_data_mapping(data):
    """
    Opens ui for data mapping configuration
    """
    logging.info('Configure Data Mapping button clicked.')
    # Implement your data mapping configuration here
    configuration_popup.configure_data_mapping()


@xl_macro
def clear_configuration(data):
    """
    Clear the configuration for the current active worksheet.
    """
    store.clear_current_active_worksheet_config()


def subscribe_to_events():
    global _sheet_with_events

    xl = xl_app()
    sheet = xl.ActiveSheet
    _sheet_with_events = DispatchWithEvents(sheet, WorksheetEventHandler)


# Schedule a call to 'subscribe_to_events' to be called later when it's safe.
schedule_call(subscribe_to_events)
