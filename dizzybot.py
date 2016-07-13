import json
import collections
from tornado.httpclient import AsyncHTTPClient
from tornado.websocket import websocket_connect
from tornado import ioloop

class Dizzybot(object):
    """Tornado-based Slack bot.
    
    Parameters
    ==========
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
        """Store a special log message type in the recent dequeue."""
        self.recent.append(evt)
        
    def respond(self, evt, text):
        """Respond to a text message in the same channel."""
        if evt.get('type') != 'message' or evt.get('reply_to') is not None:
            return False
        
        self.ws.write_message(json.dumps({
            'id': self.msg_id,
            'type': 'message',
            'channel': evt['channel'],
            'text': text
        }))
        self.msg_id += 1
        return True
        
    def send(self, text, channel):
        """Send a message to a channel."""
        self.ws.write_message(json.dumps({
            'id': self.msg_id,
            'type': 'message',
            'channel': channel,
            'text': text
        }))
        self.msg_id += 1
        return True
    
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
                'text': 'failed to fetch websocket url'
            })
            raise RuntimeError(resp.code)

        self.log({
            'type': 'log',
            'text': 'connecting to websocket url'
        })
        info = json.loads(resp.body.decode('utf-8'))    
        websocket_connect(info['url'], callback=self._on_ws_connect, on_message_callback=self._on_ws_message)
    
    def _rtm_start(self):
        self.log({
            'type': 'log',
            'text': 'fetching websocket url'
        })
        self.http_client.fetch('https://slack.com/api/rtm.start?no_unreads=true&simple_latest=true&token={}'.format(self.token),
                               callback=self._on_rtm_start)

    def _on_check_health(self):
        if self.ws is None:
            self.log({
                'type': 'log',
                'text': 'reconnecting websocket'
            })
            ioloop.IOLoop.current().call_later(0, self._rtm_start)
        
    def start(self):
        """Start the bot."""
        self.heartbeat.stop()
        self.heartbeat.start()
        self._on_check_health()
            
    def stop(self):
        """Stop the bot."""
        self.heartbeat.stop()
        if self.ws:
            self.ws.close()
        self.ws = None