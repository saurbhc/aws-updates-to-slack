import time

from slack_sdk import WebClient


class Slacker:
    def __init__(self, token):
        self.client = WebClient(token=token)


class SlackProgress(object):
    def __init__(self, token, channel, suffix='%'):
        self.suffix = suffix
        self.channel = channel
        self.slack = Slacker(token).client

    def new(self, total=100):
        """
        Instantiate and return a new ProgressBar object
        params:
            - total(int): total number of items
        """
        res = self.slack.chat_postMessage(channel=self.channel, text=self._makebar(0), as_user=True)
        bar = ProgressBar(self, total)
        bar.msg_ts = res['ts']
        bar.channel_id = res['channel']
        return bar

    def iter(self, iterable):
        """
        Wraps an iterable object, automatically creating
        and updating a progress bar
        """
        bar = self.new(total=len(iterable)-1)
        for idx, item in enumerate(iterable):
            yield(item)
            bar.done = idx

    def _update(self, chan, msg_ts, pos, msg_log):
        content = [self._makebar(pos)] + msg_log
        content = '\n'.join(content)
        self.slack.chat_update(channel=chan, ts=msg_ts, text=content)

    def _reply_in_thread(self, chan, msg_ts, msg_log):
        self.slack.chat_postMessage(channel=chan, text=msg_log, thread_ts=msg_ts, as_user=True)

    def _makebar(self, pos):
        bar = (round(pos / 5) * chr(9608))
        return '{} {}{}'.format(bar, pos, self.suffix)


class ProgressBar(object):

    msg_ts = None
    channel_id = None

    def __init__(self, sp, total):
        self._sp = sp
        self._pos = 0
        self._done = 0
        self.total = total
        self._msg_log = []

    @property
    def done(self):
        return self._done

    @done.setter
    def done(self, val):
        self._done = val
        self.pos = round((val/self.total) * 100)

    @property
    def pos(self):
        return self._pos

    @pos.setter
    def pos(self, val):
        if val != self._pos:
            self._pos = val
            self._update()

    def log(self, msg):
        timestamp = time.strftime('%X')  # returns HH:MM:SS time
        self._msg_log.append('*{}* - [{}]'.format(timestamp, msg))
        self._update()

    def log_thread(self, msg):
        self._sp._reply_in_thread(self.channel_id, self.msg_ts, msg)

    def _update(self):
        self._sp._update(self.channel_id, self.msg_ts, self._pos, self._msg_log)
