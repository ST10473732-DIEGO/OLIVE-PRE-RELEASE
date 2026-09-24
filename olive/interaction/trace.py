"""Bounded, content-free diagnostics owned by one conversation request.

No prompts, visible answers, screenshots or reasoning are retained here.
"""
from contextvars import ContextVar
from functools import wraps
import hashlib
import json
import time
import uuid

_current = ContextVar('olive_request_trace', default=None)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def event(stage, **metadata):
    current = _current.get()
    if current is not None and len(current['events']) < 64:
        current['events'].append({'stage':stage,'elapsed_ms':round((time.monotonic()-current['_start'])*1000,2), **metadata})


def model_request(model, messages, options=None, format=None, think=None):
    if _current.get() is None:
        return
    event('model_request', model=model, prompt_sha256=digest(json.dumps(messages,sort_keys=True,ensure_ascii=False)),
          system_sha256=digest('\n'.join(m.get('content','') for m in messages if m.get('role')=='system')),
          messages=len(messages), options=dict(options or {}), thinking=think,
          schema_sha256=digest(json.dumps(format,sort_keys=True)) if format is not None else None)


def traced_request(function):
    @wraps(function)
    async def invoke(self, text, chat_id=None, *args, **kwargs):
        chat_id = chat_id or self.s.current_chat_id
        chat = self.s.chats[chat_id]
        record = {'id':uuid.uuid4().hex,'chat_id':chat_id,'request_sha256':digest(text),
                  'preset':getattr(chat, 'preset', ''),'selected_model':getattr(chat, 'model', ''),
                  'remote':bool(getattr(self.s.chat, 'targets', {}).get(chat_id)), '_start':time.monotonic(),'events':[]}
        token = _current.set(record)
        try:
            result = await function(self,text,chat_id,*args,**kwargs)
            event('request_finished', status='returned')
            return result
        except BaseException as error:
            event('request_finished',status=type(error).__name__)
            raise
        finally:
            _current.reset(token)
            record.pop('_start')
            self.request_traces.append(record)
            self.request_traces[:] = self.request_traces[-100:]
    return invoke
