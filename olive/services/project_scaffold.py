"""Local, bounded starter files. Never downloads packages or replaces a folder."""
from pathlib import Path
import re

TEMPLATES = {
    'csharp': {
        'Program.cs': 'Console.WriteLine("Hello from OLIVE!");\n',
        'App.csproj': '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <OutputType>Exe</OutputType>\n    <TargetFramework>net10.0</TargetFramework>\n    <ImplicitUsings>enable</ImplicitUsings>\n    <Nullable>enable</Nullable>\n  </PropertyGroup>\n</Project>\n',
        'NuGet.Config': '<?xml version="1.0" encoding="utf-8"?>\n<configuration>\n  <packageSources><clear /></packageSources>\n</configuration>\n',
        '.gitignore': 'bin/\nobj/\n',
        'README.md': '# C# console project\n\nRequires the .NET 10 SDK. Open Program.cs and use Run in Studio.\nThe starter has no package dependencies; NuGet.Config clears remote sources for offline builds.\nConfigure approved package sources explicitly when adding dependencies.\nStudio validation restores and builds the project; this starter has no unit-test suite.\n',
    },
    'python': {'main.py': 'def main():\n    print("Hello from OLIVE!")\n\nif __name__ == "__main__":\n    main()\n',
               'requirements.txt': '# Add project dependencies here.\n'},
    'java': {'Main.java': 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello from OLIVE!");\n    }\n}\n',
             'lib/.gitkeep': '',
             'README.md': '# Java project\n\nRun uses the installed JDK. Put approved dependency JARs in lib/.\nBuild checks compile root Java sources. Maven/Gradle projects use their own manifests.\n'},
    'javascript': {'main.js': 'console.log("Hello from OLIVE!");\n',
                   'package.json': '{"private":true,"type":"module","scripts":{"start":"node main.js","test":"node --test"}}\n'},
    'empty': {'README.md': '# New project\n'},
}


def create_folder(data_dir, name, language):
    if (not isinstance(name, str) or not re.fullmatch(r'[\w][\w .-]{0,79}', name)
            or name.endswith((' ', '.')) or name.split('.')[0].upper() in
            {'CON', 'PRN', 'AUX', 'NUL', *{f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}}):
        raise ValueError('Use a project name without path separators or reserved filename characters.')
    if language not in TEMPLATES:
        raise ValueError('Choose a supported starter language.')
    data = Path(data_dir).resolve(strict=True)
    parent = data / 'projects'
    parent.mkdir(exist_ok=True)
    if parent.resolve() != parent:
        raise PermissionError('The projects directory must remain inside OLIVE data.')
    target = parent / name
    target.mkdir()  # Exclusive: never overwrite or merge another project.
    for relative, content in TEMPLATES[language].items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as handle:
            handle.write(content)
    return target
