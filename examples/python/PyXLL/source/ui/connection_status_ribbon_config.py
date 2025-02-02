import logging
from websocket_handler import websocket_client


def get_connection_status_label(control):
    """
    Callback to get the label for the connection status button.
    """
    return "Connected" if websocket_client.connected else "Disconnected"


def get_connection_status_image(control):
    """
    Callback to get the image for the connection status button.
    """
    try:
        # Use valid imageMso names
        return "HappyFace" if websocket_client.connected else "SadFace"
    except Exception as e:
        logging.info(f"Error in get_connection_status_image: {e}")
        # Return a default image to prevent Ribbon from breaking
        return "QuestionMark"

# Register the callbacks with PyXLL
# xl_func(lambda control: get_connection_status_label(
#     control), name="main.get_connection_status_label")
# xl_func(lambda control: get_connection_status_image(
#     control), name="main.get_connection_status_image")
