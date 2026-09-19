from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

class IDEService:
    def detect(self) -> dict[str,str]:
        from ..tools.system import WindowsApplicationResolver
        found={}; resolver=WindowsApplicationResolver()
        code=shutil.which("code") or resolver.resolve("Visual Studio Code")
        visual=resolver.resolve("Visual Studio")
        if code: found["vscode"]=str(code.path if hasattr(code,"path") else code)
        if visual: found["visual_studio"]=str(visual.path)
        return found

    def open_workspace(self,root:str|Path,ide:str="") -> str:
        root=Path(root).resolve(strict=True); available=self.detect(); selected=ide or ("visual_studio" if any(root.glob("*.sln")) and "visual_studio" in available else "vscode")
        if selected not in available: raise FileNotFoundError(f"{selected} is not installed")
        target=next(iter(sorted(root.glob("*.sln"))),root) if selected=="visual_studio" else root
        subprocess.Popen([available[selected],str(target)],shell=False,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        return str(target)

    def open_file(self,path:str|Path,ide:str="vscode") -> str:
        path=Path(path).resolve(strict=True); available=self.detect()
        if ide not in available: raise FileNotFoundError(f"{ide} is not installed")
        subprocess.Popen([available[ide],str(path)],shell=False,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)); return str(path)
