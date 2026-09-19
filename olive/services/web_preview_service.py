from __future__ import annotations
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse
import urllib.request

@dataclass(frozen=True,slots=True)
class WebPreviewResult:
    reachable:bool;status_code:int|None;title:str|None;contains_expected:bool|None;error:str|None=None
class _Title(HTMLParser):
    def __init__(self):super().__init__();self.in_title=False;self.title=""
    def handle_starttag(self,tag,attrs):self.in_title=tag.casefold()=="title"
    def handle_endtag(self,tag):
        if tag.casefold()=="title":self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title+=data
class WebPreviewService:
    def check(self,url,expected=None,timeout=5):
        parsed=urlparse(url)
        if parsed.hostname not in {"localhost","127.0.0.1","::1"}:raise PermissionError("Preview checks are limited to localhost")
        try:
            with urllib.request.urlopen(url,timeout=timeout) as response:
                body=response.read(1_000_000).decode("utf-8",errors="replace");parser=_Title();parser.feed(body)
                return WebPreviewResult(True,response.status,parser.title.strip() or None,expected in body if expected is not None else None)
        except Exception as exc:return WebPreviewResult(False,None,None,None,type(exc).__name__)
