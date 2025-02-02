import websockets
import json
import time
import asyncio
import logging
import threading
from utils.authentication import create_get_id_token
from ui.connection_status_ribbon import invalidate_ribbon
from typing import Callable, List
from pyxll import schedule_call


class WebSocketHandler:
    def __init__(self, url):
        self.url = url
        self.ws = None
        self.get_id_token = None
        self.connected = False
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.subscribers: List[Callable[[dict], None]] = []
        self.subscribers_lock = threading.Lock()

    def run_loop(self):
        asyncio.set_event_loop(self.loop)
        logging.debug("Event loop set for the thread.")
        try:
            self.loop.run_until_complete(self.connect())
            self.loop.run_forever()  # Keep the loop running
        except Exception as e:
            logging.error(f"Error in event loop: {e}")

    async def connect(self):
        while True:  # Retry connection if it fails
            try:
                self.ws = await websockets.connect(
                    self.url,
                    max_size=10 ** 8,
                    open_timeout=None,
                    ping_timeout=None
                )
                self.connected = True
                invalidate_ribbon()
                logging.info('WebSocket connection established.')
                # Start the send token task
                asyncio.create_task(self.send_token_periodically())
                # Start the receive loop
                asyncio.create_task(self.receive_messages())
                break  # Exit the loop after successful connection
            except Exception as e:
                self.connected = False
                invalidate_ribbon()
                logging.error(f"Failed to connect to WebSocket: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def send_token_periodically(self):
        last_sent_time = time.time()

        while True:
            await asyncio.sleep(120)  # Check every 2 minutes
            if time.time() - last_sent_time >= 55 * 60:  # 55 minutes
                if self.ws:
                    try:
                        token_message = {'token': self.get_id_token()}
                        await self.ws.send(json.dumps(token_message))
                        logging.info("Token sent to WebSocket.")
                        last_sent_time = time.time()
                    except Exception as e:
                        logging.error(f"Failed to send token: {e}")

    def send_message(self, message):
        if self.connected and self.ws and self.get_id_token:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._send(message), self.loop)
                result = future.result(timeout=10)
            except asyncio.TimeoutError:
                logging.error("Timeout in run_coroutine_threadsafe.")
            except Exception as e:
                logging.exception("Error in run_coroutine_threadsafe:")
        else:
            logging.error(
                "WebSocket connection is not established or not connected.")

    async def _send(self, message):
        try:
            token = self.get_id_token()

            if not token:
                logging.error("Token is empty.")
                return

            message['token'] = token  # send token with every request
            await self.ws.send(json.dumps(message))
            # logging.info(f"Sent message: {message}")
            self.last_sent_time = time.time()  # Reset the timer
        except Exception as e:
            logging.error(f"Failed to send message: {e}")

    def configure_auth_token(self, email, password):
        region = "us-west-2"
        client_id = "6k68k0irga6h8v6aknnta0q80u"
        # use to hardcode configuration
        # email = ""
        # password = ""

        self.get_id_token = create_get_id_token(
            region, client_id, email, password)
        logging.debug("Authentication token configured successfully.")

    async def receive_messages(self):
        try:
            async for message in self.ws:
                logging.info(f"Received message: {message}")
                data = json.loads(message)
                self.notify_subscribers(data)
        except websockets.exceptions.ConnectionClosed as e:
            self.connected = False
            invalidate_ribbon()
            logging.error(f"WebSocket connection closed: {e}")
            # Attempt to reconnect
            await self.connect()
        except Exception as e:
            self.connected = False
            invalidate_ribbon()
            logging.error(f"Error receiving message: {e}")
            await self.connect()

    def notify_subscribers(self, message: dict):
        with self.subscribers_lock:
            for callback in self.subscribers:
                try:
                    schedule_call(callback, message)
                except Exception as e:
                    logging.error(f"Error in subscriber callback: {e}")

    def subscribe(self, callback: Callable[[dict], None]):
        """
        Register a callback to be called when a new message is received.

        Parameters:
        - callback (Callable): A function that takes a dict as its parameter.
        """
        with self.subscribers_lock:
            if callback not in self.subscribers:
                self.subscribers.append(callback)
                logging.info("Subscriber added.")
            else:
                logging.warning("Subscriber already registered.")

    def unsubscribe(self, callback: Callable[[dict], None]):
        """
        Unregister a previously registered callback.

        Parameters:
        - callback (Callable): The function to remove from subscribers.
        """
        with self.subscribers_lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)
                logging.info("Subscriber removed.")
            else:
                logging.warning("Subscriber not found.")

    def close(self):
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
            logging.info("WebSocket connection closed.")
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()


# Initialize a global WebSocketHandler instance
websocket_client = WebSocketHandler("wss://staging1.deepmm.com")


def send_subscribe(subscribe_array):
    """
    Sends a subscribe message to the WebSocket server.

    Parameters:
    - subscribe_array (list): List of dictionaries to subscribe.
    """
    try:
        logging.info("before Subscribe message sent.")
        for item in subscribe_array:
            item['subscribe'] = True

        websocket_client.send_message({
            "inference": subscribe_array
        })
        logging.info("Subscribe message sent.")
    except Exception as e:
        logging.error(f"Error sending subscribe message: {e}")


def send_unsubscribe(unsubscribe_array):
    """
    Sends an unsubscribe message to the WebSocket server.

    Parameters:
    - unsubscribe_array (list): List of dictionaries to unsubscribe.
    """
    try:
        for item in unsubscribe_array:
            item['unsubscribe'] = True

        websocket_client.send_message({
            "inference": unsubscribe_array  # Corrected to send the actual array
        })
        logging.info("Unsubscribe message sent.")
    except Exception as e:
        logging.error(f"Error sending unsubscribe message: {e}")
