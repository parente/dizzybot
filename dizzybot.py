import json
import collections

import requests
from tornado.httpclient import AsyncHTTPClient
from tornado.websocket import websocket_connect
from tornado import ioloop

class Dizzybot(object):
    """Tornado-based Slack bot.

    Attributes
    ----------
    recent:
        Dequeue of recent events

    Parameters
    ----------
    token: str
        Slack bot token
    max_recents: int
        Number of most recent messages to store
    health_check_interval: int
        Milliseconds between checks that the websocket is still connected
    """
    def __init__(self, token, max_recent=50, health_check_interval=10000):
        self.ws = None
        self.token = token
        self.recent = collections.deque(maxlen=max_recent)
        self.http_client = AsyncHTTPClient()
        self.heartbeat = ioloop.PeriodicCallback(self._on_check_health, health_check_interval)
        self.msg_id = 0

    def __del__(self):
        self.stop()

    def log(self, evt):
        """Stores an event in the ring buffer."""
        self.recent.append(evt)

    def post_message(self, msg):
        """Posts a fully defined Slack message via the web API.

        Useful when you want to use rich formatting features that the RTM
        API does not support (ala links).
        """
        msg['as_user'] = True
        return requests.post(
            'https://slack.com/api/chat.postMessage',
            json=msg,
            headers={
              'Authorization': f'Bearer {self.token}'
        })

    def respond(self, evt, msg, thread=True, rich=False):
        """Responds to a message in the same channel.

        Parameters
        ----------
        evt: dict
            Event object of type "message" received from Slack
        msg: str or dict
            Message to send back to Slack, either a text message (str) or full
            message structure (dict) https://api.slack.com/docs/messages
        thread: bool, optional
            True to respond to a thread or start a thread on a message or False
            to respond directly in a channel or 1:1 conversation

        Returns
        -------
        int
            Unique message ID
        """
        if evt.get('type') != 'message' or evt.get('reply_to') is not None:
            return None

        msg_id = self.msg_id
        full_msg = {
            'id': msg_id,
            'type': 'message',
            'channel': evt['channel']
        }
        if isinstance(msg, dict):
            full_msg.update(msg)
        elif isinstance(msg, str):
            full_msg['text'] = msg
        else:
            raise TypeError('unsupported msg type: {}'.format(type(msg)))

        if thread:
            full_msg['thread_ts'] = evt.get('thread_ts', evt.get('ts'))

        if rich:
            self.post_message(full_msg)
        else:
            self.ws.write_message(json.dumps(full_msg))

        self.msg_id += 1
        return msg_id

    def send(self, msg, channel, rich=False):
        """Sends a message to a channel.

        Parameters
        ----------
        msg: str or dict
            Message to send to Slack, either a text message (str) or full
            message structure (dict) https://api.slack.com/docs/messages
        channel: str
            Slack channel ID

        Returns
        -------
        int
            Unique message ID
        """
        msg_id = self.msg_id
        full_msg = {
            'id': msg_id,
            'type': 'message',
            'channel': channel,
        }
        if isinstance(msg, dict):
            full_msg.update(msg)
        elif isinstance(msg, str):
            full_msg['text'] = msg
        else:
            raise TypeError('unsupported msg type: {}'.format(type(msg)))
        if rich:
            self.post_message(full_msg)
        else:
            self.ws.write_message(json.dumps(full_msg))
        self.msg_id += 1
        return msg_id

    def write(self, msg, rich=False):
        """Writes a raw message dictionary on the websocket.

        Parameters
        ----------
        msg: dict
            Slack message https://api.slack.com/docs/messages

        Returns
        -------
        int
            Unique message ID
        """
        msg_id = self.msg_id
        msg['id'] = msg_id
        if rich:
            self.post_message(full_msg)
        else:
            self.ws.write_message(json.dumps(full_msg))
        self.msg_id += 1
        return msg_id

    def on_connect(self):
        """Override to handle connection to Slack."""
        pass

    def on_event(self, evt):
        """Override to handle Slack events."""
        pass

    def on_disconnect(self):
        """Override to handle disconnection from Slack."""
        pass

    def _on_ws_message(self, msg):
        if msg is None:
            self.log({
                'type': 'log',
                'text': 'disconnected from websocket'
            })
            self.ws = None
            try:
                self.on_disconnect()
            except Exception as ex:
                self.log({
                    'type': 'exception',
                    'exception': ex
                })
            return
        evt = json.loads(msg)
        self.log(evt)
        try:
            self.on_event(evt)
        except Exception as ex:
            self.log({
                'type': 'exception',
                'exception': ex
            })

    def _on_ws_connect(self, future):
        self.log({
            'type': 'log',
            'text': 'connected to websocket url'
        })
        self.ws = future.result()
        try:
            self.on_connect()
        except Exception as ex:
            self.log({
                'type': 'exception',
                'exception': ex
            })

    def _on_rtm_start(self, resp):
        if resp.code >= 400:
            self.log({
                'type': 'log',
                'text': 'failed to fetch websocket url',
                'error': resp
            })
            raise RuntimeError(resp)

        info = json.loads(resp.body.decode('utf-8'))
        if not info['ok']:
            self.log({
                'type': 'log',
                'text': 'rtm.connect failed',
                'error': info
            })
            raise RuntimeError(info)

        self.log({
            'type': 'log',
            'text': 'connecting to websocket url'
        })
        websocket_connect(info['url'], callback=self._on_ws_connect, on_message_callback=self._on_ws_message)

    def _rtm_start(self):
        self.log({
            'type': 'log',
            'text': 'fetching websocket url'
        })
        self.http_client.fetch(f'https://slack.com/api/rtm.connect?token={self.token}', callback=self._on_rtm_start)

    def _on_check_health(self):
        if self.ws is None:
            self.log({
                'type': 'log',
                'text': 'reconnecting websocket'
            })
            ioloop.IOLoop.current().call_later(0, self._rtm_start)

    def start(self):
        """Connect to Slack and start reconnection attempts."""
        self.heartbeat.stop()
        self.heartbeat.start()
        self._on_check_health()

    def stop(self):
        """Disconnect from Slack and cease reconnect attempts."""
        self.heartbeat.stop()
        if self.ws:
            self.ws.close()
        self.ws = None